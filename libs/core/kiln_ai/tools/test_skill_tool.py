from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.skill import Skill
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.tool_id import (
    SKILL_TOOL_ID_PREFIX,
    _check_tool_id,
    build_skill_tool_id,
    skill_id_from_tool_id,
)
from kiln_ai.tools.skill_tool import SkillTool
from kiln_ai.tools.tool_registry import tool_from_id


def _make_skill(name: str, description: str, body: str) -> Skill:
    return Skill(name=name, description=description, body=body)


@pytest.fixture
def sample_skills() -> list[Skill]:
    return [
        _make_skill(
            "code_review", "Review code for quality", "## Code Review\nCheck for bugs."
        ),
        _make_skill("testing", "Write tests for code", "## Testing\nWrite unit tests."),
    ]


@pytest.fixture
def skill_tool(sample_skills: list[Skill]) -> SkillTool:
    return SkillTool("kiln_tool::skill::123", sample_skills)


class TestSkillToolDefinition:
    async def test_name(self, skill_tool: SkillTool):
        assert await skill_tool.name() == "skill"

    async def test_id(self, skill_tool: SkillTool):
        assert await skill_tool.id() == "kiln_tool::skill::123"

    async def test_description_includes_all_skills(self, skill_tool: SkillTool):
        desc = await skill_tool.description()
        assert "<available_skills>" in desc
        assert "<name>code_review</name>" in desc
        assert "<name>testing</name>" in desc
        assert "Review code for quality" in desc
        assert "Write tests for code" in desc

    async def test_toolcall_definition_schema(self, skill_tool: SkillTool):
        defn = await skill_tool.toolcall_definition()
        assert defn["type"] == "function"
        assert defn["function"]["name"] == "skill"
        params = defn["function"]["parameters"]
        assert params["required"] == ["name"]
        assert "name" in params["properties"]

    async def test_single_skill(self):
        tool = SkillTool("id", [_make_skill("only", "The only skill", "body")])
        desc = await tool.description()
        assert "<name>only</name>" in desc

    async def test_empty_skills(self):
        tool = SkillTool("id", [])
        desc = await tool.description()
        assert "<available_skills>" in desc


class TestSkillToolRun:
    async def test_load_valid_skill(self, skill_tool: SkillTool):
        result = await skill_tool.run(name="code_review")
        assert result.output == "## Code Review\nCheck for bugs."

    async def test_load_second_skill(self, skill_tool: SkillTool):
        result = await skill_tool.run(name="testing")
        assert result.output == "## Testing\nWrite unit tests."

    async def test_unknown_skill(self, skill_tool: SkillTool):
        result = await skill_tool.run(name="nonexistent")
        assert "Error" in result.output
        assert "nonexistent" in result.output
        assert "code_review" in result.output
        assert "testing" in result.output

    async def test_missing_name_param(self, skill_tool: SkillTool):
        result = await skill_tool.run()
        assert "Error" in result.output
        assert "'name' parameter is required" in result.output

    async def test_with_context(self, skill_tool: SkillTool):
        from kiln_ai.tools.base_tool import ToolCallContext

        ctx = ToolCallContext(allow_saving=True)
        result = await skill_tool.run(context=ctx, name="code_review")
        assert result.output == "## Code Review\nCheck for bugs."


class TestSkillToolId:
    @pytest.mark.parametrize(
        "tool_id",
        [
            "kiln_tool::skill::abc123",
            "kiln_tool::skill::my_skill",
            "kiln_tool::skill::1",
        ],
    )
    def test_valid_skill_tool_ids(self, tool_id: str):
        assert _check_tool_id(tool_id) == tool_id

    @pytest.mark.parametrize(
        "tool_id",
        [
            "kiln_tool::skill::",
            "kiln_tool::skill::id::extra",
        ],
    )
    def test_invalid_skill_tool_ids(self, tool_id: str):
        with pytest.raises(ValueError, match="Invalid skill tool ID"):
            _check_tool_id(tool_id)

    def test_skill_id_from_tool_id(self):
        assert skill_id_from_tool_id("kiln_tool::skill::abc") == "abc"
        assert skill_id_from_tool_id("kiln_tool::skill::123") == "123"

    def test_skill_id_from_tool_id_invalid(self):
        with pytest.raises(ValueError, match="Invalid skill tool ID"):
            skill_id_from_tool_id("kiln_tool::rag::abc")
        with pytest.raises(ValueError, match="Invalid skill tool ID"):
            skill_id_from_tool_id("kiln_tool::skill::a::b")

    def test_build_skill_tool_id(self):
        assert build_skill_tool_id("abc") == "kiln_tool::skill::abc"
        assert build_skill_tool_id("123") == "kiln_tool::skill::123"


class TestSkillToolRegistry:
    def test_skill_tool_from_id_success(self):
        mock_skill = _make_skill("my_skill", "A test skill", "body content")

        mock_project = Mock(spec=Project)
        mock_project.id = "proj_id"
        mock_project.path = Path("/test/path")

        mock_task = Mock(spec=Task)
        mock_task.parent_project.return_value = mock_project

        with patch("kiln_ai.tools.tool_registry.Skill") as mock_skill_cls:
            mock_skill_cls.from_id_and_parent_path.return_value = mock_skill
            tool_id = f"{SKILL_TOOL_ID_PREFIX}skill_abc"
            tool = tool_from_id(tool_id, task=mock_task)

            assert isinstance(tool, SkillTool)
            mock_skill_cls.from_id_and_parent_path.assert_called_once_with(
                "skill_abc", Path("/test/path")
            )

    def test_skill_tool_from_id_no_task(self):
        tool_id = f"{SKILL_TOOL_ID_PREFIX}skill_abc"
        with pytest.raises(ValueError, match="Requires a parent project/task"):
            tool_from_id(tool_id, task=None)

    def test_skill_tool_from_id_no_project(self):
        mock_task = Mock(spec=Task)
        mock_task.parent_project.return_value = None

        tool_id = f"{SKILL_TOOL_ID_PREFIX}skill_abc"
        with pytest.raises(ValueError, match="Requires a parent project/task"):
            tool_from_id(tool_id, task=mock_task)

    def test_skill_tool_from_id_not_found(self):
        mock_project = Mock(spec=Project)
        mock_project.id = "proj_id"
        mock_project.path = Path("/test/path")

        mock_task = Mock(spec=Task)
        mock_task.parent_project.return_value = mock_project

        with patch("kiln_ai.tools.tool_registry.Skill") as mock_skill_cls:
            mock_skill_cls.from_id_and_parent_path.return_value = None
            tool_id = f"{SKILL_TOOL_ID_PREFIX}missing_skill"
            with pytest.raises(ValueError, match="Skill not found: missing_skill"):
                tool_from_id(tool_id, task=mock_task)


class TestSkillConsolidation:
    def test_consolidates_multiple_skill_tools(self):
        from kiln_ai.adapters.model_adapters.base_adapter import BaseAdapter

        s1 = _make_skill("a", "Skill A", "body A")
        s2 = _make_skill("b", "Skill B", "body B")
        tool1 = SkillTool("kiln_tool::skill::1", [s1])
        tool2 = SkillTool("kiln_tool::skill::2", [s2])

        result = BaseAdapter._consolidate_skill_tools([tool1, tool2])

        assert len(result) == 1
        assert isinstance(result[0], SkillTool)
        assert {s.name for s in result[0].skills} == {"a", "b"}

    def test_single_skill_tool_not_consolidated(self):
        from kiln_ai.adapters.model_adapters.base_adapter import BaseAdapter

        s = _make_skill("a", "Skill A", "body A")
        tool = SkillTool("kiln_tool::skill::1", [s])

        result = BaseAdapter._consolidate_skill_tools([tool])
        assert len(result) == 1
        assert result[0] is tool

    def test_no_skill_tools_unchanged(self):
        from kiln_ai.adapters.model_adapters.base_adapter import BaseAdapter
        from kiln_ai.tools.built_in_tools.math_tools import AddTool

        add_tool = AddTool()
        result = BaseAdapter._consolidate_skill_tools([add_tool])
        assert len(result) == 1
        assert result[0] is add_tool

    def test_mixed_tools_preserves_non_skill(self):
        from kiln_ai.adapters.model_adapters.base_adapter import BaseAdapter
        from kiln_ai.tools.built_in_tools.math_tools import AddTool

        add_tool = AddTool()
        s1 = _make_skill("x", "Skill X", "body X")
        s2 = _make_skill("y", "Skill Y", "body Y")
        st1 = SkillTool("kiln_tool::skill::1", [s1])
        st2 = SkillTool("kiln_tool::skill::2", [s2])

        result = BaseAdapter._consolidate_skill_tools([add_tool, st1, st2])
        assert len(result) == 2
        assert add_tool in result
        consolidated = next(t for t in result if isinstance(t, SkillTool))
        assert {s.name for s in consolidated.skills} == {"x", "y"}

    def test_duplicate_skill_names_raises(self):
        from kiln_ai.adapters.model_adapters.base_adapter import BaseAdapter

        s1 = _make_skill("dup", "First", "body 1")
        s2 = _make_skill("dup", "Second", "body 2")
        st1 = SkillTool("kiln_tool::skill::1", [s1])
        st2 = SkillTool("kiln_tool::skill::2", [s2])

        with pytest.raises(ValueError, match="Duplicate skill name 'dup'"):
            BaseAdapter._consolidate_skill_tools([st1, st2])

    async def test_consolidated_tool_loads_all_skills(self):
        from kiln_ai.adapters.model_adapters.base_adapter import BaseAdapter

        s1 = _make_skill("a", "Skill A", "body A")
        s2 = _make_skill("b", "Skill B", "body B")
        st1 = SkillTool("kiln_tool::skill::1", [s1])
        st2 = SkillTool("kiln_tool::skill::2", [s2])

        result = BaseAdapter._consolidate_skill_tools([st1, st2])
        tool = result[0]

        r1 = await tool.run(name="a")
        assert r1.output == "body A"
        r2 = await tool.run(name="b")
        assert r2.output == "body B"
