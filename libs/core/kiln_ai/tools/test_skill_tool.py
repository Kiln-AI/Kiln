import pytest

from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.skill import Skill
from kiln_ai.datamodel.tool_id import (
    _check_tool_id,
    build_skill_tool_id,
    skill_id_from_tool_id,
)
from kiln_ai.tools.skill_tool import SkillTool


def _make_saved_skill(
    project: Project, name: str, description: str, body: str
) -> Skill:
    skill = Skill(name=name, description=description, parent=project)
    skill.save_to_file()
    skill.save_skill_md(body)
    return skill


@pytest.fixture
def mock_project(tmp_path):
    project_path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()
    project = Project(name="Test Project", path=project_path)
    project.save_to_file()
    return project


@pytest.fixture
def sample_skills(mock_project) -> list[Skill]:
    return [
        _make_saved_skill(
            mock_project,
            "code_review",
            "Review code for quality",
            "## Code Review\nCheck for bugs.",
        ),
        _make_saved_skill(
            mock_project,
            "testing",
            "Write tests for code",
            "## Testing\nWrite unit tests.",
        ),
    ]


@pytest.fixture
def skill_tool(sample_skills: list[Skill]) -> SkillTool:
    return SkillTool("kiln_tool::skill::123", sample_skills)


class TestSkillToolDefinition:
    async def test_name(self, skill_tool: SkillTool):
        assert await skill_tool.name() == "skill"

    async def test_id(self, skill_tool: SkillTool):
        assert await skill_tool.id() == "kiln_tool::skill::123"

    async def test_description_mentions_resource(self, skill_tool: SkillTool):
        desc = await skill_tool.description()
        assert "Load an agent skill by name" in desc
        assert "resource" in desc
        assert len(desc) <= 1024

    async def test_toolcall_definition_schema(self, skill_tool: SkillTool):
        defn = await skill_tool.toolcall_definition()
        assert defn["type"] == "function"
        assert defn["function"]["name"] == "skill"
        params = defn["function"]["parameters"]
        assert params["required"] == ["name"]
        assert "name" in params["properties"]
        assert "resource" in params["properties"]
        assert params["properties"]["resource"]["type"] == "string"


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


class TestSkillToolResource:
    async def test_load_reference(
        self, sample_skills: list[Skill], skill_tool: SkillTool
    ):
        sample_skills[0].save_reference("guide.md", "# Guide\nReference content.")
        result = await skill_tool.run(
            name="code_review", resource="references/guide.md"
        )
        assert result.output == "# Guide\nReference content."

    async def test_invalid_prefix(self, skill_tool: SkillTool):
        result = await skill_tool.run(name="code_review", resource="secrets/key.txt")
        assert "Error" in result.output
        assert "references/" in result.output

    async def test_path_traversal_blocked(self, skill_tool: SkillTool):
        result = await skill_tool.run(
            name="code_review", resource="references/../../etc/passwd"
        )
        assert "Error" in result.output

    async def test_missing_reference(self, skill_tool: SkillTool):
        result = await skill_tool.run(
            name="code_review", resource="references/nonexistent.md"
        )
        assert "Error" in result.output
        assert "not found" in result.output.lower()

    async def test_no_filename_after_prefix(self, skill_tool: SkillTool):
        result = await skill_tool.run(name="code_review", resource="references/")
        assert "Error" in result.output

    async def test_without_resource_returns_body(self, skill_tool: SkillTool):
        result = await skill_tool.run(name="code_review")
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
