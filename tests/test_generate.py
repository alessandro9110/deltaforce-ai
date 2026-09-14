import json

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
    assert settings["permissions"] == {"allow": ["Bash(ls)"]}
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
    assert ".deltaforce/.databrickscfg" in gitignore


def test_mcp_server_and_local_settings_share_the_project_profile(example_config, tmp_path):
    paths = ProjectPaths(tmp_path)
    generate.generate_all(example_config, paths)

    server = json.loads(read(paths.mcp_json))["mcpServers"]["databricks"]
    assert server["command"] == paths.venv_python.resolve().as_posix()
    assert server["args"] == [paths.mcp_entry.resolve().as_posix()]
    assert server["env"]["DATABRICKS_CONFIG_PROFILE"] == "deltaforce-customer-360"
    assert server["env"]["DATABRICKS_CONFIG_FILE"].endswith(".deltaforce/.databrickscfg")
    assert json.loads(read(paths.claude_settings_local))["env"] == server["env"]


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


def test_medallion_schemas_are_distinct():
    dev = {"catalog": "c", "medallion": {"layout": "multi_schema", "bronze": "raw", "silver": "clean", "gold": "raw"}}
    assert generate.medallion_schemas(dev) == ["raw", "clean"]
    assert generate.medallion_variables(dev)["prefix_bronze"] == ""
