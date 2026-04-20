import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.exceptions import HTTPException
from fastapi.testclient import TestClient
from kiln_ai.datamodel import Project
from kiln_ai.datamodel.eval import (
    Eval,
    EvalConfig,
    EvalConfigType,
    EvalOutputScore,
)
from kiln_ai.datamodel.prompt import Prompt
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.task_output import TaskOutput, TaskOutputRatingType
from kiln_ai.datamodel.task_run import TaskRun
from kiln_ai.utils.config import Config
from kiln_ai.utils.project_utils import DuplicateProjectError

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
            "/api/projects",
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
    response = client.post("/api/projects", json={"description": "A test project"})

    assert response.status_code == 422
    assert '"Field required"' in response.text


def test_create_project_invalid_description(client):
    response = client.post(
        "/api/projects",
        json={"name": "Test Project", "description": 123},
    )

    assert response.status_code == 422
    assert "Input should be a valid string" in response.text


def test_create_project_existing_name(client):
    with patch("os.path.exists", return_value=True):
        response = client.post(
            "/api/projects",
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
                "/api/projects",
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
        "message": "Failed to load project. The file is invalid: Load error"
    }


def test_import_project_duplicate_same_path(client):
    mock_project = Project(
        name="Imported Project", description="An imported project", id="dup-id"
    )
    with (
        patch("os.path.exists", return_value=True),
        patch("kiln_ai.datamodel.Project.load_from_file", return_value=mock_project),
        patch(
            "kiln_server.project_api.check_duplicate_project_id",
            side_effect=DuplicateProjectError(
                "This project is already imported.", same_path=True
            ),
        ),
    ):
        response = client.post("/api/import_project?project_path=/path/to/project.kiln")

    assert response.status_code == 409
    assert response.json()["message"] == "This project is already imported."


def test_import_project_duplicate_different_path(client):
    mock_project = Project(
        name="Imported Project", description="An imported project", id="dup-id"
    )
    with (
        patch("os.path.exists", return_value=True),
        patch("kiln_ai.datamodel.Project.load_from_file", return_value=mock_project),
        patch(
            "kiln_server.project_api.check_duplicate_project_id",
            side_effect=DuplicateProjectError(
                'You already have a project with this ID. You must remove project "Existing" before adding this.',
                same_path=False,
            ),
        ),
    ):
        response = client.post("/api/import_project?project_path=/path/to/project.kiln")

    assert response.status_code == 409
    assert "remove project" in response.json()["message"]


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
            f"/api/projects/{original_project.id}", json=updated_data
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
            f"/api/projects/{original_project.id}", json=updated_data
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
    response = client.patch("/api/projects/non-existent-id", json={})

    assert response.status_code == 404
    assert response.json() == {"message": "Project not found. ID: non-existent-id"}


def _build_project_with_entities(tmp_path):
    project_path = tmp_path / "project" / "project.kiln"
    project = Project(
        name="Ctx Project", description="Context test project", path=project_path
    )
    project.save_to_file()

    task1 = Task(
        name="Task One",
        description="First task",
        instruction="Do thing one.",
        parent=project,
    )
    task1.save_to_file()

    task2 = Task(
        name="Task Two",
        description=None,
        instruction="Do thing two.",
        parent=project,
    )
    task2.save_to_file()

    # Two runs on task1, zero on task2
    for i in range(2):
        TaskRun(
            input=f"in-{i}",
            output=TaskOutput(output=f"out-{i}"),
            parent=task1,
        ).save_to_file()

    eval_ = Eval(
        name="Accuracy Eval",
        description="Measures accuracy",
        eval_set_filter_id="tag::eval",
        eval_configs_filter_id="tag::golden",
        output_scores=[
            EvalOutputScore(name="accuracy", type=TaskOutputRatingType.five_star)
        ],
        parent=task1,
    )
    eval_.save_to_file()

    for i in range(2):
        EvalConfig(
            name=f"Config {i}",
            config_type=EvalConfigType.g_eval,
            properties={"eval_steps": ["step1", "step2"]},
            model_name="gpt-4",
            model_provider="openai",
            parent=eval_,
        ).save_to_file()

    Prompt(
        name="My Prompt",
        description="A prompt",
        prompt="You are helpful.",
        parent=task1,
    ).save_to_file()

    return project, task1, task2, eval_


def test_get_project_context_success(client, tmp_path):
    project, task1, task2, eval_ = _build_project_with_entities(tmp_path)

    with patch(
        "kiln_server.project_api.project_from_id",
        return_value=project,
    ):
        response = client.get(f"/api/projects/{project.id}/context")

    assert response.status_code == 200
    body = response.json()

    assert body["id"] == project.id
    assert body["name"] == "Ctx Project"
    assert body["description"] == "Context test project"

    # Top-level project-scoped buckets are present and empty for the untouched ones
    for key in [
        "skills",
        "documents",
        "extractor_configs",
        "chunker_configs",
        "embedding_configs",
        "rag_configs",
        "vector_store_configs",
        "external_tool_servers",
        "reranker_configs",
    ]:
        assert body[key] == [], f"expected empty list for {key}"

    tasks_by_id = {t["id"]: t for t in body["tasks"]}
    assert set(tasks_by_id.keys()) == {task1.id, task2.id}

    t1 = tasks_by_id[task1.id]
    assert t1["name"] == "Task One"
    assert t1["description"] == "First task"
    assert t1["run_count"] == 2
    assert len(t1["evals"]) == 1
    assert t1["evals"][0]["id"] == eval_.id
    assert t1["evals"][0]["name"] == "Accuracy Eval"
    assert t1["evals"][0]["description"] == "Measures accuracy"
    assert t1["evals"][0]["config_count"] == 2
    assert len(t1["prompts"]) == 1
    assert t1["prompts"][0]["name"] == "My Prompt"
    assert t1["finetunes"] == []
    assert t1["run_configs"] == []
    assert t1["dataset_splits"] == []
    assert t1["prompt_optimization_jobs"] == []
    assert t1["specs"] == []

    t2 = tasks_by_id[task2.id]
    assert t2["name"] == "Task Two"
    assert t2["description"] is None
    assert t2["run_count"] == 0
    assert t2["evals"] == []


def test_get_project_context_empty_project(client, tmp_path):
    project_path = tmp_path / "empty" / "project.kiln"
    project = Project(name="Empty", path=project_path)
    project.save_to_file()

    with patch(
        "kiln_server.project_api.project_from_id",
        return_value=project,
    ):
        response = client.get(f"/api/projects/{project.id}/context")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Empty"
    assert body["tasks"] == []
    assert body["skills"] == []
    assert body["rag_configs"] == []


def test_get_project_context_not_found(client):
    with patch(
        "kiln_server.project_api.project_from_id",
        side_effect=HTTPException(status_code=404, detail="Project not found"),
    ):
        response = client.get("/api/projects/missing-id/context")

    assert response.status_code == 404
    assert response.json() == {"message": "Project not found"}


def test_get_project_context_agent_policy(app):
    schema = app.openapi()
    path = schema["paths"]["/api/projects/{project_id}/context"]["get"]
    assert path["x-agent-policy"] == {
        "permission": "allow",
        "requires_approval": False,
    }


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
            f"/api/projects/{original_project.id}", json={"name": 123}
        )

    assert response.status_code == 422
    assert "Input should be a valid string" in response.text
    mock_project_from_id.assert_called_once_with(original_project.id)
