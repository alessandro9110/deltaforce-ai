"""Structure of the DeltaForce skills and agent templates.

These checks are cheap and catch what review misses: a skill added without being wired in,
a PO command the model could invoke by itself, a preloaded skill growing past its token budget,
a reference to a skill that does not exist.
"""

import re
from pathlib import Path

import pytest
import yaml

from deltaforce import generate
from deltaforce.paths import ProjectPaths

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "templates" / "claude" / "skills"
AGENTS = ROOT / "templates" / "claude" / "agents"

# Commands the Product Owner types. They must never be invoked by the model on its own.
PO_COMMANDS = {"df-prepare", "df-kickoff", "df-status", "df-approve", "df-changes", "df-conventions"}
# Every preloaded skill sits in the context of every call of that agent (design §6, "Token use").
PRELOADED_MAX_LINES = 200
SKILL_REFERENCE = re.compile(r"\bdf-[a-z]+(?:-[a-z]+)*\b")


def frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path} has no frontmatter"
    return yaml.safe_load(text.split("---\n", 2)[1])


def skill_names() -> set[str]:
    return {path.parent.name for path in SKILLS.glob("*/SKILL.md")}


def test_every_skill_declares_its_own_name_and_a_trigger_description():
    for name in sorted(skill_names()):
        meta = frontmatter(SKILLS / name / "SKILL.md")
        assert meta.get("name") == name, f"{name}: frontmatter name is {meta.get('name')!r}"
        description = meta.get("description") or ""
        # The description is what makes the model load the skill at the right moment.
        assert len(description) > 40, f"{name}: description too short to trigger on"


def test_po_commands_are_the_only_skills_the_model_cannot_invoke():
    for name in sorted(skill_names()):
        meta = frontmatter(SKILLS / name / "SKILL.md")
        disabled = meta.get("disable-model-invocation") is True
        assert disabled == (name in PO_COMMANDS), f"{name}: disable-model-invocation is {disabled}"


def test_preloaded_skills_stay_within_their_token_budget():
    preloaded = {
        skill
        for path in AGENTS.glob("*.md")
        for skill in frontmatter(path).get("skills") or []
    }
    assert preloaded, "no agent preloads a skill — the templates changed shape"
    for name in sorted(preloaded):
        path = SKILLS / name / "SKILL.md"
        assert path.exists(), f"{name} is preloaded but does not exist"
        lines = len(path.read_text(encoding="utf-8").splitlines())
        assert lines <= PRELOADED_MAX_LINES, f"{name}: {lines} lines preloaded into every call"


@pytest.mark.parametrize("folder", ["agents", "skills"])
def test_every_referenced_skill_exists(folder):
    names = skill_names()
    for path in sorted((ROOT / "templates" / "claude" / folder).glob("*/SKILL.md")) + sorted(
        (ROOT / "templates" / "claude" / folder).glob("*.md")
    ):
        for reference in SKILL_REFERENCE.findall(path.read_text(encoding="utf-8")):
            assert reference in names, f"{path.name} references {reference}, which is not a skill"


def test_the_project_context_block_lists_every_po_command(example_config, tmp_path):
    paths = ProjectPaths(tmp_path)
    generate.generate_all(example_config, paths)

    block = paths.claude_md.read_text(encoding="utf-8")
    for command in sorted(PO_COMMANDS):
        assert f"/{command}" in block, f"CLAUDE.md does not tell the team about /{command}"
