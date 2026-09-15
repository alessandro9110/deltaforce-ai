"""The monitor's view of a project, built from the files in .deltaforce — it reads files and never writes."""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

import yaml

LIB_DIR = Path(__file__).resolve().parents[1]
ROLES_FILE = LIB_DIR / "data" / "roles.yaml"

MAIN_ROLE = "pm"
ROLE_ORDER = (
    "pm", "solution-architect", "business-analyst", "data-engineer", "data-analyst", "data-scientist",
    "ai-engineer", "qa-engineer", "devops-engineer",
)
ROLE_SHORT = {
    "pm": "PM", "solution-architect": "SA", "business-analyst": "BA", "data-engineer": "DE", "data-analyst": "DA",
    "data-scientist": "DS", "ai-engineer": "AI", "qa-engineer": "QA", "devops-engineer": "DO", "po": "PO",
}
PHASES = {
    "discovery": "Discovery", "awaiting_g1": "Waiting for G1", "delivery": "Delivery", "handover": "Handover", "done": "Done",
}
FEATURE_STATUS = {
    "todo": "To do", "in_progress": "In progress", "integrating": "Integrating", "in_test": "In test",
    "awaiting_po": "Waiting for you", "done": "Done", "blocked": "Blocked",
}
TASK_STATUS = {
    "todo": "To do", "in_progress": "In progress", "ready_for_integration": "Ready for integration",
    "integrated": "Integrated", "done": "Done", "blocked": "Blocked",
}
COLUMNS = {
    "todo": "todo", "blocked": "todo", "in_progress": "doing", "integrating": "doing", "in_test": "doing",
    "awaiting_po": "po", "done": "done",
}
FINISHED_TASKS = {"integrated", "done"}
STATUS_ORDER = {"todo": 0, "in_progress": 1, "integrating": 2, "in_test": 3, "awaiting_po": 4, "done": 5}
LOOP_CAUSES = {
    "awaiting_po": "you asked for changes", "in_test": "tests failed", "integrating": "integration or deploy failed",
    "done": "reopened after approval",
}
NOT_DONE_RESULTS = {"blocked", "needs-decision", "needs_decision", "failed"}
OK_RESULTS = {"success", "succeeded", "ok", "done", "passed"}
DOC_GROUPS = {"requirements": "Requirements", "architecture": "Architecture", "reports": "Reports"}
NOT_DOCUMENTS = {"framework", "runtime", "review", "bin"}
ACTIVITY_TAIL_BYTES = 4 * 1024 * 1024
AGENT_STALE = dt.timedelta(hours=3)
SESSION_STALE = dt.timedelta(hours=4)
MAIN_ROLE_BUSY = dt.timedelta(minutes=2)
FEATURE_FILE = re.compile(r"^(F-\d{3,})")
WORKTREE_PREFIX = re.compile(r"^.*?/\.claude/worktrees/[^/]+/")
ACTION = re.compile(r'"action"\s*:\s*"([\w-]+)"')
CD_PREFIX = re.compile(r"""^(?:cd\s+(?:"[^"]*"|'[^']*'|\S+)\s*(?:&&|;)\s*)+""")
COMMANDS = (
    (re.compile(r"\bbundle\s+deploy\b"), "Deploying the bundle to dev"),
    (re.compile(r"\bbundle\s+run\b"), "Running a bundle job on dev"),
    (re.compile(r"\bbundle\s+validate\b"), "Validating the bundle"),
    (re.compile(r"\bgit\b.*\bmerge\b"), "Merging branches"),
    (re.compile(r"\bgit\b.*\bcommit\b"), "Committing changes"),
    (re.compile(r"\bgit\b.*\bpush\b"), "Pushing a branch"),
    (re.compile(r"\bgit\b.*\bworktree\b"), "Preparing a worktree"),
    (re.compile(r"\bdf\s+event\b"), "Recording progress"),
    (re.compile(r"\bdf\s+validate\b"), "Checking the backlog"),
    (re.compile(r"\bpytest\b"), "Running tests"),
)


# ─── reading ────────────────────────────────────────────────────


def _normalize(value: Any) -> Any:
    """YAML turns unquoted timestamps into datetime objects; the view uses ISO strings."""
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


def parse_ts(value: Any) -> dt.datetime | None:
    if not value:
        return None
    try:
        moment = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=dt.timezone.utc)


def _iso(moment: dt.datetime | None) -> str | None:
    return moment.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z") if moment else None


def _load_yaml(path: Path, problems: list[str]) -> Any:
    if not path.exists():
        return None
    try:
        return _normalize(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        problems.append(f"{path.name}: {str(exc).splitlines()[0]}")
        return None


def _read_jsonl(path: Path, problems: list[str], tail_bytes: int | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open("rb") as handle:
            if tail_bytes:
                handle.seek(0, 2)
                size = handle.tell()
                handle.seek(max(0, size - tail_bytes))
            data = handle.read().decode("utf-8", errors="replace")
    except OSError as exc:
        problems.append(f"{path.name}: {exc}")
        return []
    lines = data.splitlines()
    if tail_bytes and len(data.encode("utf-8")) >= tail_bytes:
        lines = lines[1:]  # the first line may be cut in half
    records = []
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        raise ValueError("missing YAML frontmatter")
    end = text.find("\n---", 4)
    if end == -1:
        raise ValueError("unterminated YAML frontmatter")
    try:
        data = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML frontmatter ({str(exc).splitlines()[0]})") from exc
    if not isinstance(data, dict):
        raise ValueError("frontmatter is not a mapping")
    body = text[end + 4 :].split("\n", 1)[1] if "\n" in text[end + 4 :] else ""
    return _normalize(data), body.strip("\n")


def _roles_catalog() -> dict[str, dict[str, Any]]:
    try:
        return (yaml.safe_load(ROLES_FILE.read_text(encoding="utf-8")) or {}).get("roles", {})
    except (OSError, yaml.YAMLError):
        return {}


# ─── wording ────────────────────────────────────────────────────


def role_title(role: str | None, catalog: dict[str, dict[str, Any]]) -> str:
    if role == "po":
        return "You"
    return str(catalog.get(role or "", {}).get("title") or role or "Someone")


def short_path(path: str, root: Path) -> str:
    text = path.replace("\\", "/")
    text = WORKTREE_PREFIX.sub("", text)
    root_text = root.as_posix().rstrip("/") + "/"
    if text.lower().startswith(root_text.lower()):
        text = text[len(root_text) :]
    return text.lstrip("/") or path


def describe_action(tool: str, summary: str, root: Path) -> str:
    """What a tool call means, in words a Product Owner reads at a glance."""
    if tool in {"Edit", "Write", "NotebookEdit"}:
        return f"Editing {short_path(summary, root)}" if summary else "Editing files"
    if tool == "Bash":
        command = CD_PREFIX.sub("", summary.strip())
        for pattern, text in COMMANDS:
            if pattern.search(command):
                return text
        first = command.splitlines()[0] if command else ""
        return f"Running {first[:90]}" if first else "Running a command"
    if tool.startswith("mcp__"):
        parts = tool.split("__", 2)
        server, name = (parts[1], parts[2]) if len(parts) == 3 else ("", tool)
        where = "production" if server.endswith("-prod") else "dev"
        if name in {"execute_sql", "execute_sql_multi"}:
            return f"Querying data on {where}"
        action = ACTION.search(summary)
        label = name.replace("_", " ")
        return f"Databricks {label}{f' ({action.group(1)})' if action else ''} on {where}"
    return tool


def _label(mapping: dict[str, str], value: Any) -> str:
    return mapping.get(str(value), str(value).replace("_", " ")) if value is not None else "—"


def describe_event(event: dict[str, Any], catalog: dict[str, dict[str, Any]]) -> dict[str, Any]:
    kind = str(event.get("event", ""))
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    feature, task = event.get("feature"), event.get("task")
    agent = role_title(data.get("agent"), catalog) if data.get("agent") else None
    work = task or data.get("task") or feature or ""
    tone = "info"
    if kind == "kickoff_completed":
        text = "Kickoff completed"
    elif kind == "phase_changed":
        text = f"Phase changed to {_label(PHASES, data.get('to'))}"
    elif kind == "feature_created":
        text = f"{feature} created: {data.get('title', '')}".rstrip(": ")
    elif kind == "feature_status_changed":
        text = f"{feature}: {_label(FEATURE_STATUS, data.get('from'))} → {_label(FEATURE_STATUS, data.get('to'))}"
        if data.get("reason"):
            text += f" ({data['reason']})"
        tone = "ok" if data.get("to") == "done" else ("po" if data.get("to") == "awaiting_po" else "info")
    elif kind == "task_status_changed":
        text = f"{task}: {_label(TASK_STATUS, data.get('from'))} → {_label(TASK_STATUS, data.get('to'))}"
    elif kind == "delegation_started":
        text = f"{agent or 'A specialist'} started {work}".strip()
    elif kind == "delegation_finished":
        result = data.get("result")
        text = f"{agent or 'A specialist'} finished {work}".strip() + (f" — {result}" if result and result != "done" else "")
        tone = "bad" if result in {"blocked", "failed"} else "info"
    elif kind == "deploy_started":
        text = f"Deploy to {data.get('target', 'dev')} started"
    elif kind == "deploy_finished":
        result = str(data.get("result", "finished"))
        text = f"Deploy to {data.get('target', 'dev')}: {result}"
        tone = "ok" if result in {"success", "succeeded", "ok"} else "bad"
    elif kind == "test_run":
        passed, failed = data.get("passed"), data.get("failed")
        text = f"Tests: {passed} passed, {failed} failed" if passed is not None else "Tests run"
        tone = "bad" if failed else "ok"
    elif kind == "po_decision":
        decision = data.get("decision")
        subject = data.get("gate") or feature or ""
        text = f"You {'approved' if decision == 'approved' else 'asked for changes to'} {subject}".strip()
        tone = "po"
    elif kind == "escalation":
        text = f"Escalation: {data.get('summary') or data.get('reason') or 'the team needs a decision'}"
        tone = "bad"
    elif kind == "conventions_changed":
        text = "Client conventions changed"
    else:
        text = kind.replace("_", " ")
    return {"ts": event.get("ts"), "role": event.get("role"), "text": text, "tone": tone, "feature": feature, "task": task}


# ─── features ───────────────────────────────────────────────────


def _event_ts(events: list[dict[str, Any]], match, last: bool = False) -> str | None:
    found = [event.get("ts") for event in events if match(event)]
    return (found[-1] if last else found[0]) if found else None


def _status_to(event: dict[str, Any], values: set[str]) -> bool:
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    return event.get("event") == "feature_status_changed" and data.get("to") in values


def _features(root: Path, events: list[dict[str, Any]], catalog, problems: list[str]) -> list[dict[str, Any]]:
    backlog = root / ".deltaforce" / "backlog"
    by_feature: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        if event.get("feature"):
            by_feature.setdefault(str(event["feature"]), []).append(event)

    features: list[dict[str, Any]] = []
    for path in sorted(backlog.glob("F-*.md")) if backlog.is_dir() else []:
        try:
            meta, body = split_frontmatter(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            problems.append(f"{path.name}: {exc}")
            continue
        match = FEATURE_FILE.match(path.name)
        feature_id = str(meta.get("id") or (match.group(1) if match else path.stem))
        status = str(meta.get("status")) if meta.get("status") in FEATURE_STATUS else "todo"
        feature_events = by_feature.get(feature_id, [])

        tasks = []
        for task in meta.get("tasks") or []:
            if not isinstance(task, dict):
                continue
            task_status = str(task.get("status")) if task.get("status") in TASK_STATUS else "todo"
            tasks.append({
                "id": str(task.get("id", "")),
                "title": str(task.get("title", "")),
                "role": task.get("role"),
                "status": task_status,
                "status_label": TASK_STATUS[task_status],
                "branch": task.get("branch"),
                "report": task.get("report"),
            })

        decision = meta.get("po_decision") if isinstance(meta.get("po_decision"), dict) else None
        started = meta.get("started") or _event_ts(
            feature_events, lambda e: _status_to(e, set(FEATURE_STATUS) - {"todo", "blocked"})
        ) or _event_ts(feature_events, lambda e: e.get("event") in {"task_status_changed", "delegation_started"})
        completed = None
        if status == "done":
            completed = meta.get("completed") or (decision or {}).get("at") or _event_ts(
                feature_events, lambda e: _status_to(e, {"done"}), last=True
            )
        start_moment, end_moment = parse_ts(started), parse_ts(completed)
        review = root / ".deltaforce" / "reports" / f"{feature_id}-po-review.md"

        features.append({
            "id": feature_id,
            "title": str(meta.get("title") or feature_id),
            "status": status,
            "status_label": FEATURE_STATUS[status],
            "column": COLUMNS[status],
            "depends_on": [str(item) for item in meta.get("depends_on") or []],
            "blocked_by": [],
            "branch": meta.get("branch"),
            "tasks": tasks,
            "tasks_done": sum(task["status"] in FINISHED_TASKS for task in tasks),
            "po_decision": decision,
            "started": started,
            "completed": completed,
            "cycle_seconds": int((end_moment - start_moment).total_seconds()) if start_moment and end_moment else None,
            "created": meta.get("created"),
            "updated": meta.get("updated"),
            "body": body,
            "file": f".deltaforce/backlog/{path.name}",
            "review_report": f".deltaforce/reports/{review.name}" if review.exists() else None,
            "events": [describe_event(event, catalog) for event in reversed(feature_events)][:80],
            "flow": feature_flow(feature_events),
        })

    done = {feature["id"] for feature in features if feature["status"] == "done"}
    for feature in features:
        feature["blocked_by"] = [item for item in feature["depends_on"] if item not in done]
    return features


# ─── workflow ───────────────────────────────────────────────────


def _data(event: dict[str, Any]) -> dict[str, Any]:
    return event.get("data") if isinstance(event.get("data"), dict) else {}


def _step_back(event: dict[str, Any]) -> dict[str, Any] | None:
    """A feature status change that sends work back, with its most likely cause."""
    data = _data(event)
    before, after = data.get("from"), data.get("to")
    if event.get("event") != "feature_status_changed" or before not in STATUS_ORDER or after not in STATUS_ORDER:
        return None
    if STATUS_ORDER[after] >= STATUS_ORDER[before]:
        return None
    cause = LOOP_CAUSES.get(str(before), "sent back")
    if data.get("reason"):
        cause = f"{cause} ({data['reason']})"
    return {
        "ts": event.get("ts"), "feature": event.get("feature"),
        "text": f"{_label(FEATURE_STATUS, before)} → {_label(FEATURE_STATUS, after)}", "cause": cause,
    }


def _deploy_ok(event: dict[str, Any]) -> bool:
    return str(_data(event).get("result", "")).lower() in OK_RESULTS


def feature_flow(events: list[dict[str, Any]]) -> dict[str, Any]:
    """The path a feature took through the statuses, with the steps back, deploys, test runs and PO decisions."""
    path = [{"status": "todo", "label": FEATURE_STATUS["todo"], "ts": None, "back": False, "cause": None}]
    deploys = {"ok": 0, "failed": 0}
    tests = {"passed": 0, "failed": 0}
    decisions = 0
    for event in events:
        kind, data = event.get("event"), _data(event)
        if kind == "feature_status_changed" and data.get("to") in FEATURE_STATUS:
            back = _step_back(event)
            path.append({
                "status": data["to"], "label": FEATURE_STATUS[data["to"]], "ts": event.get("ts"),
                "back": bool(back), "cause": back["cause"] if back else None,
            })
        elif kind == "deploy_finished":
            deploys["ok" if _deploy_ok(event) else "failed"] += 1
        elif kind == "test_run":
            tests["failed" if data.get("failed") else "passed"] += 1
        elif kind == "po_decision":
            decisions += 1
    return {
        "path": path, "loops": sum(step["back"] for step in path), "deploys": deploys, "tests": tests, "po_decisions": decisions,
    }


def _workflow(
    events: list[dict[str, Any]], activity: list[dict[str, Any]], catalog: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    loops = [back for event in events if (back := _step_back(event))]
    for event in events:
        data = _data(event)
        if event.get("event") == "po_decision" and data.get("gate") == "G1" and data.get("decision") == "changes_requested":
            loops.append({"ts": event.get("ts"), "feature": None, "text": "Design sent back", "cause": "you asked for changes at G1"})

    # Handoffs: delegations recorded by the hooks (nested ones included) and, before the hooks recorded any,
    # the delegations the PM logged as events. Outcomes come from the PM's events.
    recorded = [record for record in activity if record.get("event") == "delegated" and record.get("target_role")]
    hooks_since = min((str(record.get("ts")) for record in recorded), default=None)
    pairs: dict[tuple[str, str], dict[str, Any]] = {}

    def pair(source: Any, target: Any) -> dict[str, Any]:
        key = (str(source or MAIN_ROLE), str(target))
        return pairs.setdefault(key, {"from": key[0], "to": key[1], "count": 0, "done": 0, "not_done": 0})

    for record in recorded:
        pair(record.get("role"), record["target_role"])["count"] += 1
    for event in events:
        agent = _data(event).get("agent")
        if not agent:
            continue
        if event.get("event") == "delegation_started" and (hooks_since is None or str(event.get("ts")) < hooks_since):
            pair(event.get("role"), agent)["count"] += 1
        elif event.get("event") == "delegation_finished":
            result = str(_data(event).get("result", "done")).lower()
            pair(event.get("role"), agent)["not_done" if result in NOT_DONE_RESULTS else "done"] += 1
    handoffs = sorted(pairs.values(), key=lambda item: (-item["count"], item["from"], item["to"]))
    for item in handoffs:
        item.update({
            "from_title": role_title(item["from"], catalog), "to_title": role_title(item["to"], catalog),
            "from_short": ROLE_SHORT.get(item["from"], item["from"][:2].upper()),
            "to_short": ROLE_SHORT.get(item["to"], item["to"][:2].upper()),
        })

    deploys = {"ok": 0, "failed": 0}
    tests = {"passed": 0, "failed": 0}
    po_items: list[dict[str, Any]] = []
    po = {"gates": 0, "changes": 0, "questions": 0, "escalations": 0, "messages": 0}
    for event in events:
        kind, data = event.get("event"), _data(event)
        if kind == "deploy_finished":
            deploys["ok" if _deploy_ok(event) else "failed"] += 1
        elif kind == "test_run":
            tests["failed" if data.get("failed") else "passed"] += 1
        elif kind == "po_decision":
            po["gates"] += 1
            approved = data.get("decision") == "approved"
            po["changes"] += not approved
            subject = data.get("gate") or event.get("feature") or "decision"
            if data.get("gate") == "G2" and event.get("feature"):
                subject = f"G2 {event['feature']}"
            po_items.append({
                "ts": event.get("ts"), "kind": "gate", "feature": event.get("feature"),
                "text": f"{subject}: you {'approved' if approved else 'asked for changes'}",
            })
        elif kind == "escalation":
            po["escalations"] += 1
            po_items.append({
                "ts": event.get("ts"), "kind": "escalation", "feature": event.get("feature"),
                "text": f"Escalation: {data.get('reason') or data.get('summary') or 'the team needed a decision'}",
            })
    for record in activity:
        if record.get("event") == "asked_po":
            count = int(record.get("questions") or 1)
            po["questions"] += count
            po_items.append({
                "ts": record.get("ts"), "kind": "question", "feature": None,
                "text": f"{role_title(record.get('role') or MAIN_ROLE, catalog)} asked you {count} question{'s' if count != 1 else ''}",
            })
        elif record.get("event") == "po_message":
            po["messages"] += 1
            if record.get("command"):
                po_items.append({"ts": record.get("ts"), "kind": "command", "feature": None, "text": f"You ran {record['command']}"})

    changes = [(event.get("ts"), _data(event).get("to")) for event in events if event.get("event") == "phase_changed"]
    phases = [
        {"phase": phase, "label": PHASES.get(str(phase), str(phase)), "start": start, "end": changes[index + 1][0] if index + 1 < len(changes) else None}
        for index, (start, phase) in enumerate(changes) if phase
    ]

    return {
        "counts": {
            "handoffs": sum(item["count"] for item in handoffs),
            "loops": len(loops),
            "deploys": deploys,
            "tests": tests,
            "po": {**po, "total": po["gates"] + po["questions"] + po["escalations"]},
        },
        "loops": sorted(loops, key=lambda item: str(item["ts"] or ""), reverse=True),
        "handoffs": handoffs,
        "po": sorted(po_items, key=lambda item: str(item["ts"] or ""), reverse=True)[:60],
        "phases": phases,
    }


# ─── team ───────────────────────────────────────────────────────


def _team(
    root: Path,
    config: dict[str, Any],
    catalog: dict[str, dict[str, Any]],
    features: list[dict[str, Any]],
    events: list[dict[str, Any]],
    activity: list[dict[str, Any]],
    now: dt.datetime,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    team = config.get("team") if isinstance(config.get("team"), dict) else {}
    enabled = [role for role in ROLE_ORDER if role in (team.get("roles") or ROLE_ORDER)]
    models = team.get("models") if isinstance(team.get("models"), dict) else {}

    sessions: dict[str, dict[str, Any]] = {}
    agents: dict[str, dict[str, Any]] = {}
    delegations: dict[str, list[dict[str, Any]]] = {}
    last_action: dict[str, dict[str, Any]] = {}
    recent: dict[str, list[dict[str, Any]]] = {role: [] for role in enabled}
    last_activity: dt.datetime | None = None

    for record in activity:
        moment = parse_ts(record.get("ts"))
        if not moment:
            continue
        last_activity = max(last_activity, moment) if last_activity else moment
        kind, agent_id = record.get("event"), record.get("agent_id")
        role = agents[agent_id]["role"] if agent_id in agents else (record.get("role") or MAIN_ROLE)
        session_id = record.get("session_id")
        if session_id:
            session = sessions.setdefault(session_id, {"ended": None, "last": moment})
            session["last"] = moment
            if kind == "session_started":
                session["ended"] = None
            elif kind == "session_ended":
                session["ended"] = moment
        if kind == "agent_started" and agent_id:
            agents[agent_id] = {"role": record.get("role"), "started": moment, "stopped": None, "last": moment}
        elif kind == "agent_stopped" and agent_id:
            agents.setdefault(agent_id, {"role": role, "started": moment, "last": moment})["stopped"] = moment
        elif kind == "delegated":
            target = record.get("target_role")
            delegations.setdefault(str(target), []).append(record)
            text = f"Delegated to {role_title(target, catalog)}: {record.get('summary', '')}".rstrip(": ")
            recent.setdefault(role, []).append({"ts": record.get("ts"), "text": text})
        elif kind == "asked_po":
            count = record.get("questions") or 1
            recent.setdefault(role, []).append({"ts": record.get("ts"), "text": f"Asked you {count} question{'s' if count != 1 else ''}"})
        elif kind == "tool_used":
            if agent_id in agents:
                agents[agent_id]["last"] = moment
            entry = {"ts": record.get("ts"), "text": describe_action(str(record.get("tool", "")), str(record.get("summary", "")), root)}
            last_action[role] = entry
            recent.setdefault(role, []).append(entry)

    for event in events:
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        if event.get("event") in {"delegation_started", "delegation_finished"} and data.get("agent") in recent:
            described = describe_event(event, catalog)
            recent[data["agent"]].append({"ts": event.get("ts"), "text": described["text"]})

    open_agents = [
        agent for agent in agents.values()
        if not agent.get("stopped") and now - agent["last"] < AGENT_STALE and agent.get("role")
    ]
    session_open = any(not session["ended"] and now - session["last"] < SESSION_STALE for session in sessions.values())

    roles = []
    for role in enabled:
        spec = catalog.get(role, {})
        mine = [agent for agent in open_agents if agent["role"] == role]
        tasks = [
            {"feature": feature["id"], **{key: task[key] for key in ("id", "title", "status", "status_label")}}
            for feature in features for task in feature["tasks"] if task["role"] == role
        ]
        open_tasks = [task for task in tasks if task["status"] in {"in_progress", "todo", "blocked"}]
        open_tasks.sort(key=lambda task: task["status"] != "in_progress")
        status, current, waiting_for = "idle", None, []

        if mine:
            status = "working"
            latest = (delegations.get(role) or [None])[-1]
            current = {
                "text": (latest or {}).get("summary") or None,
                "since": _iso(min(agent["started"] for agent in mine)),
                "task": (latest or {}).get("task"),
                "feature": (latest or {}).get("feature"),
            }
        elif role == MAIN_ROLE:
            others = [agent["role"] for agent in open_agents if agent["role"] != MAIN_ROLE]
            if others:
                status = "waiting"
                waiting_for = [role_title(item, catalog) for item in dict.fromkeys(others)]
            elif role in last_action and session_open and now - parse_ts(last_action[role]["ts"]) < MAIN_ROLE_BUSY:
                status = "working"

        history = sorted(recent.get(role, []), key=lambda item: str(item.get("ts") or ""), reverse=True)
        roles.append({
            "id": role,
            "title": role_title(role, catalog),
            "short": ROLE_SHORT.get(role, role[:2].upper()),
            "model": models.get(role) or models.get("default") or spec.get("model"),
            "description": " ".join(str(spec.get("description", "")).split()),
            "status": status,
            "instances": len(mine),
            "current": current,
            "waiting_for": waiting_for,
            "last_action": last_action.get(role),
            "next_task": open_tasks[0] if open_tasks else None,
            "tasks": tasks,
            "recent": history[:25],
            "involved": role == MAIN_ROLE or bool(tasks or history or mine),
        })

    session = {"open": session_open, "last_activity": _iso(last_activity)}
    return roles, session


# ─── documents ──────────────────────────────────────────────────


def _doc_title(path: Path) -> str:
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for _, line in zip(range(30), handle):
                if line.startswith("# "):
                    return line[2:].strip()
    except OSError:
        pass
    return path.stem.replace("-", " ")


def documents(root: Path) -> list[dict[str, Any]]:
    base = root / ".deltaforce"
    if not base.is_dir():
        return []
    found: list[Path] = []
    for child in base.iterdir():
        if child.is_dir() and child.name not in NOT_DOCUMENTS and child.name != "backlog":
            found += child.rglob("*.md")
        elif child.is_file() and child.suffix == ".md":
            found.append(child)
    docs = []
    for path in found:
        relative = path.relative_to(base)
        try:
            modified = dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc)
        except OSError:
            continue
        docs.append({
            "path": f".deltaforce/{relative.as_posix()}",
            "group": DOC_GROUPS.get(relative.parts[0], "Other") if len(relative.parts) > 1 else "Other",
            "title": _doc_title(path),
            "modified": _iso(modified),
        })
    order = list(DOC_GROUPS.values()) + ["Other"]
    return sorted(docs, key=lambda doc: (order.index(doc["group"]), doc["path"]))


def read_document(root: Path, relative: str) -> dict[str, Any] | None:
    """A Markdown file under .deltaforce, or None for anything else."""
    text = str(relative).replace("\\", "/")
    parts = text.split("/")
    if (
        len(parts) < 2 or parts[0] != ".deltaforce" or not text.endswith(".md")
        or parts[1] in NOT_DOCUMENTS or any(part in {"", ".", ".."} for part in parts)
    ):
        return None
    base = (root / ".deltaforce").resolve()
    path = (root / text).resolve()
    if base not in path.parents or not path.is_file():
        return None
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    modified = dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc)
    return {"path": text, "title": _doc_title(path), "text": content, "modified": _iso(modified)}


# ─── snapshot ───────────────────────────────────────────────────


def _waiting_for_po(state: dict[str, Any], features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    if state.get("phase") == "awaiting_g1":
        items.append({"text": "Approve the design and the feature list (G1)", "command": "/df-approve", "route": "docs"})
    for feature in features:
        # Approved features stay awaiting_po until the DevOps Engineer merges them: nothing left for the PO.
        if feature["status"] == "awaiting_po" and (feature["po_decision"] or {}).get("decision") != "approved":
            items.append({
                "text": f"Review {feature['id']} — {feature['title']}",
                "command": f"/df-approve {feature['id']}",
                "route": f"feature/{feature['id']}",
            })
    reviewed = {item["route"] for item in items}
    for step in state.get("next_steps") or []:
        if isinstance(step, dict) and step.get("owner") == "po" and f"feature/{step.get('feature')}" not in reviewed:
            items.append({"text": str(step.get("action", "")), "route": f"feature/{step['feature']}" if step.get("feature") else None})
    return items


def status(view: dict[str, Any]) -> dict[str, Any]:
    """The few numbers the Claude Code status line shows."""
    return {
        "project": view["project"]["name"],
        "phase": view["phase_label"],
        "waiting": len(view["waiting"]),
        "working": sum(role["status"] == "working" for role in view["team"]),
        "features": len(view["features"]),
        "done": sum(feature["status"] == "done" for feature in view["features"]),
    }


def snapshot(root: Path, now: dt.datetime | None = None) -> dict[str, Any]:
    now = now or dt.datetime.now(dt.timezone.utc)
    base = root / ".deltaforce"
    problems: list[str] = []
    catalog = _roles_catalog()
    config = _load_yaml(base / "config.yaml", problems)
    config = config if isinstance(config, dict) else {}
    state = _load_yaml(base / "state.yaml", problems)
    state = state if isinstance(state, dict) else {}
    events = _read_jsonl(base / "events.jsonl", problems)
    activity = _read_jsonl(base / "runtime" / "activity.jsonl", problems, ACTIVITY_TAIL_BYTES)

    features = _features(root, events, catalog, problems)
    team, session = _team(root, config, catalog, features, events, activity, now)

    project = config.get("project") if isinstance(config.get("project"), dict) else {}
    databricks = config.get("databricks") if isinstance(config.get("databricks"), dict) else {}
    dev = ((config.get("targets") or {}).get("dev") or {}) if isinstance(config.get("targets"), dict) else {}

    update = state.get("last_update") if isinstance(state.get("last_update"), dict) else None
    if update and update.get("summary"):
        latest = {"text": str(update["summary"]), "ts": update.get("at")}
    elif events:
        described = describe_event(events[-1], catalog)
        latest = {"text": described["text"], "ts": described["ts"]}
    else:
        latest = None

    next_steps = [
        {
            "owner": step.get("owner"),
            "owner_title": role_title(step.get("owner"), catalog),
            "action": str(step.get("action", "")),
            "feature": step.get("feature"),
        }
        for step in state.get("next_steps") or [] if isinstance(step, dict)
    ]

    return {
        "project": {
            "name": project.get("name") or root.name,
            "dev_branch": project.get("dev_branch"),
            "workspace": databricks.get("host"),
            "catalog": dev.get("catalog"),
        },
        "started": bool(state),
        "phase": state.get("phase"),
        "phase_label": PHASES.get(str(state.get("phase")), "Not started"),
        "latest": latest,
        "next_steps": next_steps,
        "waiting": _waiting_for_po(state, features),
        "features": features,
        "team": team,
        "session": session,
        "workflow": _workflow(events, activity, catalog),
        "documents": documents(root),
        "problems": problems,
    }
