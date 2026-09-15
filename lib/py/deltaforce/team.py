"""Install the DeltaForce team into a project: agents rendered from the role catalog, skills and conventions."""

from __future__ import annotations

import datetime as dt
import json
import shutil
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from . import guardrails
from .config import AGENT_TEMPLATES, ConfigError, huggingface_skills_for_roles, load_roles, read_agent_template
from .paths import FRAMEWORK_DIR, ProjectPaths

TEMPLATES = FRAMEWORK_DIR / "templates"
SKILL_TEMPLATES = TEMPLATES / "claude" / "skills"
CONVENTIONS_TEMPLATE = TEMPLATES / "deltaforce" / "conventions.yaml"

MCP_TOOL_PREFIX = "mcp__databricks__"
BUILTIN_AGENTS = {"Explore": "built-in read-only codebase explorer"}


def skill_template_names() -> list[str]:
    return sorted(path.name for path in SKILL_TEMPLATES.iterdir() if (path / "SKILL.md").exists())


def _remove_tree(path: Path, attempts: int = 5) -> None:
    # Windows can briefly lock files that were just written (indexers, antivirus).
    for attempt in range(attempts):
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            return
        time.sleep(0.2 * (attempt + 1))
    shutil.rmtree(path)


def _sync_tree(source: Path, destination: Path) -> None:
    """Make destination match source without deleting and recreating destination itself."""
    shutil.copytree(source, destination, dirs_exist_ok=True)
    expected = {path.relative_to(source) for path in source.rglob("*")}
    for path in sorted(destination.rglob("*"), reverse=True):
        if path.relative_to(destination) not in expected:
            if path.is_dir():
                _remove_tree(path)
            else:
                path.unlink(missing_ok=True)


def _bullets(lines: list[str]) -> str:
    return "\n".join(f"- {line}" for line in lines)


def render_agent(role: str, config: Mapping[str, Any], roles: Mapping[str, Mapping[str, Any]] | None = None) -> str:
    """Build .claude/agents/<role>.md from its template, in the Claude Code subagent format, for this project."""
    roles = roles or load_roles()
    spec = roles[role]
    enabled = set(config["team"]["roles"])
    models = config["team"]["models"]

    delegates = [name for name in spec.get("delegates", []) if name in enabled or name in BUILTIN_AGENTS]
    tools = list(spec["tools"])
    if delegates:
        tools.append(f"Agent({', '.join(delegates)})")
    tools.extend(MCP_TOOL_PREFIX + tool for tool in spec.get("mcp", []))
    if config.get("prod") and spec.get("prod_read"):
        tools.extend(f"mcp__{guardrails.PROD_MCP_SERVER}__{tool}" for tool in guardrails.PROD_READ_TOOLS)

    frontmatter: dict[str, Any] = {
        "name": role,
        "description": " ".join(spec["description"].split()),
        "tools": ", ".join(tools),
        "model": models.get(role, models["default"]),
        "skills": list(spec.get("process_skills", [])),
    }
    for optional in ("isolation", "color"):
        if spec.get(optional):
            frontmatter[optional] = spec[optional]

    delegate_lines = [
        f"`{name}` — {roles[name]['title'] if name in roles else BUILTIN_AGENTS[name]}" for name in delegates
    ]
    _, body = read_agent_template(role)
    body = body.replace("{{delegates}}", _bullets(delegate_lines) if delegate_lines else "_You do not delegate._")
    body = body.replace("{{databricks_skills}}", _bullets([f"`{skill}`" for skill in spec.get("skills", [])]))
    huggingface = spec.get("huggingface_skills") or []
    body = body.replace("{{huggingface_skills}}", _bullets([f"`{skill}`" for skill in huggingface]) if huggingface else "_None._")

    header = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True, width=10_000)
    return f"---\n{header}---\n\n{body}"


def install_team(config: Mapping[str, Any], paths: ProjectPaths) -> list[str]:
    """Write agents for the enabled roles, refresh the DeltaForce skills, create conventions once."""
    roles = load_roles()
    enabled = config["team"]["roles"]
    summary = []

    paths.agents.mkdir(parents=True, exist_ok=True)
    for role in roles:
        target = paths.agents / f"{role}.md"
        if role in enabled:
            target.write_text(render_agent(role, config, roles), encoding="utf-8", newline="\n")
        elif target.exists():
            target.unlink()  # role disabled: only files DeltaForce owns are removed
    summary.append(f".claude/agents ({len(enabled)} agents)")

    names = skill_template_names()
    paths.skills.mkdir(parents=True, exist_ok=True)
    for existing in paths.skills.glob("df-*"):
        if existing.is_dir() and existing.name not in names:
            _remove_tree(existing)
    for name in names:
        _sync_tree(SKILL_TEMPLATES / name, paths.skills / name)
    summary.append(f".claude/skills ({len(names)} DeltaForce skills)")

    if not paths.conventions.exists():
        paths.conventions.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CONVENTIONS_TEMPLATE, paths.conventions)
        summary.append(".deltaforce/conventions.yaml")
    return summary


def install_huggingface_skills(config: Mapping[str, Any], paths: ProjectPaths, source: Path, repo: str, commit: str) -> list[str]:
    """Copy the Hugging Face skills of the enabled roles from a checkout of their repository and record the commit.

    Skills an earlier install recorded and the roles no longer need are removed; other skills are never touched.
    """
    wanted = huggingface_skills_for_roles(config["team"]["roles"])
    missing = [name for name in wanted if not (source / "skills" / name / "SKILL.md").exists()]
    if missing:
        raise ConfigError(f"Hugging Face skills not found in {repo}: {', '.join(missing)}")
    try:
        previous = json.loads(paths.huggingface_skills_record.read_text(encoding="utf-8")).get("skills") or []
    except (OSError, ValueError, AttributeError):
        previous = []
    paths.skills.mkdir(parents=True, exist_ok=True)
    for name in previous:
        if name not in wanted and (paths.skills / name).is_dir():
            _remove_tree(paths.skills / name)
    for name in wanted:
        _sync_tree(source / "skills" / name, paths.skills / name)
    record = {
        "repo": repo,
        "commit": commit,
        "skills": wanted,
        "installed_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    paths.huggingface_skills_record.parent.mkdir(parents=True, exist_ok=True)
    paths.huggingface_skills_record.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return wanted
