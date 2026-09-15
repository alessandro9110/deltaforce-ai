import json

from deltaforce import backlog, environments
from deltaforce.paths import ProjectPaths


def test_installer_offers_only_environments_the_team_can_reach():
    declared = [
        {"name": "proto", "bundle_target": "proto", "catalogs": ["proto_lab"], "team": "deploy"},
        {"name": "qa", "workspace": "other", "bundle_target": "qa", "catalogs": ["qa"], "team": "deploy"},
        {"name": "uat", "bundle_target": "uat", "catalogs": ["uat"], "team": "read", "deployed_by": "cicd"},
        {"name": "lab", "team": "deploy"},
        {"name": "dev", "bundle_target": "dev", "catalogs": ["main"], "team": "deploy"},
        {"name": "prod", "workspace": "production", "team": "none", "deployed_by": "cicd"},
    ]
    candidates, notes = environments.deploy_candidates(declared, "dev")
    assert candidates == [{"name": "proto", "bundle_target": "proto", "catalogs": ["proto_lab"]}]
    assert [name for name, _ in notes] == ["qa", "uat", "lab", "dev", "prod"]
    assert "another workspace" in notes[0][1] and "only reads" in notes[1][1]


def test_declared_environments_reach_the_hook_and_pending_ones_are_reported(example_config, tmp_path):
    paths = ProjectPaths(tmp_path)
    paths.conventions.parent.mkdir(parents=True)
    paths.conventions.write_text(
        "version: 1\nsource: po\nenvironments:\n  - name: proto\n    bundle_target: proto\n    catalogs: [proto_lab]\n    team: deploy\n",
        encoding="utf-8",
    )
    assert environments.write_runtime(paths) == paths.declared_environments
    assert json.loads(paths.declared_environments.read_text(encoding="utf-8"))["environments"][0]["name"] == "proto"
    assert environments.pending(paths, example_config) == ["proto"]
    granted = {**example_config, "environments": [{"name": "proto", "bundle_target": "proto", "catalogs": ["proto_lab"]}]}
    assert environments.pending(paths, granted) == []

    paths.conventions.write_text("version: 1\nsource: po\nenvironments:\n  - name: proto\n    team: everything\n", encoding="utf-8")
    assert environments.write_runtime(paths) is None  # invalid conventions keep the previous copy
    assert "proto_lab" in paths.declared_environments.read_text(encoding="utf-8")


def test_production_environments_are_never_deployed_by_the_team():
    def errors(env):
        return backlog._schema_errors("conventions", {"version": 1, "source": "po", "environments": [env]}, "conventions.yaml")

    assert errors({"name": "prod", "workspace": "production", "team": "deploy"})
    assert errors({"name": "prod", "production": True, "team": "deploy"})
    assert not errors({"name": "prod", "workspace": "production", "team": "read", "deployed_by": "cicd"})
