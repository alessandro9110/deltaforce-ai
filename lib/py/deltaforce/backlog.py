"""Validate the project state written by the team and append lifecycle events."""

from __future__ import annotations

import datetime as dt
import json
import re
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from . import config as cfg
from .paths import FRAMEWORK_DIR, ProjectPaths

SCHEMAS_DIR = FRAMEWORK_DIR / "schemas"
FEATURE_FILE = re.compile(r"^(F-\d{3,})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@cache
def _validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((SCHEMAS_DIR / f"{name}.schema.json").read_text(encoding="utf-8")))


def event_types() -> list[str]:
    return list(_validator("event").schema["properties"]["event"]["enum"])


def _normalize(value: Any) -> Any:
    """YAML turns unquoted timestamps into datetime objects; the schemas expect ISO strings."""
    if isinstance(value, dt.datetime):
        text = value.isoformat()
        return text.replace("+00:00", "Z") if value.tzinfo else text
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


def _schema_errors(name: str, data: Any, where: str) -> list[str]:
    errors = sorted(_validator(name).iter_errors(data), key=lambda e: list(e.absolute_path))
    return [f"{where}: {'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors]


def read_frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if not text.startswith("---\n"):
        raise cfg.ConfigError(f"{path.name}: missing YAML frontmatter")
    end = text.find("\n---", 4)
    if end == -1:
        raise cfg.ConfigError(f"{path.name}: unterminated YAML frontmatter")
    data = yaml.safe_load(text[4:end]) or {}
    if not isinstance(data, dict):
        raise cfg.ConfigError(f"{path.name}: frontmatter is not a mapping")
    return _normalize(data)


def _load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return _normalize(yaml.safe_load(f))


def validate_project(paths: ProjectPaths, include_config: bool = True) -> list[str]:
    """All problems in config, conventions, state, backlog and events; empty when valid."""
    problems: list[str] = []

    if include_config:
        try:
            cfg.load_config(paths.config)
        except cfg.ConfigError as exc:
            problems.append(f"config.yaml: {exc}")

    for name, path in (("conventions", paths.conventions), ("state", paths.state_yaml)):
        if path.exists():
            try:
                problems += _schema_errors(name, _load_yaml(path), path.name)
            except yaml.YAMLError as exc:
                problems.append(f"{path.name}: invalid YAML ({exc})")

    features: dict[str, dict[str, Any]] = {}
    for path in sorted(paths.backlog.glob("*.md")) if paths.backlog.exists() else []:
        match = FEATURE_FILE.match(path.name)
        if not match:
            problems.append(f"{path.name}: file name must be F-<number>-<slug>.md")
            continue
        try:
            data = read_frontmatter(path)
        except (cfg.ConfigError, yaml.YAMLError) as exc:
            problems.append(str(exc))
            continue
        errors = _schema_errors("feature", data, path.name)
        problems += errors
        if errors:
            continue
        if data["id"] != match.group(1):
            problems.append(f"{path.name}: id {data['id']} does not match the file name")
        if data["id"] in features:
            problems.append(f"{path.name}: duplicate feature id {data['id']}")
        number = data["id"].split("-", 1)[1]
        task_ids = [task["id"] for task in data["tasks"]]
        for task_id in task_ids:
            if not task_id.startswith(f"T-{number}."):
                problems.append(f"{path.name}: task {task_id} does not belong to {data['id']}")
        if len(task_ids) != len(set(task_ids)):
            problems.append(f"{path.name}: duplicate task ids")
        for task in data["tasks"]:
            report = task.get("report")
            if report and not (paths.root / report).exists():
                problems.append(f"{path.name}: report {report} of {task['id']} does not exist")
        features[data["id"]] = data

    for feature in features.values():
        for dependency in feature["depends_on"]:
            if dependency not in features:
                problems.append(f"{feature['id']}: depends on unknown feature {dependency}")
            elif dependency == feature["id"]:
                problems.append(f"{feature['id']}: depends on itself")

    if paths.state_yaml.exists() and not any(p.startswith("state.yaml") for p in problems):
        state = _load_yaml(paths.state_yaml)
        for feature_id in state.get("active_features", []):
            if feature_id not in features:
                problems.append(f"state.yaml: active feature {feature_id} has no backlog file")
        for step in state.get("next_steps", []):
            if step.get("feature") and step["feature"] not in features:
                problems.append(f"state.yaml: next step references unknown feature {step['feature']}")

    if paths.events.exists():
        for number, line in enumerate(paths.events.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                problems += _schema_errors("event", json.loads(line), f"events.jsonl line {number}")
            except json.JSONDecodeError as exc:
                problems.append(f"events.jsonl line {number}: invalid JSON ({exc.msg})")

    return problems


def append_event(
    paths: ProjectPaths,
    event_type: str,
    role: str,
    feature: str | None = None,
    task: str | None = None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {"ts": now_iso(), "role": role, "event": event_type}
    if feature:
        event["feature"] = feature
    if task:
        event["task"] = task
    event["data"] = data or {}
    errors = _schema_errors("event", event, "event")
    if errors:
        raise cfg.ConfigError("\n".join(errors))
    paths.events.parent.mkdir(parents=True, exist_ok=True)
    with paths.events.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event
