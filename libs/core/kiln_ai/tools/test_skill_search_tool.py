import pytest

from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.skill import Skill
from kiln_ai.tools.skill_search_tool import (
    DEFAULT_MAX_FILES,
    DEFAULT_MAX_LINE_LENGTH,
    DEFAULT_MAX_MATCHES_PER_FILE,
    SkillSearchTool,
    _Hunk,
)


def _make_saved_skill(project, name, description, body):
    skill = Skill(name=name, description=description, parent=project)
    skill.save_to_file()
    skill.save_skill_md(body)
    return skill


def _seed_refs(skill: Skill, files: dict[str, str]) -> None:
    """Write each {rel_path: content} under the skill's references/ dir."""
    ref_dir = skill.references_dir()
    ref_dir.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        path = ref_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


@pytest.fixture
def mock_project(tmp_path):
    project_path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()
    project = Project(name="Test Project", path=project_path)
    project.save_to_file()
    return project


@pytest.fixture
def sample_skill(mock_project) -> Skill:
    return _make_saved_skill(
        mock_project,
        "kiln-chat",
        "Chat skill for kiln",
        "## kiln-chat\nMain body.",
    )


@pytest.fixture
def sample_skills(mock_project) -> list[Skill]:
    return [
        _make_saved_skill(
            mock_project, "kiln-chat", "Chat skill", "## kiln-chat\nbody"
        ),
        _make_saved_skill(mock_project, "other-skill", "Other skill", "## other\nbody"),
    ]


@pytest.fixture
def search_tool(sample_skills: list[Skill]) -> SkillSearchTool:
    return SkillSearchTool("kiln_tool::skill_search::abc", sample_skills)


class TestSkillSearchToolDefinition:
    async def test_name(self, search_tool: SkillSearchTool):
        assert await search_tool.name() == "skill_search"

    async def test_id(self, search_tool: SkillSearchTool):
        assert await search_tool.id() == "kiln_tool::skill_search::abc"

    async def test_description_not_empty(self, search_tool: SkillSearchTool):
        desc = await search_tool.description()
        assert "regex" in desc.lower()
        assert "skill" in desc.lower()
        assert len(desc) <= 1024

    async def test_toolcall_definition_schema(self, search_tool: SkillSearchTool):
        defn = await search_tool.toolcall_definition()
        assert defn["type"] == "function"
        assert defn["function"]["name"] == "skill_search"
        params = defn["function"]["parameters"]
        assert params["required"] == ["name", "pattern"]
        props = params["properties"]
        for key in (
            "name",
            "pattern",
            "resource",
            "path_prefix",
            "context_before",
            "context_after",
            "context_lines",
            "max_matches_per_file",
            "max_files",
            "max_line_length",
        ):
            assert key in props, f"missing property: {key}"
        assert props["pattern"]["type"] == "string"
        assert props["max_files"]["type"] == "integer"

    async def test_skills_property(self, search_tool: SkillSearchTool):
        assert {s.name for s in search_tool.skills} == {"kiln-chat", "other-skill"}


class TestSkillSearchToolValidation:
    async def test_missing_name(self, search_tool: SkillSearchTool):
        result = await search_tool.run(pattern="foo")
        assert "Error" in result.output
        assert "'name' parameter is required" in result.output

    async def test_empty_name(self, search_tool: SkillSearchTool):
        result = await search_tool.run(name="", pattern="foo")
        assert "'name' parameter is required" in result.output

    async def test_unknown_skill(self, search_tool: SkillSearchTool):
        result = await search_tool.run(name="nonexistent", pattern="foo")
        assert "not found" in result.output
        assert "kiln-chat" in result.output
        assert "other-skill" in result.output

    async def test_missing_pattern(self, search_tool: SkillSearchTool):
        result = await search_tool.run(name="kiln-chat")
        assert "'pattern' parameter is required" in result.output

    async def test_empty_pattern(self, search_tool: SkillSearchTool):
        result = await search_tool.run(name="kiln-chat", pattern="")
        assert "'pattern' parameter is required" in result.output

    async def test_invalid_regex(self, search_tool: SkillSearchTool):
        result = await search_tool.run(name="kiln-chat", pattern="[")
        assert "Invalid regex" in result.output

    async def test_resource_and_path_prefix_mutex(self, search_tool: SkillSearchTool):
        result = await search_tool.run(
            name="kiln-chat",
            pattern="foo",
            resource="references/a.md",
            path_prefix="references/docs",
        )
        assert "either 'resource' or 'path_prefix'" in result.output

    async def test_context_lines_and_context_before_mutex(
        self, search_tool: SkillSearchTool
    ):
        result = await search_tool.run(
            name="kiln-chat", pattern="foo", context_lines=2, context_before=1
        )
        assert "either 'context_lines' or 'context_before'" in result.output

    async def test_context_lines_and_context_after_mutex(
        self, search_tool: SkillSearchTool
    ):
        result = await search_tool.run(
            name="kiln-chat", pattern="foo", context_lines=2, context_after=1
        )
        assert "either 'context_lines' or 'context_before'" in result.output

    async def test_bad_resource_prefix(self, search_tool: SkillSearchTool):
        result = await search_tool.run(
            name="kiln-chat", pattern="foo", resource="assets/data.md"
        )
        assert "'references/'" in result.output

    async def test_bad_path_prefix(self, search_tool: SkillSearchTool):
        result = await search_tool.run(
            name="kiln-chat", pattern="foo", path_prefix="assets/"
        )
        assert "'references/'" in result.output

    async def test_resource_traversal_blocked(
        self, search_tool: SkillSearchTool, sample_skills: list[Skill]
    ):
        _seed_refs(sample_skills[0], {"ok.md": "hello"})
        result = await search_tool.run(
            name="kiln-chat",
            pattern="foo",
            resource="references/../../etc/passwd.md",
        )
        assert "Path traversal" in result.output

    async def test_path_prefix_traversal_blocked(
        self, search_tool: SkillSearchTool, sample_skills: list[Skill]
    ):
        _seed_refs(sample_skills[0], {"ok.md": "hello"})
        result = await search_tool.run(
            name="kiln-chat",
            pattern="foo",
            path_prefix="references/../..",
        )
        assert "Path traversal" in result.output or "Error" in result.output

    async def test_resource_not_markdown(self, search_tool: SkillSearchTool):
        result = await search_tool.run(
            name="kiln-chat", pattern="foo", resource="references/data.json"
        )
        assert "Only markdown files" in result.output

    async def test_resource_is_a_directory(
        self, search_tool: SkillSearchTool, sample_skills: list[Skill]
    ):
        ref_dir = sample_skills[0].references_dir()
        ref_dir.mkdir(parents=True, exist_ok=True)
        sub = ref_dir / "dir.md"
        sub.mkdir()
        result = await search_tool.run(
            name="kiln-chat", pattern="foo", resource="references/dir.md"
        )
        assert "Error" in result.output

    async def test_resource_missing_file(self, search_tool: SkillSearchTool):
        result = await search_tool.run(
            name="kiln-chat", pattern="foo", resource="references/missing.md"
        )
        assert "not found" in result.output.lower()

    async def test_clamps_context_lines_high(
        self, search_tool: SkillSearchTool, sample_skills: list[Skill]
    ):
        _seed_refs(
            sample_skills[0], {"a.md": "\n".join(f"line {i}" for i in range(50))}
        )
        result = await search_tool.run(
            name="kiln-chat", pattern="line 25", context_lines=999
        )
        # Not an error; the huge context value is clamped to 10
        assert "Error" not in result.output.splitlines()[0]
        assert "line 25" in result.output

    async def test_clamps_context_lines_negative(
        self, search_tool: SkillSearchTool, sample_skills: list[Skill]
    ):
        _seed_refs(sample_skills[0], {"a.md": "alpha\nbeta\ngamma\n"})
        result = await search_tool.run(
            name="kiln-chat", pattern="beta", context_lines=-5
        )
        # Negative clamps to 0 — no context lines
        out = result.output
        assert "  2: beta" in out
        assert "  1- alpha" not in out
        assert "  3- gamma" not in out


class TestSkillSearchToolMatching:
    async def test_zero_matches(
        self, search_tool: SkillSearchTool, sample_skills: list[Skill]
    ):
        _seed_refs(sample_skills[0], {"a.md": "alpha\nbeta\n"})
        result = await search_tool.run(name="kiln-chat", pattern="nonexistent")
        assert "No matches for pattern 'nonexistent'" in result.output
        assert "kiln-chat" in result.output

    async def test_zero_matches_with_scope(
        self, search_tool: SkillSearchTool, sample_skills: list[Skill]
    ):
        _seed_refs(sample_skills[0], {"docs/a.md": "alpha\n"})
        result = await search_tool.run(
            name="kiln-chat", pattern="nonexistent", path_prefix="references/docs"
        )
        assert "under 'references/docs'" in result.output

    async def test_single_match(
        self, search_tool: SkillSearchTool, sample_skills: list[Skill]
    ):
        _seed_refs(sample_skills[0], {"a.md": "alpha\nbeta\ngamma\n"})
        result = await search_tool.run(name="kiln-chat", pattern="beta")
        out = result.output
        assert "=== references/a.md" in out
        assert "  2: beta" in out
        assert "Found 1 files" in out

    async def test_multi_match_ordering_within_file(
        self, search_tool: SkillSearchTool, sample_skills: list[Skill]
    ):
        _seed_refs(
            sample_skills[0],
            {"a.md": "alpha\nbeta\ngamma\nbeta again\n"},
        )
        result = await search_tool.run(name="kiln-chat", pattern="beta")
        out = result.output
        assert out.index("  2: beta") < out.index("  4: beta again")

    async def test_ordering_across_files(
        self, search_tool: SkillSearchTool, sample_skills: list[Skill]
    ):
        _seed_refs(
            sample_skills[0],
            {
                "z_last.md": "match here\n",
                "a_first.md": "match here\n",
                "m_middle.md": "match here\n",
            },
        )
        result = await search_tool.run(name="kiln-chat", pattern="match")
        out = result.output
        assert (
            out.index("a_first.md") < out.index("m_middle.md") < out.index("z_last.md")
        )

    async def test_case_insensitive(
        self, search_tool: SkillSearchTool, sample_skills: list[Skill]
    ):
        _seed_refs(sample_skills[0], {"a.md": "Hello World\n"})
        result = await search_tool.run(name="kiln-chat", pattern="hello")
        assert "Hello World" in result.output

    async def test_regex_character_class(
        self, search_tool: SkillSearchTool, sample_skills: list[Skill]
    ):
        _seed_refs(sample_skills[0], {"a.md": "cat\ndog\nbird\n"})
        result = await search_tool.run(name="kiln-chat", pattern=r"^(cat|dog)$")
        out = result.output
        assert "  1: cat" in out
        assert "  2: dog" in out
        assert "  3: bird" not in out

    async def test_resource_scoped_search(
        self, search_tool: SkillSearchTool, sample_skills: list[Skill]
    ):
        _seed_refs(
            sample_skills[0],
            {"a.md": "match in a\n", "b.md": "match in b\n"},
        )
        result = await search_tool.run(
            name="kiln-chat", pattern="match", resource="references/a.md"
        )
        out = result.output
        assert "references/a.md" in out
        assert "b.md" not in out
        assert "Found 1 files" in out

    async def test_path_prefix_scoped_search(
        self, search_tool: SkillSearchTool, sample_skills: list[Skill]
    ):
        _seed_refs(
            sample_skills[0],
            {
                "docs/a.md": "match in docs\n",
                "knowledge/b.md": "match in knowledge\n",
            },
        )
        result = await search_tool.run(
            name="kiln-chat", pattern="match", path_prefix="references/docs"
        )
        out = result.output
        assert "docs/a.md" in out
        assert "knowledge/b.md" not in out

    async def test_whole_tree_default(
        self, search_tool: SkillSearchTool, sample_skills: list[Skill]
    ):
        _seed_refs(
            sample_skills[0],
            {"docs/a.md": "match\n", "knowledge/b.md": "match\n"},
        )
        result = await search_tool.run(name="kiln-chat", pattern="match")
        out = result.output
        assert "docs/a.md" in out
        assert "knowledge/b.md" in out


class TestSkillSearchToolOutput:
    async def test_header_includes_path_and_total_lines(
        self, search_tool: SkillSearchTool, sample_skills: list[Skill]
    ):
        _seed_refs(sample_skills[0], {"a.md": "line1\nmatchme\nline3\nline4\n"})
        result = await search_tool.run(name="kiln-chat", pattern="matchme")
        assert "=== references/a.md (4 lines) ===" in result.output

    async def test_frontmatter_surfaces_name_and_description(
        self, search_tool: SkillSearchTool, sample_skills: list[Skill]
    ):
        content = "---\nname: my-ref\ndescription: A short note.\n---\n\nhello world\n"
        _seed_refs(sample_skills[0], {"a.md": content})
        result = await search_tool.run(name="kiln-chat", pattern="hello")
        out = result.output
        assert "name: my-ref" in out
        assert "description: A short note." in out

    async def test_frontmatter_block_scalar_flattened(
        self, search_tool: SkillSearchTool, sample_skills: list[Skill]
    ):
        content = (
            "---\n"
            "name: doc\n"
            "description: |\n"
            "  This is a long\n"
            "  description that\n"
            "  spans multiple lines.\n"
            "---\n\n"
            "hello\n"
        )
        _seed_refs(sample_skills[0], {"a.md": content})
        result = await search_tool.run(name="kiln-chat", pattern="hello")
        out = result.output
        assert (
            "description: This is a long description that spans multiple lines." in out
        )

    async def test_h1_fallback_when_no_frontmatter(
        self, search_tool: SkillSearchTool, sample_skills: list[Skill]
    ):
        content = "# Big Title\n\nsome body\nmatchme here\n"
        _seed_refs(sample_skills[0], {"a.md": content})
        result = await search_tool.run(name="kiln-chat", pattern="matchme")
        out = result.output
        assert "# Big Title" in out
        assert "name:" not in out
        assert "description:" not in out

    async def test_no_metadata_line_when_neither(
        self, search_tool: SkillSearchTool, sample_skills: list[Skill]
    ):
        content = "plain text\nmatchme\n"
        _seed_refs(sample_skills[0], {"a.md": content})
        result = await search_tool.run(name="kiln-chat", pattern="matchme")
        out = result.output
        # header then directly the hunk lines, no name:/description:/# line between
        header_idx = out.index("=== references/a.md")
        match_idx = out.index("  2: matchme")
        between = out[header_idx:match_idx]
        assert "name:" not in between
        assert "description:" not in between
        assert "# " not in between

    async def test_match_line_uses_colon_separator(
        self, search_tool: SkillSearchTool, sample_skills: list[Skill]
    ):
        _seed_refs(sample_skills[0], {"a.md": "match\n"})
        result = await search_tool.run(name="kiln-chat", pattern="match")
        assert "  1: match" in result.output

    async def test_context_line_uses_dash_separator(
        self, search_tool: SkillSearchTool, sample_skills: list[Skill]
    ):
        _seed_refs(sample_skills[0], {"a.md": "line1\nmatch\nline3\n"})
        result = await search_tool.run(
            name="kiln-chat", pattern="match", context_lines=1
        )
        out = result.output
        assert "  1- line1" in out
        assert "  2: match" in out
        assert "  3- line3" in out

    async def test_hunks_separated_by_blank_line(
        self, search_tool: SkillSearchTool, sample_skills: list[Skill]
    ):
        body = "\n".join(f"line {i}" for i in range(20)) + "\nmatch A\n"
        body2 = body + "\n".join(f"mid {i}" for i in range(20)) + "\nmatch B\n"
        _seed_refs(sample_skills[0], {"a.md": body2})
        result = await search_tool.run(
            name="kiln-chat", pattern="match", context_lines=0
        )
        out = result.output
        lines = out.splitlines()
        match_a_idx = next(i for i, ln in enumerate(lines) if "match A" in ln)
        match_b_idx = next(i for i, ln in enumerate(lines) if "match B" in ln)
        # there must be at least one blank line between the two hunks
        assert "" in lines[match_a_idx + 1 : match_b_idx]

    async def test_max_matches_per_file_truncation(
        self, search_tool: SkillSearchTool, sample_skills: list[Skill]
    ):
        body = "\n".join("match" for _ in range(15)) + "\n"
        _seed_refs(sample_skills[0], {"a.md": body})
        result = await search_tool.run(
            name="kiln-chat", pattern="match", max_matches_per_file=5
        )
        out = result.output
        assert "truncated: 10 more matches in this file" in out

    async def test_max_files_truncation_in_footer(
        self, search_tool: SkillSearchTool, sample_skills: list[Skill]
    ):
        files = {f"f{i:02d}.md": "match\n" for i in range(5)}
        _seed_refs(sample_skills[0], files)
        result = await search_tool.run(name="kiln-chat", pattern="match", max_files=3)
        out = result.output
        assert "Found 3 files (+2 more truncated)" in out

    async def test_long_line_truncated_with_ellipsis(
        self, search_tool: SkillSearchTool, sample_skills: list[Skill]
    ):
        long_line = "x" * 500 + " match " + "y" * 200 + "\n"
        _seed_refs(sample_skills[0], {"a.md": long_line})
        result = await search_tool.run(
            name="kiln-chat", pattern="match", max_line_length=60
        )
        out = result.output
        assert "…" in out
        # Find the rendered match line (starts with "  1: ")
        rendered = next(ln for ln in out.splitlines() if ln.startswith("  1: "))
        body = rendered[len("  1: ") :]
        assert len(body) == 60

    async def test_footer_includes_skill_name_and_tip(
        self, search_tool: SkillSearchTool, sample_skills: list[Skill]
    ):
        _seed_refs(sample_skills[0], {"a.md": "match\n"})
        result = await search_tool.run(name="kiln-chat", pattern="match")
        out = result.output
        assert 'skill(name="kiln-chat"' in out
        assert 'resource="references/..."' in out


class TestSkillSearchToolMergedHunks:
    def test_overlapping_windows_merge(self):
        hunks = SkillSearchTool._merge_hunks([5, 7], before=2, after=2, total=100)
        assert len(hunks) == 1
        assert hunks[0].start == 3
        assert hunks[0].end == 9
        assert hunks[0].match_lines == {5, 7}

    def test_non_overlapping_windows_stay_separate(self):
        hunks = SkillSearchTool._merge_hunks([5, 50], before=2, after=2, total=100)
        assert len(hunks) == 2
        assert hunks[0].match_lines == {5}
        assert hunks[1].match_lines == {50}

    def test_adjacent_windows_merge(self):
        # match at 5 with after=2 ends at 7; match at 8 with before=2 starts at 6.
        # 6 <= 7 + 1 → merge.
        hunks = SkillSearchTool._merge_hunks([5, 8], before=2, after=2, total=100)
        assert len(hunks) == 1
        assert hunks[0].match_lines == {5, 8}

    def test_touching_windows_merge(self):
        # match at 5 ends at 5 (after=0); match at 6 starts at 6; 6 <= 5+1 → merge.
        hunks = SkillSearchTool._merge_hunks([5, 6], before=0, after=0, total=100)
        assert len(hunks) == 1
        assert hunks[0].start == 5
        assert hunks[0].end == 6

    def test_match_at_line_0_with_before_context(self):
        hunks = SkillSearchTool._merge_hunks([0], before=3, after=0, total=10)
        assert len(hunks) == 1
        assert hunks[0].start == 0
        assert hunks[0].end == 0

    def test_match_at_last_line_with_after_context(self):
        hunks = SkillSearchTool._merge_hunks([9], before=0, after=3, total=10)
        assert len(hunks) == 1
        assert hunks[0].start == 9
        assert hunks[0].end == 9

    def test_empty_matches_returns_empty(self):
        assert SkillSearchTool._merge_hunks([], 1, 1, 10) == []

    def test_hunk_dataclass_default(self):
        h = _Hunk(start=0, end=1)
        assert h.match_lines == set()


class TestSkillSearchToolFileHandling:
    async def test_invalid_utf8_file_is_skipped(
        self, search_tool: SkillSearchTool, sample_skills: list[Skill]
    ):
        ref_dir = sample_skills[0].references_dir()
        ref_dir.mkdir(parents=True, exist_ok=True)
        (ref_dir / "bad.md").write_bytes(b"\xff\xfe\xfdnot utf8\n")
        (ref_dir / "good.md").write_text("match here\n", encoding="utf-8")
        result = await search_tool.run(name="kiln-chat", pattern="match")
        out = result.output
        assert "good.md" in out
        assert "bad.md" not in out

    async def test_empty_frontmatter_does_not_error(
        self, search_tool: SkillSearchTool, sample_skills: list[Skill]
    ):
        content = "---\n---\n\nmatch me\n"
        _seed_refs(sample_skills[0], {"a.md": content})
        result = await search_tool.run(name="kiln-chat", pattern="match")
        assert "match me" in result.output
        # no name:/description: emitted
        out = result.output
        assert "name:" not in out.split("=== references/a.md")[1].split("match me")[0]

    async def test_missing_name_in_frontmatter(
        self, search_tool: SkillSearchTool, sample_skills: list[Skill]
    ):
        content = "---\ndescription: Only description.\n---\n\nmatch here\n"
        _seed_refs(sample_skills[0], {"a.md": content})
        result = await search_tool.run(name="kiln-chat", pattern="match")
        out = result.output
        assert "description: Only description." in out
        assert (
            "name:" not in out.split("description:")[0].split("=== references/a.md")[1]
        )

    async def test_malformed_yaml_frontmatter_falls_back(
        self, search_tool: SkillSearchTool, sample_skills: list[Skill]
    ):
        content = "---\nname: [unclosed\n---\n\n# A Title\n\nmatch here\n"
        _seed_refs(sample_skills[0], {"a.md": content})
        result = await search_tool.run(name="kiln-chat", pattern="match")
        out = result.output
        # Frontmatter invalid → parsed as empty → H1 fallback kicks in
        assert "# A Title" in out


class TestSkillSearchToolDefaults:
    def test_default_exposed_constants(self):
        assert DEFAULT_MAX_MATCHES_PER_FILE == 10
        assert DEFAULT_MAX_FILES == 20
        assert DEFAULT_MAX_LINE_LENGTH == 240

    def test_resolve_int_clamp(self):
        assert SkillSearchTool._resolve_int(999, default=5, clamp_range=(0, 10)) == 10
        assert SkillSearchTool._resolve_int(-5, default=5, clamp_range=(0, 10)) == 0
        assert SkillSearchTool._resolve_int(None, default=5, clamp_range=(0, 10)) == 5
        assert SkillSearchTool._resolve_int("abc", default=5, clamp_range=(0, 10)) == 5
        assert SkillSearchTool._resolve_int(7, default=5, clamp_range=(0, 10)) == 7


class TestSkillSearchToolFrontmatter:
    def test_parse_frontmatter_returns_empty_when_no_block(self):
        assert SkillSearchTool._parse_frontmatter("hello\nworld\n") == {}

    def test_parse_frontmatter_valid_block(self):
        text = "---\nname: foo\ndescription: bar\n---\n\nbody\n"
        result = SkillSearchTool._parse_frontmatter(text)
        assert result == {"name": "foo", "description": "bar"}

    def test_parse_frontmatter_flattens_whitespace(self):
        text = "---\ndescription: |\n  line1\n  line2\n---\n\nbody\n"
        result = SkillSearchTool._parse_frontmatter(text)
        assert result == {"description": "line1 line2"}

    def test_parse_frontmatter_unclosed_returns_empty(self):
        text = "---\nname: foo\n\nbody\n"
        assert SkillSearchTool._parse_frontmatter(text) == {}

    def test_parse_frontmatter_ignores_extra_fields(self):
        text = "---\nname: foo\nother: baz\n---\n\nbody\n"
        result = SkillSearchTool._parse_frontmatter(text)
        assert result == {"name": "foo"}
