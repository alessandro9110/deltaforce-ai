import json
import shlex

import pytest

from deltaforce import config as cfg


def answers(**overrides):
    values = {
        "DF_PROJECT_NAME": "customer-360",
        "DF_DEV_BRANCH": "dev",
        "DF_PROTECTED_BRANCHES": "main, master",
        "DF_GIT_PROVIDER": "azure-devops",
        "DF_CICD": "azure-devops",
        "DF_DB_HOST": "https://adb-1234567890123456.7.azuredatabricks.net/",
        "DF_DB_PROFILE": "deltaforce-customer-360",
        "DF_DB_AUTH": "oauth",
        "DF_WAREHOUSE_ID": "1234abcd5678efgh",
        "DF_COMPUTE": "serverless",
        "DF_CATALOG": "sandbox_dev",
        "DF_MEDALLION_LAYOUT": "single_schema",
        "DF_SCHEMA": "customer_360",
    }
    values.update(overrides)
    return values


def test_example_config_is_valid(example_config):
    cfg.validate(example_config)


def test_schema_roles_match_roles_catalog():
    schema = json.loads(cfg.SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["$defs"]["role"]["enum"] == list(cfg.load_roles())


def test_build_from_env_applies_defaults(example_config):
    data = cfg.build_from_env(answers())
    cfg.validate(data)
    assert data == example_config


def test_multi_schema_layout():
    data = cfg.build_from_env(
        answers(DF_MEDALLION_LAYOUT="multi_schema", DF_SCHEMA="", DF_SCHEMA_BRONZE="b", DF_SCHEMA_SILVER="s", DF_SCHEMA_GOLD="g")
    )
    cfg.validate(data)
    assert data["targets"]["dev"]["medallion"] == {"layout": "multi_schema", "bronze": "b", "silver": "s", "gold": "g"}


def test_cluster_compute_keeps_cluster_id():
    data = cfg.build_from_env(answers(DF_COMPUTE="cluster", DF_CLUSTER_ID="0123-456789-abcdef"))
    cfg.validate(data)
    assert data["databricks"]["cluster_id"] == "0123-456789-abcdef"


@pytest.mark.parametrize(
    "overrides",
    [
        {"DF_DB_PROFILE": "DEFAULT"},
        {"DF_DB_HOST": "http://insecure.example.com"},
        {"DF_COMPUTE": "cluster"},
        {"DF_MEDALLION_LAYOUT": "multi_schema"},
        {"DF_ROLES": "data-engineer"},
        {"DF_ROLES": "pm,wizard"},
        {"DF_MAX_SPAWN_DEPTH": "9"},
    ],
)
def test_invalid_answers_are_rejected(overrides):
    with pytest.raises(cfg.ConfigError):
        cfg.validate(cfg.build_from_env(answers(**overrides)))


def test_export_env_round_trips(example_config):
    env = {"DF_GIT_PROVIDER": example_config["project"]["git_provider"]}
    for line in cfg.export_env(example_config).splitlines():
        guard, assignment = line.split(" || ", 1)
        key, value = assignment.split("=", 1)
        assert guard == f'[ -n "${{{key}-}}" ]'
        env[key] = shlex.split(value)[0]
    assert cfg.build_from_env(env) == example_config


def parse_exports(text):
    env = {}
    for line in text.splitlines():
        _, assignment = line.split(" || ", 1)
        key, value = assignment.split("=", 1)
        env[key] = shlex.split(value)[0]
    return env


PROD_ANSWERS = {
    "DF_PROD_ENABLED": "true",
    "DF_PROD_HOST": "https://dbc-prod.cloud.databricks.com/",
    "DF_PROD_PROFILE": "deltaforce-customer-360-prod",
    "DF_PROD_WAREHOUSE_ID": "prodwh01",
}


def test_production_workspace_round_trips():
    data = cfg.build_from_env(answers(**PROD_ANSWERS))
    cfg.validate(data)
    assert data["prod"] == {
        "host": "https://dbc-prod.cloud.databricks.com",
        "profile": "deltaforce-customer-360-prod",
        "auth": "oauth",
        "warehouse_id": "prodwh01",
    }
    env = parse_exports(cfg.export_env(data))
    env["DF_GIT_PROVIDER"] = data["project"]["git_provider"]
    assert cfg.build_from_env(env) == data


@pytest.mark.parametrize(
    "overrides",
    [
        {"DF_PROD_PROFILE": "deltaforce-customer-360"},
        {"DF_PROD_HOST": "https://adb-1234567890123456.7.azuredatabricks.net"},
        {"DF_PROD_WAREHOUSE_ID": ""},
        {"DF_PROD_PROFILE": "DEFAULT"},
    ],
)
def test_invalid_production_settings_are_rejected(overrides):
    with pytest.raises(cfg.ConfigError):
        cfg.validate(cfg.build_from_env(answers(**{**PROD_ANSWERS, **overrides})))


def test_skills_union_is_ordered_and_deduplicated():
    skills = cfg.skills_for_roles(["pm", "data-engineer", "devops-engineer"])
    assert skills[0] == "databricks-core"
    assert len(skills) == len(set(skills))
    assert {"databricks-pipelines", "databricks-dabs", "databricks-jobs"} <= set(skills)
