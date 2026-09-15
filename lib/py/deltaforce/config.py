"""Build, validate, read and export the project configuration (.deltaforce/config.yaml)."""

from __future__ import annotations

import json
import re
import shlex
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from .paths import FRAMEWORK_DIR

SCHEMA_PATH = FRAMEWORK_DIR / "schemas" / "config.schema.json"
ROLES_PATH = FRAMEWORK_DIR / "lib" / "data" / "roles.yaml"
AGENT_TEMPLATES = FRAMEWORK_DIR / "templates" / "claude" / "agents"
VERSIONS_PATH = FRAMEWORK_DIR / "lib" / "data" / "versions.env"
LAYERS = ("bronze", "silver", "gold")
# Subagent frontmatter fields of an agent template that describe the role; its `skills` are the preloaded
# DeltaForce skills (`process_skills` in the role spec, `skills` there being the Databricks agent skills).
AGENT_FIELDS = ("description", "tools", "model", "isolation", "color")

CONFIG_HEADER = (
    "# DeltaForce AI project configuration.\n"
    "# Written by install.sh — re-run the installer to change it. Contains no secrets.\n"
)


class ConfigError(Exception):
    """The configuration is missing or does not match the schema."""


def split_tools(value: Any) -> list[str]:
    """Tools of a subagent `tools` field — a YAML list or a comma-separated string; commas inside Agent(...) are kept."""
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in re.split(r",(?![^()]*\))", str(value or "")) if item.strip()]


def read_agent_template(role: str) -> tuple[dict[str, Any], str]:
    """Frontmatter and prompt of templates/claude/agents/<role>.md."""
    path = AGENT_TEMPLATES / f"{role}.md"
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    header, separator, body = text[4:].partition("\n---\n") if text.startswith("---\n") else ("", "", "")
    data = yaml.safe_load(header) if separator else None
    if not isinstance(data, dict) or data.get("name") != role:
        raise ConfigError(f"{path.name}: needs subagent frontmatter with name: {role}")
    return data, body.lstrip("\n")


def load_roles() -> dict[str, dict[str, Any]]:
    """Each role from lib/data/roles.yaml, with the description, tools, model and skills of its agent template."""
    with ROLES_PATH.open(encoding="utf-8") as f:
        roles = yaml.safe_load(f)["roles"]
    for role, spec in roles.items():
        frontmatter, _ = read_agent_template(role)
        spec.update({key: frontmatter[key] for key in AGENT_FIELDS if key in frontmatter})
        spec["tools"] = split_tools(spec.get("tools"))
        spec["process_skills"] = list(frontmatter.get("skills") or [])
    return roles


def load_versions() -> dict[str, str]:
    values = {}
    for line in VERSIONS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def validate(data: Mapping[str, Any]) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: list(e.absolute_path))
    if errors:
        lines = [f"  - {'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors]
        raise ConfigError("invalid configuration:\n" + "\n".join(lines))
    unknown = set(data["team"]["roles"]) - set(load_roles())
    if unknown:
        raise ConfigError(f"unknown roles: {', '.join(sorted(unknown))}")
    prod = data.get("prod")
    if prod:
        if prod["profile"] == data["databricks"]["profile"]:
            raise ConfigError("the production profile must differ from the dev profile")
        if prod["host"].lower() == data["databricks"]["host"].lower():
            raise ConfigError("the production workspace must be a different workspace from dev")


def dev_bundle_target(data: Mapping[str, Any]) -> str:
    """The bundle target the team deploys to: `dev` unless the project's bundle names it differently."""
    return str(data["targets"]["dev"].get("bundle_target") or "dev")


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"{path} not found — run the installer first")
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    validate(data)
    return data


def write_config(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(dict(data), sort_keys=False, allow_unicode=True)
    path.write_text(CONFIG_HEADER + body, encoding="utf-8")


def skills_for_roles(roles: list[str]) -> list[str]:
    catalog = load_roles()
    ordered: dict[str, None] = {}
    for role in roles:
        for skill in catalog[role]["skills"]:
            ordered.setdefault(skill)
    return list(ordered)


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def build_from_env(env: Mapping[str, str]) -> dict[str, Any]:
    """Assemble a configuration from the DF_* answers exported by install.sh."""

    def get(name: str, default: str | None = None) -> str | None:
        value = env.get(name, "").strip()
        return value or default

    roles_catalog = load_roles()
    versions = load_versions()

    layout = get("DF_MEDALLION_LAYOUT", "single_schema")
    medallion: dict[str, Any] = {"layout": layout}
    if layout == "single_schema":
        medallion["schema"] = get("DF_SCHEMA")
    else:
        for layer in LAYERS:
            medallion[layer] = get(f"DF_SCHEMA_{layer.upper()}")

    compute = get("DF_COMPUTE", "serverless")
    roles = _csv(get("DF_ROLES", ",".join(roles_catalog)) or "")
    default_model = get("DF_MODEL_DEFAULT", "sonnet")
    models = {"default": default_model}
    for role in roles:
        model = roles_catalog.get(role, {}).get("model")
        if model and model != default_model:
            models[role] = model

    try:
        depth = int(get("DF_MAX_SPAWN_DEPTH", "3") or "3")
    except ValueError as exc:
        raise ConfigError("DF_MAX_SPAWN_DEPTH must be an integer") from exc

    host = get("DF_DB_HOST")
    prod = None
    if (get("DF_PROD_ENABLED", "false") or "").lower() in {"true", "yes", "1"}:
        prod_host = get("DF_PROD_HOST")
        prod = {
            "host": prod_host.rstrip("/") if prod_host else None,
            "profile": get("DF_PROD_PROFILE"),
            "auth": get("DF_PROD_AUTH", "oauth"),
            "warehouse_id": get("DF_PROD_WAREHOUSE_ID"),
        }
    return {
        "version": 1,
        "project": {
            "name": get("DF_PROJECT_NAME"),
            "dev_branch": get("DF_DEV_BRANCH", "dev"),
            "protected_branches": _csv(get("DF_PROTECTED_BRANCHES", "main,master") or ""),
            "git_provider": get("DF_GIT_PROVIDER", "other"),
            "cicd": get("DF_CICD", "azure-devops"),
        },
        "databricks": {
            "host": host.rstrip("/") if host else None,
            "profile": get("DF_DB_PROFILE"),
            "auth": get("DF_DB_AUTH", "oauth"),
            "warehouse_id": get("DF_WAREHOUSE_ID"),
            "compute": compute,
            "cluster_id": get("DF_CLUSTER_ID") if compute == "cluster" else None,
        },
        "prod": prod,
        "targets": {"dev": {"bundle_target": get("DF_BUNDLE_TARGET", "dev"), "catalog": get("DF_CATALOG"), "medallion": medallion}},
        "team": {"roles": roles, "models": models, "max_spawn_depth": depth},
        "ai_dev_kit": {
            "repo": get("DF_ADK_REPO", versions["DF_ADK_DEFAULT_REPO"]),
            "ref": get("DF_ADK_REF", versions["DF_ADK_DEFAULT_REF"]),
        },
    }


def export_env(data: Mapping[str, Any]) -> str:
    """Shell lines that set DF_* variables from a configuration unless already set."""
    project, db, team, adk = data["project"], data["databricks"], data["team"], data["ai_dev_kit"]
    dev = data["targets"]["dev"]
    medallion = dev["medallion"]
    prod = data.get("prod") or {}
    values = {
        "DF_PROD_ENABLED": "true" if prod else "false",
        "DF_PROD_HOST": prod.get("host", ""),
        "DF_PROD_PROFILE": prod.get("profile", ""),
        "DF_PROD_AUTH": prod.get("auth", ""),
        "DF_PROD_WAREHOUSE_ID": prod.get("warehouse_id", ""),
        "DF_PROJECT_NAME": project["name"],
        "DF_DEV_BRANCH": project["dev_branch"],
        "DF_PROTECTED_BRANCHES": ",".join(project["protected_branches"]),
        "DF_CICD": project["cicd"],
        "DF_DB_HOST": db["host"],
        "DF_DB_PROFILE": db["profile"],
        "DF_DB_AUTH": db["auth"],
        "DF_WAREHOUSE_ID": db["warehouse_id"],
        "DF_COMPUTE": db["compute"],
        "DF_CLUSTER_ID": db.get("cluster_id") or "",
        "DF_BUNDLE_TARGET": dev_bundle_target(data),
        "DF_CATALOG": dev["catalog"],
        "DF_MEDALLION_LAYOUT": medallion["layout"],
        "DF_SCHEMA": medallion.get("schema", ""),
        **{f"DF_SCHEMA_{layer.upper()}": medallion.get(layer, "") for layer in LAYERS},
        "DF_ROLES": ",".join(team["roles"]),
        "DF_MODEL_DEFAULT": team["models"]["default"],
        "DF_MAX_SPAWN_DEPTH": str(team["max_spawn_depth"]),
        "DF_ADK_REPO": adk["repo"],
        "DF_ADK_REF": adk["ref"],
    }
    return "".join(f'[ -n "${{{key}-}}" ] || {key}={shlex.quote(value)}\n' for key, value in values.items())
