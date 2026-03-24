import json

import pytest
from pydantic import ValidationError

from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.skill import (
    Skill,
    _parse_skill_md_body,
    _validate_reference_path,
)


@pytest.fixture
def mock_project(tmp_path):
    project_path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()
    project = Project(name="Test Project", path=project_path)
    project.save_to_file()
    return project


def make_skill(**overrides) -> Skill:
    defaults = {
        "name": "code-review",
        "description": "Review code for style and correctness.",
    }
    defaults.update(overrides)
    return Skill(**defaults)


def save_skill_with_body(
    project, body="## Instructions\n\nReview the code carefully.", **overrides
):
    skill = make_skill(parent=project, **overrides)
    skill.save_to_file()
    skill.save_skill_md(body)
    return skill


# -- Validation tests --


@pytest.mark.parametrize(
    "name",
    ["code-review", "a", "my-skill-123", "x1", "review2go"],
)
def test_valid_skill_names(name):
    skill = make_skill(name=name)
    assert skill.name == name


@pytest.mark.parametrize(
    "name,expected_error",
    [
        ("Code-Review", "only contain lowercase"),
        ("-start", "must not start or end with a hyphen"),
        ("end-", "must not start or end with a hyphen"),
        ("double--hyphen", "must not contain consecutive hyphens"),
        ("", "Skill name cannot be empty"),
        ("a" * 65, "64 characters or fewer"),
        ("has space", "only contain lowercase"),
        ("has_underscore", "only contain lowercase"),
    ],
)
def test_invalid_skill_names(name, expected_error):
    with pytest.raises((ValidationError, ValueError), match=expected_error):
        make_skill(name=name)


def test_description_min_length():
    with pytest.raises(ValidationError):
        make_skill(description="")


def test_description_max_length():
    with pytest.raises(ValidationError):
        make_skill(description="a" * 1025)


def test_description_at_max_length():
    skill = make_skill(description="a" * 1024)
    assert len(skill.description) == 1024


# -- SKILL.md storage tests --


def test_save_and_read_body(mock_project):
    skill = save_skill_with_body(mock_project)
    assert skill.body() == "## Instructions\n\nReview the code carefully."


def test_skill_md_path(mock_project):
    skill = save_skill_with_body(mock_project)
    assert skill.skill_md_path().name == "SKILL.md"
    assert skill.skill_md_path().parent == skill.path.parent


def test_skill_md_path_raises_without_path():
    skill = make_skill()
    with pytest.raises(ValueError, match="Skill must be saved"):
        skill.skill_md_path()


def test_body_raises_without_skill_md(mock_project):
    skill = make_skill(parent=mock_project)
    skill.save_to_file()
    with pytest.raises(FileNotFoundError, match=r"SKILL\.md not found"):
        skill.body()


def test_save_skill_md_empty_body_rejected(mock_project):
    skill = make_skill(parent=mock_project)
    skill.save_to_file()
    with pytest.raises(ValueError, match="body must be non-empty"):
        skill.save_skill_md("")


def test_save_skill_md_whitespace_only_rejected(mock_project):
    skill = make_skill(parent=mock_project)
    skill.save_to_file()
    with pytest.raises(ValueError, match="body must be non-empty"):
        skill.save_skill_md("   \n  ")


def test_round_trip(mock_project):
    body = "## Code Review\n\nCheck for bugs and style issues.\n\n- Naming\n- Error handling"
    skill = save_skill_with_body(mock_project, body=body)
    assert skill.body() == body


def test_kiln_file_does_not_contain_body(mock_project):
    skill = save_skill_with_body(mock_project)
    data = json.loads(skill.path.read_text())
    assert "body" not in data


def test_kiln_file_contains_description(mock_project):
    skill = save_skill_with_body(mock_project)
    data = json.loads(skill.path.read_text())
    assert data["description"] == "Review code for style and correctness."


def test_skill_md_frontmatter_matches_kiln(mock_project):
    skill = save_skill_with_body(mock_project)
    import yaml

    raw = skill.skill_md_path().read_text(encoding="utf-8")
    assert raw.startswith("---\n")
    end = raw.index("---", 3)
    fm = yaml.safe_load(raw[4:end])
    assert fm["name"] == skill.name
    assert fm["description"] == skill.description


def test_skill_md_keeps_sync_on_save(mock_project):
    skill = save_skill_with_body(mock_project)
    skill.description = "Updated description."
    skill.save_to_file()
    skill.save_skill_md("Updated body content.")

    import yaml

    raw = skill.skill_md_path().read_text(encoding="utf-8")
    end = raw.index("---", 3)
    fm = yaml.safe_load(raw[4:end])
    assert fm["description"] == "Updated description."
    assert skill.body() == "Updated body content."


# -- Persistence tests --


def test_save_and_load(mock_project):
    skill = save_skill_with_body(mock_project)

    loaded = Skill.from_id_and_parent_path(skill.id, mock_project.path)
    assert loaded is not None
    assert loaded.name == "code-review"
    assert loaded.description == "Review code for style and correctness."
    assert loaded.body() == "## Instructions\n\nReview the code carefully."


def test_kiln_file_contents(mock_project):
    skill = save_skill_with_body(mock_project)

    kiln_file = skill.path
    assert kiln_file is not None
    assert kiln_file.exists()
    assert kiln_file.name == "skill.kiln"

    data = json.loads(kiln_file.read_text())
    assert data["name"] == "code-review"
    assert data["description"] == "Review code for style and correctness."


# -- Project integration tests --


def test_project_skills_relationship(mock_project):
    s1 = save_skill_with_body(
        mock_project, name="skill-one", description="First skill.", body="Body one"
    )
    s2 = save_skill_with_body(
        mock_project, name="skill-two", description="Second skill.", body="Body two"
    )

    skills = mock_project.skills()
    assert len(skills) == 2
    assert {s.id for s in skills} == {s1.id, s2.id}


def test_skill_directory_structure(mock_project):
    skill = save_skill_with_body(mock_project)

    assert skill.path is not None
    skill_dir = skill.path.parent
    assert skill_dir.name.endswith("code-review")
    assert skill_dir.parent.name == "skills"
    assert skill_dir.parent.parent == mock_project.path.parent


def test_skill_relationship_name():
    assert Skill.relationship_name() == "skills"


def test_skill_parent_type():
    assert Skill.parent_type() is Project


# -- Frontmatter parsing tests --


@pytest.mark.parametrize(
    "raw,expected",
    [
        # basic frontmatter
        ("---\nname: test\ndescription: desc\n---\nHello world", "Hello world"),
        # blank line between frontmatter and body (standard format)
        ("---\nname: test\n---\n\nBody after blank", "Body after blank"),
        # multiple blank lines between frontmatter and body
        ("---\nname: test\n---\n\n\n\nBody", "Body"),
        # no frontmatter at all
        ("Just plain markdown", "Just plain markdown"),
        # does not start with --- (leading whitespace)
        ("  ---\nname: test\n---\nbody", "  ---\nname: test\n---\nbody"),
        # opening --- not on its own line (e.g. ---name)
        ("---name: test\n---\nbody", "---name: test\n---\nbody"),
        # bare --- with no newline (not frontmatter)
        ("---", "---"),
        # description containing --- mid-line (must not split early)
        (
            "---\ndescription: has --- in it\n---\n\nReal body",
            "Real body",
        ),
        # body itself contains --- on its own line (markdown horizontal rule)
        (
            "---\nname: test\n---\n\nBefore rule\n---\nAfter rule",
            "Before rule\n---\nAfter rule",
        ),
        # body contains multiple --- lines
        (
            "---\nname: test\n---\n\nA\n---\nB\n---\nC",
            "A\n---\nB\n---\nC",
        ),
        # body starts with ---
        ("---\nname: test\n---\n\n---\nrest", "---\nrest"),
        # minimal frontmatter (empty YAML between delimiters)
        ("---\n\n---\n\nBody", "Body"),
        # single-line body
        ("---\nname: test\n---\n\nOne liner", "One liner"),
        # body with trailing newlines (preserved)
        ("---\nname: test\n---\n\nBody\n\n\n", "Body\n\n\n"),
        # unicode in body and frontmatter
        ("---\nname: tëst\n---\n\nBödy with émojis 🎉", "Bödy with émojis 🎉"),
        # YAML multiline literal block containing ---
        (
            "---\ndesc: |\n  line one\n  ---\n  line two\n---\n\nBody",
            "Body",
        ),
        # YAML quoted value containing ---
        (
            '---\ndesc: "---"\n---\n\nBody',
            "Body",
        ),
        # four dashes in YAML value — should not match as closing fence
        (
            "---\ndesc: ----\n---\n\nBody",
            "Body",
        ),
    ],
    ids=[
        "basic",
        "blank_line_separator",
        "multiple_blank_lines",
        "no_frontmatter",
        "leading_whitespace_no_frontmatter",
        "opening_fence_not_own_line",
        "bare_dashes_no_newline",
        "triple_dashes_in_yaml_value",
        "horizontal_rule_in_body",
        "multiple_hr_in_body",
        "body_starts_with_dashes",
        "empty_yaml",
        "single_line_body",
        "trailing_newlines_preserved",
        "unicode",
        "yaml_literal_block_with_dashes",
        "yaml_quoted_dashes",
        "four_dashes_in_yaml",
    ],
)
def test_parse_skill_md_body(raw, expected):
    assert _parse_skill_md_body(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "---\nname: test\nno closing delimiter",
        "---\nname: test",
        "---\n",
    ],
    ids=[
        "no_closing_delimiter",
        "no_closing_delimiter_two_lines",
        "opening_fence_only_with_newline",
    ],
)
def test_parse_skill_md_body_malformed_raises(raw):
    with pytest.raises(ValueError):
        _parse_skill_md_body(raw)


def test_round_trip_description_with_dashes(mock_project):
    """Ensure --- in a description survives a write-read round-trip."""
    skill = save_skill_with_body(
        mock_project,
        description="Check code --- look for bugs",
        body="The body",
    )
    assert skill.body() == "The body"


# -- Filename validation tests --


class TestValidateReferencePath:
    @pytest.mark.parametrize(
        "path",
        [
            "../etc/passwd",
            "foo/../bar",
            "..",
            ".",
            "back\\slash.md",
            "",
            "   ",
            "a//b.md",
            "/leading-slash.md",
        ],
    )
    def test_invalid_paths(self, path):
        with pytest.raises(ValueError):
            _validate_reference_path(path)

    @pytest.mark.parametrize(
        "path",
        [
            "REFERENCE.md",
            "finance.md",
            "schema.json",
            "diagram.png",
            "a",
            "sub/dir.md",
            "deeply/nested/path/file.md",
        ],
    )
    def test_valid_paths(self, path):
        _validate_reference_path(path)


# -- References tests --


class TestReferences:
    def test_save_skill_md_creates_references_dir(self, mock_project):
        skill = save_skill_with_body(mock_project)
        assert skill.references_dir().is_dir()

    def test_read_reference(self, mock_project):
        skill = save_skill_with_body(mock_project)
        ref_dir = skill.references_dir()
        (ref_dir / "guide.md").write_text("# Guide\nContent here.", encoding="utf-8")
        assert skill.read_reference("guide.md") == "# Guide\nContent here."

    def test_read_reference_not_found(self, mock_project):
        skill = save_skill_with_body(mock_project)
        with pytest.raises(FileNotFoundError, match="Reference file not found"):
            skill.read_reference("missing.md")

    @pytest.mark.parametrize("path", ["../etc/passwd", "..", "foo/../bar.md"])
    def test_reference_path_traversal(self, mock_project, path):
        skill = save_skill_with_body(mock_project)
        with pytest.raises(ValueError):
            skill.read_reference(path)

    def test_read_reference_in_subdirectory(self, mock_project):
        skill = save_skill_with_body(mock_project)
        sub_dir = skill.references_dir() / "guides"
        sub_dir.mkdir(parents=True, exist_ok=True)
        (sub_dir / "style.md").write_text("# Style Guide", encoding="utf-8")
        assert skill.read_reference("guides/style.md") == "# Style Guide"

    def test_read_reference_in_deeply_nested_subdirectory(self, mock_project):
        skill = save_skill_with_body(mock_project)
        nested_dir = skill.references_dir() / "a" / "b" / "c"
        nested_dir.mkdir(parents=True, exist_ok=True)
        (nested_dir / "deep.md").write_text("Deep content", encoding="utf-8")
        assert skill.read_reference("a/b/c/deep.md") == "Deep content"

    def test_references_dir_requires_saved_skill(self):
        skill = make_skill()
        with pytest.raises(ValueError, match="Skill must be saved"):
            skill.references_dir()

    @pytest.mark.parametrize(
        "filename", ["notes.txt", "data.json", "image.png", "readme"]
    )
    def test_non_md_extension_rejected(self, mock_project, filename):
        skill = save_skill_with_body(mock_project)
        with pytest.raises(ValueError, match=r"\.md extension"):
            skill.read_reference(filename)
