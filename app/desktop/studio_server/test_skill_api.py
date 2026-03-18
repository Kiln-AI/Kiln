from unittest.mock import patch

import pytest
from app.desktop.studio_server.skill_api import connect_skill_api
from app.desktop.studio_server.tool_api import connect_tool_servers_api
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.skill import Skill
from kiln_server.custom_errors import connect_custom_errors


@pytest.fixture
def app():
    test_app = FastAPI()
    connect_custom_errors(test_app)
    connect_skill_api(test_app)
    connect_tool_servers_api(test_app)
    return test_app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def test_project(tmp_path):
    project_path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()
    project = Project(name="Test Project", path=project_path)
    project.save_to_file()
    return project


@pytest.fixture
def mock_project_from_id(test_project):
    with (
        patch(
            "app.desktop.studio_server.skill_api.project_from_id",
            return_value=test_project,
        ) as mock_skill,
        patch(
            "app.desktop.studio_server.tool_api.project_from_id",
            return_value=test_project,
        ),
    ):
        yield mock_skill


@pytest.fixture
def sample_skill_data():
    return {
        "name": "code-review",
        "description": "Reviews code for quality and best practices.",
        "body": "## Code Review Skill\n\nCheck for:\n- Naming conventions\n- Error handling\n- Test coverage",
    }


@pytest.fixture
def saved_skill(test_project):
    skill = Skill(
        name="test-skill",
        description="A test skill for unit tests.",
        parent=test_project,
    )
    skill.save_to_file()
    skill.save_skill_md("## Test Skill\n\nDo the test thing.")
    return skill


class TestCreateSkill:
    def test_create_skill_success(
        self, client, test_project, mock_project_from_id, sample_skill_data
    ):
        response = client.post(
            f"/api/projects/{test_project.id}/skills",
            json=sample_skill_data,
        )
        assert response.status_code == 200
        result = response.json()
        assert result["name"] == "code-review"
        assert result["description"] == "Reviews code for quality and best practices."
        assert "id" in result

        skill = Skill.from_id_and_parent_path(result["id"], test_project.path)
        assert skill is not None
        assert skill.references_dir().is_dir()

    def test_create_skill_invalid_name(
        self, client, test_project, mock_project_from_id
    ):
        response = client.post(
            f"/api/projects/{test_project.id}/skills",
            json={
                "name": "Invalid Name!",
                "description": "Bad name.",
                "body": "content",
            },
        )
        assert response.status_code == 422

    def test_create_skill_missing_body(
        self, client, test_project, mock_project_from_id
    ):
        response = client.post(
            f"/api/projects/{test_project.id}/skills",
            json={
                "name": "no-body",
                "description": "Missing body field.",
            },
        )
        assert response.status_code == 422


class TestGetSkills:
    def test_list_skills_empty(self, client, test_project, mock_project_from_id):
        response = client.get(f"/api/projects/{test_project.id}/skills")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_skills(self, client, test_project, mock_project_from_id, saved_skill):
        response = client.get(f"/api/projects/{test_project.id}/skills")
        assert response.status_code == 200
        result = response.json()
        assert len(result) == 1
        assert result[0]["name"] == "test-skill"

    def test_get_skill_by_id(
        self, client, test_project, mock_project_from_id, saved_skill
    ):
        response = client.get(
            f"/api/projects/{test_project.id}/skills/{saved_skill.id}"
        )
        assert response.status_code == 200
        result = response.json()
        assert result["name"] == "test-skill"
        assert result["description"] == "A test skill for unit tests."
        assert "skill_md" not in result

    def test_get_skill_not_found(self, client, test_project, mock_project_from_id):
        response = client.get(f"/api/projects/{test_project.id}/skills/nonexistent-id")
        assert response.status_code == 404
        assert response.json()["message"] == "Skill not found"


class TestGetSkillContent:
    def test_get_skill_content(
        self, client, test_project, mock_project_from_id, saved_skill
    ):
        response = client.get(
            f"/api/projects/{test_project.id}/skills/{saved_skill.id}/content"
        )
        assert response.status_code == 200
        result = response.json()
        assert "## Test Skill" in result["skill_md"]
        assert "## Test Skill" in result["body"]

    def test_get_skill_content_not_found(
        self, client, test_project, mock_project_from_id
    ):
        response = client.get(
            f"/api/projects/{test_project.id}/skills/nonexistent-id/content"
        )
        assert response.status_code == 404

    def test_get_skill_content_missing_file(
        self, client, test_project, mock_project_from_id
    ):
        skill = Skill(
            name="no-md-skill",
            description="Skill without SKILL.md.",
            parent=test_project,
        )
        skill.save_to_file()
        response = client.get(
            f"/api/projects/{test_project.id}/skills/{skill.id}/content"
        )
        assert response.status_code == 200
        assert response.json()["skill_md"] == ""
        assert response.json()["body"] == ""


class TestUpdateSkill:
    def test_update_skill_not_found(self, client, test_project, mock_project_from_id):
        response = client.patch(
            f"/api/projects/{test_project.id}/skills/nonexistent-id",
            json={"is_archived": True},
        )
        assert response.status_code == 404


class TestArchiveSkill:
    def test_archive_skill(
        self, client, test_project, mock_project_from_id, saved_skill
    ):
        response = client.patch(
            f"/api/projects/{test_project.id}/skills/{saved_skill.id}",
            json={"is_archived": True},
        )
        assert response.status_code == 200
        assert response.json()["is_archived"] is True

        response = client.get(
            f"/api/projects/{test_project.id}/skills/{saved_skill.id}"
        )
        assert response.status_code == 200
        assert response.json()["is_archived"] is True

    def test_unarchive_skill(
        self, client, test_project, mock_project_from_id, saved_skill
    ):
        client.patch(
            f"/api/projects/{test_project.id}/skills/{saved_skill.id}",
            json={"is_archived": True},
        )
        response = client.patch(
            f"/api/projects/{test_project.id}/skills/{saved_skill.id}",
            json={"is_archived": False},
        )
        assert response.status_code == 200
        assert response.json()["is_archived"] is False


class TestAvailableToolsSkillIntegration:
    def test_available_tools_includes_skills(
        self, client, test_project, mock_project_from_id, saved_skill
    ):
        response = client.get(f"/api/projects/{test_project.id}/available_tools")
        assert response.status_code == 200
        result = response.json()

        skill_set = next(
            (s for s in result if s["type"] == "skill"),
            None,
        )
        assert skill_set is not None
        assert skill_set["set_name"] == "Skills"
        assert len(skill_set["tools"]) == 1
        assert skill_set["tools"][0]["name"] == "test-skill"
        assert skill_set["tools"][0]["description"] == "A test skill for unit tests."
        assert skill_set["tools"][0]["id"] == f"kiln_tool::skill::{saved_skill.id}"

    def test_available_tools_no_skills(
        self, client, test_project, mock_project_from_id
    ):
        response = client.get(f"/api/projects/{test_project.id}/available_tools")
        assert response.status_code == 200
        result = response.json()

        skill_set = next(
            (s for s in result if s["type"] == "skill"),
            None,
        )
        assert skill_set is None

    def test_available_tools_multiple_skills(
        self, client, test_project, mock_project_from_id
    ):
        for i in range(3):
            s = Skill(
                name=f"skill-{i}",
                description=f"Skill number {i}.",
                parent=test_project,
            )
            s.save_to_file()
            s.save_skill_md(f"Body for skill {i}")

        response = client.get(f"/api/projects/{test_project.id}/available_tools")
        assert response.status_code == 200
        result = response.json()

        skill_set = next(
            (s for s in result if s["type"] == "skill"),
            None,
        )
        assert skill_set is not None
        assert len(skill_set["tools"]) == 3
        tool_names = {t["name"] for t in skill_set["tools"]}
        assert tool_names == {"skill-0", "skill-1", "skill-2"}
        for tool in skill_set["tools"]:
            assert tool["id"].startswith("kiln_tool::skill::")

    def test_available_tools_excludes_archived_skills(
        self, client, test_project, mock_project_from_id
    ):
        active = Skill(
            name="active-skill",
            description="Active.",
            parent=test_project,
        )
        active.save_to_file()
        active.save_skill_md("Active body")
        archived = Skill(
            name="archived-skill",
            description="Archived.",
            is_archived=True,
            parent=test_project,
        )
        archived.save_to_file()
        archived.save_skill_md("Archived body")

        response = client.get(f"/api/projects/{test_project.id}/available_tools")
        assert response.status_code == 200
        result = response.json()

        skill_set = next(
            (s for s in result if s["type"] == "skill"),
            None,
        )
        assert skill_set is not None
        assert len(skill_set["tools"]) == 1
        assert skill_set["tools"][0]["name"] == "active-skill"
