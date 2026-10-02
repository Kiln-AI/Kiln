import re
from unittest.mock import MagicMock

import pytest

import kiln_ai.tools.skill_tool as skill_tool_module
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.skill import Skill
from kiln_ai.datamodel.tool_id import _check_tool_id
from kiln_ai.tools.skill_tool import SkillTool


def _make_saved_skill(project, name, description, body):
    skill = Skill(name=name, description=description, parent=project)
    skill.save_to_file()
    skill.save_skill_md(body)
    return skill


@pytest.fixture
def skills():
    s1 = MagicMock(spec=Skill)
    s1.name = "code-review"
    s1.description = "Review code"

    s2 = MagicMock(spec=Skill)
    s2.name = "test-writing"
    s2.description = "Write tests"

    return [s1, s2]


@pytest.fixture
def tool(skills):
    return SkillTool(tool_id="skill_tool_1", skills=skills)


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
            "code-review",
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
        assert "assets/" in desc
        assert len(desc) <= 1024

    async def test_description_teaches_root_first_protocol(self, skill_tool: SkillTool):
        desc = await skill_tool.description()
        assert "skill(name)" in desc
        assert "skill(name, resource)" in desc
        assert "never guess" in desc

    async def test_schema_contains_no_concrete_resource_path(
        self, skill_tool: SkillTool
    ):
        """The schema must describe the shape of a resource path, never spell one out.

        A concrete-looking path in a tool schema gets copied verbatim as a real
        request. The previous description's `references/guide.md` example was
        issued as an actual resource request 32 times on an external agent-port
        corpus, including at skills that ship no resource files at all.
        """
        concrete_path = re.compile(r"(?:references|assets)/\S*\.\w+")
        defn = await skill_tool.toolcall_definition()
        properties = defn["function"]["parameters"]["properties"]
        texts = [
            await skill_tool.description(),
            properties["name"]["description"],
            properties["resource"]["description"],
        ]
        for text in texts:
            assert concrete_path.search(text) is None, (
                f"schema text spells out a resource path: {text!r}"
            )

    async def test_toolcall_definition_schema(self, skill_tool: SkillTool):
        defn = await skill_tool.toolcall_definition()
        assert defn["type"] == "function"
        assert defn["function"]["name"] == "skill"
        params = defn["function"]["parameters"]
        assert params["required"] == ["name"]
        assert "name" in params["properties"]
        assert "resource" in params["properties"]
        assert params["properties"]["resource"]["type"] == "string"

    async def test_skills_property(self, skill_tool: SkillTool):
        assert set(s.name for s in skill_tool.skills) == {"code-review", "testing"}


class TestSkillToolRun:
    async def test_missing_name_parameter(self, tool):
        result = await tool.run()
        assert "Error" in result.output
        assert "'name' parameter is required" in result.output
        assert result.is_error is True
        assert result.error_message == result.output

    async def test_empty_name_parameter(self, tool):
        result = await tool.run(name="")
        assert "'name' parameter is required" in result.output
        assert result.is_error is True
        assert result.error_message == result.output

    async def test_unknown_skill(self, tool):
        result = await tool.run(name="nonexistent")
        assert "not found" in result.output
        assert "code-review" in result.output
        assert "test-writing" in result.output
        assert result.is_error is True
        assert result.error_message == result.output

    async def test_successful_skill_load(self, tool, skills):
        skills[0].body.return_value = "# Code Review\nReview all code."
        result = await tool.run(name="code-review")
        assert result.output == "# Code Review\nReview all code."
        assert result.is_error is False
        assert result.error_message is None

    async def test_body_io_error_is_caught(self, tool, skills):
        skills[0].body.side_effect = FileNotFoundError(
            "SKILL.md not found at /tmp/fake"
        )
        result = await tool.run(name="code-review")
        assert "Error" in result.output
        assert "code-review" in result.output
        assert result.is_error is True
        assert result.error_message == result.output

    async def test_body_value_error_is_caught(self, tool, skills):
        skills[0].body.side_effect = ValueError(
            "Skill must be saved before accessing SKILL.md path"
        )
        result = await tool.run(name="code-review")
        assert "Error" in result.output
        assert "Failed to load skill" in result.output
        assert result.is_error is True
        assert result.error_message == result.output

    async def test_body_parse_error_is_caught(self, tool, skills):
        skills[0].body.side_effect = Exception("frontmatter parse error")
        result = await tool.run(name="code-review")
        assert "Error" in result.output
        assert "frontmatter parse error" in result.output
        assert result.is_error is True
        assert result.error_message == result.output


class TestSkillToolResource:
    async def test_load_reference(
        self, sample_skills: list[Skill], skill_tool: SkillTool
    ):
        ref_dir = sample_skills[0].references_dir()
        ref_dir.mkdir(parents=True, exist_ok=True)
        (ref_dir / "guide.md").write_text(
            "# Guide\nReference content.", encoding="utf-8"
        )
        result = await skill_tool.run(
            name="code-review", resource="references/guide.md"
        )
        assert result.output == "# Guide\nReference content."

    async def test_load_reference_in_subdirectory(
        self, sample_skills: list[Skill], skill_tool: SkillTool
    ):
        sub_dir = sample_skills[0].references_dir() / "guides"
        sub_dir.mkdir(parents=True, exist_ok=True)
        (sub_dir / "style.md").write_text("# Style Guide", encoding="utf-8")
        result = await skill_tool.run(
            name="code-review", resource="references/guides/style.md"
        )
        assert result.output == "# Style Guide"

    async def test_load_asset(self, sample_skills: list[Skill], skill_tool: SkillTool):
        assets_dir = sample_skills[0].assets_dir()
        assets_dir.mkdir(parents=True, exist_ok=True)
        (assets_dir / "prices.csv").write_text(
            "item,price\nwidget,9.99", encoding="utf-8"
        )
        result = await skill_tool.run(name="code-review", resource="assets/prices.csv")
        assert result.output == "item,price\nwidget,9.99"

    async def test_load_asset_in_subdirectory(
        self, sample_skills: list[Skill], skill_tool: SkillTool
    ):
        sub_dir = sample_skills[0].assets_dir() / "data"
        sub_dir.mkdir(parents=True, exist_ok=True)
        (sub_dir / "config.json").write_text('{"key": "val"}', encoding="utf-8")
        result = await skill_tool.run(
            name="code-review", resource="assets/data/config.json"
        )
        assert result.output == '{"key": "val"}'

    async def test_invalid_prefix(self, skill_tool: SkillTool):
        result = await skill_tool.run(name="code-review", resource="secrets/key.txt")
        assert "Error" in result.output
        assert "references/" in result.output
        assert "assets/" in result.output
        assert result.is_error is True
        assert result.error_message == result.output

    async def test_path_traversal_blocked(self, skill_tool: SkillTool):
        result = await skill_tool.run(
            name="code-review", resource="references/../../etc/passwd"
        )
        assert "Error" in result.output
        assert result.is_error is True
        assert result.error_message == result.output

    async def test_missing_reference(self, skill_tool: SkillTool):
        result = await skill_tool.run(
            name="code-review", resource="references/nonexistent.md"
        )
        assert "Error" in result.output
        assert "not found" in result.output.lower()
        assert result.is_error is True
        assert result.error_message == result.output

    async def test_no_filename_after_prefix(self, skill_tool: SkillTool):
        result = await skill_tool.run(name="code-review", resource="references/")
        assert "Error" in result.output
        assert result.is_error is True
        assert result.error_message == result.output

    async def test_unknown_resource_directory(
        self, skill_tool: SkillTool, monkeypatch: pytest.MonkeyPatch
    ):
        # The prefix allowlist normally makes this branch unreachable; widen it
        # so the "unknown resource directory" failure shape can be exercised.
        monkeypatch.setattr(
            skill_tool_module,
            "ALLOWED_RESOURCE_PREFIXES",
            ("references/", "assets/", "templates/"),
        )
        result = await skill_tool.run(
            name="code-review", resource="templates/report.md"
        )
        assert result.output == "Error: Unknown resource directory: templates"
        assert result.is_error is True
        assert result.error_message == result.output

    async def test_without_resource_returns_body(self, skill_tool: SkillTool):
        result = await skill_tool.run(name="code-review")
        assert result.output == "## Code Review\nCheck for bugs."
        assert result.is_error is False
        assert result.error_message is None

    async def test_successful_resource_load_is_not_flagged(
        self, sample_skills: list[Skill], skill_tool: SkillTool
    ):
        ref_dir = sample_skills[0].references_dir()
        ref_dir.mkdir(parents=True, exist_ok=True)
        (ref_dir / "ok.md").write_text("fine", encoding="utf-8")
        result = await skill_tool.run(name="code-review", resource="references/ok.md")
        assert result.output == "fine"
        assert result.is_error is False
        assert result.error_message is None

    async def test_binary_resource_rejected(
        self, sample_skills: list[Skill], skill_tool: SkillTool
    ):
        ref_dir = sample_skills[0].references_dir()
        ref_dir.mkdir(parents=True, exist_ok=True)
        (ref_dir / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00")
        result = await skill_tool.run(
            name="code-review", resource="references/image.png"
        )
        assert "Error" in result.output
        assert "not a readable text file" in result.output
        assert result.is_error is True
        assert result.error_message == result.output


class TestSkillToolErrorOutputIsStable:
    """The ``output`` text of each failure is a stable contract.

    Downstream consumers match on these exact strings, so flagging a failure
    with ``is_error``/``error_message`` must never reword the output.
    """

    async def test_missing_name_output_unchanged(self, tool):
        result = await tool.run()
        assert result.output == "Error: 'name' parameter is required."

    async def test_unknown_skill_output_unchanged(self, tool):
        result = await tool.run(name="nonexistent")
        assert result.output == (
            "Error: Skill 'nonexistent' not found. "
            "Available skills: code-review, test-writing"
        )

    async def test_body_failure_output_unchanged(self, tool, skills):
        skills[0].body.side_effect = ValueError("boom")
        result = await tool.run(name="code-review")
        assert result.output == "Error: Failed to load skill 'code-review': boom"

    async def test_invalid_prefix_output_unchanged(self, skill_tool: SkillTool):
        result = await skill_tool.run(name="code-review", resource="secrets/key.txt")
        assert result.output == (
            "Error: Resource path must start with one of: references/, assets/"
        )

    async def test_no_filename_output_unchanged(self, skill_tool: SkillTool):
        result = await skill_tool.run(name="code-review", resource="references/")
        assert result.output == (
            "Error: Resource path must include a filename after the directory prefix."
        )

    async def test_resource_not_found_output_unchanged(self, skill_tool: SkillTool):
        result = await skill_tool.run(
            name="code-review", resource="references/nonexistent.md"
        )
        assert result.output == "Error: Resource not found: references/nonexistent.md"

    async def test_value_error_output_unchanged(
        self, sample_skills: list[Skill], skill_tool: SkillTool
    ):
        ref_dir = sample_skills[0].references_dir()
        ref_dir.mkdir(parents=True, exist_ok=True)
        (ref_dir / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00")
        result = await skill_tool.run(
            name="code-review", resource="references/image.png"
        )
        assert result.output.startswith("Error: ")
        assert "Error: Error:" not in result.output


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
