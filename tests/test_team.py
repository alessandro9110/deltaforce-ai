import copy

import yaml

from deltaforce import backlog, guardrails, team
from deltaforce import config as cfg
from deltaforce.paths import ProjectPaths

AI_DEV_KIT_TOOLS = set(guardrails.AI_DEV_KIT_TOOLS)


def split(document):
    assert document.startswith("---\n")
    header, body = document[4:].split("\n---\n", 1)
    return yaml.safe_load(header), body


def test_role_catalog_is_consistent():
    roles = cfg.load_roles()
    skills = set(team.skill_template_names())
    for name, spec in roles.items():
        assert (team.AGENT_TEMPLATES / f"{name}.md").exists(), name
        assert set(spec["mcp"]) <= AI_DEV_KIT_TOOLS, name
        assert set(spec["process_skills"]) <= skills, name
        for delegate in spec["delegates"]:
            assert delegate in roles or delegate in team.BUILTIN_AGENTS, (name, delegate)


def test_every_agent_renders_without_placeholders(example_config):
    for role in cfg.load_roles():
        frontmatter, body = split(team.render_agent(role, example_config))
        assert frontmatter["name"] == role
        assert "{{" not in body, role
        assert frontmatter["model"] in {"opus", "sonnet"}


def test_pm_frontmatter(example_config):
    frontmatter, body = split(team.render_agent("pm", example_config))
    assert frontmatter["model"] == "opus"
    assert frontmatter["skills"] == ["df-backlog", "df-handoff", "df-git-flow"]
    agent_tool = next(tool for tool in frontmatter["tools"] if tool.startswith("Agent("))
    assert "devops-engineer" in agent_tool and "Explore" in agent_tool
    assert "mcp__databricks__get_current_user" in frontmatter["tools"]
    assert "`qa-engineer` — QA Engineer" in body


def test_production_read_tools_only_for_data_roles(example_config):
    assert set(guardrails.PROD_READ_TOOLS) <= AI_DEV_KIT_TOOLS
    config = copy.deepcopy(example_config)
    config["prod"] = {"host": "https://prod.cloud.databricks.com", "profile": "p-prod", "auth": "oauth", "warehouse_id": "w1"}
    for role, spec in cfg.load_roles().items():
        frontmatter, _ = split(team.render_agent(role, config))
        prod_tools = sorted(t.split("__")[-1] for t in frontmatter["tools"] if t.startswith("mcp__databricks-prod__"))
        assert prod_tools == (sorted(guardrails.PROD_READ_TOOLS) if spec.get("prod_read") else []), role

    frontmatter, _ = split(team.render_agent("data-analyst", example_config))
    assert not any(t.startswith("mcp__databricks-prod__") for t in frontmatter["tools"])


def test_disabled_roles_are_dropped_and_removed(example_config, tmp_path):
    config = copy.deepcopy(example_config)
    config["team"]["roles"] = ["pm", "data-engineer", "devops-engineer"]
    paths = ProjectPaths(tmp_path)
    paths.agents.mkdir(parents=True)
    (paths.agents / "data-analyst.md").write_text("old", encoding="utf-8")
    (paths.agents / "my-own-agent.md").write_text("mine", encoding="utf-8")

    team.install_team(config, paths)

    assert sorted(p.name for p in paths.agents.iterdir()) == [
        "data-engineer.md", "devops-engineer.md", "my-own-agent.md", "pm.md",
    ]
    frontmatter, _ = split((paths.agents / "pm.md").read_text(encoding="utf-8"))
    agent_tool = next(tool for tool in frontmatter["tools"] if tool.startswith("Agent("))
    assert agent_tool == "Agent(data-engineer, devops-engineer, Explore)"

    frontmatter, _ = split((paths.agents / "devops-engineer.md").read_text(encoding="utf-8"))
    assert not any(tool.startswith("Agent(") for tool in frontmatter["tools"])
    assert "isolation" not in frontmatter

    frontmatter, _ = split((paths.agents / "data-engineer.md").read_text(encoding="utf-8"))
    assert frontmatter["isolation"] == "worktree"
    assert "Agent(data-engineer)" in frontmatter["tools"]


def test_skills_are_refreshed_and_conventions_created_once(example_config, tmp_path):
    paths = ProjectPaths(tmp_path)
    stale = paths.skills / "df-retired"
    stale.mkdir(parents=True)
    (stale / "SKILL.md").write_text("---\nname: df-retired\n---\n", encoding="utf-8")
    databricks_skill = paths.skills / "databricks-core"
    databricks_skill.mkdir()

    team.install_team(example_config, paths)
    assert not stale.exists()
    assert databricks_skill.exists()
    for name in team.skill_template_names():
        frontmatter, _ = split((paths.skills / name / "SKILL.md").read_text(encoding="utf-8"))
        assert frontmatter["name"] == name

    assert backlog.validate_project(paths, include_config=False) == []
    paths.conventions.write_text("version: 1\nsource: po\ncustom: [Use notebooks]\n", encoding="utf-8")
    summary = team.install_team(example_config, paths)
    assert ".deltaforce/conventions.yaml" not in summary
    assert "Use notebooks" in paths.conventions.read_text(encoding="utf-8")
