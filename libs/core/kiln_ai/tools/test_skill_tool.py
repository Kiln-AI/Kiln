from unittest.mock import MagicMock

import pytest

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

    async def test_empty_name_parameter(self, tool):
        result = await tool.run(name="")
        assert "'name' parameter is required" in result.output

    async def test_unknown_skill(self, tool):
        result = await tool.run(name="nonexistent")
        assert "not found" in result.output
        assert "code-review" in result.output
        assert "test-writing" in result.output

    async def test_successful_skill_load(self, tool, skills):
        skills[0].body.return_value = "# Code Review\nReview all code."
        result = await tool.run(name="code-review")
        assert result.output == "# Code Review\nReview all code."

    async def test_body_io_error_is_caught(self, tool, skills):
        skills[0].body.side_effect = FileNotFoundError(
            "SKILL.md not found at /tmp/fake"
        )
        result = await tool.run(name="code-review")
        assert "Error" in result.output
        assert "code-review" in result.output

    async def test_body_value_error_is_caught(self, tool, skills):
        skills[0].body.side_effect = ValueError(
            "Skill must be saved before accessing SKILL.md path"
        )
        result = await tool.run(name="code-review")
        assert "Error" in result.output
        assert "Failed to load skill" in result.output

    async def test_body_parse_error_is_caught(self, tool, skills):
        skills[0].body.side_effect = Exception("frontmatter parse error")
        result = await tool.run(name="code-review")
        assert "Error" in result.output
        assert "frontmatter parse error" in result.output


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

    async def test_path_traversal_blocked(self, skill_tool: SkillTool):
        result = await skill_tool.run(
            name="code-review", resource="references/../../etc/passwd"
        )
        assert "Error" in result.output

    async def test_missing_reference(self, skill_tool: SkillTool):
        result = await skill_tool.run(
            name="code-review", resource="references/nonexistent.md"
        )
        assert "Error" in result.output
        assert "not found" in result.output.lower()

    async def test_without_resource_returns_body(self, skill_tool: SkillTool):
        result = await skill_tool.run(name="code-review")
        assert result.output == "## Code Review\nCheck for bugs."

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


class TestSkillToolDirectoryListing:
    def _seed_refs(self, skill: Skill) -> None:
        ref_dir = skill.references_dir()
        ref_dir.mkdir(parents=True, exist_ok=True)
        (ref_dir / "guide.md").write_text("# Guide\nline2\nline3\n", encoding="utf-8")
        (ref_dir / "notes.txt").write_text("plain text", encoding="utf-8")
        sub = ref_dir / "knowledge"
        sub.mkdir()
        (sub / "rag.md").write_text("# RAG\nbody\n", encoding="utf-8")
        (sub / "tools.md").write_text("# Tools\na\nb\nc\n", encoding="utf-8")

    async def test_references_with_trailing_slash_returns_listing(
        self, sample_skills: list[Skill], skill_tool: SkillTool
    ):
        self._seed_refs(sample_skills[0])
        result = await skill_tool.run(name="code-review", resource="references/")
        out = result.output
        assert out.startswith("Directory: references/")
        assert "references/\n" in out
        assert "guide.md (3 lines)" in out
        assert "notes.txt" in out
        assert "knowledge/ (2 files)" in out
        assert "rag.md (2 lines)" in out
        assert "tools.md (4 lines)" in out
        assert "Total: 3 markdown files, 9 lines." in out
        assert "Tip: read a file with skill(" in out
        assert 'skill_search(name="code-review"' in out

    async def test_references_no_slash_returns_listing(
        self, sample_skills: list[Skill], skill_tool: SkillTool
    ):
        self._seed_refs(sample_skills[0])
        result = await skill_tool.run(name="code-review", resource="references")
        assert "Directory: references/" in result.output
        assert "guide.md (3 lines)" in result.output

    async def test_subdirectory_listing(
        self, sample_skills: list[Skill], skill_tool: SkillTool
    ):
        self._seed_refs(sample_skills[0])
        result = await skill_tool.run(
            name="code-review", resource="references/knowledge"
        )
        out = result.output
        assert out.startswith("Directory: references/knowledge/")
        assert "rag.md (2 lines)" in out
        assert "tools.md (4 lines)" in out
        assert "guide.md" not in out  # top-level file excluded
        assert "Total: 2 markdown files, 6 lines." in out

    async def test_subdirectory_listing_trailing_slash(
        self, sample_skills: list[Skill], skill_tool: SkillTool
    ):
        self._seed_refs(sample_skills[0])
        result = await skill_tool.run(
            name="code-review", resource="references/knowledge/"
        )
        assert "Directory: references/knowledge/" in result.output

    async def test_empty_directory_returns_empty_marker(
        self, sample_skills: list[Skill], skill_tool: SkillTool
    ):
        result = await skill_tool.run(name="code-review", resource="references/")
        out = result.output
        assert out == ("Directory: references/\n\n(empty)\nTotal: 0 files, 0 lines.")

    async def test_non_markdown_files_have_no_line_count(
        self, sample_skills: list[Skill], skill_tool: SkillTool
    ):
        ref_dir = sample_skills[0].references_dir()
        ref_dir.mkdir(parents=True, exist_ok=True)
        (ref_dir / "data.json").write_text('{"k": 1}', encoding="utf-8")
        result = await skill_tool.run(name="code-review", resource="references/")
        out = result.output
        assert "data.json" in out
        assert "data.json (" not in out  # no annotation for non-md
        assert "Total: 0 markdown files, 0 lines." in out

    async def test_assets_listing(
        self, sample_skills: list[Skill], skill_tool: SkillTool
    ):
        assets_dir = sample_skills[0].assets_dir()
        assets_dir.mkdir(parents=True, exist_ok=True)
        (assets_dir / "prices.csv").write_text(
            "item,price\nwidget,9.99", encoding="utf-8"
        )
        result = await skill_tool.run(name="code-review", resource="assets/")
        out = result.output
        assert out.startswith("Directory: assets/")
        assert "prices.csv" in out
        assert "Tip: read a file with skill(" in out

    async def test_single_file_read_still_works(
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

    async def test_path_traversal_on_directory_blocked(self, skill_tool: SkillTool):
        result = await skill_tool.run(name="code-review", resource="references/..")
        assert "Error" in result.output
        assert "Path traversal" in result.output

    async def test_nested_directory_count_is_recursive(
        self, sample_skills: list[Skill], skill_tool: SkillTool
    ):
        ref_dir = sample_skills[0].references_dir()
        ref_dir.mkdir(parents=True, exist_ok=True)
        nested = ref_dir / "outer" / "inner"
        nested.mkdir(parents=True)
        (nested / "deep.md").write_text("one\ntwo\n", encoding="utf-8")
        (ref_dir / "outer" / "sibling.md").write_text("a\n", encoding="utf-8")
        result = await skill_tool.run(name="code-review", resource="references/")
        out = result.output
        assert "outer/ (2 files)" in out
        assert "inner/ (1 files)" in out
        assert "Total: 2 markdown files, 3 lines." in out


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
