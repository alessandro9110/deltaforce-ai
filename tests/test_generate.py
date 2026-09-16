import copy
import json

import pytest
import yaml

from deltaforce import generate
from deltaforce.paths import ProjectPaths


def read(path):
    return path.read_text(encoding="utf-8")


def test_generate_is_idempotent_and_preserves_user_content(example_config, tmp_path):
    paths = ProjectPaths(tmp_path)
    paths.claude_settings.parent.mkdir()
    paths.claude_settings.write_text(
        json.dumps({"permissions": {"allow": ["Bash(ls)"]}, "enabledMcpjsonServers": ["other"]}), encoding="utf-8"
    )
    paths.claude_md.write_text("# My project\n\nHand-written notes.\n", encoding="utf-8")
    paths.gitignore.write_text("node_modules/\n", encoding="utf-8")

    generate.generate_all(example_config, paths)
    generate.generate_all(example_config, paths)

    settings = json.loads(read(paths.claude_settings))
    assert settings["permissions"]["allow"] == ["Bash(ls)", generate.DF_HELPER_PERMISSION]
    assert "Read(**/.deltaforce/.databrickscfg)" in settings["permissions"]["deny"]
    assert "Read(**/.deltaforce/.databrickscfg.*)" in settings["permissions"]["deny"]
    assert "Edit(**/.claude/agents/**)" in settings["permissions"]["deny"]
    assert "Edit(**/.claude/skills/df-*/**)" in settings["permissions"]["deny"]
    assert "Edit(**/.claude/skills/huggingface-llm-trainer/**)" in settings["permissions"]["deny"]
    assert not any(rule.startswith("mcp__databricks-prod__") for rule in settings["permissions"]["deny"])
    assert settings["enabledMcpjsonServers"] == ["other", "databricks"]
    assert settings["worktree"] == {"baseRef": "head"}
    assert settings["env"]["CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH"] == "3"

    claude_md = read(paths.claude_md)
    assert claude_md.startswith("# My project\n\nHand-written notes.")
    assert claude_md.count(generate.CLAUDE_MD_START) == 1
    assert "`sandbox_dev`" in claude_md
    assert "`${var.schema_silver}`" in claude_md

    gitignore = read(paths.gitignore)
    assert gitignore.startswith("node_modules/\n")
    assert gitignore.count(generate.GITIGNORE_START) == 1
    assert ".deltaforce/.databrickscfg*" in gitignore


def test_new_bundle_declares_the_direct_engine_and_an_existing_one_is_left_alone(example_config, tmp_path):
    paths = ProjectPaths(tmp_path)
    generate.write_bundle(example_config, paths)

    bundle = yaml.safe_load(read(paths.bundle))
    # Genie spaces and the newer resource types deploy only with the direct engine.
    assert bundle["bundle"]["engine"] == "direct"
    assert example_config["targets"]["dev"].get("bundle_target", "dev") in bundle["targets"]

    own = "bundle:\n  name: client_platform\ntargets:\n  development: {}\n"
    paths.bundle.write_text(own, encoding="utf-8")
    generate.write_bundle(example_config, paths)
    assert read(paths.bundle) == own


def test_mcp_server_and_local_settings_share_the_project_profile(example_config, tmp_path):
    paths = ProjectPaths(tmp_path)
    generate.generate_all(example_config, paths)

    server = json.loads(read(paths.mcp_json))["mcpServers"]["databricks"]
    assert server["command"] == paths.venv_python.resolve().as_posix()
    assert server["args"] == [paths.mcp_entry.resolve().as_posix()]
    assert server["env"]["DATABRICKS_CONFIG_PROFILE"] == "deltaforce-customer-360"
    assert server["env"]["DATABRICKS_CONFIG_FILE"].endswith(".deltaforce/.databrickscfg")
    local_env = json.loads(read(paths.claude_settings_local))["env"]
    assert server["env"].items() <= local_env.items()
    assert local_env["DF_ROOT"] == tmp_path.resolve().as_posix()

    settings = json.loads(read(paths.claude_settings))
    assert settings["agent"] == "pm"
    assert generate.DF_HELPER_PERMISSION in settings["permissions"]["allow"]


def test_df_wrapper_is_lf_and_targets_the_project(example_config, tmp_path):
    paths = ProjectPaths(tmp_path)
    generate.generate_all(example_config, paths)
    raw = paths.df_wrapper.read_bytes()
    assert b"\r\n" not in raw
    script = raw.decode("utf-8")
    assert script.startswith("#!/usr/bin/env bash\n")
    assert "lib/py/dfcli.py" in script
    assert f"--target {tmp_path.resolve().as_posix()}" in script or f"--target '{tmp_path.resolve().as_posix()}'" in script


def test_bundle_is_created_once_and_prod_values_are_never_defaulted(example_config, tmp_path):
    paths = ProjectPaths(tmp_path)
    generate.generate_all(example_config, paths)
    paths.bundle.write_text("bundle:\n  name: customised\n", encoding="utf-8")
    generate.generate_all(example_config, paths)
    assert read(paths.bundle) == "bundle:\n  name: customised\n"

    document = yaml.safe_load(read(paths.bundle_variables))
    assert "default" not in document["variables"]["catalog"]
    assert document["variables"]["prefix_silver"]["default"] == "silver_"
    dev = document["targets"]["dev"]["variables"]
    assert dev["catalog"] == "sandbox_dev"
    assert dev["schema_bronze"] == dev["schema_gold"] == "customer_360"


@pytest.fixture
def prod_config(example_config):
    config = copy.deepcopy(example_config)
    config["prod"] = {
        "host": "https://prod.cloud.databricks.com",
        "profile": "deltaforce-customer-360-prod",
        "auth": "oauth",
        "warehouse_id": "prodwh01",
    }
    return config


def test_production_server_rules_hooks_and_policy(prod_config, tmp_path):
    paths = ProjectPaths(tmp_path)
    generate.generate_all(prod_config, paths)

    servers = json.loads(read(paths.mcp_json))["mcpServers"]
    assert servers["databricks-prod"]["env"]["DATABRICKS_CONFIG_PROFILE"] == "deltaforce-customer-360-prod"
    settings = json.loads(read(paths.claude_settings))
    assert settings["enabledMcpjsonServers"] == ["databricks", "databricks-prod"]
    assert settings["env"]["MCP_TIMEOUT"] == generate.MCP_STARTUP_TIMEOUT_MS
    deny = settings["permissions"]["deny"]
    assert "mcp__databricks-prod__execute_code" in deny
    assert "mcp__databricks-prod__execute_sql" not in deny

    hooks = json.loads(read(paths.claude_settings_local))["hooks"]
    pre = hooks["PreToolUse"][0]["hooks"][0]
    assert pre["command"] == paths.venv_python.resolve().as_posix()
    assert pre["args"][1:] == ["pre", paths.guard_policy.resolve().as_posix()]
    assert "async" not in pre  # the guard must block the tool call
    assert hooks["PostToolUse"][0]["hooks"][0]["async"] is True
    assert "async" not in hooks["SessionEnd"][0]["hooks"][0]
    assert hooks["UserPromptSubmit"][0]["hooks"][0]["async"] is True
    assert hooks["PreToolUse"][1]["matcher"] == "Agent|Task|AskUserQuestion"
    assert [group["hooks"][0]["args"][1] for group in hooks["PreToolUse"]] == ["pre", "activity"]

    policy = json.loads(read(paths.guard_policy))
    assert policy["project_root"] == tmp_path.resolve().as_posix() and policy["monitor_enabled"] is True
    assert policy["prod"]["enabled"] and policy["prod"]["profile"] == "deltaforce-customer-360-prod"
    assert "data-analyst" in policy["prod"]["read_roles"]
    assert "devops-engineer" not in policy["prod"]["read_roles"] and "pm" not in policy["prod"]["read_roles"]
    assert "Production (read-only)" in read(paths.claude_md)


def test_disabling_production_cleans_up_and_keeps_user_hooks(prod_config, tmp_path):
    paths = ProjectPaths(tmp_path)
    generate.generate_all(prod_config, paths)
    local = json.loads(read(paths.claude_settings_local))
    local["hooks"]["PreToolUse"].append({"matcher": "Bash", "hooks": [{"type": "command", "command": "my-hook"}]})
    paths.claude_settings_local.write_text(json.dumps(local), encoding="utf-8")

    plain = copy.deepcopy(prod_config)
    plain["prod"] = None
    generate.generate_all(plain, paths)
    generate.generate_all(plain, paths)

    assert "databricks-prod" not in json.loads(read(paths.mcp_json))["mcpServers"]
    settings = json.loads(read(paths.claude_settings))
    assert settings["enabledMcpjsonServers"] == ["databricks"]
    assert not any(rule.startswith("mcp__databricks-prod__") for rule in settings["permissions"]["deny"])
    pre_groups = json.loads(read(paths.claude_settings_local))["hooks"]["PreToolUse"]
    assert sum("deltaforce_hook.py" in json.dumps(group) for group in pre_groups) == 2  # guard and activity
    assert any("my-hook" in json.dumps(group) for group in pre_groups)
    assert json.loads(read(paths.guard_policy))["prod"]["enabled"] is False


def test_the_bundle_target_name_is_used_everywhere(example_config, tmp_path):
    config = copy.deepcopy(example_config)
    config["targets"]["dev"]["bundle_target"] = "development"
    paths = ProjectPaths(tmp_path)
    generate.generate_all(config, paths)

    assert list(yaml.safe_load(read(paths.bundle))["targets"]) == ["development", "prod"]
    assert list(yaml.safe_load(read(paths.bundle_variables))["targets"]) == ["development"]
    assert "always pass `-t development`" in read(paths.claude_md)
    assert json.loads(read(paths.guard_policy))["dev_target"] == "development"
    assert list(generate.existing_bundle_targets(paths)) == ["development", "prod"]


def test_environments_reach_the_policy_and_the_project_context(example_config, tmp_path):
    config = copy.deepcopy(example_config)
    config["environments"] = [{"name": "proto", "bundle_target": "proto", "catalogs": ["proto_lab"]}]
    paths = ProjectPaths(tmp_path)
    paths.conventions.parent.mkdir(parents=True)
    paths.conventions.write_text(
        "version: 1\nsource: po\nenvironments:\n"
        "  - name: proto\n    bundle_target: proto\n    catalogs: [proto_lab]\n    team: deploy\n"
        "  - name: prod\n    workspace: production\n    team: read\n    deployed_by: cicd\n",
        encoding="utf-8",
    )
    generate.generate_all(config, paths)

    policy = json.loads(read(paths.guard_policy))
    assert policy["environments"] == config["environments"]
    assert policy["environments_file"] == paths.declared_environments.resolve().as_posix()
    assert [env["name"] for env in json.loads(read(paths.declared_environments))["environments"]] == ["proto", "prod"]
    claude_md = read(paths.claude_md)
    assert "`proto` — target `proto`, catalogs `proto_lab`" in claude_md
    assert "always pass `-t dev`, or `-t <target>` of an environment below" in claude_md


def test_existing_bundle_variables_are_not_redefined(example_config, tmp_path):
    paths = ProjectPaths(tmp_path)
    paths.bundle.write_text("bundle:\n  name: sales\ninclude:\n  - resources/*.yml\n  - conf/*.yml\nvariables:\n  catalog:\n    description: own\n", encoding="utf-8")
    (tmp_path / "resources").mkdir()
    (tmp_path / "resources" / "sales.job.yml").write_text("resources: {}\n", encoding="utf-8")
    (tmp_path / "conf").mkdir()
    (tmp_path / "conf" / "vars.yml").write_text("variables:\n  warehouse_id:\n    description: own\n", encoding="utf-8")

    generate.generate_all(example_config, paths)
    generate.generate_all(example_config, paths)  # the generated file itself never counts as the project's

    text = read(paths.bundle_variables)
    document = yaml.safe_load(text)
    assert "catalog" not in document["variables"] and "warehouse_id" not in document["variables"]
    assert "schema_bronze" in document["variables"]
    assert set(document["targets"]["dev"]["variables"]) == {"schema_bronze", "schema_silver", "schema_gold"}
    assert "already defines them: catalog, warehouse_id" in text
    assert read(paths.bundle).startswith("bundle:")  # an existing bundle is never rewritten


def test_status_line_links_the_monitor_and_keeps_a_users_own(example_config, tmp_path):
    paths = ProjectPaths(tmp_path)
    generate.generate_all(example_config, paths)
    line = json.loads(read(paths.claude_settings_local))["statusLine"]
    assert line["type"] == "command" and line["refreshInterval"] == generate.STATUSLINE_REFRESH_SECONDS
    assert line["command"].startswith(". ") and "statusline.sh" in line["command"]
    assert f'"{tmp_path.resolve().as_posix()}"' in line["command"]

    local = json.loads(read(paths.claude_settings_local))
    local["statusLine"] = {"type": "command", "command": "my-status-line"}
    paths.claude_settings_local.write_text(json.dumps(local), encoding="utf-8")
    generate.generate_all(example_config, paths)
    assert json.loads(read(paths.claude_settings_local))["statusLine"]["command"] == "my-status-line"


def test_medallion_schemas_are_distinct():
    dev = {"catalog": "c", "medallion": {"layout": "multi_schema", "bronze": "raw", "silver": "clean", "gold": "raw"}}
    assert generate.medallion_schemas(dev) == ["raw", "clean"]
    assert generate.medallion_variables(dev)["prefix_bronze"] == ""
