import json
import shutil

import pytest

from deltaforce import backlog
from deltaforce import config as cfg
from deltaforce.paths import ProjectPaths

from conftest import ROOT


@pytest.fixture
def project(example_config, tmp_path):
    paths = ProjectPaths(tmp_path)
    cfg.write_config(paths.config, example_config)
    shutil.copyfile(ROOT / "templates" / "deltaforce" / "conventions.yaml", paths.conventions)
    shutil.copyfile(ROOT / "examples" / "state.example.yaml", paths.state_yaml)
    paths.backlog.mkdir()
    shutil.copyfile(ROOT / "examples" / "feature.example.md", paths.backlog / "F-001-silver-customer-dedup.md")
    return paths


def write_feature(paths, name, text):
    (paths.backlog / name).write_text(text, encoding="utf-8")


def test_examples_are_valid(project):
    assert backlog.validate_project(project) == []


def test_feature_problems_are_reported(project):
    write_feature(
        project,
        "F-002-gold-sales.md",
        "---\nid: F-002\ntitle: Gold sales\nstatus: todo\ndepends_on: [F-009]\nbranch: null\n"
        "tasks:\n  - {id: T-001.1, title: x, role: data-engineer, status: todo, branch: null}\n"
        "po_decision: null\ncreated: 2026-09-14T10:00:00Z\nupdated: 2026-09-14T10:00:00Z\n---\n",
    )
    write_feature(project, "notes.md", "# not a feature\n")
    problems = backlog.validate_project(project)
    assert any("depends on unknown feature F-009" in p for p in problems)
    assert any("task T-001.1 does not belong to F-002" in p for p in problems)
    assert any("notes.md: file name" in p for p in problems)


def test_invalid_status_and_missing_active_feature(project):
    text = (project.backlog / "F-001-silver-customer-dedup.md").read_text(encoding="utf-8")
    (project.backlog / "F-001-silver-customer-dedup.md").write_text(
        text.replace("status: in_test", "status: finished"), encoding="utf-8"
    )
    project.state_yaml.write_text(
        project.state_yaml.read_text(encoding="utf-8").replace("[F-001]", "[F-001, F-004]"), encoding="utf-8"
    )
    problems = backlog.validate_project(project)
    assert any("F-001-silver-customer-dedup.md: status" in p for p in problems)
    assert any("active feature F-004" in p for p in problems)


def test_append_event_and_validate_events(project):
    event = backlog.append_event(project, "feature_status_changed", "pm", "F-001", None, {"from": "in_test", "to": "awaiting_po"})
    assert event["ts"].endswith("Z")
    line = project.events.read_text(encoding="utf-8").splitlines()[0]
    assert json.loads(line)["event"] == "feature_status_changed"
    assert backlog.validate_project(project) == []

    with pytest.raises(cfg.ConfigError):
        backlog.append_event(project, "feature_status_changed", "wizard")

    with project.events.open("a", encoding="utf-8") as f:
        f.write("{not json}\n")
    assert any("events.jsonl line 2" in p for p in backlog.validate_project(project))


def test_derived_conventions_need_a_reference(project):
    project.conventions.write_text("version: 1\nsource: derived\n", encoding="utf-8")
    assert any("source_reference" in p for p in backlog.validate_project(project))
