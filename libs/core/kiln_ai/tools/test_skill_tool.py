from unittest.mock import MagicMock

import pytest

from kiln_ai.datamodel.skill import Skill
from kiln_ai.tools.skill_tool import SkillTool


@pytest.fixture
def skills():
    s1 = MagicMock(spec=Skill)
    s1.name = "code_review"
    s1.description = "Review code"

    s2 = MagicMock(spec=Skill)
    s2.name = "test_writing"
    s2.description = "Write tests"

    return [s1, s2]


@pytest.fixture
def tool(skills):
    return SkillTool(tool_id="skill_tool_1", skills=skills)


class TestSkillToolRun:
    async def test_missing_name_parameter(self, tool):
        result = await tool.run()
        assert "Error" in result.output
        assert "'name' parameter is required" in result.output

    async def test_empty_name_parameter(self, tool):
        result = await tool.run(name="")
        assert "'name' parameter is required" in result.output

    async def test_unknown_skill(self, tool):
        result = await tool.run(name="nonexistent")
        assert "not found" in result.output
        assert "code_review" in result.output
        assert "test_writing" in result.output

    async def test_successful_skill_load(self, tool, skills):
        skills[0].body.return_value = "# Code Review\nReview all code."
        result = await tool.run(name="code_review")
        assert result.output == "# Code Review\nReview all code."

    async def test_body_io_error_is_caught(self, tool, skills):
        skills[0].body.side_effect = FileNotFoundError(
            "SKILL.md not found at /tmp/fake"
        )
        result = await tool.run(name="code_review")
        assert "Error" in result.output
        assert "code_review" in result.output

    async def test_body_value_error_is_caught(self, tool, skills):
        skills[0].body.side_effect = ValueError(
            "Skill must be saved before accessing SKILL.md path"
        )
        result = await tool.run(name="code_review")
        assert "Error" in result.output
        assert "Failed to load skill" in result.output

    async def test_body_parse_error_is_caught(self, tool, skills):
        skills[0].body.side_effect = Exception("frontmatter parse error")
        result = await tool.run(name="code_review")
        assert "Error" in result.output
        assert "frontmatter parse error" in result.output


class TestSkillToolDefinition:
    async def test_toolcall_definition_shape(self, tool):
        defn = await tool.toolcall_definition()
        assert defn["type"] == "function"
        func = defn["function"]
        assert func["name"] == "skill"
        assert "name" in func["parameters"]["properties"]
        assert func["parameters"]["required"] == ["name"]

    async def test_id(self, tool):
        assert await tool.id() == "skill_tool_1"

    async def test_skills_property(self, tool, skills):
        assert set(s.name for s in tool.skills) == {"code_review", "test_writing"}
