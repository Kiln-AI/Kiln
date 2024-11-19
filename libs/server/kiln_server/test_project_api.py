import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.exceptions import HTTPException
from fastapi.testclient import TestClient
from kiln_ai.datamodel import Project
from kiln_ai.utils.config import Config

from kiln_server.custom_errors import connect_custom_errors
from kiln_server.project_api import (
    connect_project_api,
    project_from_id,
)


@pytest.fixture
def app():
    app = FastAPI()
    connect_project_api(app)
    connect_custom_errors(app)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_create_project_success(client):
    with (
        patch("os.path.exists", return_value=False),
        patch("os.makedirs"),
        patch("kiln_ai.datamodel.Project.save_to_file"),
    ):
        response = client.post(
            "/api/project",
            json={
                "name": "Test Project",
                "description": "A test project",
            },
        )

    assert response.status_code == 200
    res = response.json()
    assert res["name"] == "Test Project"
    assert res["description"] == "A test project"
    assert res["v"] == 1
    assert res["model_type"] == "project"
    assert res["created_by"] == Config.shared().user_id
    assert res["created_at"] is not None


def test_create_project_missing_name(client):
    response = client.post("/api/project", json={"description": "A test project"})

    assert response.status_code == 422
    assert '"Field required"' in response.text


def test_create_project_invalid_description(client):
    response = client.post(
        "/api/project",
        json={"name": "Test Project", "description": 123},
    )

    assert response.status_code == 422
    assert "Input should be a valid string" in response.text


def test_create_project_existing_name(client):
    with patch("os.path.exists", return_value=True):
        response = client.post(
            "/api/project",
            json={
                "name": "Existing Project",
                "description": "This project already exists",
            },
        )

    assert response.status_code == 400
    assert response.json() == {
        "message": "Project with this folder name already exists. Please choose a different name or rename the prior project's folder.",
    }


def test_create_and_load_project(client):
    with tempfile.TemporaryDirectory() as temp_dir:
        # Mock the default_project_path to use our temporary directory
        with patch(
            "kiln_server.project_api.default_project_path",
            return_value=temp_dir,
        ):
            # Create a new project
            response = client.post(
                "/api/project",
                json={
                    "name": "Test Project",
                    "description": "A test project description",
                },
            )

            assert response.status_code == 200
            res = response.json()
            assert res["name"] == "Test Project"
            assert res["description"] == "A test project description"
            assert res["v"] == 1
            assert res["model_type"] == "project"
            assert res["created_by"] == Config.shared().user_id
            assert res["created_at"] is not None

            # Verify the project file was created
            project_path = os.path.join(temp_dir, "Test Project")
            project_file = os.path.join(project_path, "project.kiln")
            assert os.path.exists(project_path)
            assert os.path.isfile(project_file)

            # Load the project and verify its contents
            loaded_project = Project.load_from_file(project_file)
            assert loaded_project.name == "Test Project"
            assert loaded_project.description == "A test project description"

            # Verify the project is in the list of projects
            assert project_file in Config.shared().projects


def test_get_projects_empty(client):
    with patch.object(Config, "shared") as mock_config:
        mock_config.return_value.projects = []
        response = client.get("/api/projects")

    assert response.status_code == 200
    assert response.json() == []


def test_get_projects_with_current_project(client, mock_projects):
    with (
        patch.object(Config, "shared") as mock_config,
        patch("kiln_ai.datamodel.Project.load_from_file") as mock_load,
    ):
        mock_config.return_value.projects = [p.path for p in mock_projects]
        mock_config.return_value.current_project = mock_projects[1].path
        mock_load.side_effect = mock_projects

        response = client.get("/api/projects")

    assert response.status_code == 200
    result = response.json()
    assert len(result) == 2


def test_get_projects_with_invalid_current_project(client, mock_projects):
    with (
        patch.object(Config, "shared") as mock_config,
        patch("kiln_ai.datamodel.Project.load_from_file") as mock_load,
    ):
        mock_config.return_value.projects = [p.path for p in mock_projects]
        mock_config.return_value.current_project = "/invalid/path"
        mock_load.side_effect = mock_projects

        response = client.get("/api/projects")

    assert response.status_code == 200
    result = response.json()
    assert len(result) == 2


def test_get_projects_with_no_projects(client):
    with patch.object(Config, "shared") as mock_config:
        mock_config.return_value.projects = []
        mock_config.return_value.current_project = None

        response = client.get("/api/projects")

    assert response.status_code == 200
    result = response.json()
    assert result == []


def test_import_project_success(client):
    mock_project = Project(name="Imported Project", description="An imported project")
    with (
        patch("os.path.exists", return_value=True),
        patch("kiln_ai.datamodel.Project.load_from_file", return_value=mock_project),
        patch("kiln_server.project_api.add_project_to_config") as mock_add,
    ):
        response = client.post("/api/import_project?project_path=/path/to/project.kiln")

    assert response.status_code == 200
    result = response.json()
    assert result["name"] == "Imported Project"
    assert result["description"] == "An imported project"
    mock_add.assert_called_once_with("/path/to/project.kiln")


def test_import_project_not_found(client):
    with patch("os.path.exists", return_value=False):
        response = client.post(
            "/api/import_project?project_path=/nonexistent/path.json"
        )

    assert response.status_code == 400
    assert response.json() == {
        "message": "Project not found. Check the path and try again."
    }


def test_import_project_load_error(client):
    with (
        patch("os.path.exists", return_value=True),
        patch(
            "kiln_ai.datamodel.Project.load_from_file",
            side_effect=Exception("Load error"),
        ),
    ):
        response = client.post("/api/import_project?project_path=/path/to/project.kiln")

    assert response.status_code == 500
    assert response.json() == {
        "message": "Failed to load project. The file be invalid: Load error"
    }


def test_import_project_missing_path(client):
    response = client.post("/api/import_project")

    assert response.status_code == 422
    assert "project_path" in response.text
    assert "field required" in response.text.lower()


def test_get_project_success(client):
    mock_project = Project(
        name="Test Project", description="A test project", id="test-id"
    )
    with patch(
        "kiln_server.project_api.project_from_id",
        return_value=mock_project,
    ):
        response = client.get("/api/projects/test-id")

    assert response.status_code == 200
    result = response.json()
    assert result["name"] == "Test Project"
    assert result["description"] == "A test project"
    assert result["id"] == "test-id"


def test_get_project_not_found(client):
    with patch(
        "kiln_server.project_api.project_from_id",
        side_effect=HTTPException(status_code=404, detail="Project not found"),
    ):
        response = client.get("/api/projects/non-existent-id")

    assert response.status_code == 404
    assert response.json() == {"message": "Project not found"}


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.projects = ["/path/to/project1.json", "/path/to/project2.json"]
    return config


@pytest.fixture
def mock_projects():
    return [
        Project(
            name="Project 1",
            description="Description 1",
            path="/path/to/project1.json",
            id="project1-id",
        ),
        Project(
            name="Project 2",
            description="Description 2",
            path="/path/to/project2.json",
            id="project2-id",
        ),
    ]


@pytest.fixture
def patched_config(mock_config):
    with patch(
        "kiln_server.project_api.Config.shared",
        return_value=mock_config,
    ) as mock:
        yield mock


@pytest.fixture
def patched_load_project(mock_projects):
    with patch(
        "kiln_ai.datamodel.Project.load_from_file", side_effect=mock_projects
    ) as mock:
        yield mock


def test_project_from_id_success(patched_config, patched_load_project, mock_projects):
    result = project_from_id("project2-id")
    assert result == mock_projects[1]


def test_project_from_id_not_found(patched_config, patched_load_project):
    with pytest.raises(HTTPException) as exc_info:
        project_from_id("non-existent-id")
    assert exc_info.value.status_code == 404
    assert "Project not found" in str(exc_info.value.detail)


def test_project_from_id_config_projects_none(patched_config):
    patched_config.return_value.projects = None
    with pytest.raises(HTTPException) as exc_info:
        project_from_id("any-id")
    assert exc_info.value.status_code == 404
    assert "Project not found" in str(exc_info.value.detail)


def test_project_from_id_load_exception(patched_config, mock_config):
    mock_config.projects = ["/path/to/project.kiln"]
    with patch(
        "kiln_ai.datamodel.Project.load_from_file",
        side_effect=Exception("Load error"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            project_from_id("any-id")
        assert exc_info.value.status_code == 404
        assert "Project not found" in str(exc_info.value.detail)


def test_get_projects_success(client, mock_projects):
    with (
        patch.object(Config, "shared") as mock_config,
        patch("kiln_ai.datamodel.Project.load_from_file") as mock_load,
    ):
        mock_config.return_value.projects = [p.path for p in mock_projects]
        mock_load.side_effect = mock_projects

        response = client.get("/api/projects")

    assert response.status_code == 200
    result = response.json()
    assert len(result) == 2
    assert result[0]["name"] == "Project 1"
    assert result[0]["description"] == "Description 1"
    assert result[1]["name"] == "Project 2"
    assert result[1]["description"] == "Description 2"


def test_get_projects_with_one_exception(client, mock_projects):
    with (
        patch.object(Config, "shared") as mock_config,
        patch("kiln_ai.datamodel.Project.load_from_file") as mock_load,
    ):
        mock_config.return_value.projects = [p.path for p in mock_projects]
        mock_load.side_effect = [Exception("Load error"), mock_projects[1]]

        response = client.get("/api/projects")

    assert response.status_code == 200
    result = response.json()
    assert len(result) == 1
    assert result[0]["name"] == "Project 2"
    assert result[0]["description"] == "Description 2"


def test_delete_project_success(client):
    mock_project = MagicMock(path="/path/to/project.kiln")
    with (
        patch(
            "kiln_server.project_api.project_from_id",
            return_value=mock_project,
        ),
        patch.object(Config, "shared") as mock_config,
    ):
        mock_config.return_value.projects = [
            "/path/to/project.kiln",
            "/path/to/other_project.kiln",
        ]
        mock_config.return_value.save_setting = MagicMock()

        response = client.delete("/api/projects/test-id")

    assert response.status_code == 200
    assert response.json() == {"message": "Project removed. ID: test-id"}
    mock_config.return_value.save_setting.assert_called_once_with(
        "projects", ["/path/to/other_project.kiln"]
    )


def test_delete_project_not_found(client):
    with patch(
        "kiln_server.project_api.project_from_id",
        side_effect=HTTPException(status_code=404, detail="Project not found"),
    ):
        response = client.delete("/api/projects/non-existent-id")

    assert response.status_code == 404
    assert response.json() == {"message": "Project not found"}


def test_update_project_success(client, tmp_path):
    project_path = tmp_path / "update_test" / "project.kiln"
    original_project = Project(
        name="Original Name",
        description="Original Description",
        path=project_path,
    )
    original_project.save_to_file()
    updated_data = {"name": "Updated Name", "description": "Updated Description"}

    with patch(
        "kiln_server.project_api.project_from_id",
        return_value=original_project,
    ) as mock_project_from_id:
        response = client.patch(
            f"/api/project/{original_project.id}", json=updated_data
        )

    assert response.status_code == 200
    result = response.json()
    assert result["name"] == "Updated Name"
    assert result["description"] == "Updated Description"
    assert result["id"] == original_project.id

    mock_project_from_id.assert_called_once_with(original_project.id)

    loaded_project = Project.load_from_file(project_path)
    assert loaded_project.name == "Updated Name"
    assert loaded_project.description == "Updated Description"
    assert loaded_project.id == original_project.id


def test_update_project_partial(client, tmp_path):
    project_path = tmp_path / "update_test" / "project.kiln"
    original_project = Project(
        name="Original Name",
        description="Original Description",
        path=project_path,
    )
    original_project.save_to_file()
    updated_data = {"name": "Updated Name"}

    with patch(
        "kiln_server.project_api.project_from_id",
        return_value=original_project,
    ) as mock_project_from_id:
        response = client.patch(
            f"/api/project/{original_project.id}", json=updated_data
        )

    assert response.status_code == 200
    result = response.json()
    assert result["name"] == "Updated Name"
    assert result["description"] == original_project.description
    assert result["id"] == original_project.id

    mock_project_from_id.assert_called_once_with(original_project.id)

    loaded_project = Project.load_from_file(project_path)
    assert loaded_project.name == "Updated Name"
    assert loaded_project.description == original_project.description
    assert loaded_project.id == original_project.id


def test_update_project_not_found(client):
    response = client.patch("/api/project/non-existent-id", json={})

    assert response.status_code == 404
    assert response.json() == {"message": "Project not found. ID: non-existent-id"}


@pytest.mark.filterwarnings("ignore")
def test_update_project_invalid_data(client, tmp_path):
    project_path = tmp_path / "update_test" / "project.kiln"
    original_project = Project(
        name="Original Name",
        description="Original Description",
        path=project_path,
    )
    original_project.save_to_file()

    with patch(
        "kiln_server.project_api.project_from_id",
        return_value=original_project,
    ) as mock_project_from_id:
        response = client.patch(
            f"/api/project/{original_project.id}", json={"name": 123}
        )

    assert response.status_code == 422
    assert "Input should be a valid string" in response.text
    mock_project_from_id.assert_called_once_with(original_project.id)
