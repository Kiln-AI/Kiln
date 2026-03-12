import json

import pytest
from pydantic import ValidationError

from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.skill import Skill, _parse_skill_md_body


@pytest.fixture
def mock_project(tmp_path):
    project_path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()
    project = Project(name="Test Project", path=project_path)
    project.save_to_file()
    return project


def make_skill(**overrides) -> Skill:
    defaults = {
        "name": "code_review",
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
    ["code_review", "a", "my_skill_123", "x1", "review2go"],
)
def test_valid_skill_names(name):
    skill = make_skill(name=name)
    assert skill.name == name


@pytest.mark.parametrize(
    "name,expected_error",
    [
        ("Code_Review", "snake_case"),
        ("_start", "cannot start or end with an underscore"),
        ("end_", "cannot start or end with an underscore"),
        ("double__underscore", "cannot contain consecutive underscores"),
        ("", "Tool name cannot be empty"),
        ("a" * 65, "less than 64 characters"),
        ("code-review", "snake_case"),
        ("has space", "snake_case"),
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
    assert loaded.name == "code_review"
    assert loaded.description == "Review code for style and correctness."
    assert loaded.body() == "## Instructions\n\nReview the code carefully."


def test_kiln_file_contents(mock_project):
    skill = save_skill_with_body(mock_project)

    kiln_file = skill.path
    assert kiln_file is not None
    assert kiln_file.exists()
    assert kiln_file.name == "skill.kiln"

    data = json.loads(kiln_file.read_text())
    assert data["name"] == "code_review"
    assert data["description"] == "Review code for style and correctness."


# -- Project integration tests --


def test_project_skills_relationship(mock_project):
    s1 = save_skill_with_body(
        mock_project, name="skill_one", description="First skill.", body="Body one"
    )
    s2 = save_skill_with_body(
        mock_project, name="skill_two", description="Second skill.", body="Body two"
    )

    skills = mock_project.skills()
    assert len(skills) == 2
    assert {s.id for s in skills} == {s1.id, s2.id}


def test_skill_directory_structure(mock_project):
    skill = save_skill_with_body(mock_project)

    assert skill.path is not None
    skill_dir = skill.path.parent
    assert skill_dir.name.endswith("code_review")
    assert skill_dir.parent.name == "skills"
    assert skill_dir.parent.parent == mock_project.path.parent


def test_skill_relationship_name():
    assert Skill.relationship_name() == "skills"


def test_skill_parent_type():
    assert Skill.parent_type() is Project


# -- Frontmatter parsing tests --


def test_parse_skill_md_body_valid():
    raw = "---\nname: test\ndescription: desc\n---\nHello world"
    assert _parse_skill_md_body(raw) == "Hello world"


def test_parse_skill_md_body_no_frontmatter():
    raw = "Just plain markdown"
    assert _parse_skill_md_body(raw) == "Just plain markdown"


def test_parse_skill_md_body_with_leading_newline():
    raw = "---\nname: test\n---\n\nBody after blank line"
    assert _parse_skill_md_body(raw) == "\nBody after blank line"


def test_parse_skill_md_body_malformed_raises():
    raw = "---\nname: test\nno closing delimiter"
    with pytest.raises(ValueError):
        _parse_skill_md_body(raw)
