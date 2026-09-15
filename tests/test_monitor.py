import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request

import pytest
import yaml

from conftest import ROOT

sys.path.insert(0, str(ROOT / "lib"))
from monitor import launcher, model, server, statusline  # noqa: E402

NOW = dt.datetime(2026, 9, 14, 17, 0, tzinfo=dt.timezone.utc)


def write_feature(root, name, meta, body="## User stories\n\n- **US-1** As an analyst, I want clean trips.\n"):
    path = root / ".deltaforce" / "backlog" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{yaml.safe_dump(meta, sort_keys=False)}---\n\n{body}", encoding="utf-8")


def task(task_id, role, status):
    return {"id": task_id, "title": f"Task {task_id}", "role": role, "status": status, "branch": None}


def feature(feature_id, title, status, depends_on=(), tasks=(), **extra):
    return {
        "id": feature_id, "title": title, "status": status, "depends_on": list(depends_on), "branch": f"df/{feature_id}",
        "tasks": list(tasks), "po_decision": None, "created": "2026-09-14T15:38:00Z", "updated": "2026-09-14T16:00:00Z", **extra,
    }


def write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")


@pytest.fixture
def project(tmp_path, example_config):
    root = tmp_path
    base = root / ".deltaforce"
    base.mkdir()
    (base / "config.yaml").write_text(yaml.safe_dump(example_config), encoding="utf-8")
    (base / "state.yaml").write_text(
        yaml.safe_dump({
            "version": 1, "phase": "delivery", "dev_branch": "dev", "active_features": ["F-002"],
            "g1": {"status": "approved", "at": "2026-09-14T15:30:00Z", "notes": ""},
            "next_steps": [
                {"owner": "po", "action": "Confirm the KPI list", "feature": "F-003"},
                {"owner": "qa-engineer", "action": "Test F-002 on dev", "feature": "F-002"},
            ],
            "last_update": {"at": "2026-09-14T16:55:00Z", "summary": "F-002 deployed to dev"},
            "updated": "2026-09-14T16:55:00Z",
        }),
        encoding="utf-8",
    )
    write_feature(root, "F-001-bronze-silver.md", feature(
        "F-001", "Bronze and silver", "done", tasks=[task("T-001.1", "data-engineer", "integrated")],
        po_decision={"decision": "approved", "at": "2026-09-14T16:30:00Z", "notes": "ok"},
    ))
    write_feature(root, "F-002-gold-kpis.md", feature(
        "F-002", "Gold KPIs", "in_test", depends_on=["F-001"],
        tasks=[task("T-002.1", "data-engineer", "integrated"), task("T-002.2", "qa-engineer", "todo")],
    ))
    write_feature(root, "F-003-dashboard.md", feature("F-003", "KPI dashboard", "todo", depends_on=["F-002"]))
    write_feature(root, "F-004-revenue.md", feature("F-004", "Monthly revenue", "awaiting_po"))
    write_jsonl(base / "events.jsonl", [
        {"ts": "2026-09-14T15:00:00Z", "role": "pm", "event": "phase_changed", "data": {"from": None, "to": "discovery"}},
        {"ts": "2026-09-14T15:15:00Z", "role": "pm", "event": "phase_changed", "data": {"from": "discovery", "to": "awaiting_g1"}},
        {"ts": "2026-09-14T15:20:00Z", "role": "pm", "event": "po_decision", "data": {"gate": "G1", "decision": "changes_requested"}},
        {"ts": "2026-09-14T15:30:00Z", "role": "pm", "event": "po_decision", "data": {"gate": "G1", "decision": "approved"}},
        {"ts": "2026-09-14T15:31:00Z", "role": "pm", "event": "phase_changed", "data": {"from": "awaiting_g1", "to": "delivery"}},
        {"ts": "2026-09-14T15:40:00Z", "role": "pm", "event": "feature_status_changed", "feature": "F-001",
         "data": {"from": "todo", "to": "in_progress"}},
        {"ts": "2026-09-14T16:10:00Z", "role": "pm", "event": "test_run", "feature": "F-002", "data": {"passed": 3, "failed": 2}},
        {"ts": "2026-09-14T16:11:00Z", "role": "pm", "event": "feature_status_changed", "feature": "F-002",
         "data": {"from": "in_test", "to": "in_progress", "reason": "row count mismatch"}},
        {"ts": "2026-09-14T16:20:00Z", "role": "devops-engineer", "event": "deploy_finished", "feature": "F-002",
         "data": {"target": "dev", "result": "success"}},
        {"ts": "2026-09-14T16:21:00Z", "role": "pm", "event": "delegation_started", "feature": "F-002",
         "data": {"agent": "qa-engineer", "task": "F-002 test phase"}},
        {"ts": "2026-09-14T16:30:00Z", "role": "pm", "event": "delegation_finished", "feature": "F-002",
         "data": {"agent": "qa-engineer", "task": "F-002 test phase", "result": "blocked"}},
    ])
    worktree_file = f"{root.as_posix()}/.claude/worktrees/agent-a1/src/pipelines/silver.py"
    write_jsonl(base / "runtime" / "activity.jsonl", [
        {"ts": "2026-09-14T15:00:00Z", "session_id": "s0", "role": "pm", "event": "session_started"},
        {"ts": "2026-09-14T15:01:00Z", "session_id": "s0", "agent_id": "a0", "role": "qa-engineer", "event": "agent_started"},
        {"ts": "2026-09-14T15:10:00Z", "session_id": "s0", "agent_id": "a0", "role": "qa-engineer", "event": "agent_stopped"},
        {"ts": "2026-09-14T15:11:00Z", "session_id": "s0", "role": "pm", "event": "session_ended"},
        {"ts": "2026-09-14T16:47:00Z", "session_id": "s1", "role": "po", "event": "po_message"},
        {"ts": "2026-09-14T16:48:00Z", "session_id": "s1", "role": "po", "event": "po_message", "command": "/df-status"},
        {"ts": "2026-09-14T16:49:00Z", "session_id": "s1", "role": "pm", "event": "asked_po", "tool": "AskUserQuestion", "questions": 2},
        {"ts": "2026-09-14T16:50:00Z", "session_id": "s1", "role": "pm", "event": "session_started"},
        {"ts": "2026-09-14T16:51:00Z", "session_id": "s1", "role": "pm", "event": "delegated", "tool": "Agent",
         "summary": "T-002.1 fix silver joins", "target_role": "data-engineer", "task": "T-002.1", "feature": "F-002"},
        {"ts": "2026-09-14T16:52:00Z", "session_id": "s1", "agent_id": "a1", "role": "data-engineer", "event": "agent_started"},
        {"ts": "2026-09-14T16:58:00Z", "session_id": "s1", "agent_id": "a1", "role": "data-engineer", "event": "tool_used",
         "tool": "Edit", "summary": worktree_file},
    ])
    (base / "requirements").mkdir()
    (base / "requirements" / "functional-analysis.md").write_text("# Functional Analysis\n\n| a | b |\n|---|---|\n", encoding="utf-8")
    (base / "reports").mkdir()
    (base / "reports" / "F-004-po-review.md").write_text("# F-004 review\n", encoding="utf-8")
    (base / "runtime" / "notes.md").write_text("# runtime\n", encoding="utf-8")
    (base / "framework").mkdir()
    (base / "framework" / "README.md").write_text("# framework\n", encoding="utf-8")
    (base / "secret.md").write_text("# top level\n", encoding="utf-8")
    return root


def test_board_columns_dates_dependencies_and_what_waits_for_the_po(project):
    snap = model.snapshot(project, NOW)
    features = {item["id"]: item for item in snap["features"]}

    assert [features[i]["column"] for i in ("F-001", "F-002", "F-003", "F-004")] == ["done", "doing", "todo", "po"]
    assert features["F-001"]["started"] == "2026-09-14T15:40:00Z"  # from the first status change
    assert features["F-001"]["completed"] == "2026-09-14T16:30:00Z"  # from the PO decision
    assert features["F-001"]["cycle_seconds"] == 50 * 60
    assert features["F-002"]["blocked_by"] == [] and features["F-003"]["blocked_by"] == ["F-002"]
    assert features["F-002"]["tasks_done"] == 1 and features["F-002"]["status_label"] == "In test"
    assert features["F-004"]["review_report"] == ".deltaforce/reports/F-004-po-review.md"
    assert "US-1" in features["F-001"]["body"]
    assert features["F-002"]["events"][0] == {**features["F-002"]["events"][0], "text": "QA Engineer finished F-002 test phase — blocked", "tone": "bad"}
    assert features["F-002"]["events"][1]["text"] == "QA Engineer started F-002 test phase"

    assert snap["phase_label"] == "Delivery" and snap["started"] is True
    assert snap["latest"] == {"text": "F-002 deployed to dev", "ts": "2026-09-14T16:55:00Z"}
    assert [item["route"] for item in snap["waiting"]] == ["feature/F-004", "feature/F-003"]
    assert snap["next_steps"][1]["owner_title"] == "QA Engineer"
    assert snap["project"]["name"] == "customer-360" and snap["problems"] == []


def test_workflow_counts_handoffs_steps_back_and_po_involvement(project):
    snap = model.snapshot(project, NOW)
    flow = snap["workflow"]
    counts = flow["counts"]

    assert counts["loops"] == 2  # F-002 sent back by the tests, the design sent back at G1
    assert flow["loops"][0] == {
        "ts": "2026-09-14T16:11:00Z", "feature": "F-002", "text": "In test → In progress", "cause": "tests failed (row count mismatch)",
    }
    assert flow["loops"][1]["text"] == "Design sent back"
    assert counts["deploys"] == {"ok": 1, "failed": 0} and counts["tests"] == {"passed": 0, "failed": 1}
    assert counts["po"] == {"gates": 2, "changes": 1, "questions": 2, "escalations": 0, "messages": 2, "total": 4}
    assert [item["kind"] for item in flow["po"]] == ["question", "command", "gate", "gate"]
    assert flow["po"][0]["text"] == "Project Manager asked you 2 questions"

    handoffs = {(item["from"], item["to"]): item for item in flow["handoffs"]}
    assert handoffs[("pm", "data-engineer")]["count"] == 1  # recorded by the hook
    assert handoffs[("pm", "qa-engineer")] == {**handoffs[("pm", "qa-engineer")], "count": 1, "done": 0, "not_done": 1}
    assert counts["handoffs"] == 2
    assert [phase["phase"] for phase in flow["phases"]] == ["discovery", "awaiting_g1", "delivery"]
    assert flow["phases"][0]["end"] == "2026-09-14T15:15:00Z" and flow["phases"][-1]["end"] is None

    feature_flow = {item["id"]: item for item in snap["features"]}["F-002"]["flow"]
    assert [(step["status"], step["back"]) for step in feature_flow["path"]] == [("todo", False), ("in_progress", True)]
    assert feature_flow["loops"] == 1 and feature_flow["tests"] == {"passed": 0, "failed": 1}
    assert feature_flow["deploys"] == {"ok": 1, "failed": 0}


def test_team_shows_who_works_on_what(project):
    snap = model.snapshot(project, NOW)
    team = {role["id"]: role for role in snap["team"]}

    engineer = team["data-engineer"]
    assert engineer["status"] == "working" and engineer["instances"] == 1
    assert engineer["current"] == {"text": "T-002.1 fix silver joins", "since": "2026-09-14T16:52:00Z", "task": "T-002.1", "feature": "F-002"}
    assert engineer["last_action"]["text"] == "Editing src/pipelines/silver.py"

    assert team["pm"]["status"] == "waiting" and team["pm"]["waiting_for"] == ["Data Engineer"]
    assert team["pm"]["model"] == "opus" and team["data-engineer"]["model"] == "sonnet"
    assert team["qa-engineer"]["status"] == "idle" and team["qa-engineer"]["next_task"]["id"] == "T-002.2"
    assert any("F-002 test phase" in item["text"] for item in team["qa-engineer"]["recent"])
    assert team["data-scientist"]["involved"] is False
    assert snap["session"] == {"open": True, "last_activity": "2026-09-14T16:58:00Z"}


def test_sessions_end_and_stale_agents_go_idle(project):
    later = NOW + dt.timedelta(hours=4)
    team = {role["id"]: role for role in model.snapshot(project, later)["team"]}
    assert team["data-engineer"]["status"] == "idle" and team["pm"]["status"] == "idle"

    activity = project / ".deltaforce" / "runtime" / "activity.jsonl"
    with activity.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"ts": "2026-09-14T16:59:00Z", "session_id": "s1", "role": "pm", "event": "session_ended"}) + "\n")
    assert model.snapshot(project, NOW)["session"]["open"] is False


def test_an_approved_feature_being_closed_no_longer_waits_for_the_po(project):
    write_feature(project, "F-004-revenue.md", feature(
        "F-004", "Monthly revenue", "awaiting_po", po_decision={"decision": "approved", "at": "2026-09-14T16:59:00Z", "notes": ""},
    ))
    snap = model.snapshot(project, NOW)
    assert [item["route"] for item in snap["waiting"]] == ["feature/F-003"]


def test_broken_files_are_reported_without_breaking_the_view(project):
    (project / ".deltaforce" / "state.yaml").write_text("phase: [unclosed\n", encoding="utf-8")
    (project / ".deltaforce" / "backlog" / "F-009-broken.md").write_text("no frontmatter\n", encoding="utf-8")
    with (project / ".deltaforce" / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")

    snap = model.snapshot(project, NOW)
    assert snap["started"] is False and snap["phase_label"] == "Not started"
    assert any(problem.startswith("state.yaml") for problem in snap["problems"])
    assert any(problem.startswith("F-009-broken.md") for problem in snap["problems"])
    assert len(snap["features"]) == 4


def test_empty_project_before_kickoff(tmp_path):
    snap = model.snapshot(tmp_path, NOW)
    assert snap["started"] is False and snap["features"] == [] and snap["documents"] == []
    assert snap["team"][0]["id"] == "pm" and snap["session"]["open"] is False


def test_documents_are_limited_to_team_markdown(project):
    paths = [doc["path"] for doc in model.documents(project)]
    assert paths == [
        ".deltaforce/requirements/functional-analysis.md",
        ".deltaforce/reports/F-004-po-review.md",
        ".deltaforce/secret.md",
    ]
    assert model.documents(project)[0]["title"] == "Functional Analysis"

    assert model.read_document(project, ".deltaforce/reports/F-004-po-review.md")["title"] == "F-004 review"
    assert model.read_document(project, ".deltaforce/backlog/F-001-bronze-silver.md")["text"].startswith("---")
    for refused in [
        ".deltaforce/../outside.md",
        ".deltaforce/runtime/notes.md",
        ".deltaforce/framework/README.md",
        ".deltaforce/config.yaml",
        "README.md",
        str(project / ".deltaforce" / "reports" / "F-004-po-review.md"),
        ".deltaforce\\reports\\..\\..\\x.md",
    ]:
        assert model.read_document(project, refused) is None, refused


def test_actions_and_events_in_plain_words(tmp_path):
    assert model.describe_action("Bash", '"$DF_ROOT/.deltaforce/bin/databricks" bundle deploy -t dev', tmp_path) == "Deploying the bundle to dev"
    assert model.describe_action("Bash", "ls -la\nmore", tmp_path) == "Running ls -la"
    assert model.describe_action("Bash", 'cd "C:/Users/me/My Project" && git merge --no-ff df/F-001', tmp_path) == "Merging branches"
    assert model.describe_action("Bash", "cd repo; pytest -q", tmp_path) == "Running tests"
    assert model.describe_action("mcp__databricks-prod__execute_sql", "SELECT 1", tmp_path) == "Querying data on production"
    assert model.describe_action("mcp__databricks__manage_jobs", '{"action": "list"}', tmp_path) == "Databricks manage jobs (list) on dev"
    assert model.describe_action("Write", f"{tmp_path.as_posix()}/resources/jobs.yml", tmp_path) == "Editing resources/jobs.yml"

    catalog = model._roles_catalog()
    bad = model.describe_event({"event": "deploy_finished", "data": {"result": "blocked"}}, catalog)
    assert bad["tone"] == "bad" and bad["text"] == "Deploy to dev: blocked"
    decision = model.describe_event({"event": "po_decision", "data": {"gate": "G1", "decision": "approved"}}, catalog)
    assert decision == {**decision, "text": "You approved G1", "tone": "po"}


def request(port, path, headers=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read()


def test_server_serves_the_page_snapshot_and_documents_only(project):
    httpd = server.MonitorServer(("127.0.0.1", 0), server.make_handler(project))
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = request(port, "/api/ping")
        assert status == 200 and json.loads(body)["app"] == launcher.APP_ID
        assert launcher.ping(port, project) and not launcher.ping(port, project / "other")

        status, _, body = request(port, "/api/status")
        assert status == 200 and json.loads(body)["phase"] == "Delivery"

        status, headers, body = request(port, "/api/snapshot")
        assert status == 200 and json.loads(body)["project"]["name"] == "customer-360"
        assert request(port, "/api/snapshot", {"If-None-Match": headers["ETag"]})[0] == 304

        assert request(port, "/api/doc?path=.deltaforce/reports/F-004-po-review.md")[0] == 200
        assert request(port, "/api/doc?path=.deltaforce/config.yaml")[0] == 404
        status, headers, body = request(port, "/")
        assert status == 200 and b"/static/app.js" in body and headers["Cache-Control"] == "no-store"
        assert request(port, "/static/app.css")[0] == 200
        assert request(port, "/static/../model.py")[0] == 404
        assert request(port, "/static/%2e%2e/model.py")[0] == 404
        assert request(port, "/api/ping", {"Host": "attacker.example:80"})[0] == 403
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_server_stops_when_the_team_is_gone(project):
    started = NOW - dt.timedelta(hours=1)
    idle = dt.timedelta(minutes=30)
    activity = project / ".deltaforce" / "runtime" / "activity.jsonl"

    recent = (NOW - dt.timedelta(minutes=5)).timestamp()
    os.utime(activity, (recent, recent))
    assert server.should_stop(project, started, idle, NOW) is False

    quiet = (NOW - dt.timedelta(minutes=45)).timestamp()
    os.utime(activity, (quiet, quiet))
    assert server.should_stop(project, started, idle, NOW) is False  # session s1 is still open

    with activity.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"ts": "2026-09-14T16:59:00Z", "session_id": "s1", "event": "session_ended"}) + "\n")
    os.utime(activity, (quiet, quiet))
    assert server.should_stop(project, started, idle, NOW) is True

    old = (NOW - dt.timedelta(hours=5)).timestamp()
    os.utime(activity, (old, old))
    assert server.should_stop(project, NOW - dt.timedelta(hours=6), idle, NOW) is True


def test_status_summary(project):
    assert model.status(model.snapshot(project, NOW)) == {
        "project": "customer-360", "phase": "Delivery", "waiting": 2, "working": 1, "features": 4, "done": 1,
    }


def test_status_line_links_the_monitor_without_the_model(tmp_path, monkeypatch):
    url = "http://127.0.0.1:8765/"
    monkeypatch.setattr(launcher, "start_in_background", lambda root, python: url)
    monkeypatch.setattr(statusline, "fetch_status", lambda address: {"phase": "Delivery", "features": 4, "done": 1, "waiting": 2})
    line = statusline.render(tmp_path, tmp_path / "python")
    assert f"\x1b]8;;{url}\amonitor {url}\x1b]8;;\a" in line
    assert "Delivery" in line and "1/4 features done" in line and "2 waiting for you" in line

    monkeypatch.setattr(launcher, "start_in_background", lambda root, python: None)
    assert "starting" in statusline.render(tmp_path, tmp_path / "python")
    monkeypatch.setattr(launcher, "running_url", lambda root: None)
    assert "monitor off" in statusline.render(tmp_path, tmp_path / "python", autostart=False)


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is not available")
def test_status_line_script_asks_the_monitor_with_bash_builtins(project):
    httpd = server.MonitorServer(("127.0.0.1", 0), server.make_handler(project))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    script = (ROOT / "lib" / "monitor" / "statusline.sh").as_posix()
    command = f'. "{script}" "{project.as_posix()}" "no-python-needed"'
    try:
        launcher.update_state(project, port=port)
        result = subprocess.run(["bash", "-c", command], capture_output=True, text=True, encoding="utf-8", timeout=60)
        assert f"\x1b]8;;http://127.0.0.1:{port}/\a" in result.stdout
        assert "2 waiting for you" in result.stdout and result.stdout.count("\n") == 1
    finally:
        httpd.shutdown()
        httpd.server_close()

    launcher.update_state(project, port=None)
    off = subprocess.run(
        ["bash", "-c", command], capture_output=True, text=True, encoding="utf-8", timeout=60,
        env={**os.environ, "DELTAFORCE_MONITOR": "off"},
    )
    assert "monitor off" in off.stdout


def test_background_start_does_not_spawn_twice(tmp_path, monkeypatch):
    spawned = []
    monkeypatch.setattr(launcher, "running_url", lambda root: None)
    monkeypatch.setattr(launcher, "_spawn", lambda root, python: spawned.append(root))
    assert launcher.start_in_background(tmp_path, tmp_path / "python") is None
    assert launcher.start_in_background(tmp_path, tmp_path / "python") is None
    assert len(spawned) == 1
    launcher.update_state(tmp_path, spawned_at=1.0)  # long ago
    launcher.start_in_background(tmp_path, tmp_path / "python")
    assert len(spawned) == 2


def test_ports_are_stable_per_project(tmp_path):
    first = launcher.preferred_port(tmp_path)
    assert first == launcher.preferred_port(tmp_path)
    assert launcher.PORT_BASE <= first < launcher.PORT_BASE + launcher.PORT_SPAN
    ports = launcher.candidate_ports(tmp_path)
    assert ports[0] == first and len(set(ports)) == launcher.PORT_ATTEMPTS
    assert all(launcher.PORT_BASE <= port < launcher.PORT_BASE + launcher.PORT_SPAN for port in ports)


def test_the_page_opens_once_per_session(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(launcher, "start", lambda root, python: launcher.url_for(8765))
    monkeypatch.setattr(launcher, "open_browser", lambda url: opened.append(url) or True)

    assert launcher.ensure(tmp_path, tmp_path / "python", "s1", open_page=False) == "http://127.0.0.1:8765/"
    assert opened == []
    launcher.ensure(tmp_path, tmp_path / "python", "s1", open_page=True)
    launcher.ensure(tmp_path, tmp_path / "python", "s1", open_page=True)
    launcher.ensure(tmp_path, tmp_path / "python", "s2", open_page=True)
    assert len(opened) == 2
    assert launcher.read_state(tmp_path)["opened_sessions"] == ["s1", "s2"]

    launcher.update_state(tmp_path, port=8765)
    monkeypatch.setattr(launcher, "start", lambda root, python: pytest.fail("a known session must not ping or spawn"))
    assert launcher.ensure(tmp_path, tmp_path / "python", "s1", open_page=True) == "http://127.0.0.1:8765/"
