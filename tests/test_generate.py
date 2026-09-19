import copy
import json

import pytest
import yaml

from deltaforce import generate
from deltaforce import guardrails
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
    # The script finds the project from its own location: no path of the installing machine may appear in it.
    assert '--target "$root"' in script
    assert tmp_path.resolve().as_posix() not in script


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

    # The registration is committed and written through ${CLAUDE_PROJECT_DIR}: no path of the installing machine.
    hooks = settings["hooks"]
    assert "hooks" not in json.loads(read(paths.claude_settings_local))
    pre = hooks["PreToolUse"][0]["hooks"][0]
    assert pre["command"] == "${CLAUDE_PROJECT_DIR}/.deltaforce/runtime/venv/Scripts/python.exe"
    assert pre["args"][1:] == ["pre", "${CLAUDE_PROJECT_DIR}/.deltaforce/runtime/guard-policy.json"]
    assert tmp_path.name not in json.dumps(hooks)
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
    settings = json.loads(read(paths.claude_settings))
    settings["hooks"]["PreToolUse"].append({"matcher": "Bash", "hooks": [{"type": "command", "command": "my-hook"}]})
    paths.claude_settings.write_text(json.dumps(settings), encoding="utf-8")

    plain = copy.deepcopy(prod_config)
    plain["prod"] = None
    generate.generate_all(plain, paths)
    generate.generate_all(plain, paths)

    assert "databricks-prod" not in json.loads(read(paths.mcp_json))["mcpServers"]
    settings = json.loads(read(paths.claude_settings))
    assert settings["enabledMcpjsonServers"] == ["databricks"]
    assert not any(rule.startswith("mcp__databricks-prod__") for rule in settings["permissions"]["deny"])
    pre_groups = settings["hooks"]["PreToolUse"]
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


def test_table_prefixes_can_be_configured_and_emptied():
    """One schema without prefixes is a real client layout; the defaults stay `bronze_`, `silver_`, `gold_`."""
    default = {"catalog": "c", "medallion": {"layout": "single_schema", "schema": "dev"}}
    assert generate.medallion_variables(default)["prefix_gold"] == "gold_"

    without = {"catalog": "c", "medallion": {"layout": "single_schema", "schema": "dev", "prefixes": {"bronze": "", "silver": "", "gold": ""}}}
    variables = generate.medallion_variables(without)
    assert [variables[f"prefix_{layer}"] for layer in ("bronze", "silver", "gold")] == ["", "", ""]
    assert variables["schema_gold"] == "dev"

    named = {"catalog": "c", "medallion": {"layout": "single_schema", "schema": "dev", "prefixes": {"bronze": "raw_", "silver": "cln_", "gold": "biz_"}}}
    assert generate.medallion_variables(named)["prefix_silver"] == "cln_"


def test_the_project_context_block_states_the_prefixes_in_use(example_config):
    example_config["targets"]["dev"]["medallion"] = {"layout": "single_schema", "schema": "dev", "prefixes": {"bronze": "", "silver": "", "gold": ""}}
    assert "without a layer prefix" in generate.render_project_context(example_config)

    example_config["targets"]["dev"]["medallion"]["prefixes"] = {"bronze": "raw_", "silver": "silver_", "gold": "gold_"}
    assert "`raw_`, `silver_`, `gold_`" in generate.render_project_context(example_config)


def test_the_values_of_the_projects_own_bundle_are_read_back(tmp_path):
    """An existing project already names its catalog and schemas: those values are the defaults and the doctor's truth."""
    paths = ProjectPaths(tmp_path)
    (tmp_path / "resources").mkdir(parents=True)
    paths.bundle.write_text(
        "bundle:\n  name: client\ninclude:\n  - resources/*.yml\n"
        "variables:\n  catalog:\n    default: main\n  schema_gold:\n    default: gold\n"
        "targets:\n  development:\n    variables:\n      catalog: dev_main\n",
        encoding="utf-8",
    )
    (tmp_path / "resources" / "more.yml").write_text(
        "variables:\n  warehouse_id:\n    default: abc123\n  unused:\n    description: no default\n", encoding="utf-8"
    )

    values = generate.existing_bundle_variable_values(paths)
    assert values == {"catalog": "main", "schema_gold": "gold", "warehouse_id": "abc123"}
    assert generate.existing_bundle_variable_values(paths, "development")["catalog"] == "dev_main"
    assert generate.existing_bundle_variable_values(paths, "unknown")["catalog"] == "main"


def _doctor_with(config, tmp_path):
    from deltaforce import doctor as doctor_module

    paths = ProjectPaths(tmp_path)
    checker = doctor_module.Doctor(paths)
    checker.config = config
    checker.check_bundle_alignment()
    return {check.id: check for check in checker.checks}


def test_the_doctor_reports_a_configuration_that_disagrees_with_the_bundle(example_config, tmp_path):
    """The typo that survived a whole install: config said `goald`, the project's bundle said `gold`."""
    paths = ProjectPaths(tmp_path)
    paths.bundle.write_text(
        "bundle:\n  name: client\nvariables:\n  catalog:\n    default: main\n"
        "  schema_gold:\n    default: gold\n  schema_silver:\n    default: silver\n  schema_bronze:\n    default: bronze\n",
        encoding="utf-8",
    )
    config = copy.deepcopy(example_config)
    config["targets"]["dev"]["catalog"] = "main"
    config["targets"]["dev"]["medallion"] = {"layout": "multi_schema", "bronze": "bronze", "silver": "silver", "gold": "goald"}

    check = _doctor_with(config, tmp_path)["bundle-alignment"]
    assert not check.ok and "schema_gold: config 'goald' vs bundle 'gold'" in check.detail

    config["targets"]["dev"]["medallion"]["gold"] = "gold"
    assert _doctor_with(config, tmp_path)["bundle-alignment"].ok


def test_the_doctor_says_nothing_when_the_project_has_no_bundle_of_its_own(example_config, tmp_path):
    assert "bundle-alignment" not in _doctor_with(copy.deepcopy(example_config), tmp_path)


def test_an_installed_project_carries_no_path_of_the_machine(example_config, tmp_path, monkeypatch):
    """A real install keeps the framework under the project: registration and CLI must then be fully portable."""
    framework = tmp_path / ".deltaforce" / "framework"
    (framework / "lib" / "hooks").mkdir(parents=True)
    (framework / "lib" / "py").mkdir(parents=True)
    monkeypatch.setattr(generate, "FRAMEWORK_DIR", framework)
    monkeypatch.setattr(guardrails, "HOOK_SCRIPT", framework / "lib" / "hooks" / "deltaforce_hook.py")

    paths = ProjectPaths(tmp_path)
    generate.generate_all(example_config, paths)

    machine = tmp_path.resolve().as_posix()
    hooks = json.dumps(json.loads(read(paths.claude_settings))["hooks"])
    assert machine not in hooks and "${CLAUDE_PROJECT_DIR}/.deltaforce/framework" in hooks
    assert machine not in paths.df_wrapper.read_text(encoding="utf-8")


def test_hooks_registered_by_an_older_install_are_moved_out_of_the_local_settings(example_config, tmp_path):
    paths = ProjectPaths(tmp_path)
    generate.generate_all(example_config, paths)
    # What an install before the move left behind, next to a hook of the user's own.
    old = json.loads(read(paths.claude_settings_local))
    old["hooks"] = {
        "PreToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "python", "args": ["deltaforce_hook.py", "pre"]}]},
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "my-hook"}]},
        ]
    }
    paths.claude_settings_local.write_text(json.dumps(old), encoding="utf-8")

    generate.generate_all(example_config, paths)

    local = json.loads(read(paths.claude_settings_local))
    assert "deltaforce_hook.py" not in json.dumps(local.get("hooks", {}))
    assert "my-hook" in json.dumps(local["hooks"])
    assert guardrails.hooks_registered(json.loads(read(paths.claude_settings)))
