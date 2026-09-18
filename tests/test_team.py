import copy
import json

import pytest
import yaml
from conftest import ROOT

from deltaforce import backlog, guardrails, team
from deltaforce import config as cfg
from deltaforce.paths import ProjectPaths

AI_DEV_KIT_TOOLS = set(guardrails.AI_DEV_KIT_TOOLS)


def split(document):
    assert document.startswith("---\n")
    header, body = document[4:].split("\n---\n", 1)
    frontmatter = yaml.safe_load(header)
    if "tools" in frontmatter:  # agents: comma-separated, as in the Claude Code subagent docs
        assert isinstance(frontmatter["tools"], str)
        frontmatter["tools"] = cfg.split_tools(frontmatter["tools"])
    return frontmatter, body


def test_agent_templates_use_the_subagent_format():
    for path in sorted(team.AGENT_TEMPLATES.glob("*.md")):
        frontmatter, body = cfg.read_agent_template(path.stem)
        assert set(frontmatter) <= {"name", "description", "tools", "model", "skills", "isolation", "color"}, path.name
        assert frontmatter["description"] and isinstance(frontmatter["tools"], str), path.name
        assert isinstance(frontmatter.get("skills", []), list), path.name  # skills must be a YAML list
        assert body.startswith("# DeltaForce — "), path.name
    assert cfg.split_tools("Agent(a, b), Read, mcp__x__y") == ["Agent(a, b)", "Read", "mcp__x__y"]


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
    assert frontmatter["skills"] == ["df-backlog", "df-handoff"]
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


def test_skill_references_are_installed_next_to_their_skill(example_config, tmp_path):
    """A skill loads its references by relative path: they must land in the project, not only in the framework."""
    paths = ProjectPaths(tmp_path)
    team.install_team(example_config, paths)

    standards = paths.skills / "df-engineering-standards"
    assert (standards / "SKILL.md").exists()
    installed = sorted(path.name for path in (standards / "references").glob("*.md"))
    expected = sorted(path.name for path in (team.SKILL_TEMPLATES / "df-engineering-standards" / "references").glob("*.md"))
    assert installed == expected and installed, installed
    assert (paths.skills / "df-bi" / "references" / "genie-space.md").exists()


@pytest.mark.parametrize(
    "files",
    [
        ["azure-devops/azure-pipelines.yml"],
        ["github/databricks-bundle.yml", "github/databricks-bundle/action.yml"],
    ],
)
def test_standard_cicd_templates_validate_on_prs_and_deploy_prod(files):
    texts = [(ROOT / "templates" / "cicd" / name).read_text(encoding="utf-8") for name in files]
    assert all(yaml.safe_load(part) for part in texts)
    text = "\n".join(texts)
    assert "databricks bundle validate -t prod" in text and "databricks bundle deploy -t prod" in text
    assert ".devops/" in texts[0]  # project pipelines live in .devops/ at the repository root
    assert "BUNDLE_VAR_catalog" in text and "DATABRICKS_CLIENT_SECRET" in text
    assert "dapi" not in text  # no token ever written in a template


def test_ml_and_genai_agents_list_their_hugging_face_skills(example_config):
    _, body = split(team.render_agent("data-scientist", example_config))
    assert "`huggingface-vision-trainer`" in body and "df-mlops" in body
    _, body = split(team.render_agent("ai-engineer", example_config))
    assert "`train-sentence-transformers`" in body and "df-aiops" in body


def test_hugging_face_skills_are_copied_recorded_and_retired(example_config, tmp_path):
    config = copy.deepcopy(example_config)
    config["team"]["roles"] = ["pm", "data-scientist", "ai-engineer"]
    wanted = cfg.huggingface_skills_for_roles(config["team"]["roles"])
    source = tmp_path / "hf"
    for name in [*wanted, "hf-cli"]:
        (source / "skills" / name / "references").mkdir(parents=True)
        (source / "skills" / name / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")
        (source / "skills" / name / "references" / "guide.md").write_text("guide\n", encoding="utf-8")
    paths = ProjectPaths(tmp_path / "project")
    retired = paths.skills / "huggingface-gradio"
    retired.mkdir(parents=True)
    (paths.skills / "my-own-skill").mkdir()
    paths.huggingface_skills_record.parent.mkdir(parents=True)
    paths.huggingface_skills_record.write_text(json.dumps({"skills": ["huggingface-gradio"]}), encoding="utf-8")

    assert team.install_huggingface_skills(config, paths, source, "https://example.com/skills.git", "abc1234") == wanted
    assert all((paths.skills / name / "references" / "guide.md").exists() for name in wanted)
    assert not retired.exists() and (paths.skills / "my-own-skill").exists() and not (paths.skills / "hf-cli").exists()
    record = json.loads(paths.huggingface_skills_record.read_text(encoding="utf-8"))
    assert record["commit"] == "abc1234" and record["skills"] == wanted

    (source / "skills" / "trl-training" / "SKILL.md").unlink()
    with pytest.raises(cfg.ConfigError, match="trl-training"):
        team.install_huggingface_skills(config, paths, source, "https://example.com/skills.git", "def5678")


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


def test_langchain_skills_come_from_their_own_folder_of_the_repository(example_config, tmp_path):
    """The LangChain repository keeps its skills under config/skills, not skills/ like the Hugging Face one."""
    config = copy.deepcopy(example_config)
    wanted = cfg.langchain_skills_for_roles(config["team"]["roles"])
    assert wanted, "the AI Engineer should have LangChain skills"

    source = tmp_path / "lc"
    for name in [*wanted, "langchain-typescript-quickstart"]:
        (source / "config" / "skills" / name).mkdir(parents=True)
        (source / "config" / "skills" / name / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")
    paths = ProjectPaths(tmp_path / "project")

    installed = team.install_external_skills("langchain", config, paths, source, "https://example.com/lc.git", "def5678")
    assert installed == wanted
    assert all((paths.skills / name / "SKILL.md").exists() for name in wanted)
    assert not (paths.skills / "langchain-typescript-quickstart").exists()  # only what the roles asked for
    record = json.loads(paths.langchain_skills_record.read_text(encoding="utf-8"))
    assert record["commit"] == "def5678" and record["repo"].endswith("lc.git")

    _, body = split(team.render_agent("ai-engineer", config))
    assert "`langchain-rag`" in body and "`langgraph-fundamentals`" in body


def test_a_missing_external_skill_stops_the_install(example_config, tmp_path):
    source = tmp_path / "lc"
    (source / "config" / "skills").mkdir(parents=True)
    with pytest.raises(cfg.ConfigError, match="LangChain skills not found"):
        team.install_external_skills("langchain", example_config, ProjectPaths(tmp_path / "p"), source, "repo", "c0ffee")
