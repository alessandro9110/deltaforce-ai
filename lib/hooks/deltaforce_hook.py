#!/usr/bin/env python3
"""DeltaForce guardrails and audit for Claude Code — standard library only.

The installer registers this script in .claude/settings.local.json:

    python deltaforce_hook.py <mode> <guard-policy.json>
    modes: pre, post, activity, subagent-start, subagent-stop, session-start, session-end

Claude Code passes the hook input as JSON on stdin. In `pre` mode the script prints a deny
decision when an action breaks a DeltaForce rule; otherwise it prints nothing and Claude Code
applies its normal permission flow. Every denial, Databricks call and shell command is appended
to the audit file. Agent activity (tool calls, delegations, agents, sessions) feeds the monitor,
which the hook starts with a session and opens in the browser when the team starts working.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

READ_FIRST_KEYWORDS = {"SELECT", "WITH", "SHOW", "DESCRIBE", "DESC", "EXPLAIN", "VALUES", "LIST"}
WRITE_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "MERGE", "CREATE", "ALTER", "DROP", "TRUNCATE", "GRANT", "REVOKE",
    "COPY", "OPTIMIZE", "VACUUM", "REFRESH", "RESTORE", "MSCK", "UNCACHE", "CALL", "EXECUTE", "UNDROP",
}
SQL_ARGUMENT = {"execute_sql": "sql_query", "execute_sql_multi": "sql_content"}
READ_ACTIONS = {"get", "list", "describe", "status", "get_best", "query", "search", "preview", "read"}
GOVERNANCE_TOOLS = {
    "manage_uc_grants", "manage_uc_security_policies", "manage_uc_sharing", "manage_uc_connections", "manage_uc_storage",
}
# Tools that create, change or delete Databricks resources: on dev only their read actions are allowed,
# because every resource is declared in the asset bundle and deployed by the DevOps Engineer.
RESOURCE_TOOLS = {
    "manage_jobs", "manage_pipeline", "manage_dashboard", "manage_genie", "manage_app", "manage_ka", "manage_mas",
    "manage_metric_views", "manage_serving_endpoint", "manage_vs_endpoint", "manage_vs_index", "manage_uc_objects",
    "manage_uc_tags", "manage_uc_monitors", "manage_cluster", "manage_sql_warehouse", "manage_workspace",
    "manage_workspace_files", "manage_lakebase_database", "manage_lakebase_branch", "manage_lakebase_sync",
}
DATA_WRITE_TOOLS_WITHOUT_ACTION = {"generate_and_upload_pdf"}
PUSH_FORBIDDEN_FLAGS = {"-f", "-d", "--delete", "--mirror", "--prune"}
SHELL_WRAPPERS = {"timeout", "nohup", "time", "command", "env", "nice"}
AGENT_TOOLS = {"Agent", "Task"}
FILE_TOOLS = {"Edit", "Write", "NotebookEdit", "Read"}
FEATURE_REF = re.compile(r"\bF-\d{3,}\b")
TASK_REF = re.compile(r"\bT-(\d{3,})\.\d+\b")
MONITOR_MODES = {"post", "activity", "subagent-start", "session-start"}

WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
NAME = r"[A-Za-z0-9_-]+"
THREE_PART = re.compile(rf"(?<![\w.])({NAME})\s*\.\s*{NAME}\s*\.\s*{NAME}")
USE_CATALOG = re.compile(rf"\bUSE\s+CATALOG\s+({NAME})", re.IGNORECASE)
VOLUME_PATH = re.compile(r"^/Volumes/([^/]+)/", re.IGNORECASE)
FULL_NAME = re.compile(rf"^({NAME})\.{NAME}\.{NAME}$")
TWO_PART_NAME = re.compile(rf"^({NAME})\.{NAME}$")
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
SEPARATORS = re.compile(r"\|\||&&|;|\||\n")
QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")
WRITE_HINT = re.compile(r"(>|\bsed\s+-i|\brm\b|\bmv\b|\bcp\b|\btee\b|\btruncate\b|\bdd\b|\bperl\s+-i|Set-Content|Out-File)")


# ─── SQL ────────────────────────────────────────────────────────


def strip_sql(sql: str) -> str:
    """Drop comments and string literals; keep identifiers (without backticks)."""
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        char = sql[i]
        if sql.startswith("--", i):
            end = sql.find("\n", i)
            i = n if end == -1 else end
            continue
        if sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            i = n if end == -1 else end + 2
            out.append(" ")
            continue
        if char in ("'", '"'):
            j = i + 1
            while j < n:
                if sql[j] == "\\":
                    j += 2
                    continue
                if sql[j] == char:
                    if j + 1 < n and sql[j + 1] == char:
                        j += 2
                        continue
                    break
                j += 1
            out.append("''")
            i = j + 1
            continue
        if char == "`":
            end = sql.find("`", i + 1)
            end = n if end == -1 else end
            out.append(sql[i + 1 : end])
            i = end + 1
            continue
        out.append(char)
        i += 1
    return "".join(out)


def is_read_only(sql: str) -> bool:
    for statement in (part.strip() for part in strip_sql(sql).split(";")):
        if not statement:
            continue
        words = [word.upper() for word in WORD.findall(statement)]
        if not words or words[0] not in READ_FIRST_KEYWORDS or WRITE_KEYWORDS.intersection(words):
            return False
    return True


def sql_catalogs(sql: str) -> set[str]:
    stripped = strip_sql(sql)
    catalogs = {match.group(1).lower() for match in THREE_PART.finditer(stripped)}
    catalogs |= {match.group(1).lower() for match in USE_CATALOG.finditer(stripped)}
    return catalogs


def input_catalogs(value: Any, key: str = "") -> set[str]:
    """Catalogs named in a tool input: catalog fields, three-part names, /Volumes paths."""
    found: set[str] = set()
    if isinstance(value, dict):
        for child_key, child in value.items():
            found |= input_catalogs(child, str(child_key))
    elif isinstance(value, list):
        for child in value:
            found |= input_catalogs(child, key)
    elif isinstance(value, str):
        lowered_key = key.lower()
        if lowered_key in {"catalog", "catalog_name"}:
            found.add(value.lower())
        elif match := VOLUME_PATH.match(value):
            found.add(match.group(1).lower())
        elif match := FULL_NAME.match(value):
            found.add(match.group(1).lower())
        elif lowered_key == "full_name" and (match := TWO_PART_NAME.match(value)):
            found.add(match.group(1).lower())
    return found


# ─── decisions ──────────────────────────────────────────────────


def role_of(event: dict[str, Any], policy: dict[str, Any]) -> str:
    return event.get("agent_type") or policy.get("main_role", "pm")


def decide_pre(event: dict[str, Any], policy: dict[str, Any]) -> str | None:
    """The reason an action must be blocked, or None to let Claude Code decide."""
    tool = str(event.get("tool_name", ""))
    tool_input = event.get("tool_input") or {}
    role = role_of(event, policy)
    if tool.startswith("mcp__"):
        return _decide_mcp(tool, tool_input, role, policy)
    if tool == "Bash":
        return decide_bash(str(tool_input.get("command", "")), role, policy, str(event.get("cwd") or "."))
    if tool in {"Edit", "Write", "NotebookEdit", "Read"}:
        return _decide_file(tool, tool_input, role, policy)
    return None


def _decide_mcp(tool: str, tool_input: dict[str, Any], role: str, policy: dict[str, Any]) -> str | None:
    parts = tool.split("__", 2)
    if len(parts) != 3:
        return None
    _, server, name = parts
    prod = policy.get("prod") or {}

    if server == prod.get("server"):
        if not prod.get("enabled"):
            return "no production workspace is configured"
        if role not in prod.get("read_roles", []):
            return f"the {role} role may not access the production workspace"
        if name not in prod.get("allowed_tools", []):
            return f"'{name}' is not allowed on production: only queries, model and vector search calls, Genie and table stats"
        argument = SQL_ARGUMENT.get(name)
        if argument and not is_read_only(str(tool_input.get(argument, ""))):
            return "production is read-only: only SELECT, WITH … SELECT, SHOW, DESCRIBE and EXPLAIN are allowed"
        return None

    if server != policy.get("dev_server"):
        return None
    dev_catalog = str(policy["dev_catalog"])
    argument = SQL_ARGUMENT.get(name)
    if argument:
        sql = str(tool_input.get(argument, ""))
        if is_read_only(sql):
            return None
        catalogs = sql_catalogs(sql)
        if tool_input.get("catalog"):
            catalogs.add(str(tool_input["catalog"]).lower())
        if not catalogs:
            return f"qualify SQL writes with the dev catalog ({dev_catalog}.<schema>.<table>) or pass catalog='{dev_catalog}'"
        outside = sorted(catalog for catalog in catalogs if catalog != dev_catalog.lower())
        if outside:
            return f"writes are allowed only in the dev catalog '{dev_catalog}' (found: {', '.join(outside)})"
        return None

    action = str(tool_input.get("action", "")).lower()
    if name == "delete_tracked_resource":
        return "Databricks resources are removed only through the asset bundle: ask the DevOps Engineer"
    if action in READ_ACTIONS:
        return None
    if name in GOVERNANCE_TOOLS:
        return "permission, sharing, connection and storage changes need a person: escalate to the PO"
    if name in RESOURCE_TOOLS:
        return (
            f"Databricks resources are created, changed and deleted only through the asset bundle "
            f"('{name}' action '{action or 'default'}'): declare it in resources/*.yml and let the DevOps Engineer deploy"
        )
    if action or name in DATA_WRITE_TOOLS_WITHOUT_ACTION:
        outside = sorted(catalog for catalog in input_catalogs(tool_input) if catalog != dev_catalog.lower())
        if outside:
            return f"changes are allowed only in the dev catalog '{dev_catalog}' (found: {', '.join(outside)})"
    return None


def _normalized(path: str) -> str:
    return path.replace("\\", "/").lower()


def installed_path(path: str, policy: dict[str, Any]) -> str | None:
    """The installer-owned file or folder a path belongs to, also inside agent worktrees."""
    path = _normalized(path)
    if path.startswith("./"):
        path = path[2:]
    for managed in policy.get("installer_files", []):
        managed_norm = _normalized(managed)
        if path == managed_norm or path.endswith("/" + managed_norm):
            return managed
    for prefix in policy.get("installer_dirs", []):
        prefix_norm = _normalized(prefix)
        if path.startswith(prefix_norm) or f"/{prefix_norm}" in path:
            return prefix
    return None


def _installed_reason(managed: str) -> str:
    return f"{managed} was installed by DeltaForce and agents may not change it: the PO re-runs the installer"


def _decide_file(tool: str, tool_input: dict[str, Any], role: str, policy: dict[str, Any]) -> str | None:
    path = _normalized(str(tool_input.get("file_path") or tool_input.get("notebook_path") or ""))
    if not path:
        return None
    secret = _normalized(policy["secret_file"])
    if path == secret or path.endswith("/" + secret):
        return "the Databricks credentials file is off-limits"
    if tool == "Read":
        return None
    managed = installed_path(path, policy)
    if managed:
        return _installed_reason(managed)
    for owned in policy.get("pm_only_files", []):
        owned_norm = _normalized(owned)
        if (path == owned_norm or path.endswith("/" + owned_norm)) and role != policy.get("main_role", "pm"):
            return f"{owned} is changed only by the PM, through /df-conventions"
    return None


# ─── shell ──────────────────────────────────────────────────────


def _tokens(text: str) -> list[str]:
    try:
        return shlex.split(text, posix=True)
    except ValueError:
        return text.split()


def _program(token: str) -> str:
    name = token.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


def decide_bash(command: str, role: str, policy: dict[str, Any], cwd: str = ".") -> str | None:
    env: dict[str, str] = {}
    for part in (piece.strip() for piece in SEPARATORS.split(command)):
        if not part:
            continue
        reason = _decide_command_files(part, policy)
        if reason:
            return reason
        tokens = _tokens(part)
        while tokens and ASSIGNMENT.match(tokens[0]):
            key, value = tokens.pop(0).split("=", 1)
            env[key] = value
        if tokens and tokens[0] == "export":
            for token in tokens[1:]:
                if "=" in token:
                    key, value = token.split("=", 1)
                    env[key] = value
            continue
        while tokens and _program(tokens[0]) in SHELL_WRAPPERS:
            tokens.pop(0)
            while tokens and (tokens[0].startswith("-") or re.fullmatch(r"\d+[smhd]?", tokens[0]) or ASSIGNMENT.match(tokens[0])):
                token = tokens.pop(0)
                if ASSIGNMENT.match(token):
                    key, value = token.split("=", 1)
                    env[key] = value
        if not tokens:
            continue
        program, arguments = _program(tokens[0]), tokens[1:]
        if program in {"bash", "sh"} and "-c" in arguments:
            index = arguments.index("-c")
            if index + 1 < len(arguments):
                reason = decide_bash(arguments[index + 1], role, policy, cwd)
                if reason:
                    return reason
            continue
        if program == "databricks":
            reason = _decide_databricks(arguments, env, role, policy)
        elif program == "git":
            reason = _decide_git(arguments, role, policy, cwd)
        else:
            reason = None
        if reason:
            return reason
    return None


def _decide_command_files(command: str, policy: dict[str, Any]) -> str | None:
    text = _normalized(command)
    if _normalized(policy["secret_file"]).rsplit("/", 1)[-1] in text:
        return "the Databricks credentials file is off-limits"
    # Look for redirections and write commands outside quoted text, so JSON such as "a -> b" is not a write.
    if WRITE_HINT.search(QUOTED.sub(" ", command)):
        for managed in [*policy.get("installer_files", []), *policy.get("installer_dirs", [])]:
            if _normalized(managed).rstrip("/") in text:
                return _installed_reason(managed)
        # Whole parent folders that contain installed files, e.g. `rm -rf .claude/skills`.
        for token in _tokens(command):
            if _normalized(token).rstrip("/") in {".claude", ".claude/skills", ".deltaforce"}:
                return _installed_reason(token)
    return None


def _decide_databricks(arguments: list[str], env: dict[str, str], role: str, policy: dict[str, Any]) -> str | None:
    profile = env.get("DATABRICKS_CONFIG_PROFILE")
    host = env.get("DATABRICKS_HOST")
    target = None
    positional: list[str] = []
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        for flags, name in ((("-p", "--profile"), "profile"), (("--host",), "host"), (("-t", "--target"), "target")):
            if argument in flags and index + 1 < len(arguments):
                value = arguments[index + 1]
                index += 1
                break
            prefix = next((flag + "=" for flag in flags if flag.startswith("--") and argument.startswith(flag + "=")), None)
            if prefix:
                value = argument[len(prefix) :]
                break
        else:
            if not argument.startswith("-"):
                positional.append(argument)
            index += 1
            continue
        if name == "profile":
            profile = value
        elif name == "host":
            host = value
        else:
            target = value
        index += 1

    prod = policy.get("prod") or {}
    if prod.get("enabled"):
        if (profile and profile == prod.get("profile")) or (
            host and prod.get("host") and host.rstrip("/").lower() == str(prod["host"]).lower()
        ):
            return "the Databricks CLI may not target production: read production data with the databricks-prod query tools"

    if len(positional) >= 2 and positional[0] == "bundle":
        verb = positional[1]
        if verb == "destroy":
            return "bundle destroy is not allowed to agents: ask a person"
        if verb in {"deploy", "run", "deployment"}:
            deployer = policy.get("deployer_role", "devops-engineer")
            if role != deployer:
                return f"only the {deployer} deploys and runs bundles"
            if target and target != policy.get("dev_target", "dev"):
                return f"bundles are deployed only to the '{policy.get('dev_target', 'dev')}' target: production goes through CI/CD"
    return None


def _git_lines(cwd: str, arguments: list[str]) -> list[str]:
    try:
        result = subprocess.run(["git", "-C", cwd, *arguments], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()] if result.returncode == 0 else []


def _current_branch(cwd: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _decide_git(arguments: list[str], role: str, policy: dict[str, Any], cwd: str) -> str | None:
    while len(arguments) >= 2 and arguments[0] in ("-C", "-c"):
        if arguments[0] == "-C":
            cwd = arguments[1]
        arguments = arguments[2:]
    if not arguments:
        return None
    verb, rest = arguments[0], arguments[1:]
    protected = set(policy.get("protected_branches", []))
    dev_branch = policy.get("dev_branch")
    deployer = policy.get("deployer_role", "devops-engineer")
    integration = policy.get("integration_branch", "df/integration")

    if verb == "push":
        flags = [argument for argument in rest if argument.startswith("-")]
        if any(flag in PUSH_FORBIDDEN_FLAGS or flag.startswith("--force") for flag in flags):
            return "force pushes, mirror pushes and remote branch deletions are not allowed"
        positional = [argument for argument in rest if not argument.startswith("-")]
        refspecs = positional[1:] or [_current_branch(cwd)]
        for refspec in refspecs:
            if refspec.startswith(("+", ":")):
                return "force pushes and remote branch deletions are not allowed"
            branch = refspec.split(":", 1)[-1] if ":" in refspec else refspec
            if branch in ("", "HEAD"):
                branch = _current_branch(cwd)
            branch = branch.removeprefix("refs/heads/")
            if branch in protected:
                return f"pushing to protected branch '{branch}' is not allowed: a person opens the pull request"
            if branch == integration:
                return f"{integration} is local only and is never pushed"
            if branch == dev_branch and role != deployer:
                return f"only the {deployer} pushes the dev branch '{dev_branch}'"
        return None

    if verb == "reset" and "--hard" in rest:
        return "git reset --hard is not allowed"
    if verb in {"rebase", "filter-branch", "filter-repo"}:
        return f"git {verb} rewrites history and is not allowed"
    if verb in {"switch", "checkout"}:
        for flag in ("-C", "-B", "--force-create"):
            if flag in rest:
                index = rest.index(flag)
                branch = rest[index + 1] if index + 1 < len(rest) else ""
                if branch != integration:
                    return f"resetting branch '{branch}' with {flag} is not allowed (only {integration})"
    if verb == "branch" and any(flag in rest for flag in ("-D", "-d", "--delete", "-M", "-m", "--move", "-f", "--force")):
        names = [argument for argument in rest if not argument.startswith("-")]
        touched = [name for name in names if name in protected or name == dev_branch]
        if touched:
            return f"deleting, renaming or forcing branch '{touched[0]}' is not allowed"
    if verb in {"commit", "merge", "cherry-pick", "revert", "am"}:
        branch = _current_branch(cwd)
        if branch in protected:
            return f"committing or merging on protected branch '{branch}' is not allowed"
        if verb == "merge" and branch == dev_branch and role != deployer:
            return f"only the {deployer} merges into the dev branch '{dev_branch}'"
    if verb == "commit":
        files = _git_lines(cwd, ["diff", "--cached", "--name-only"])
        if any(arg == "--all" or (arg.startswith("-") and not arg.startswith("--") and "a" in arg[1:]) for arg in rest):
            files += _git_lines(cwd, ["diff", "--name-only"])
        for name in files:
            if installed_path(name, policy):
                return f"commits may not include files installed by DeltaForce ({name}): the PO re-runs the installer, which commits them"
    return None


# ─── audit and activity ─────────────────────────────────────────


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _append(path: str | None, record: dict[str, Any]) -> None:
    if not path:
        return
    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass


def _workspace(tool: str, policy: dict[str, Any]) -> str | None:
    if tool.startswith(f"mcp__{(policy.get('prod') or {}).get('server')}__"):
        return "prod"
    if tool.startswith(f"mcp__{policy.get('dev_server')}__"):
        return "dev"
    return None


def _summary(tool: str, tool_input: dict[str, Any], limit: int = 2000) -> str:
    name = tool.split("__", 2)[-1]
    if name in SQL_ARGUMENT:
        text = str(tool_input.get(SQL_ARGUMENT[name], ""))
    elif tool == "Bash":
        text = str(tool_input.get("command", ""))
    else:
        text = json.dumps(tool_input, ensure_ascii=False, default=str)
    return text[:limit]


def audit(event: dict[str, Any], policy: dict[str, Any], decision: str, reason: str | None = None) -> None:
    tool = str(event.get("tool_name", ""))
    record = {
        "ts": _now(),
        "session_id": event.get("session_id"),
        "agent_id": event.get("agent_id"),
        "role": role_of(event, policy),
        "tool": tool,
        "workspace": _workspace(tool, policy),
        "decision": decision,
        "input": _summary(tool, event.get("tool_input") or {}),
    }
    if reason:
        record["reason"] = reason
    _append(policy.get("audit_file"), record)


def _detail(tool: str, tool_input: dict[str, Any]) -> str:
    """What a tool call touches, for the monitor: a file, a command, a delegation or a Databricks call."""
    if tool in FILE_TOOLS:
        return str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
    if tool in AGENT_TOOLS:
        return str(tool_input.get("description") or "")[:200]
    return _summary(tool, tool_input, 200)


def activity(event: dict[str, Any], policy: dict[str, Any], kind: str) -> None:
    record = {
        "ts": _now(),
        "session_id": event.get("session_id"),
        "agent_id": event.get("agent_id"),
        "role": role_of(event, policy),
        "event": kind,
    }
    tool = str(event.get("tool_name") or "")
    tool_input = event.get("tool_input") or {}
    if tool:
        record["tool"] = tool
        record["summary"] = _detail(tool, tool_input)
    if tool in AGENT_TOOLS:
        record["target_role"] = tool_input.get("subagent_type")
        text = f"{tool_input.get('description', '')}\n{str(tool_input.get('prompt', ''))[:4000]}"
        if task := TASK_REF.search(text):
            record["task"] = task.group(0)
        if feature := FEATURE_REF.search(text):
            record["feature"] = feature.group(0)
        elif task:
            record["feature"] = f"F-{task.group(1)}"
    if event.get("reason"):
        record["reason"] = event["reason"]
    _append(policy.get("activity_file"), record)


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        return 0
    for stream in (sys.stdin, sys.stdout):
        stream.reconfigure(encoding="utf-8")
    mode, policy_path = argv[1], argv[2]
    try:
        event = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    try:
        policy = json.loads(Path(policy_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        if mode == "pre" and "databricks-prod" in str(event.get("tool_name", "")):
            _deny("the DeltaForce guard policy is missing: production access is disabled until the installer runs again")
        return 0

    if mode == "pre":
        try:
            reason = decide_pre(event, policy)
        except Exception as exc:  # fail closed on production, open elsewhere
            reason = f"the guard failed ({exc}): production calls are blocked" if _workspace(
                str(event.get("tool_name", "")), policy
            ) == "prod" else None
        if reason:
            audit(event, policy, "denied", reason)
            _deny(reason)
    elif mode == "post":
        audit(event, policy, "allowed")
        activity(event, policy, "tool_used")
    elif mode == "activity":
        activity(event, policy, "delegated" if str(event.get("tool_name")) in AGENT_TOOLS else "tool_used")
    elif mode == "subagent-start":
        activity(event, policy, "agent_started")
    elif mode == "subagent-stop":
        activity(event, policy, "agent_stopped")
    elif mode == "session-start":
        activity(event, policy, "session_started")
    elif mode == "session-end":
        activity(event, policy, "session_ended")
    if mode in MONITOR_MODES:
        monitor(event, policy, open_page=mode != "session-start")
    return 0


def monitor(event: dict[str, Any], policy: dict[str, Any], open_page: bool) -> None:
    """Start the monitor with a session; open it in the browser the first time the team works in it."""
    root = policy.get("project_root")
    disabled = os.environ.get("DELTAFORCE_MONITOR", "").strip().lower() in {"off", "0", "false", "no"}
    if not policy.get("monitor_enabled") or not root or disabled:
        return
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from monitor import launcher

        launcher.ensure(Path(root), Path(sys.executable), event.get("session_id"), open_page)
    except Exception:  # the monitor never gets in the team's way
        pass


def _deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"DeltaForce guardrail: {reason}",
                }
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv))
