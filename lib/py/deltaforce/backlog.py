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
        changed = feature.get("change_of")
        if changed and (changed == feature["id"] or changed not in features):
            problems.append(f"{feature['id']}: change_of must name another feature of the backlog ({changed})")
    problems += _bug_problems(features)

    if paths.state_yaml.exists() and not any(p.startswith("state.yaml") for p in problems):
        state = _load_yaml(paths.state_yaml)
        for feature_id in state.get("active_features", []):
            if feature_id not in features:
                problems.append(f"state.yaml: active feature {feature_id} has no backlog file")
        for step in state.get("next_steps", []):
            if step.get("feature") and step["feature"] not in features:
                problems.append(f"state.yaml: next step references unknown feature {step['feature']}")

    if paths.events.exists():
        bug_ids = {bug["id"] for feature in features.values() for bug in feature.get("bugs", [])}
        for number, line in enumerate(paths.events.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                problems.append(f"events.jsonl line {number}: invalid JSON ({exc.msg})")
                continue
            errors = _schema_errors("event", event, f"events.jsonl line {number}")
            problems += errors
            if not errors and event.get("bug") and event["bug"] not in bug_ids:
                problems.append(f"events.jsonl line {number}: bug {event['bug']} is not in any feature file")

    return problems


OPEN_BUGS = {"open", "fixing", "fixed"}
CLOSED_BUGS = {"verified", "wont_fix"}
GATE_BLOCKING = {"blocker", "major"}


def _bug_problems(features: dict[str, dict[str, Any]]) -> list[str]:
    """Bugs: one numbering across the backlog, links that resolve, and no blocker or major bug left open at G2."""
    problems: list[str] = []
    tasks = {task["id"]: feature_id for feature_id, feature in features.items() for task in feature["tasks"]}
    seen: set[str] = set()
    for feature_id, feature in features.items():
        for bug in feature.get("bugs", []):
            where = f"{feature_id}: bug {bug['id']}"
            if bug["id"] in seen:
                problems.append(f"{where}: duplicate bug id (bugs are numbered across the whole backlog)")
            seen.add(bug["id"])
            if bug["found_in"] not in features:
                problems.append(f"{where}: found_in names unknown feature {bug['found_in']}")
            for task_id in bug["fix_tasks"]:
                if task_id not in tasks:
                    problems.append(f"{where}: fix task {task_id} is not in any feature")
            if (bug["status"] in CLOSED_BUGS) != bool(bug["closed"]):
                problems.append(f"{where}: closed is set when, and only when, the bug is verified or wont_fix")
            if bug["status"] == "wont_fix" and not str(bug.get("notes") or "").strip():
                problems.append(f"{where}: wont_fix needs notes with the PO's decision")
            if bug["status"] not in OPEN_BUGS or bug["severity"] not in GATE_BLOCKING:
                continue
            # The features that must fix it first: the one it was found in, when it lives there, and those holding its fix tasks.
            owners = {tasks[task_id] for task_id in bug["fix_tasks"] if task_id in tasks}
            if bug["found_in"] == feature_id:
                owners.add(feature_id)
            for owner in sorted(owners):
                if features[owner]["status"] in {"awaiting_po", "done"}:
                    problems.append(
                        f"{owner}: is {features[owner]['status']} with {bug['severity']} bug {bug['id']} still {bug['status']}"
                    )
    return problems


def _build_event(
    event_type: Any, role: Any, feature: Any = None, task: Any = None, data: Any = None, where: str = "event", bug: Any = None
) -> dict[str, Any]:
    event: dict[str, Any] = {"ts": now_iso(), "role": role, "event": event_type}
    if feature:
        event["feature"] = feature
    if task:
        event["task"] = task
    if bug:
        event["bug"] = bug
    event["data"] = data if data is not None else {}
    errors = _schema_errors("event", event, where)
    if errors:
        raise cfg.ConfigError("\n".join(errors))
    return event


def _write_events(paths: ProjectPaths, events: list[dict[str, Any]]) -> None:
    paths.events.parent.mkdir(parents=True, exist_ok=True)
    with paths.events.open("a", encoding="utf-8", newline="\n") as f:
        f.write("".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events))


def append_event(
    paths: ProjectPaths,
    event_type: str,
    role: str,
    feature: str | None = None,
    task: str | None = None,
    data: dict[str, Any] | None = None,
    bug: str | None = None,
) -> dict[str, Any]:
    event = _build_event(event_type, role, feature, task, data, bug=bug)
    _write_events(paths, [event])
    return event


def append_events(paths: ProjectPaths, items: list[Any]) -> list[dict[str, Any]]:
    """Several events of one change, recorded together: all of them, or none when one is invalid."""
    events = []
    for number, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise cfg.ConfigError(f"event {number}: must be a JSON object")
        events.append(_build_event(
            item.get("type") or item.get("event"), item.get("role"), item.get("feature"), item.get("task"),
            item.get("data"), where=f"event {number}", bug=item.get("bug"),
        ))
    _write_events(paths, events)
    return events
