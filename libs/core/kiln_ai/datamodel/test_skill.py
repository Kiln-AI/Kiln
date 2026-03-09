import json

import pytest
from pydantic import ValidationError

from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.skill import Skill


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
        "body": "## Instructions\n\nReview the code carefully.",
    }
    defaults.update(overrides)
    return Skill(**defaults)


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


def test_body_required():
    with pytest.raises(ValidationError):
        Skill(name="test_skill", description="A test skill.")


def test_body_empty_rejected():
    with pytest.raises(ValidationError):
        make_skill(body="")


# -- Persistence tests --


def test_save_and_load(mock_project):
    skill = make_skill(parent=mock_project)
    skill.save_to_file()

    loaded = Skill.from_id_and_parent_path(skill.id, mock_project.path)
    assert loaded is not None
    assert loaded.name == "code_review"
    assert loaded.description == "Review code for style and correctness."
    assert loaded.body == "## Instructions\n\nReview the code carefully."


def test_kiln_file_contents(mock_project):
    skill = make_skill(parent=mock_project)
    skill.save_to_file()

    kiln_file = skill.path
    assert kiln_file is not None
    assert kiln_file.exists()
    assert kiln_file.name == "skill.kiln"

    data = json.loads(kiln_file.read_text())
    assert data["name"] == "code_review"
    assert data["description"] == "Review code for style and correctness."
    assert data["body"] == "## Instructions\n\nReview the code carefully."


# -- Project integration tests --


def test_project_skills_relationship(mock_project):
    s1 = make_skill(parent=mock_project, name="skill_one", description="First skill.")
    s2 = make_skill(parent=mock_project, name="skill_two", description="Second skill.")
    s1.save_to_file()
    s2.save_to_file()

    skills = mock_project.skills()
    assert len(skills) == 2
    assert {s.id for s in skills} == {s1.id, s2.id}


def test_skill_directory_structure(mock_project):
    skill = make_skill(parent=mock_project)
    skill.save_to_file()

    assert skill.path is not None
    skill_dir = skill.path.parent
    assert skill_dir.name.endswith("code_review")
    assert skill_dir.parent.name == "skills"
    assert skill_dir.parent.parent == mock_project.path.parent


def test_skill_relationship_name():
    assert Skill.relationship_name() == "skills"


def test_skill_parent_type():
    assert Skill.parent_type() is Project
