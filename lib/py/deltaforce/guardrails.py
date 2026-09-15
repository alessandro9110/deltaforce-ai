"""DeltaForce guardrails: guard policy, hook registration and static permission rules."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .paths import FRAMEWORK_DIR, ProjectPaths

HOOK_SCRIPT = FRAMEWORK_DIR / "lib" / "hooks" / "deltaforce_hook.py"
DEV_MCP_SERVER = "databricks"
PROD_MCP_SERVER = "databricks-prod"
DEPLOYER_ROLE = "devops-engineer"
MAIN_ROLE = "pm"
INTEGRATION_BRANCH = "df/integration"

# Tools registered by the ai-dev-kit MCP server (v0.2.0).
AI_DEV_KIT_TOOLS = (
    "ask_genie", "delete_tracked_resource", "execute_code", "execute_sql", "execute_sql_multi",
    "generate_and_upload_pdf", "generate_lakebase_credential", "get_current_user", "get_table_stats_and_schema",
    "get_volume_folder_details", "list_compute", "list_tracked_resources", "manage_app", "manage_cluster",
    "manage_dashboard", "manage_genie", "manage_job_runs", "manage_jobs", "manage_ka", "manage_lakebase_branch",
    "manage_lakebase_database", "manage_lakebase_sync", "manage_mas", "manage_metric_views", "manage_pipeline",
    "manage_pipeline_run", "manage_serving_endpoint", "manage_sql_warehouse", "manage_uc_connections",
    "manage_uc_grants", "manage_uc_monitors", "manage_uc_objects", "manage_uc_security_policies",
    "manage_uc_sharing", "manage_uc_storage", "manage_uc_tags", "manage_volume_files", "manage_vs_data",
    "manage_vs_endpoint", "manage_vs_index", "manage_warehouse", "manage_workspace", "manage_workspace_files",
    "query_vs_index",
)

# On production only reads: SQL queries, model serving (get/list/query), vector search queries, Genie, stats.
PROD_READ_TOOLS = (
    "ask_genie", "execute_sql", "execute_sql_multi", "get_current_user", "get_table_stats_and_schema",
    "get_volume_folder_details", "manage_serving_endpoint", "query_vs_index",
)

# Everything DeltaForce installs is off-limits to agents: only the installer changes it.
INSTALLER_FILES = (
    ".claude/settings.json",
    ".claude/settings.local.json",
    ".mcp.json",
    ".deltaforce/config.yaml",
    "CLAUDE.md",
    ".gitignore",
    "resources/deltaforce.variables.yml",
)
INSTALLER_DIRS = (
    ".claude/agents/",
    ".claude/skills/df-",
    ".claude/skills/databricks-",
    ".deltaforce/framework/",
    ".deltaforce/bin/",
    ".deltaforce/runtime/",
)
PM_ONLY_FILES = (".deltaforce/conventions.yaml",)
# What the installer commits at the end of an install (agents cannot commit installed files).
INSTALLED_COMMIT_PATHS = (
    ".gitignore", "CLAUDE.md", ".claude/settings.json", ".claude/agents", ".claude/skills", "databricks.yml",
    "resources/deltaforce.variables.yml", ".deltaforce/config.yaml", ".deltaforce/conventions.yaml",
)
SECRET_FILE = ".deltaforce/.databrickscfg"
LEGACY_DENY_RULES = ("Edit(**/.deltaforce/runtime/guard-policy.json)",)

# (event, matcher, hook mode, timeout in seconds, runs in the background). Only the guard must block the
# tool call; audit and activity run in the background. SessionEnd stays synchronous so it is not cut short.
HOOK_EVENTS = (
    ("PreToolUse", "Bash|Edit|Write|NotebookEdit|Read|mcp__databricks.*", "pre", 30, False),
    ("PreToolUse", "Agent|Task|AskUserQuestion", "activity", 30, True),
    ("UserPromptSubmit", None, "prompt", 15, True),
    ("PostToolUse", "Bash|mcp__databricks.*", "post", 30, True),
    ("PostToolUse", "Edit|Write|NotebookEdit", "activity", 30, True),
    ("SubagentStart", None, "subagent-start", 30, True),
    ("SubagentStop", None, "subagent-stop", 15, True),
    ("SessionStart", None, "session-start", 30, True),
    ("SessionEnd", None, "session-end", 15, False),
)


def _posix(path: Path) -> str:
    return path.resolve().as_posix()


def prod_read_roles(config: Mapping[str, Any], roles: Mapping[str, Mapping[str, Any]]) -> list[str]:
    if not config.get("prod"):
        return []
    return [role for role in config["team"]["roles"] if roles.get(role, {}).get("prod_read")]


def build_policy(config: Mapping[str, Any], paths: ProjectPaths, roles: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    prod = config.get("prod")
    return {
        "version": 1,
        "dev_server": DEV_MCP_SERVER,
        "dev_catalog": config["targets"]["dev"]["catalog"],
        "dev_target": "dev",
        "dev_branch": config["project"]["dev_branch"],
        "protected_branches": list(config["project"]["protected_branches"]),
        "integration_branch": INTEGRATION_BRANCH,
        "deployer_role": DEPLOYER_ROLE,
        "main_role": MAIN_ROLE,
        "prod": {
            "enabled": bool(prod),
            "server": PROD_MCP_SERVER,
            "host": prod["host"] if prod else None,
            "profile": prod["profile"] if prod else None,
            "read_roles": prod_read_roles(config, roles),
            "allowed_tools": list(PROD_READ_TOOLS),
        },
        "installer_files": list(INSTALLER_FILES),
        "installer_dirs": list(INSTALLER_DIRS),
        "pm_only_files": list(PM_ONLY_FILES),
        "secret_file": SECRET_FILE,
        "audit_file": _posix(paths.audit),
        "activity_file": _posix(paths.activity),
        "project_root": _posix(paths.root),
        "monitor_enabled": True,
    }


def _file_rules() -> list[str]:
    # The credentials file and its backups (the Databricks CLI writes .databrickscfg.bak).
    rules = [f"Read(**/{SECRET_FILE})", f"Edit(**/{SECRET_FILE})", f"Read(**/{SECRET_FILE}.*)", f"Edit(**/{SECRET_FILE}.*)"]
    rules += [f"Edit(**/{name})" for name in INSTALLER_FILES]
    rules += [f"Edit(**/{prefix}**)" if prefix.endswith("/") else f"Edit(**/{prefix}*/**)" for prefix in INSTALLER_DIRS]
    return rules


def static_deny_rules(config: Mapping[str, Any]) -> list[str]:
    """Deny rules that hold even if a hook fails: installer files, credentials, non-read tools on production."""
    rules = _file_rules()
    if config.get("prod"):
        rules += [f"mcp__{PROD_MCP_SERVER}__{tool}" for tool in AI_DEV_KIT_TOOLS if tool not in PROD_READ_TOOLS]
    return rules


def is_managed_deny_rule(rule: str) -> bool:
    return rule.startswith(f"mcp__{PROD_MCP_SERVER}__") or rule in _file_rules() or rule in LEGACY_DENY_RULES


def _is_deltaforce_group(group: Mapping[str, Any]) -> bool:
    return HOOK_SCRIPT.name in json.dumps(group)


def merge_hooks(existing: Mapping[str, Any] | None, paths: ProjectPaths) -> dict[str, Any]:
    """Replace DeltaForce hook groups, keep every other hook the user configured."""
    hooks: dict[str, list[Any]] = {
        event: [group for group in groups if not _is_deltaforce_group(group)] for event, groups in (existing or {}).items()
    }
    for event, matcher, mode, timeout, background in HOOK_EVENTS:
        hook: dict[str, Any] = {
            "type": "command",
            "command": _posix(paths.venv_python),
            "args": [_posix(HOOK_SCRIPT), mode, _posix(paths.guard_policy)],
            "timeout": timeout,
        }
        if background:
            hook["async"] = True
        group: dict[str, Any] = {"hooks": [hook]}
        if matcher:
            group = {"matcher": matcher, **group}
        hooks.setdefault(event, []).append(group)
    return {event: groups for event, groups in hooks.items() if groups}


def hooks_registered(settings_local: Mapping[str, Any]) -> bool:
    hooks = settings_local.get("hooks") or {}
    return all(any(_is_deltaforce_group(group) for group in hooks.get(event, [])) for event, *_ in HOOK_EVENTS)
