import importlib.util
import json
import subprocess
import sys

import pytest

from conftest import ROOT

HOOK_PATH = ROOT / "lib" / "hooks" / "deltaforce_hook.py"
_spec = importlib.util.spec_from_file_location("deltaforce_hook", HOOK_PATH)
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)

PROD_SQL = "mcp__databricks-prod__execute_sql"
DEV_SQL = "mcp__databricks__execute_sql"
CLI = '"$DF_ROOT/.deltaforce/bin/databricks"'


@pytest.fixture
def policy(tmp_path):
    return {
        "version": 1,
        "dev_server": "databricks",
        "dev_catalog": "main",
        "dev_target": "dev",
        "dev_branch": "dev",
        "protected_branches": ["main", "master"],
        "integration_branch": "df/integration",
        "deployer_role": "devops-engineer",
        "main_role": "pm",
        "prod": {
            "enabled": True,
            "server": "databricks-prod",
            "host": "https://prod.cloud.databricks.com",
            "profile": "sandbox-prod",
            "read_roles": ["data-analyst", "data-engineer", "qa-engineer"],
            "allowed_tools": [
                "ask_genie", "execute_sql", "execute_sql_multi", "get_current_user", "get_table_stats_and_schema",
                "get_volume_folder_details", "manage_serving_endpoint", "query_vs_index",
            ],
        },
        "installer_files": [
            ".claude/settings.json", ".claude/settings.local.json", ".mcp.json", ".deltaforce/config.yaml",
            ".deltaforce/runtime/guard-policy.json",
        ],
        "secret_file": ".deltaforce/.databrickscfg",
        "audit_file": str(tmp_path / "audit.jsonl"),
        "activity_file": str(tmp_path / "activity.jsonl"),
    }


def decide(policy, tool, tool_input, role="data-analyst", cwd="."):
    event = {"tool_name": tool, "tool_input": tool_input, "cwd": cwd}
    if role:
        event["agent_type"] = role
    return hook.decide_pre(event, policy)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM a.b.c",
        "with x as (select 1) select * from x",
        "SHOW TABLES IN a.b",
        "DESCRIBE TABLE a.b.c",
        "EXPLAIN SELECT 1",
        "SELECT 'DROP TABLE x; DELETE FROM y' AS text",
        "SELECT 1; -- DELETE FROM x\nSELECT 2",
        "select created_at, last_update from a.b.c",
        "SELECT ai_query('endpoint', text) FROM a.b.c",
    ],
)
def test_read_only_sql(sql):
    assert hook.is_read_only(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE a.b.c",
        "SELECT 1; DROP TABLE a.b.c",
        "WITH x AS (SELECT 1) INSERT INTO a.b.c SELECT * FROM x",
        "CREATE OR REPLACE TABLE a.b.c AS SELECT 1",
        "/* note */ MERGE INTO a.b.c USING d ON true WHEN MATCHED THEN DELETE",
        "OPTIMIZE a.b.c",
        "EXECUTE IMMEDIATE 'DROP TABLE x'",
        "GRANT SELECT ON TABLE a.b.c TO `someone`",
        "COPY INTO a.b.c FROM '/Volumes/x'",
    ],
)
def test_write_sql(sql):
    assert not hook.is_read_only(sql)


def test_production_allows_only_reads_for_reader_roles(policy):
    assert decide(policy, PROD_SQL, {"sql_query": "SELECT count(*) FROM sales.gold.orders"}) is None
    assert "read-only" in decide(policy, PROD_SQL, {"sql_query": "DELETE FROM sales.gold.orders"})
    assert "read-only" in decide(policy, "mcp__databricks-prod__execute_sql_multi", {"sql_content": "SELECT 1; DROP TABLE a.b.c"})
    assert decide(policy, "mcp__databricks-prod__manage_serving_endpoint", {"action": "query", "name": "m"}) is None
    assert decide(policy, "mcp__databricks-prod__query_vs_index", {"index_name": "a.b.i", "columns": ["x"]}) is None
    assert "not allowed on production" in decide(policy, "mcp__databricks-prod__execute_code", {"code": "print(1)"})
    assert "not allowed on production" in decide(policy, "mcp__databricks-prod__manage_uc_objects", {"action": "list"})
    assert "may not access" in decide(policy, PROD_SQL, {"sql_query": "SELECT 1"}, role="devops-engineer")
    assert "may not access" in decide(policy, PROD_SQL, {"sql_query": "SELECT 1"}, role=None)  # main session: pm


def test_production_disabled_blocks_prod_tools(policy):
    policy["prod"]["enabled"] = False
    assert "no production workspace" in decide(policy, PROD_SQL, {"sql_query": "SELECT 1"})


def test_dev_writes_stay_in_the_dev_catalog(policy):
    assert decide(policy, DEV_SQL, {"sql_query": "CREATE TABLE main.bronze.trips AS SELECT 1"}) is None
    assert decide(policy, DEV_SQL, {"sql_query": "CREATE TABLE bronze.trips AS SELECT 1", "catalog": "main"}) is None
    assert decide(policy, DEV_SQL, {"sql_query": "SELECT * FROM samples.nyctaxi.trips"}) is None
    assert "only in the dev catalog" in decide(policy, DEV_SQL, {"sql_query": "INSERT INTO samples.x.y SELECT 1"})
    assert "qualify SQL writes" in decide(policy, DEV_SQL, {"sql_query": "DROP TABLE bronze.trips"})
    assert decide(policy, "mcp__databricks__manage_uc_objects", {"action": "list", "catalog_name": "samples"}) is None
    assert "need a person" in decide(policy, "mcp__databricks__manage_uc_grants", {"action": "grant", "full_name": "main.bronze"})
    assert "only in the dev catalog" in decide(
        policy, "mcp__databricks__manage_volume_files", {"action": "upload", "volume_path": "/Volumes/other/raw/files/a.csv"}
    )
    assert decide(policy, "mcp__databricks__manage_volume_files", {"action": "upload", "volume_path": "/Volumes/main/bronze/raw/a.csv"}) is None


def test_databricks_resources_only_through_the_bundle(policy):
    for tool, tool_input in [
        ("manage_jobs", {"action": "create", "name": "trips"}),
        ("manage_pipeline", {"action": "create_or_update", "name": "trips"}),
        ("manage_dashboard", {"action": "create", "display_name": "KPIs"}),
        ("manage_vs_index", {"action": "create", "index_name": "main.gold.docs_index"}),
        ("manage_uc_objects", {"action": "create", "object_type": "schema", "full_name": "main.bronze"}),
        ("manage_app", {"action": "deploy", "name": "kpi-app"}),
        ("manage_workspace_files", {"action": "upload", "path": "/Workspace/Shared/x.py"}),
        ("manage_jobs", {"name": "no action given"}),
        ("delete_tracked_resource", {"resource_id": "123"}),
    ]:
        reason = decide(policy, f"mcp__databricks__{tool}", tool_input, role="devops-engineer")
        assert reason and "asset bundle" in reason, tool
    assert decide(policy, "mcp__databricks__manage_jobs", {"action": "list"}) is None
    assert decide(policy, "mcp__databricks__manage_job_runs", {"action": "run_now", "job_id": 1}) is None
    assert decide(policy, "mcp__databricks__manage_serving_endpoint", {"action": "query", "name": "m"}) is None


def test_bundle_rules(policy):
    assert decide(policy, "Bash", {"command": f"{CLI} bundle deploy -t dev"}, role="devops-engineer") is None
    assert decide(policy, "Bash", {"command": f"{CLI} bundle run -t dev trips_pipeline"}, role="devops-engineer") is None
    assert decide(policy, "Bash", {"command": f"{CLI} bundle validate -t dev"}, role="data-engineer") is None
    assert "only the devops-engineer" in decide(policy, "Bash", {"command": f"{CLI} bundle deploy -t dev"}, role="data-engineer")
    assert "only to the 'dev' target" in decide(policy, "Bash", {"command": f"{CLI} bundle deploy --target=prod"}, role="devops-engineer")
    assert "destroy" in decide(policy, "Bash", {"command": "databricks bundle destroy -t dev"}, role="devops-engineer")


def test_cli_may_not_target_production(policy):
    assert "may not target production" in decide(policy, "Bash", {"command": "databricks catalogs list -p sandbox-prod"})
    assert "may not target production" in decide(
        policy, "Bash", {"command": "DATABRICKS_CONFIG_PROFILE=sandbox-prod databricks tables list a b"}
    )
    assert "may not target production" in decide(
        policy, "Bash", {"command": "export DATABRICKS_HOST=https://prod.cloud.databricks.com && databricks jobs list"}
    )
    assert decide(policy, "Bash", {"command": "databricks catalogs list"}) is None


def test_git_rules(policy):
    assert "protected branch 'main'" in decide(policy, "Bash", {"command": "git push origin main"}, role="devops-engineer")
    assert "force" in decide(policy, "Bash", {"command": "git push --force origin df/F-001"})
    assert "force" in decide(policy, "Bash", {"command": "git push origin +df/F-001"})
    assert "deletions" in decide(policy, "Bash", {"command": "git push origin :df/F-001"})
    assert decide(policy, "Bash", {"command": "git push -u origin df/F-001-data-engineer-T1"}, role="data-engineer") is None
    assert "only the devops-engineer pushes" in decide(policy, "Bash", {"command": "git push origin dev"}, role="data-engineer")
    assert decide(policy, "Bash", {"command": "git push origin dev"}, role="devops-engineer") is None
    assert "never pushed" in decide(policy, "Bash", {"command": "git push origin df/integration"}, role="devops-engineer")
    assert "reset --hard" in decide(policy, "Bash", {"command": "git reset --hard HEAD~1"})
    assert decide(policy, "Bash", {"command": "git switch -C df/integration dev"}, role="devops-engineer") is None
    assert "resetting branch 'dev'" in decide(policy, "Bash", {"command": "git switch -C dev"}, role="devops-engineer")
    assert "protected branch 'main'" in decide(policy, "Bash", {"command": "cd repo && git push origin main"})
    assert "protected branch 'main'" in decide(policy, "Bash", {"command": 'bash -c "git push origin main"'})


def test_commit_and_upstream_push_use_the_current_branch(policy, tmp_path):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "--allow-empty", "-m", "init"],
        check=True,
    )
    assert "protected branch 'main'" in decide(policy, "Bash", {"command": "git commit -m x"}, "pm", str(repo))
    assert "protected branch 'main'" in decide(policy, "Bash", {"command": "git push origin"}, "devops-engineer", str(repo))
    subprocess.run(["git", "-C", str(repo), "switch", "-q", "-c", "dev"], check=True)
    assert decide(policy, "Bash", {"command": "git commit -m x"}, "pm", str(repo)) is None
    assert "only the devops-engineer merges" in decide(policy, "Bash", {"command": "git merge df/F-001"}, "pm", str(repo))


def test_protected_files(policy):
    assert "credentials" in decide(policy, "Read", {"file_path": "C:/p/.deltaforce/.databrickscfg"})
    assert "credentials" in decide(policy, "Bash", {"command": "cat .deltaforce/.databrickscfg"})
    assert "managed by the DeltaForce installer" in decide(policy, "Edit", {"file_path": "C:\\p\\.claude\\settings.local.json"})
    assert "managed by the DeltaForce installer" in decide(policy, "Bash", {"command": "sed -i s/a/b/ .claude/settings.json"})
    assert decide(policy, "Bash", {"command": "cat .claude/settings.json"}) is None
    assert decide(policy, "Write", {"file_path": "C:/p/src/pipelines/silver/trips.py"}) is None
    assert decide(policy, "Read", {"file_path": "C:/p/CLAUDE.md"}) is None


def run_hook(mode, policy_path, event):
    return subprocess.run(
        [sys.executable, str(HOOK_PATH), mode, str(policy_path)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )


def test_main_denies_with_json_and_audits(policy, tmp_path):
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    event = {"tool_name": PROD_SQL, "tool_input": {"sql_query": "DELETE FROM a.b.c"}, "agent_type": "data-analyst", "session_id": "s1"}

    decision = json.loads(run_hook("pre", policy_path, event).stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert decision["permissionDecisionReason"].startswith("DeltaForce guardrail: ")

    allowed = {**event, "tool_input": {"sql_query": "SELECT 1"}}
    assert run_hook("pre", policy_path, allowed).stdout.strip() == ""
    run_hook("post", policy_path, allowed)
    run_hook("subagent-start", policy_path, {"agent_type": "data-analyst", "agent_id": "a1", "session_id": "s1"})
    run_hook("session-end", policy_path, {"session_id": "s1", "reason": "logout"})

    records = [json.loads(line) for line in (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["decision"] for r in records] == ["denied", "allowed"]
    assert records[0]["workspace"] == "prod" and records[0]["role"] == "data-analyst"
    activity = [json.loads(line) for line in (tmp_path / "activity.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [a["event"] for a in activity] == ["tool_used", "agent_started", "session_ended"]
    assert activity[-1]["reason"] == "logout" and activity[-1]["role"] == "pm"


def test_missing_policy_fails_closed_on_production(tmp_path):
    missing = tmp_path / "missing.json"
    prod = run_hook("pre", missing, {"tool_name": PROD_SQL, "tool_input": {"sql_query": "SELECT 1"}})
    assert "deny" in prod.stdout
    dev = run_hook("pre", missing, {"tool_name": DEV_SQL, "tool_input": {"sql_query": "DROP TABLE a.b.c"}})
    assert dev.stdout.strip() == ""
