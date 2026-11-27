"""Unit tests for the agent's skills and for how a skill is loaded.

The first part runs against every skill in src/agent/skills, whatever they are,
so it keeps passing when a skill is added, changed or replaced, and fails when
one is malformed. Add tests of your own skill's content at the end: a test for
each rule the skill must keep, looking for a phrase, so that a rule cannot be
edited out unnoticed.
"""

import re
import shutil

import pytest

import example
import loader
import prompt
from session import record as rec
from session import tools

SKILLS = sorted(loader.SKILLS)
TOOL_NAME = re.compile(r"`((?:add|update)_[a-z0-9_]+)`")


def tool_names(skill):
    """Every tool a session of the skill can be offered."""
    made = [name for kind in skill.schema.kinds for name in (tools.add_tool(kind), tools.update_tool(kind))]
    return set(tools.STATIC_TOOLS) | set(tools.REPOSITORY_TOOLS) | set(made)


# --- every skill the agent has ------------------------------------------------


def test_the_agent_has_at_least_one_skill():
    assert SKILLS


@pytest.mark.parametrize("name", SKILLS)
def test_a_skill_is_whole(name):
    skill = loader.SKILLS[name]
    assert skill.name == name == skill.path.name
    assert skill.description and skill.instructions.startswith("# ")
    assert len(skill.stages) >= 2
    for stage in skill.stages:
        assert skill.reference(stage).startswith("# Stage:"), stage


@pytest.mark.parametrize("name", SKILLS)
def test_a_skill_names_only_tools_that_exist(name):
    skill = loader.SKILLS[name]
    texts = {"SKILL.md": skill.instructions}
    texts.update({f"references/{stage}.md": skill.reference(stage) for stage in skill.stages})
    for where, text in texts.items():
        unknown = set(TOOL_NAME.findall(text)) - tool_names(skill)
        assert not unknown, f"{where} names {sorted(unknown)}, which the skill's session.yaml does not make"


@pytest.mark.parametrize("name", SKILLS)
def test_a_stage_s_reference_names_only_tools_offered_in_that_stage(name):
    skill = loader.SKILLS[name]
    every = {tool for kind in skill.schema.kinds for tool in (tools.add_tool(kind), tools.update_tool(kind))}
    for stage in skill.schema.stages:
        offered = {tool for kind in stage.records for tool in (tools.add_tool(kind), tools.update_tool(kind))}
        offered |= {tools.update_tool(kind) for kind in stage.fills}
        named = set(TOOL_NAME.findall(skill.reference(stage.name))) & every
        assert named <= offered, f"references/{stage.name}.md names {sorted(named - offered)}"


@pytest.mark.parametrize("name", SKILLS)
def test_a_skill_does_not_say_who_the_agent_is(name):
    skill = loader.SKILLS[name]
    assert prompt.AGENT_NAME not in skill.instructions


def test_the_shared_guide_names_only_tools_that_exist():
    known = set(tools.STATIC_TOOLS) | set(tools.REPOSITORY_TOOLS)
    words = set(rec.NOTE_KINDS) | set(rec.FINDING_KINDS) | set(rec.CHANGES)
    named = set(re.findall(r"`([a-z]+_[a-z_]+)`", prompt.GUIDE)) - words
    assert named <= known, sorted(named - known)


# --- how a skill is loaded ----------------------------------------------------


@pytest.fixture
def copy(tmp_path):
    """A copy of the tests' skills folder that a test may damage."""
    target = tmp_path / "skills"
    shutil.copytree(example.SKILLS_DIR, target)
    return target


def test_a_skill_loads_with_its_schema_and_its_stages(copy):
    skill = loader.load_skills(copy)[example.SKILL]
    assert skill.stages == ("scope", "parts", "findings", "rating", "plan", "report")
    assert skill.schema.document_title == "Review"
    assert skill.description == "A skill the unit tests use. It reviews a system in six stages."
    assert skill.reference("rating") == "# Stage: rating\n\nThe guidance for the rating stage."


@pytest.mark.parametrize("stage", ["scope", "report"])
def test_removing_a_stage_s_reference_stops_the_agent_starting(copy, stage):
    (copy / example.SKILL / "references" / f"{stage}.md").unlink()
    with pytest.raises(loader.SkillError, match=f"no references/{stage}.md"):
        loader.load_skills(copy)


def test_a_skill_without_a_session_file_does_not_load(copy):
    (copy / example.SKILL / "session.yaml").unlink()
    with pytest.raises(loader.SkillError, match="session.yaml: no session.yaml"):
        loader.load_skills(copy)


def test_a_bad_session_file_says_where(copy):
    path = copy / example.SKILL / "session.yaml"
    path.write_text(path.read_text().replace("prefix: FX", "prefix: F"), encoding="utf-8")
    with pytest.raises(loader.SkillError, match="test-review: session.yaml: records.fix.prefix: F is used twice"):
        loader.load_skills(copy)


def test_a_skill_without_its_source_does_not_load(copy):
    (copy / example.SKILL / "SOURCE.md").unlink()
    with pytest.raises(loader.SkillError, match="SOURCE.md"):
        loader.load_skills(copy)


def test_a_source_that_names_no_licence_does_not_load(copy):
    (copy / example.SKILL / "SOURCE.md").write_text("# Source\n\nWritten here.\n", encoding="utf-8")
    with pytest.raises(loader.SkillError, match="names no licence"):
        loader.load_skills(copy)


@pytest.mark.parametrize("content", ["", "no front matter here", "---\nname: test-review\n---\n"])
def test_a_malformed_skill_file_does_not_load(copy, content):
    (copy / example.SKILL / "SKILL.md").write_text(content, encoding="utf-8")
    with pytest.raises(loader.SkillError):
        loader.load_skills(copy)


def test_a_skill_whose_name_is_not_its_folder_s_does_not_load(copy):
    (copy / example.SKILL).rename(copy / "another-name")
    with pytest.raises(loader.SkillError):
        loader.load_skills(copy)


def test_folders_that_begin_with_a_dot_or_an_underscore_are_not_skills(copy):
    (copy / "_drafts").mkdir()
    (copy / ".hidden").mkdir()
    assert list(loader.load_skills(copy)) == [example.SKILL]


# --- this agent's own skills --------------------------------------------------
# Tests of what your skills must say go here. These are for the example skill that
# came with the project: replace them when you replace it.


def test_the_decision_record_skill_keeps_the_work_with_the_participants():
    skill = loader.SKILLS.get("decision-record")
    if skill is None:
        pytest.skip("the example skill has been replaced")
    for phrase in ("DO NOT propose an option", "DO NOT say which option is best"):
        assert phrase in skill.instructions
    assert "DO NOT say which is best" in skill.reference("decision")
    assert skill.stages == ("context", "options", "decision", "record")
