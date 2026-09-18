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
AGENT_TEMPLATES = LIB_DIR.parent / "templates" / "claude" / "agents"

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
BUG_STATUS = {
    "open": "Open", "fixing": "Fixing", "fixed": "Fixed, to verify", "verified": "Verified", "wont_fix": "Won't fix",
}
OPEN_BUGS = {"open", "fixing", "fixed"}
BUG_SEVERITY = ("blocker", "major", "minor")
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
IDLE_GAP = dt.timedelta(minutes=30)  # a stretch this long without events or activity is not time worked
MAIN_ROLE_BUSY = dt.timedelta(minutes=2)
FEATURE_FILE = re.compile(r"^(F-\d{3,})")
WORKTREE_PREFIX = re.compile(r"^.*?/\.claude/worktrees/[^/]+/")
ACTION = re.compile(r'"action"\s*:\s*"([\w-]+)"')
CD_PREFIX = re.compile(r"""^(?:cd\s+(?:"[^"]*"|'[^']*'|\S+)\s*(?:&&|;)\s*)+""")
MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
MARKDOWN_EMPHASIS = re.compile(r"\*\*|__|`")
BOLD = re.compile(r"\*\*(.+?)\*\*")
LIST_ITEM = re.compile(r"^(?:\d+[.)]|[-*+])\s+(.*)$")
DESCRIPTION_LIMIT = 360
FEATURE_DESCRIPTION_LIMIT = 220
STORY_ID = re.compile(r"^(?:US|FR)-[\d.]+[a-z]?\s*[—–:-]?\s*", re.IGNORECASE)
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")
DESCRIPTION_SECTIONS = ("summary", "business goal and expected value", "goal and users", "in the po's words")
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
    """Roles with the description and model of their agent template (Claude Code subagent frontmatter)."""
    try:
        catalog = (yaml.safe_load(ROLES_FILE.read_text(encoding="utf-8")) or {}).get("roles", {})
    except (OSError, yaml.YAMLError):
        return {}
    for role, spec in catalog.items():
        try:
            frontmatter, _ = split_frontmatter((AGENT_TEMPLATES / f"{role}.md").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        spec.update({key: frontmatter[key] for key in ("description", "model", "color") if key in frontmatter})
    return catalog


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
    elif kind == "bug_opened":
        where = f" in {feature}" if feature else ""
        found = f", found during {data['found_in']}" if data.get("found_in") and data.get("found_in") != feature else ""
        text = f"Bug {event.get('bug') or ''} opened{where}: {data.get('title', '')}".replace("  ", " ").rstrip(": ")
        text += f" ({data['severity']}{found})" if data.get("severity") else ""
        tone = "bad"
    elif kind == "bug_status_changed":
        text = f"Bug {event.get('bug') or ''}: {_label(BUG_STATUS, data.get('from'))} → {_label(BUG_STATUS, data.get('to'))}"
        tone = "ok" if data.get("to") == "verified" else "info"
    elif kind == "conventions_changed":
        text = "Client conventions changed"
    else:
        text = kind.replace("_", " ")
    return {"ts": event.get("ts"), "role": event.get("role"), "text": text, "tone": tone, "feature": feature, "task": task}


# ─── time worked ────────────────────────────────────────────────


def moments_of(*records: list[dict[str, Any]]) -> list[dt.datetime]:
    """Every moment the project left a trace, in order: events and recorded activity."""
    found = [moment for group in records for record in group if (moment := parse_ts(record.get("ts")))]
    found.sort()
    return found


def active_seconds(moments: list[dt.datetime], start: dt.datetime | None, end: dt.datetime | None) -> int | None:
    """Time worked between two moments: stretches of 30 minutes or more without a trace do not count."""
    if not start or not end or end <= start:
        return None
    points = [start, *(moment for moment in moments if start < moment < end), end]
    return int(sum((later - earlier).total_seconds() for earlier, later in zip(points, points[1:]) if later - earlier < IDLE_GAP))


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

        bugs = []
        for bug in meta.get("bugs") or []:
            if not isinstance(bug, dict):
                continue
            bug_status = str(bug.get("status")) if bug.get("status") in BUG_STATUS else "open"
            bugs.append({
                "id": str(bug.get("id", "")),
                "feature": feature_id,
                "title": str(bug.get("title", "")),
                "severity": str(bug.get("severity")) if bug.get("severity") in BUG_SEVERITY else "major",
                "status": bug_status,
                "status_label": BUG_STATUS[bug_status],
                "open": bug_status in OPEN_BUGS,
                "found_by": bug.get("found_by"),
                "found_by_title": role_title(bug.get("found_by"), catalog) if bug.get("found_by") != "po" else "You",
                "found_during": bug.get("found_during"),
                "found_in": str(bug["found_in"]) if bug.get("found_in") else None,
                "evidence": str(bug.get("evidence") or ""),
                "fix_tasks": [str(item) for item in bug.get("fix_tasks") or []],
                "opened": bug.get("opened"),
                "closed": bug.get("closed"),
                "notes": str(bug.get("notes") or ""),
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
        sections = feature_sections(body)
        criteria = next((item["markdown"] for item in sections if item["key"] == "acceptance criteria"), "")

        features.append({
            "id": feature_id,
            "title": str(meta.get("title") or feature_id),
            "status": status,
            "status_label": FEATURE_STATUS[status],
            "column": COLUMNS[status],
            "depends_on": [str(item) for item in meta.get("depends_on") or []],
            "change_of": str(meta["change_of"]) if meta.get("change_of") else None,
            "changed_by": [],
            "blocked_by": [],
            "branch": meta.get("branch"),
            "tasks": tasks,
            "tasks_done": sum(task["status"] in FINISHED_TASKS for task in tasks),
            "bugs": bugs,
            "bugs_open": sum(bug["open"] for bug in bugs),
            "bugs_found": [],
            "po_decision": decision,
            "started": started,
            "completed": completed,
            "cycle_seconds": int((end_moment - start_moment).total_seconds()) if start_moment and end_moment else None,
            "created": meta.get("created"),
            "updated": meta.get("updated"),
            "body": body,
            "sections": sections,
            "description": feature_description(sections),
            "criteria_count": len(_top_level_items(criteria)),
            "file": f".deltaforce/backlog/{path.name}",
            "review_report": f".deltaforce/reports/{review.name}" if review.exists() else None,
            "evidence": review_evidence(review) if review.exists() else None,
            "events": [describe_event(event, catalog) for event in reversed(feature_events)][:80],
            "flow": feature_flow(feature_events),
        })

    done = {feature["id"] for feature in features if feature["status"] == "done"}
    by_id = {feature["id"]: feature for feature in features}
    for feature in features:
        feature["blocked_by"] = [item for item in feature["depends_on"] if item not in done]
        if feature["change_of"] in by_id:
            by_id[feature["change_of"]]["changed_by"].append(feature["id"])
        # Bugs found while building this feature that live in another one.
        feature["bugs_found"] = [
            bug for other in features if other["id"] != feature["id"] for bug in other["bugs"] if bug["found_in"] == feature["id"]
        ]
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


def interrupted_agents(activity: list[dict[str, Any]]) -> dict[str, str]:
    """Agents that never stopped because their session died (a crash, a PC restart): agent id → last activity.

    An agent without a stop is interrupted when its session ended, or when another session started
    after the agent's last activity — one session works on the repository at a time.
    """
    agents: dict[str, dict[str, Any]] = {}
    ended: dict[str, str] = {}
    starts: list[tuple[str, str]] = []
    for record in activity:
        ts, agent_id, session_id, kind = str(record.get("ts") or ""), record.get("agent_id"), record.get("session_id"), record.get("event")
        if not ts:
            continue
        if kind == "session_started" and session_id:
            starts.append((ts, session_id))
            ended.pop(session_id, None)
        elif kind == "session_ended" and session_id:
            ended[session_id] = ts
        if not agent_id:
            continue
        if kind == "agent_started":
            agents[agent_id] = {"session": session_id, "last": ts, "stopped": False}
        elif agent_id in agents:
            agents[agent_id]["last"] = max(agents[agent_id]["last"], ts)
            agents[agent_id]["stopped"] = agents[agent_id]["stopped"] or kind == "agent_stopped"
    return {
        agent_id: agent["last"] for agent_id, agent in agents.items()
        if not agent["stopped"] and (
            agent["session"] in ended
            or any(other != agent["session"] and ts >= agent["last"] for ts, other in starts)
        )
    }


def _timeline(
    events: list[dict[str, Any]],
    activity: list[dict[str, Any]],
    catalog: dict[str, dict[str, Any]],
    task_titles: dict[str, str],
    hooks_since: str | None,
    now: dt.datetime,
) -> dict[str, Any]:
    """Who worked when, who asked them, and the gates, deploys, tests and steps back along the way."""
    runs: list[dict[str, Any]] = []

    def run(role: Any, source: Any, start: Any, end: Any, summary: Any, task: Any, feature: Any, result: Any) -> None:
        role, source = str(role or "unknown"), str(source or MAIN_ROLE)
        started = parse_ts(start)
        if task and not summary:
            summary = f"{task} {task_titles.get(str(task), '')}".strip()
        runs.append({
            "role": role, "role_title": role_title(role, catalog), "short": ROLE_SHORT.get(role, role[:2].upper()),
            "from": source, "from_title": role_title(source, catalog),
            "start": start, "end": end, "running": not end and bool(started) and now - started < AGENT_STALE,
            "summary": summary, "task": task, "feature": feature or (f"F-{str(task)[2:].split('.')[0]}" if task else None),
            "result": result,
        })

    finished = [event for event in events if event.get("event") == "delegation_finished"]

    # Runs recorded by the hooks: each agent from start to stop, with the delegation that started it.
    delegations = [record for record in activity if record.get("event") == "delegated" and record.get("target_role")]
    used: set[int] = set()
    agents: dict[str, dict[str, Any]] = {}
    for record in activity:
        agent_id = record.get("agent_id")
        if agent_id and record.get("event") == "agent_started":
            agents[agent_id] = {"role": record.get("role"), "start": record.get("ts"), "end": None}
        elif agent_id and record.get("event") == "agent_stopped" and agent_id in agents:
            agents[agent_id]["end"] = record.get("ts")
    for agent_id, last in interrupted_agents(activity).items():
        agents[agent_id].update(end=last, interrupted=True)
    for agent in sorted(agents.values(), key=lambda item: str(item["start"])):
        started, stopped = parse_ts(agent["start"]), parse_ts(agent["end"])
        match: tuple[int, dict[str, Any]] | None = None
        for index, delegation in enumerate(delegations):
            moment = parse_ts(delegation.get("ts"))
            if index in used or delegation.get("target_role") != agent["role"] or not (moment and started):
                continue
            if started - dt.timedelta(minutes=2) <= moment <= started + dt.timedelta(seconds=5):
                match = (index, delegation)
        delegation = {}
        if match:
            used.add(match[0])
            delegation = match[1]
        result = "interrupted" if agent.get("interrupted") else None
        if stopped and not result:
            for event in finished:
                moment = parse_ts(event.get("ts"))
                if _data(event).get("agent") == agent["role"] and moment and stopped - dt.timedelta(seconds=5) <= moment <= stopped + dt.timedelta(minutes=10):
                    result = _data(event).get("result")
                    break
        run(agent["role"], delegation.get("role"), agent["start"], agent["end"], delegation.get("summary"),
            delegation.get("task"), delegation.get("feature"), result)

    # Before the hooks recorded anything: the delegations the PM logged as events.
    waiting: dict[tuple[Any, Any], list[dict[str, Any]]] = {}
    for event in events:
        if hooks_since and str(event.get("ts")) >= hooks_since:
            break
        data = _data(event)
        if not data.get("agent") or event.get("event") not in {"delegation_started", "delegation_finished"}:
            continue
        key = (data["agent"], event.get("task") or data.get("task"))
        if event.get("event") == "delegation_started":
            waiting.setdefault(key, []).append(event)
        elif waiting.get(key):
            opened = waiting[key].pop(0)
            summary = None if opened.get("task") else _data(opened).get("task")
            run(data["agent"], opened.get("role"), opened.get("ts"), event.get("ts"), summary, opened.get("task"),
                opened.get("feature"), data.get("result"))
    hook_runs = [(item["role"], parse_ts(item["start"])) for item in runs]
    for opened_list in waiting.values():
        for opened in opened_list:
            role, started = _data(opened)["agent"], parse_ts(opened.get("ts"))
            # Logged just before the hooks started recording: the hooks already show this run.
            if started and any(
                other_role == role and other_start and started <= other_start <= started + dt.timedelta(minutes=10)
                for other_role, other_start in hook_runs
            ):
                continue
            summary = None if opened.get("task") else _data(opened).get("task")
            run(role, opened.get("role"), opened.get("ts"), None, summary, opened.get("task"), opened.get("feature"), None)
            if hooks_since:
                runs[-1]["running"] = False  # the hooks would show it if it were still running

    markers: list[dict[str, Any]] = []
    for event in events:
        kind, data = event.get("event"), _data(event)
        back = _step_back(event)
        if back:
            markers.append({"ts": event.get("ts"), "lane": MAIN_ROLE, "tone": "bad", "feature": back["feature"],
                            "text": f"{back['feature']}: {back['text']} — {back['cause']}"})
        elif kind == "po_decision":
            approved = data.get("decision") == "approved"
            subject = f"G2 {event['feature']}" if data.get("gate") == "G2" and event.get("feature") else (data.get("gate") or "decision")
            markers.append({"ts": event.get("ts"), "lane": "po", "tone": "po" if approved else "bad", "feature": event.get("feature"),
                            "text": f"{subject}: you {'approved' if approved else 'asked for changes'}"})
        elif kind == "escalation":
            markers.append({"ts": event.get("ts"), "lane": "po", "tone": "bad", "feature": event.get("feature"),
                            "text": f"Escalation: {data.get('reason') or data.get('summary') or ''}".rstrip(": ")})
        elif kind == "deploy_finished":
            markers.append({"ts": event.get("ts"), "lane": "devops-engineer", "tone": "ok" if _deploy_ok(event) else "bad",
                            "feature": event.get("feature"), "text": f"Deploy to dev: {data.get('result', 'finished')}"})
        elif kind == "bug_opened":
            lane = data.get("found_by") if data.get("found_by") in ROLE_SHORT else event.get("role") or MAIN_ROLE
            markers.append({"ts": event.get("ts"), "lane": lane, "tone": "bad", "feature": event.get("feature"),
                            "text": describe_event(event, catalog)["text"]})
        elif kind == "test_run":
            markers.append({"ts": event.get("ts"), "lane": "qa-engineer", "tone": "bad" if data.get("failed") else "ok",
                            "feature": event.get("feature"), "text": f"Tests: {data.get('passed')} passed, {data.get('failed')} failed"})
    for record in activity:
        if record.get("event") == "asked_po":
            count = int(record.get("questions") or 1)
            markers.append({"ts": record.get("ts"), "lane": "po", "tone": "po", "feature": None,
                            "text": f"{role_title(record.get('role') or MAIN_ROLE, catalog)} asked you {count} question{'s' if count != 1 else ''}"})

    runs.sort(key=lambda item: str(item["start"] or ""))
    markers.sort(key=lambda item: str(item["ts"] or ""))
    return {"runs": runs[-300:], "markers": markers[-300:]}


def _workflow(
    events: list[dict[str, Any]],
    activity: list[dict[str, Any]],
    catalog: dict[str, dict[str, Any]],
    task_titles: dict[str, str] | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    now = now or dt.datetime.now(dt.timezone.utc)
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
    deploy_runs: list[dict[str, Any]] = []
    tests = {"passed": 0, "failed": 0}
    po_items: list[dict[str, Any]] = []
    po = {"gates": 0, "changes": 0, "questions": 0, "escalations": 0, "messages": 0}
    for event in events:
        kind, data = event.get("event"), _data(event)
        if kind == "deploy_finished":
            ok = _deploy_ok(event)
            deploys["ok" if ok else "failed"] += 1
            deploy_runs.append({"ts": event.get("ts"), "feature": event.get("feature"), "target": data.get("target"), "ok": ok})
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

    # Phases: how long each one lasted on the clock, and how much of it was worked (design §9).
    changes = [(event.get("ts"), _data(event).get("to")) for event in events if event.get("event") == "phase_changed"]
    moments = moments_of(events, activity)
    phases = []
    for index, (start, phase) in enumerate(changes):
        if not phase:
            continue
        end = changes[index + 1][0] if index + 1 < len(changes) else None
        started, ended = parse_ts(start), parse_ts(end) or now
        phases.append({
            "phase": phase, "label": PHASES.get(str(phase), str(phase)), "start": start, "end": end, "open": end is None,
            "elapsed_seconds": int((ended - started).total_seconds()) if started and ended else None,
            "active_seconds": active_seconds(moments, started, ended),
        })

    return {
        "counts": {
            "handoffs": sum(item["count"] for item in handoffs),
            "loops": len(loops),
            "deploys": deploys,
            "tests": tests,
            "po": {**po, "total": po["gates"] + po["questions"] + po["escalations"]},
        },
        "loops": sorted(loops, key=lambda item: str(item["ts"] or ""), reverse=True),
        "deploys": deploy_runs,
        "handoffs": handoffs,
        "po": sorted(po_items, key=lambda item: str(item["ts"] or ""), reverse=True)[:60],
        "phases": phases,
        "timeline": _timeline(events, activity, catalog, task_titles or {}, hooks_since, now),
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

    interrupted = interrupted_agents(activity)
    open_agents = [
        agent for agent_id, agent in agents.items()
        if not agent.get("stopped") and agent_id not in interrupted and now - agent["last"] < AGENT_STALE and agent.get("role")
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


# ─── project summary ────────────────────────────────────────────


def _plain(text: str) -> str:
    return " ".join(MARKDOWN_EMPHASIS.sub("", MARKDOWN_LINK.sub(r"\1", text)).split())


def _describe_section(lines: list[str]) -> str:
    """The opening paragraph of a request section, followed by its top-level list items in short."""
    paragraph: list[str] = []
    items: list[str] = []
    for line in lines:
        text = line.strip().lstrip(">").strip()
        item = LIST_ITEM.match(line)  # only top-level items: indented lines do not match
        if item:
            bold = BOLD.search(item.group(1))
            items.append(_plain(bold.group(1) if bold else item.group(1)).rstrip(".:;"))
        elif text and not items and not line.startswith((" ", "\t")):
            paragraph.append(text)
        elif not text and paragraph and not items:
            continue
    opening = _plain(" ".join(paragraph))
    if not items:
        return opening
    listed = "; ".join(items)
    if not opening:
        return listed + "."
    return f"{opening} {listed}." if opening.endswith(":") else f"{opening.rstrip('.')}: {listed}."


def project_description(root: Path) -> str | None:
    """A short description of the project, from the request recorded at kickoff."""
    try:
        text = (root / ".deltaforce" / "requirements" / "request.md").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    sections: dict[str, list[str]] = {}
    current = None
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.startswith("## "):
            current = line[3:].strip().lower()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    for key in DESCRIPTION_SECTIONS:
        description = _describe_section(sections.get(key, []))
        if description:
            return _truncate(description, DESCRIPTION_LIMIT)
    return None


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def feature_sections(body: str) -> list[dict[str, str]]:
    """The `## ` sections of a feature file body, in order."""
    sections: list[dict[str, str]] = []
    current: dict[str, Any] | None = None
    for line in body.replace("\r\n", "\n").split("\n"):
        if line.startswith("## "):
            current = {"title": line[3:].strip(), "key": line[3:].strip().lower(), "lines": []}
            sections.append(current)
        elif current is not None:
            current["lines"].append(line)
        elif line.strip():
            current = {"title": "", "key": "", "lines": [line]}
            sections.append(current)
    return [{"title": item["title"], "key": item["key"], "markdown": "\n".join(item["lines"]).strip()} for item in sections]


PASSED_RESULTS = ("pass", "✓", "ok", "success", "succeeded", "yes")
FAILED_RESULTS = ("fail", "✗", "error", "no")


def _table_results(markdown: str) -> dict[str, int]:
    """Passed and failed rows of the first Markdown table whose header has a result column."""
    rows = [line.strip() for line in markdown.split("\n") if line.strip().startswith("|")]
    counts = {"passed": 0, "failed": 0, "total": 0}
    if len(rows) < 3:
        return counts
    cells = lambda row: [cell.strip() for cell in row.strip("|").split("|")]  # noqa: E731
    header = [cell.lower() for cell in cells(rows[0])]
    column = next((index for index, name in enumerate(header) if "result" in name or "outcome" in name), None)
    if column is None:
        return counts
    for row in rows[2:]:
        values = cells(row)
        if column >= len(values):
            continue
        result = _plain(values[column]).lower()
        counts["total"] += 1
        if result.startswith(PASSED_RESULTS):
            counts["passed"] += 1
        elif result.startswith(FAILED_RESULTS):
            counts["failed"] += 1
    return counts


def review_evidence(path: Path) -> dict[str, Any] | None:
    """Test evidence, regression checks and destructive operations from a PO review report."""
    try:
        sections = {item["key"]: item["markdown"] for item in feature_sections(path.read_text(encoding="utf-8", errors="replace"))}
    except OSError:
        return None
    tests = sections.get("test evidence", "")
    regression = sections.get("regression checks", "")
    destructive = next((text for key, text in sections.items() if key.startswith("destructive operations")), "")
    if not (tests or regression or destructive):
        return None
    return {
        "tests": tests or None,
        "tests_count": _table_results(tests),
        "regression": regression or None,
        "regression_count": _table_results(regression),
        "destructive": destructive or None,
    }


def _top_level_items(markdown: str) -> list[str]:
    return [match.group(1) for line in markdown.split("\n") if (match := LIST_ITEM.match(line))]


def feature_description(sections: list[dict[str, str]]) -> str | None:
    """What a feature is, in a line: its business value, else its user stories."""
    by_key = {item["key"]: item["markdown"] for item in sections}
    value = by_key.get("business value", "")
    if value:
        prose = " ".join(line.strip() for line in value.split("\n") if line.strip() and not LIST_ITEM.match(line))
        sentences = [part for part in SENTENCE_BREAK.split(_plain(prose)) if part]
        if sentences and sentences[0].lower().startswith("objective"):
            sentences = sentences[1:]  # "Objectives: O1, O3 (see ...)." points elsewhere
        if sentences:
            return _truncate(" ".join(sentences), FEATURE_DESCRIPTION_LIMIT)
    stories = by_key.get("user stories") or by_key.get("user story") or ""
    titles = []
    for item in _top_level_items(stories):
        bold = BOLD.search(item)
        title = STORY_ID.sub("", _plain(bold.group(1))).strip(" .:—–-") if bold else ""
        if not title:  # only an id in bold: use the sentence
            title = STORY_ID.sub("", _plain(BOLD.sub("", item) if bold else item)).strip().rstrip(".")
        if title:
            titles.append(title)
    return _truncate("; ".join(titles) + ".", FEATURE_DESCRIPTION_LIMIT) if titles else None


def _overview(state: dict[str, Any], features: list[dict[str, Any]]) -> str:
    """What the team is doing, in one sentence."""
    if not state:
        return "Not started yet: run /df-kickoff in Claude Code."
    phase = state.get("phase")
    names = lambda items: ", ".join(f"{item['id']} {item['title']}" for item in items)  # noqa: E731
    if phase == "discovery":
        text = "Analysing the request and designing the solution."
    elif phase == "awaiting_g1":
        text = "The design and the feature list are ready for your approval (G1)."
    elif phase == "handover":
        text = "Every feature is delivered: handover to production through CI/CD."
    elif phase == "done":
        text = "Project delivered."
    else:
        building = [item for item in features if item["column"] == "doing"]
        review = [
            item for item in features
            if item["column"] == "po" and (item["po_decision"] or {}).get("decision") != "approved"
        ]
        parts = []
        if building:
            parts.append(f"building {names(building)}")
        if review:
            parts.append(f"waiting for your review: {names(review)}")
        text = "; ".join(parts) or "choosing the next features to build"
        text = text[0].upper() + text[1:] + "."
    if features:
        done = sum(item["status"] == "done" for item in features)
        text += f" {done} of {len(features)} features done."
    return text


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
    for item in items:
        item["title"] = _notification_title(item["text"])
    return items


def _notification_title(text: str) -> str:
    """The first sentence, short enough for one line of the collapsed Waiting for you box."""
    first = text.strip()
    for mark in (". ", "! ", "? ", "\n"):
        first = first.split(mark, 1)[0]
    return _truncate(first.rstrip("."), 60)


def status(view: dict[str, Any]) -> dict[str, Any]:
    """The few numbers the Claude Code status line shows."""
    return {
        "project": view["project"]["name"],
        "phase": view["phase_label"],
        "phase_key": view["phase"],
        "started": view["started"],
        "review": [
            feature["id"] for feature in view["features"]
            if feature["status"] == "awaiting_po" and (feature["po_decision"] or {}).get("decision") != "approved"
        ],
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

    workflow = _workflow(
        events, activity, catalog,
        {task["id"]: task["title"] for feature in features for task in feature["tasks"]}, now,
    )
    # Each task shows who worked on it, when, what they were asked and the result.
    runs_by_task: dict[str, list[dict[str, Any]]] = {}
    for item in workflow["timeline"]["runs"]:
        if item.get("task"):
            runs_by_task.setdefault(str(item["task"]), []).append({
                key: item[key] for key in ("from", "from_title", "role", "role_title", "start", "end", "running", "summary", "result")
            })
    for feature in features:
        for task in feature["tasks"]:
            task["runs"] = runs_by_task.get(task["id"], [])
    # Time worked: for a feature, the stretch from start to done without the idle gaps (nights, pauses).
    moments = moments_of(events, activity)
    for feature in features:
        feature["active_seconds"] = active_seconds(moments, parse_ts(feature["started"]), parse_ts(feature["completed"]))
    worked: dict[str, float] = {}
    for item in workflow["timeline"]["runs"]:
        start = parse_ts(item["start"])
        end = parse_ts(item["end"]) or (now if item.get("running") else None)
        if start and end and end > start:
            worked[item["role"]] = worked.get(item["role"], 0.0) + (end - start).total_seconds()
    for role in team:
        role["worked_seconds"] = int(worked.get(role["id"], 0))

    workflow["counts"]["changes_after_delivery"] = sum(bool(feature["change_of"]) for feature in features)
    workflow["counts"]["features"] = {
        "total": len(features),
        "done": sum(feature["status"] == "done" for feature in features),
    }
    all_bugs = [bug for feature in features for bug in feature["bugs"]]
    workflow["counts"]["bugs"] = {
        "total": len(all_bugs),
        "open": sum(bug["open"] for bug in all_bugs),
        "verified": sum(bug["status"] == "verified" for bug in all_bugs),
        "blocking": sum(bug["open"] and bug["severity"] != "minor" for bug in all_bugs),
    }

    conventions = _load_yaml(base / "conventions.yaml", problems)
    conventions = conventions if isinstance(conventions, dict) else {}
    kind = (conventions.get("project") or {}).get("kind") if isinstance(conventions.get("project"), dict) else None

    return {
        "project": {
            "name": project.get("name") or root.name,
            "description": project_description(root),
            "kind": kind,
            "dev_branch": project.get("dev_branch"),
            "workspace": databricks.get("host"),
            "catalog": dev.get("catalog"),
        },
        "overview": _overview(state, features),
        "started": bool(state),
        "phase": state.get("phase"),
        "phase_label": PHASES.get(str(state.get("phase")), "Not started"),
        "latest": latest,
        "next_steps": next_steps,
        "waiting": _waiting_for_po(state, features),
        "features": features,
        "team": team,
        "session": session,
        "workflow": workflow,
        "documents": documents(root),
        "problems": problems,
    }
