from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from kiln_ai.datamodel import Project, Task, TaskRequirement

from kiln_server.custom_errors import connect_custom_errors
from kiln_server.task_api import connect_task_api, task_from_id


@pytest.fixture
def app():
    app = FastAPI()
    connect_task_api(app)
    connect_custom_errors(app)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def project_and_task(tmp_path):
    project_path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()

    project = Project(name="Test Project", path=str(project_path))
    project.save_to_file()
    task = Task(
        name="Test Task",
        instruction="This is a test instruction",
        description="This is a test task",
        parent=project,
    )
    task.save_to_file()

    return project, task


def test_create_task_success(client, tmp_path):
    project_path = tmp_path / "test_project"
    project_path.mkdir()

    task_data = {
        "name": "Test Task 啊",
        "description": "This is a test task",
        "instruction": "This is a test instruction",
    }

    with (
        patch("kiln_server.task_api.project_from_id") as mock_project_from_id,
        patch("kiln_ai.datamodel.Task.save_to_file") as mock_save,
    ):
        mock_project_from_id.return_value = Project(
            name="Test Project", path=str(project_path)
        )
        mock_save.return_value = None

        response = client.post("/api/projects/project1-id/task", json=task_data)

    assert response.status_code == 200
    res = response.json()
    assert res["name"] == "Test Task 啊"
    assert res["description"] == "This is a test task"
    assert res["id"] is not None

    # Verify that project_from_id was called with the correct argument
    mock_project_from_id.assert_called_once_with("project1-id")


def test_create_task_project_not_found(client, tmp_path):
    task_data = {
        "name": "Test Task",
        "description": "This is a test task",
    }

    response = client.post("/api/projects/FAKEPROJECTID/task", json=task_data)

    assert response.status_code == 404
    assert response.json()["message"] == "Project not found. ID: FAKEPROJECTID"


def test_create_task_project_load_error(client, tmp_path):
    project_path = tmp_path / "test_project"
    project_path.mkdir()

    task_data = {
        "name": "Test Task",
        "description": "This is a test task",
    }

    with patch("kiln_server.task_api.project_from_id") as mock_load:
        mock_load.side_effect = HTTPException(
            status_code=404, detail="Project not found"
        )

        response = client.post("/api/projects/FAKEPROJECTID/task", json=task_data)

    assert response.status_code == 404
    assert "Project not found" in response.json()["message"]


def test_create_task_real_project(client, tmp_path):
    project_path = tmp_path / "real_project" / Project.base_filename()
    project_path.parent.mkdir()

    # Create a real Project
    project = Project(name="Real Project", path=str(project_path))
    project.save_to_file()

    task_data = {
        "name": "Real Task",
        "description": "This is a real task",
        "instruction": "Task instruction",
    }
    with patch("kiln_server.task_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = project

        response = client.post("/api/projects/project1-id/task", json=task_data)

        assert response.status_code == 200
        res = response.json()
        assert res["name"] == "Real Task"
        assert res["description"] == "This is a real task"
        assert res["instruction"] == "Task instruction"
        assert res["id"] is not None

        # Verify the task file on disk
        task_from_disk = project.tasks()[0]

        assert task_from_disk.name == "Real Task"
        assert task_from_disk.description == "This is a real task"
        assert task_from_disk.instruction == "Task instruction"
        assert task_from_disk.id == res["id"]

        # now post again, with an update
        update_data = {
            "description": "This is an updated task description",
        }
        response = client.patch(
            f"/api/projects/project1-id/task/{task_from_disk.id}",
            json=update_data,
        )
        assert response.status_code == 200
        res = response.json()
        assert res["description"] == "This is an updated task description"
        assert res["id"] == task_from_disk.id
        assert res["name"] == "Real Task"
        # Check disk
        task_from_disk_reloaded = project.tasks()[0]
        assert (
            task_from_disk_reloaded.description == "This is an updated task description"
        )
        assert task_from_disk_reloaded.id == task_from_disk.id
        assert task_from_disk_reloaded.instruction == "Task instruction"
        assert task_from_disk_reloaded.name == "Real Task"
        assert task_from_disk_reloaded.id == task_from_disk.id


def test_get_task_success(client, project_and_task):
    project, task = project_and_task

    with patch("kiln_server.task_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = project
        response = client.get(f"/api/projects/project1-id/tasks/{task.id}")

    assert response.status_code == 200
    res = response.json()
    assert res["name"] == "Test Task"
    assert res["description"] == "This is a test task"
    assert res["id"] == task.id
    assert res["instruction"] == "This is a test instruction"


def test_get_task_not_found(client, project_and_task):
    project, _ = project_and_task

    with patch("kiln_server.task_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = project
        response = client.get("/api/projects/project1-id/tasks/non_existent_task_id")

    assert response.status_code == 404
    assert response.json()["message"] == "Task not found. ID: non_existent_task_id"


def test_get_task_project_not_found(client):
    with patch("kiln_server.task_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.side_effect = HTTPException(
            status_code=404, detail="Project not found"
        )
        response = client.get("/api/projects/non_existent_project_id/tasks/task_id")

    assert response.status_code == 404
    assert "Project not found" in response.json()["message"]


def test_task_from_id_success(project_and_task):
    project, task = project_and_task

    with patch("kiln_server.task_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = project
        result = task_from_id("project1-id", task.id)

    assert isinstance(result, Task)
    assert result.id == task.id
    assert result.name == "Test Task"
    assert result.description == "This is a test task"


def test_task_from_id_not_found(project_and_task):
    project, _ = project_and_task

    with patch("kiln_server.task_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = project
        with pytest.raises(HTTPException) as exc_info:
            task_from_id("project1-id", "non_existent_task_id")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Task not found. ID: non_existent_task_id"


def test_update_task_input_schema_error(client, project_and_task):
    project, task = project_and_task

    update_data = {"input_json_schema": {"type": "object"}}

    with patch("kiln_server.task_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = project
        response = client.patch(
            f"/api/projects/{project.id}/task/{task.id}", json=update_data
        )

    assert response.status_code == 400
    assert (
        response.json()["message"] == "Input and output JSON schemas cannot be updated."
    )


def test_update_task_output_schema_error(client, project_and_task):
    project, task = project_and_task

    update_data = {"output_json_schema": {"type": "object"}}

    with patch("kiln_server.task_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = project
        response = client.patch(
            f"/api/projects/{project.id}/task/{task.id}", json=update_data
        )

    assert response.status_code == 400
    assert (
        response.json()["message"] == "Input and output JSON schemas cannot be updated."
    )


def test_update_task_id_mismatch_error(client, project_and_task):
    project, task = project_and_task

    update_data = {"id": "different_id"}

    with patch("kiln_server.task_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = project
        response = client.patch(
            f"/api/projects/{project.id}/task/{task.id}", json=update_data
        )

    assert response.status_code == 400
    assert (
        response.json()["message"] == "Task ID cannot be changed by client in a patch."
    )


def test_update_task_validation_error(client, project_and_task):
    project, task = project_and_task

    update_data = {"name": "Updated Task"}

    with (
        patch("kiln_server.task_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_server.task_api.Task.validate_and_save_with_subrelations"
        ) as mock_validate,
    ):
        mock_project_from_id.return_value = project
        mock_validate.return_value = None
        response = client.patch(
            f"/api/projects/{project.id}/task/{task.id}", json=update_data
        )

    assert response.status_code == 400
    assert response.json()["message"] == "Failed to create task."


def test_update_task_unexpected_return_type(client, project_and_task):
    project, task = project_and_task

    update_data = {"name": "Updated Task"}

    with (
        patch("kiln_server.task_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_server.task_api.Task.validate_and_save_with_subrelations"
        ) as mock_validate,
    ):
        mock_project_from_id.return_value = project
        mock_validate.return_value = MagicMock()  # Return a non-Task object
        response = client.patch(
            f"/api/projects/{project.id}/task/{task.id}", json=update_data
        )

    assert response.status_code == 500
    assert response.json()["message"] == "Failed to patch task."


def test_delete_task_success(client, project_and_task):
    project, task = project_and_task

    with patch("kiln_server.task_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = project

        # First verify the task exists
        response = client.get(f"/api/projects/{project.id}/tasks/{task.id}")
        assert response.status_code == 200

        # Delete the task
        response = client.delete(f"/api/projects/{project.id}/task/{task.id}")
        assert response.status_code == 200

        # Verify the task was deleted
        response = client.get(f"/api/projects/{project.id}/tasks/{task.id}")
        assert response.status_code == 404
        assert response.json()["message"] == f"Task not found. ID: {task.id}"


def test_get_rating_options_empty_task(client, project_and_task):
    project, task = project_and_task

    with patch("kiln_server.task_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = project
        response = client.get(
            f"/api/projects/{project.id}/tasks/{task.id}/rating_options"
        )

    assert response.status_code == 200
    res = response.json()
    assert res["options"] == []


def test_get_rating_options_with_requirements(client, project_and_task):
    project, task = project_and_task

    # Add a requirement to the task
    requirement = TaskRequirement(
        id="req1",
        name="Test Requirement",
        instruction="Test instruction",
        type="five_star",
    )
    task.requirements = [requirement]
    task.save_to_file()

    with patch("kiln_server.task_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = project
        response = client.get(
            f"/api/projects/{project.id}/tasks/{task.id}/rating_options"
        )

    assert response.status_code == 200
    res = response.json()
    assert len(res["options"]) == 1
    option = res["options"][0]
    assert option["requirement"]["name"] == "Test Requirement"
    assert option["show_for_all"] is True
    assert option["show_for_tags"] == []


def test_get_rating_options_with_evals(client, project_and_task):
    project, task = project_and_task

    # Create a mock eval with output scores
    eval_mock = MagicMock()
    eval_mock.eval_configs_filter_id = "tag::golden_set"

    # Create score mocks with proper name attributes
    score1 = MagicMock()
    score1.name = "Score 1"
    score1.instruction = "Score 1 instruction"
    score1.type = "five_star"

    score2 = MagicMock()
    score2.name = "Overall Rating"
    score2.instruction = "Overall instruction"
    score2.type = "five_star"

    eval_mock.output_scores = [score1, score2]

    # Create secong mock eval with duplicate output scores
    eval_mock_2 = MagicMock()
    eval_mock_2.eval_configs_filter_id = "tag::golden_set"

    # Create score mocks with proper name attributes
    score3 = MagicMock()
    score3.name = "Score 1"
    score3.instruction = "Score 1 instruction"
    score3.type = "five_star"

    eval_mock_2.output_scores = [score3]

    with (
        patch("kiln_server.task_api.project_from_id") as mock_project_from_id,
        patch("kiln_ai.datamodel.Task.evals") as mock_evals,
    ):
        mock_project_from_id.return_value = project
        mock_evals.return_value = [eval_mock, eval_mock_2]

        response = client.get(
            f"/api/projects/{project.id}/tasks/{task.id}/rating_options"
        )

    assert response.status_code == 200
    res = response.json()
    assert len(res["options"]) == 1  # Only Score 1, Overall Rating is skipped
    option = res["options"][0]
    assert option["requirement"]["name"] == "Score 1"
    assert option["show_for_all"] is False
    # Note: we're checking it's not added twice with the dupe
    assert option["show_for_tags"] == ["golden_set"]


def test_get_rating_options_with_non_tag_filter(client, project_and_task, caplog):
    project, task = project_and_task

    # Create a mock eval with non-tag filter
    eval_mock = MagicMock()
    eval_mock.id = "test_eval"
    eval_mock.eval_configs_filter_id = "filter::some_filter"

    # Create score mock with proper attributes
    score = MagicMock()
    score.name = "Score 1"
    score.instruction = "Score 1 instruction"
    score.type = "five_star"

    eval_mock.output_scores = [score]

    with (
        patch("kiln_server.task_api.project_from_id") as mock_project_from_id,
        patch("kiln_ai.datamodel.Task.evals") as mock_evals,
    ):
        mock_project_from_id.return_value = project
        mock_evals.return_value = [eval_mock]

        response = client.get(
            f"/api/projects/{project.id}/tasks/{task.id}/rating_options"
        )

    assert response.status_code == 200
    res = response.json()
    assert res["options"] == []  # No options should be added for non-tag filter

    # Verify warning was logged
    assert "non-tag filter" in caplog.text
    assert "test_eval" in caplog.text


def test_get_rating_options_duplicate_requirements(client, project_and_task):
    project, task = project_and_task

    # Create two evals with the same requirement name
    eval1 = MagicMock()
    eval1.eval_configs_filter_id = "tag::golden_set1"

    score1 = MagicMock()
    score1.name = "Duplicate Score"
    score1.instruction = "Score 1 instruction"
    score1.type = "five_star"
    eval1.output_scores = [score1]

    eval2 = MagicMock()
    eval2.eval_configs_filter_id = "tag::golden_set2"

    score2 = MagicMock()
    score2.name = "Duplicate Score"  # Same name as eval1
    score2.instruction = "Score 2 instruction"
    score2.type = "five_star"
    eval2.output_scores = [score2]

    with (
        patch("kiln_server.task_api.project_from_id") as mock_project_from_id,
        patch("kiln_ai.datamodel.Task.evals") as mock_evals,
    ):
        mock_project_from_id.return_value = project
        mock_evals.return_value = [eval1, eval2]

        response = client.get(
            f"/api/projects/{project.id}/tasks/{task.id}/rating_options"
        )

    assert response.status_code == 200
    res = response.json()
    assert len(res["options"]) == 1  # Should be merged into one option
    option = res["options"][0]
    assert option["requirement"]["name"] == "Duplicate Score"
    assert option["show_for_all"] is False
    assert set(option["show_for_tags"]) == {"golden_set1", "golden_set2"}
