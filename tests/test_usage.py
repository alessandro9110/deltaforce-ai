import json
import sys
import threading
import urllib.request

import pytest
import yaml

from conftest import ROOT

sys.path.insert(0, str(ROOT / "lib"))
from monitor import server, usage  # noqa: E402


def assistant(message_id, timestamp, model, input_tokens=10, write=100, read=1000, output=50):
    return {
        "type": "assistant",
        "timestamp": timestamp,
        "message": {
            "id": message_id,
            "model": model,
            "usage": {"input_tokens": input_tokens, "cache_creation_input_tokens": write, "cache_read_input_tokens": read, "output_tokens": output},
        },
    }


def write_lines(path, records, newline_at_end=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(json.dumps(record) for record in records)
    path.write_text(text + ("\n" if newline_at_end else ""), encoding="utf-8")


@pytest.fixture
def sessions(tmp_path, monkeypatch):
    project = tmp_path / "My Project"
    project.mkdir()
    # The real folder name repeats the whole project path, too long under a pytest temp dir on Windows.
    folder = tmp_path / "t"
    monkeypatch.setattr(usage, "transcripts_dir", lambda root: folder)
    session = folder / "11111111-aaaa.jsonl"
    write_lines(session, [
        {"type": "user", "message": {"content": "/df-status"}, "timestamp": "2026-09-15T10:00:00Z"},
        assistant("m1", "2026-09-15T10:00:05Z", "claude-opus-5", read=20_000),
        assistant("m1", "2026-09-15T10:00:06Z", "claude-opus-5", read=20_000),  # same message, second content block
        assistant("m2", "2026-09-15T11:00:00Z", "claude-opus-5", read=90_000, output=500),
    ])
    agent = folder / "11111111-aaaa" / "subagents" / "agent-a1.jsonl"
    write_lines(agent, [
        {"type": "user", "message": {"content": [{"type": "text", "text": "## Context\nFeature F-002, task T-002.1 gold views"}]}},
        assistant("s1", "2026-09-15T10:30:00Z", "claude-sonnet-5", output=200),
    ])
    agent.with_suffix(".meta.json").write_text(json.dumps({"agentType": "data-engineer", "description": "Gold views"}), encoding="utf-8")
    other = folder / "11111111-aaaa" / "subagents" / "agent-a2.jsonl"
    write_lines(other, [
        {"type": "user", "message": {"content": "Write the requirements"}},
        assistant("s2", "2026-09-15T09:30:00Z", "claude-sonnet-5"),
    ])
    other.with_suffix(".meta.json").write_text(json.dumps({"agentType": "business-analyst", "description": "Requirements"}), encoding="utf-8")
    return project, folder


def test_the_project_folder_follows_the_claude_code_naming(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    project = tmp_path / "Client - Solutioning" / "DeltaForce AI"
    project.mkdir(parents=True)
    name = usage.transcripts_dir(project).name
    assert name.endswith("Client---Solutioning-DeltaForce-AI") and "\\" not in name and "/" not in name


def test_tokens_add_up_per_role_feature_phase_and_session(sessions):
    project, _ = sessions
    phases = [("2026-09-15T09:00:00Z", "discovery"), ("2026-09-15T10:15:00Z", "delivery")]
    result = usage.usage(project, phases, usage.TranscriptCache())

    assert result["available"] and result["currency"] is None
    assert result["total"]["calls"] == 4  # m1 counted once
    roles = {row["role"]: row for row in result["roles"]}
    assert roles["pm"]["calls"] == 2 and roles["pm"]["runs"] == 1
    assert roles["data-engineer"]["output_tokens"] == 200
    features = {row["feature"]: row for row in result["features"]}
    assert set(features) == {"coordination", "F-002", "unlinked"}
    assert features["F-002"]["runs"] == 1
    phases_seen = {row["phase"]: row["calls"] for row in result["phases"]}
    assert phases_seen == {"discovery": 2, "delivery": 2}
    session = result["sessions"][0]
    assert session["agents"] == 2 and session["pm_peak_context"] == 10 + 100 + 90_000
    assert session["start"] == "2026-09-15T09:30:00Z" and session["end"] == "2026-09-15T11:00:00Z"
    expected = 10 + 1.25 * 100 + 0.1 * 1000 + 5 * 200
    assert features["F-002"]["weighted"] == pytest.approx(expected)
    assert "Write the requirements" not in json.dumps(result)  # counts only, never prompts


def test_transcripts_are_read_incrementally(sessions):
    project, folder = sessions
    cache = usage.TranscriptCache()
    session = folder / "11111111-aaaa.jsonl"
    assert usage.usage(project, [], cache)["total"]["calls"] == 4
    with session.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(assistant("m3", "2026-09-15T12:00:00Z", "claude-opus-5")) + "\n")
        handle.write(json.dumps(assistant("m4", "2026-09-15T12:01:00Z", "claude-opus-5"))[:40])  # still being written
    assert usage.usage(project, [], cache)["total"]["calls"] == 5
    with session.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(assistant("m4", "2026-09-15T12:01:00Z", "claude-opus-5"))[40:] + "\n")
    assert usage.usage(project, [], cache)["total"]["calls"] == 6


def test_optional_prices_give_a_cost(sessions):
    project, _ = sessions
    (project / ".deltaforce").mkdir()
    (project / ".deltaforce" / "pricing.yaml").write_text(yaml.safe_dump({
        "currency": "EUR",
        "models": {"claude-sonnet": {"input": 1, "cache_write": 2, "cache_read": 0.5, "output": 10}},
    }), encoding="utf-8")
    result = usage.usage(project, [], usage.TranscriptCache())
    assert result["currency"] == "EUR"
    roles = {row["role"]: row for row in result["roles"]}
    assert roles["data-engineer"]["cost"] == pytest.approx((10 * 1 + 100 * 2 + 1000 * 0.5 + 200 * 10) / 1_000_000)
    assert roles["pm"]["cost"] is None  # no price for Opus in the file


def test_no_session_files_yet(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "empty"))
    assert usage.usage(tmp_path, [])["available"] is False


def test_usage_endpoint(sessions):
    project, _ = sessions
    httpd = server.MonitorServer(("127.0.0.1", 0), server.make_handler(project))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{httpd.server_address[1]}/api/usage", timeout=5) as response:
            data = json.loads(response.read())
        assert data["available"] and data["total"]["calls"] == 4
    finally:
        httpd.shutdown()
        httpd.server_close()
