"""Client environments: declared by the PO in the conventions, deploy access confirmed by the PO in the installer.

The guard hook combines two lists. Deploy grants live in config.yaml, written only by the installer after the PO
confirms each environment in the terminal. The environments the PO declared at kickoff are copied from
conventions.yaml to .deltaforce/runtime/environments.json by `df validate` and by every install: they narrow the
grants at once and never widen them, so nothing said in a conversation gives the team more access.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from . import backlog
from .config import dev_bundle_target
from .paths import ProjectPaths


def declared(paths: ProjectPaths) -> list[dict[str, Any]] | None:
    """The environments in .deltaforce/conventions.yaml; None when the conventions are invalid."""
    if not paths.conventions.exists():
        return []
    try:
        data = backlog._load_yaml(paths.conventions)
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(data, dict) or backlog._schema_errors("conventions", data, paths.conventions.name):
        return None
    return list(data.get("environments") or [])


def write_runtime(paths: ProjectPaths) -> Path | None:
    """Copy the declared environments for the guard hook; invalid conventions keep the previous copy."""
    environments = declared(paths)
    if environments is None:
        return None
    paths.declared_environments.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps({"environments": environments}, indent=2, ensure_ascii=False) + "\n"
    paths.declared_environments.write_text(text, encoding="utf-8")
    return paths.declared_environments


def deploy_candidates(
    environments: list[Mapping[str, Any]], dev_target: str
) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    """Declared environments the installer may let the team deploy to, and why each other one is not offered."""
    candidates: list[dict[str, Any]] = []
    notes: list[tuple[str, str]] = []
    for env in environments:
        name, access = str(env.get("name")), env.get("team")
        if access != "deploy":
            notes.append((name, "no access for the team" if access == "none" else "the team only reads"))
        elif env.get("production") or env.get("workspace") == "production":
            notes.append((name, "production: deployed only through CI/CD"))
        elif env.get("workspace", "dev") != "dev":
            notes.append((name, "on another workspace: deployed through CI/CD until DeltaForce supports it"))
        elif env.get("bundle_target") == dev_target:
            notes.append((name, f"the team's dev target '{dev_target}'"))
        elif not env.get("bundle_target") or not env.get("catalogs"):
            notes.append((name, "needs its bundle target and catalogs in the conventions before the team can deploy there"))
        else:
            candidates.append(
                {"name": name, "bundle_target": str(env["bundle_target"]), "catalogs": [str(item) for item in env["catalogs"]]}
            )
    return candidates, notes


def pending(paths: ProjectPaths, config: Mapping[str, Any]) -> list[str]:
    """Declared deploy environments the PO has not confirmed in the installer yet."""
    granted = {(env["name"], env["bundle_target"], tuple(env["catalogs"])) for env in config.get("environments") or []}
    candidates, _ = deploy_candidates(declared(paths) or [], dev_bundle_target(config))
    return [env["name"] for env in candidates if (env["name"], env["bundle_target"], tuple(env["catalogs"])) not in granted]
