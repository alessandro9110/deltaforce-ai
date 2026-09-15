"""Post-install checks. The report is written to .deltaforce/status.json and gates /df-kickoff."""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from . import backlog, environments, guardrails, team
from . import config as cfg
from .generate import (
    CLAUDE_MD_START,
    GITIGNORE_START,
    MCP_SERVER_NAME,
    existing_bundle_targets,
    is_deltaforce_statusline,
    medallion_schemas,
)
from .paths import ProjectPaths

CONFLICTING_ENV = ("DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_CLIENT_ID", "DATABRICKS_CLIENT_SECRET")


@dataclass
class Check:
    id: str
    title: str
    ok: bool
    detail: str = ""
    severity: str = "error"  # "error" blocks kickoff, "warn" does not


def _first_line(text: str) -> str:
    """The most useful line of CLI output: the first 'Error' line, else the first non-notice line."""
    lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    # The Databricks CLI prints this notice on every command when skills live in a custom path.
    lines = [line for line in lines if "databricks aitools install" not in line] or lines
    errors = [line for line in lines if line.lower().startswith("error")]
    return (errors or lines or [""])[0][:200]


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


class Doctor:
    def __init__(self, paths: ProjectPaths) -> None:
        self.paths = paths
        self.checks: list[Check] = []
        self.config: dict[str, Any] | None = None

    def add(self, check_id: str, title: str, ok: bool, detail: str = "", severity: str = "error") -> bool:
        self.checks.append(Check(check_id, title, ok, detail, severity))
        return ok

    def run_command(
        self,
        argv: list[Any],
        *,
        cwd: Path | None = None,
        timeout: int = 120,
        databricks_env: bool = False,
        input_text: str | None = None,
    ) -> tuple[bool, str]:
        env = dict(os.environ)
        if databricks_env and self.config:
            for name in CONFLICTING_ENV:
                env.pop(name, None)
            env["DATABRICKS_CONFIG_FILE"] = str(self.paths.databricks_cfg)
            env["DATABRICKS_CONFIG_PROFILE"] = self.config["databricks"]["profile"]
        try:
            result = subprocess.run(
                [str(arg) for arg in argv],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=cwd,
                env=env,
                timeout=timeout,
                input=input_text,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, str(exc)
        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, (result.stderr or result.stdout).strip()

    def databricks(self, *args: str, cwd: Path | None = None, profile: str | None = None) -> tuple[bool, Any]:
        profile_args = ["-p", profile] if profile else []
        ok, output = self.run_command(
            [self.paths.databricks_cli, *args, "-o", "json", *profile_args], cwd=cwd, databricks_env=True
        )
        if not ok:
            return False, _first_line(output)
        try:
            return True, json.loads(output) if output else {}
        except json.JSONDecodeError:
            return True, output

    # ─── checks ────────────────────────────────────────────────

    def check_config(self) -> None:
        try:
            self.config = cfg.load_config(self.paths.config)
        except cfg.ConfigError as exc:
            self.add("config", "Configuration", False, _first_line(exc))
            return
        self.add("config", "Configuration", True, ".deltaforce/config.yaml is valid")

    def check_claude(self) -> None:
        path = shutil.which("claude")
        self.add("claude", "Claude Code", bool(path), path or "claude not found on PATH")

    def check_environment(self) -> None:
        conflicts = {name for name in os.environ.get("DF_ENV_CONFLICTS", "").split(",") if name}
        conflicts.update(name for name in CONFLICTING_ENV if os.environ.get(name))
        detail = ""
        if conflicts:
            detail = f"unset {', '.join(sorted(conflicts))} before starting Claude Code — they override the project profile"
        self.add("environment", "No conflicting Databricks environment variables", not conflicts, detail, "warn")

    def check_git(self) -> None:
        root, branch = self.paths.root, self.config["project"]["dev_branch"]
        ok, _ = self.run_command(["git", "-C", root, "rev-parse", "--is-inside-work-tree"])
        if not self.add("git", "Git repository", ok, str(root)):
            return
        found = any(
            self.run_command(["git", "-C", root, "show-ref", "--verify", "--quiet", ref])[0]
            for ref in (f"refs/heads/{branch}", f"refs/remotes/origin/{branch}")
        )
        hint = f"create it: git switch -c {branch} && git push -u origin {branch}"
        self.add("dev-branch", f"Dev branch '{branch}'", found, "exists" if found else hint)

    def check_tools(self) -> None:
        versions = cfg.load_versions()
        for check_id, title, binary, version in (
            ("uv", "Project-local uv", self.paths.uv, versions["DF_UV_VERSION"]),
            ("databricks-cli", "Project-local Databricks CLI", self.paths.databricks_cli, versions["DF_DATABRICKS_CLI_VERSION"]),
        ):
            ok, output = self.run_command([binary, "--version"])
            self.add(check_id, title, ok and version in output, _first_line(output) or "missing")

    def check_workspace(self) -> bool:
        db, dev = self.config["databricks"], self.config["targets"]["dev"]

        ok, user = self.databricks("current-user", "me")
        detail = user.get("userName", "") if ok and isinstance(user, dict) else str(user)
        if not self.add("auth", f"Authentication (profile {db['profile']})", ok, detail):
            return False

        ok, warehouse = self.databricks("warehouses", "get", db["warehouse_id"])
        detail = f"{warehouse.get('name')} ({warehouse.get('state')})" if ok and isinstance(warehouse, dict) else str(warehouse)
        self.add("warehouse", f"SQL warehouse {db['warehouse_id']}", ok, detail)

        if db["compute"] == "cluster":
            ok, cluster = self.databricks("clusters", "get", db["cluster_id"])
            detail = f"{cluster.get('cluster_name')} ({cluster.get('state')})" if ok and isinstance(cluster, dict) else str(cluster)
            self.add("cluster", f"Cluster {db['cluster_id']}", ok, detail)

        ok, output = self.databricks("catalogs", "get", dev["catalog"])
        self.add("catalog", f"Dev catalog '{dev['catalog']}'", ok, "exists" if ok else str(output))
        for schema in medallion_schemas(dev):
            full_name = f"{dev['catalog']}.{schema}"
            ok, output = self.databricks("schemas", "get", full_name)
            detail = "exists" if ok else f"{output} — re-run the install command to create it"
            self.add(f"schema:{schema}", f"Dev schema '{full_name}'", ok, detail)

        prod = self.config.get("prod")
        if prod:
            ok, user = self.databricks("current-user", "me", profile=prod["profile"])
            detail = user.get("userName", "") if ok and isinstance(user, dict) else str(user)
            if self.add("prod-auth", f"Production authentication (profile {prod['profile']})", ok, detail):
                ok, warehouse = self.databricks("warehouses", "get", prod["warehouse_id"], profile=prod["profile"])
                detail = f"{warehouse.get('name')} ({warehouse.get('state')})" if ok and isinstance(warehouse, dict) else str(warehouse)
                self.add("prod-warehouse", f"Production SQL warehouse {prod['warehouse_id']}", ok, detail)
        return True

    def check_mcp_runtime(self) -> None:
        title = f"AI Dev Kit MCP server ({self.config['ai_dev_kit']['ref']})"
        if not self.paths.mcp_entry.exists():
            self.add("mcp-runtime", title, False, "source missing — re-run the installer")
            return
        ok, output = self.run_command([self.paths.venv_python, "-c", "import databricks_mcp_server"], timeout=300)
        self.add("mcp-runtime", title, ok, "importable" if ok else _first_line(output))

    def check_monitor(self) -> None:
        title = "Monitor"
        if not self.paths.venv_python.exists():
            self.add("monitor", title, False, "runtime missing — re-run the installer", "warn")
            return
        ok, output = self.run_command([self.paths.venv_python, "-c", "import yaml"], timeout=120)
        detail = "opens in the browser when the team starts working" if ok else f"{_first_line(output)} — re-run the installer"
        self.add("monitor", title, ok, detail, "warn")

    def check_skills(self) -> None:
        expected = cfg.skills_for_roles(self.config["team"]["roles"])
        missing = [skill for skill in expected if not (self.paths.skills / skill / "SKILL.md").exists()]
        detail = f"{len(expected)} skills" if not missing else "missing: " + ", ".join(missing)
        self.add("skills", "Databricks agent skills", not missing, detail)

        expected = cfg.huggingface_skills_for_roles(self.config["team"]["roles"])
        if expected:
            missing = [skill for skill in expected if not (self.paths.skills / skill / "SKILL.md").exists()]
            commit = _read_json(self.paths.huggingface_skills_record).get("commit")
            detail = f"{len(expected)} skills" + (f" at commit {commit}" if commit else "")
            detail = detail if not missing else "missing: " + ", ".join(missing) + " — re-run the installer"
            self.add("huggingface-skills", "Hugging Face skills", not missing, detail)

    def check_generated(self) -> None:
        server = _read_json(self.paths.mcp_json).get("mcpServers", {}).get(MCP_SERVER_NAME, {})
        ok = bool(server) and Path(server.get("command", "")).exists()
        self.add("mcp-json", ".mcp.json registers the databricks MCP server", ok, "" if ok else "missing or stale — re-run the installer")

        settings = _read_json(self.paths.claude_settings)
        ok = MCP_SERVER_NAME in settings.get("enabledMcpjsonServers", [])
        self.add("settings", ".claude/settings.json enables the MCP server", ok)

        local = _read_json(self.paths.claude_settings_local)
        ok = local.get("env", {}).get("DATABRICKS_CONFIG_PROFILE") == self.config["databricks"]["profile"]
        self.add("settings-local", ".claude/settings.local.json selects the project profile", ok)
        ok = is_deltaforce_statusline(local.get("statusLine"))
        detail = "links the monitor" if ok else "your own status line is kept — open the monitor with: bash .deltaforce/bin/df monitor"
        self.add("statusline", "Status line", ok, detail, "warn")

        claude_md = self.paths.claude_md.read_text(encoding="utf-8") if self.paths.claude_md.exists() else ""
        self.add("claude-md", "CLAUDE.md project context block", CLAUDE_MD_START in claude_md)

        gitignore = self.paths.gitignore.read_text(encoding="utf-8") if self.paths.gitignore.exists() else ""
        self.add("gitignore", ".gitignore excludes machine-specific files and secrets", GITIGNORE_START in gitignore)

        ok = self.paths.bundle.exists() and self.paths.bundle_variables.exists()
        self.add("bundle-files", "databricks.yml and bundle variables", ok)

    def check_team(self) -> None:
        roles = self.config["team"]["roles"]
        missing = [role for role in roles if not (self.paths.agents / f"{role}.md").exists()]
        detail = f"{len(roles)} agents" if not missing else "missing: " + ", ".join(missing)
        self.add("agents", "DeltaForce agents", not missing, detail)

        expected = team.skill_template_names()
        missing = [name for name in expected if not (self.paths.skills / name / "SKILL.md").exists()]
        detail = f"{len(expected)} skills" if not missing else "missing: " + ", ".join(missing)
        self.add("team-skills", "DeltaForce skills and PO commands", not missing, detail)

        settings = _read_json(self.paths.claude_settings)
        self.add("main-agent", "Sessions start as the Project Manager", settings.get("agent") == "pm")
        self.add("df-helper", "Project helper .deltaforce/bin/df", self.paths.df_wrapper.exists())

    def check_integrity(self) -> None:
        roles = cfg.load_roles()
        changed = []
        for role in self.config["team"]["roles"]:
            path = self.paths.agents / f"{role}.md"
            if path.exists() and path.read_text(encoding="utf-8") != team.render_agent(role, self.config, roles):
                changed.append(f".claude/agents/{role}.md")
        for name in team.skill_template_names():
            source_dir = team.SKILL_TEMPLATES / name
            for source in source_dir.rglob("*"):
                target = self.paths.skills / name / source.relative_to(source_dir)
                if source.is_file() and target.exists() and target.read_text(encoding="utf-8") != source.read_text(encoding="utf-8"):
                    changed.append(target.relative_to(self.paths.root).as_posix())
        detail = "as installed" if not changed else (
            "changed outside the installer: " + ", ".join(changed[:5]) + " — re-run the installer to restore them"
        )
        self.add("integrity", "DeltaForce agents and skills unchanged", not changed, detail)

        paths = [path for path in guardrails.INSTALLED_COMMIT_PATHS if (self.paths.root / path).exists()]
        ok, output = self.run_command(["git", "-C", self.paths.root, "status", "--porcelain", "--", *paths])
        committed = ok and not output.strip()
        detail = "" if committed else "not committed — re-run the installer and accept its commit (agents cannot commit them)"
        self.add("installed-committed", "DeltaForce files committed", committed, detail, "warn")

    def check_project_state(self) -> None:
        problems = backlog.validate_project(self.paths, include_config=False)
        detail = "valid" if not problems else f"{len(problems)} problem(s): {problems[0]}"
        self.add("project-state", "Conventions, state, backlog and events", not problems, detail[:200], "warn")

    def check_environments(self) -> None:
        granted = self.config.get("environments") or []
        waiting = environments.pending(self.paths, self.config)
        if not granted and not waiting:
            return
        targets = existing_bundle_targets(self.paths)
        missing = [env["bundle_target"] for env in granted if env["bundle_target"] not in targets]
        if waiting:
            detail = f"declared, not confirmed: {', '.join(waiting)} — re-run the installer with Claude Code closed to let the team deploy there"
        elif missing:
            detail = f"no bundle target {', '.join(missing)} yet — the Solution Architect adds it to databricks.yml"
        else:
            detail = "the team also deploys to " + ", ".join(f"{env['name']} (-t {env['bundle_target']})" for env in granted)
        self.add("environments", "Environments", not waiting and not missing, detail, "warn")

    def check_guardrails(self) -> None:
        policy_ok = self.paths.guard_policy.exists()
        self.add("guard-policy", "Guardrail policy", policy_ok, "" if policy_ok else "missing — re-run the installer")
        registered = guardrails.hooks_registered(_read_json(self.paths.claude_settings_local))
        self.add("hooks", "Guardrail and audit hooks registered", registered)
        if not (policy_ok and registered and self.paths.venv_python.exists()):
            return

        cases = [
            ({"tool_name": "Bash", "tool_input": {"command": "databricks bundle deploy -t prod"}, "agent_type": "devops-engineer"}, True),
            ({"tool_name": "Bash", "tool_input": {"command": "git push --force origin dev"}, "agent_type": "devops-engineer"}, True),
            ({"tool_name": "Bash", "tool_input": {"command": "hf jobs uv run train.py"}, "agent_type": "data-scientist"}, True),
            # The project CLI must stay usable, redirections included.
            (
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": f'"$DF_ROOT/.deltaforce/bin/databricks" bundle deploy -t {cfg.dev_bundle_target(self.config)} 2>&1'},
                    "agent_type": "devops-engineer",
                },
                False,
            ),
        ]
        if self.config.get("prod"):
            tool = f"mcp__{guardrails.PROD_MCP_SERVER}__execute_sql"
            cases += [
                ({"tool_name": tool, "tool_input": {"sql_query": "DROP TABLE a.b.c"}, "agent_type": "data-analyst"}, True),
                ({"tool_name": tool, "tool_input": {"sql_query": "SELECT 1"}, "agent_type": "data-analyst"}, False),
            ]
        failed = []
        for event, should_deny in cases:
            event = {**event, "session_id": "deltaforce-doctor", "cwd": str(self.paths.root)}
            ok, output = self.run_command(
                [self.paths.venv_python, guardrails.HOOK_SCRIPT, "pre", self.paths.guard_policy],
                timeout=60,
                input_text=json.dumps(event),
            )
            if (ok and '"deny"' in output) != should_deny:
                failed.append(event["tool_input"])
        detail = f"{len(cases)} scenarios behave as expected" if not failed else f"unexpected result for {failed[0]}"
        self.add("guard-self-test", "Guardrails self-test", not failed, detail)

    def check_bundle_validate(self) -> None:
        target = cfg.dev_bundle_target(self.config)
        ok, output = self.databricks("bundle", "validate", "-t", target, cwd=self.paths.root)
        self.add("bundle-validate", f"databricks bundle validate -t {target}", ok, "valid" if ok else str(output), "warn")


def run(paths: ProjectPaths) -> dict[str, Any]:
    doctor = Doctor(paths)
    doctor.check_config()
    doctor.check_claude()
    doctor.check_environment()
    if doctor.config:
        doctor.check_git()
        doctor.check_tools()
        workspace_ok = doctor.check_workspace()
        doctor.check_mcp_runtime()
        doctor.check_monitor()
        doctor.check_skills()
        doctor.check_generated()
        doctor.check_team()
        doctor.check_integrity()
        doctor.check_project_state()
        doctor.check_environments()
        doctor.check_guardrails()
        if workspace_ok:
            doctor.check_bundle_validate()

    report = {
        "ready": all(check.ok for check in doctor.checks if check.severity == "error"),
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "checks": [asdict(check) for check in doctor.checks],
    }
    paths.state.mkdir(parents=True, exist_ok=True)
    paths.status.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def print_report(report: dict[str, Any]) -> None:
    for check in report["checks"]:
        mark = "✓" if check["ok"] else ("!" if check["severity"] == "warn" else "✗")
        detail = f" — {check['detail']}" if check["detail"] else ""
        print(f"  {mark} {check['title']}{detail}")
