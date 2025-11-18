from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.datamodel import Project, Task
from kiln_ai.datamodel.spec import Spec, SpecPriority, SpecStatus, SpecType

from kiln_server.custom_errors import connect_custom_errors
from kiln_server.spec_api import connect_spec_api


@pytest.fixture
def app():
    app = FastAPI()
    connect_spec_api(app)
    connect_custom_errors(app)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def project_and_task(tmp_path):
    project_path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()

    project = Project(name="Test Project", path=project_path)
    project.save_to_file()
    task = Task(
        name="Test Task",
        instruction="This is a test instruction",
        description="This is a test task",
        parent=project,
    )
    task.save_to_file()

    return project, task


def test_create_spec_success(client, project_and_task):
    project, task = project_and_task

    spec_data = {
        "name": "Test Spec",
        "definition": "The system should always respond politely",
        "type": "desired_behaviour",
        "priority": "high",
        "status": "not_started",
        "tags": ["test", "important"],
        "eval_id": None,
    }

    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.post(
            f"/api/projects/{project.id}/tasks/{task.id}/spec", json=spec_data
        )

    assert response.status_code == 200
    res = response.json()
    assert res["name"] == "Test Spec"
    assert res["definition"] == "The system should always respond politely"
    assert res["type"] == "desired_behaviour"
    assert res["priority"] == "high"
    assert res["status"] == "not_started"
    assert res["tags"] == ["test", "important"]

    # Check that the spec was saved to the task/file
    specs = task.specs()
    assert len(specs) == 1
    assert specs[0].name == "Test Spec"
    assert specs[0].definition == "The system should always respond politely"
    assert specs[0].type == SpecType.desired_behaviour
    assert specs[0].priority == SpecPriority.high
    assert specs[0].status == SpecStatus.not_started


def test_create_spec_with_eval_id_none(client, project_and_task):
    project, task = project_and_task

    spec_data = {
        "name": "Minimal Spec",
        "definition": "No toxic content allowed",
        "type": "toxicity",
        "priority": "high",
        "status": "not_started",
        "tags": [],
        "eval_id": None,
    }

    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.post(
            f"/api/projects/{project.id}/tasks/{task.id}/spec", json=spec_data
        )

    assert response.status_code == 200
    res = response.json()
    assert res["name"] == "Minimal Spec"
    assert res["definition"] == "No toxic content allowed"
    assert res["type"] == "toxicity"
    assert res["priority"] == "high"
    assert res["status"] == "not_started"
    assert res["tags"] == []
    assert res["eval_id"] is None


def test_create_spec_task_not_found(client):
    spec_data = {
        "name": "Test Spec",
        "definition": "System should behave correctly",
        "type": "desired_behaviour",
        "priority": "high",
        "status": "not_started",
        "tags": [],
        "eval_id": None,
    }

    response = client.post(
        "/api/projects/project-id/tasks/fake-task-id/spec", json=spec_data
    )
    assert response.status_code == 404


def test_get_specs_success(client, project_and_task):
    project, task = project_and_task

    spec1 = Spec(
        name="Spec 1",
        definition="System should respond appropriately",
        type=SpecType.desired_behaviour,
        parent=task,
    )
    spec1.save_to_file()

    spec2 = Spec(
        name="Spec 2",
        definition="No toxic responses",
        type=SpecType.toxicity,
        priority=SpecPriority.low,
        parent=task,
    )
    spec2.save_to_file()

    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.get(f"/api/projects/{project.id}/tasks/{task.id}/specs")

    assert response.status_code == 200
    res = response.json()
    assert isinstance(res, list)
    assert len(res) == 2
    spec_names = {spec["name"] for spec in res}
    assert spec_names == {"Spec 1", "Spec 2"}


def test_get_specs_empty(client, project_and_task):
    project, task = project_and_task

    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.get(f"/api/projects/{project.id}/tasks/{task.id}/specs")

    assert response.status_code == 200
    res = response.json()
    assert isinstance(res, list)
    assert len(res) == 0


def test_get_specs_task_not_found(client):
    response = client.get("/api/projects/project-id/tasks/fake-task-id/specs")
    assert response.status_code == 404


def test_get_spec_success(client, project_and_task):
    project, task = project_and_task

    spec = Spec(
        name="Test Spec",
        definition="System should not hallucinate facts",
        type=SpecType.hallucinations,
        priority=SpecPriority.medium,
        status=SpecStatus.in_progress,
        tags=["validation", "safety"],
        parent=task,
    )
    spec.save_to_file()

    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.get(
            f"/api/projects/{project.id}/tasks/{task.id}/specs/{spec.id}"
        )

    assert response.status_code == 200
    res = response.json()
    assert res["name"] == "Test Spec"
    assert res["definition"] == "System should not hallucinate facts"
    assert res["type"] == "hallucinations"
    assert res["priority"] == "medium"
    assert res["status"] == "in_progress"
    assert res["tags"] == ["validation", "safety"]


def test_get_spec_not_found(client, project_and_task):
    project, task = project_and_task

    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.get(
            f"/api/projects/{project.id}/tasks/{task.id}/specs/nonexistent_id"
        )

    assert response.status_code == 404
    assert "Spec not found" in response.json()["message"]


def test_update_spec_success(client, project_and_task):
    project, task = project_and_task

    spec = Spec(
        name="Original Name",
        definition="Original definition",
        type=SpecType.desired_behaviour,
        priority=SpecPriority.low,
        status=SpecStatus.not_started,
        tags=["old_tag"],
        parent=task,
    )
    spec.save_to_file()

    update_data = {
        "name": "Updated Name",
        "definition": "Updated definition",
        "priority": "high",
        "status": "complete",
        "tags": ["new_tag", "updated"],
        "eval_id": None,
    }

    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.patch(
            f"/api/projects/{project.id}/tasks/{task.id}/specs/{spec.id}",
            json=update_data,
        )

    assert response.status_code == 200
    res = response.json()
    assert res["name"] == "Updated Name"
    assert res["definition"] == "Updated definition"
    assert res["priority"] == "high"
    assert res["status"] == "complete"
    assert res["tags"] == ["new_tag", "updated"]
    assert res["type"] == "desired_behaviour"

    # Verify the spec was updated in the task/file
    updated_spec = next((s for s in task.specs() if s.id == spec.id), None)
    assert updated_spec is not None
    assert updated_spec.name == "Updated Name"
    assert updated_spec.definition == "Updated definition"
    assert updated_spec.priority == SpecPriority.high
    assert updated_spec.status == SpecStatus.complete
    assert updated_spec.tags == ["new_tag", "updated"]


def test_update_spec_with_eval_id_none(client, project_and_task):
    project, task = project_and_task

    spec = Spec(
        name="Original Name",
        definition="Original definition",
        type=SpecType.toxicity,
        priority=SpecPriority.medium,
        status=SpecStatus.not_started,
        tags=["old_tag"],
        eval_id="original_eval_id",
        parent=task,
    )
    spec.save_to_file()

    update_data = {
        "name": "Original Name",
        "definition": "Original definition",
        "priority": "medium",
        "status": "in_progress",
        "tags": ["old_tag"],
        "eval_id": None,
    }

    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.patch(
            f"/api/projects/{project.id}/tasks/{task.id}/specs/{spec.id}",
            json=update_data,
        )

    assert response.status_code == 200
    res = response.json()
    assert res["name"] == "Original Name"
    assert res["definition"] == "Original definition"
    assert res["type"] == "toxicity"
    assert res["priority"] == "medium"
    assert res["status"] == "in_progress"
    assert res["eval_id"] is None


def test_update_spec_not_found(client, project_and_task):
    project, task = project_and_task

    update_data = {
        "name": "Updated Name",
        "definition": "Updated definition",
        "priority": "high",
        "status": "not_started",
        "tags": [],
        "eval_id": None,
    }

    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.patch(
            f"/api/projects/{project.id}/tasks/{task.id}/specs/nonexistent_id",
            json=update_data,
        )

    assert response.status_code == 404
    assert "Spec not found" in response.json()["message"]


def test_create_spec_with_eval_id(client, project_and_task):
    project, task = project_and_task

    spec_data = {
        "name": "Eval Spec",
        "definition": "Answers must match reference answers",
        "type": "reference_answer_accuracy",
        "priority": "high",
        "status": "not_started",
        "tags": [],
        "eval_id": "test_eval_123",
    }

    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.post(
            f"/api/projects/{project.id}/tasks/{task.id}/spec", json=spec_data
        )

    assert response.status_code == 200
    res = response.json()
    assert res["eval_id"] == "test_eval_123"

    specs = task.specs()
    assert len(specs) == 1
    assert specs[0].eval_id == "test_eval_123"


# Validation error tests (422 responses)


def test_create_spec_missing_name(client, project_and_task):
    project, task = project_and_task

    spec_data = {
        "definition": "The system should always respond politely",
        "type": "desired_behaviour",
        "priority": "high",
        "status": "not_started",
        "tags": [],
        "eval_id": None,
    }

    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.post(
            f"/api/projects/{project.id}/tasks/{task.id}/spec", json=spec_data
        )

    assert response.status_code == 422
    res = response.json()
    assert "source_errors" in res
    assert any(
        error["loc"] == ["body", "name"] and error["type"] == "missing"
        for error in res["source_errors"]
    )


def test_create_spec_missing_definition(client, project_and_task):
    project, task = project_and_task

    spec_data = {
        "name": "Test Spec",
        "type": "desired_behaviour",
        "priority": "high",
        "status": "not_started",
        "tags": [],
        "eval_id": None,
    }

    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.post(
            f"/api/projects/{project.id}/tasks/{task.id}/spec", json=spec_data
        )

    assert response.status_code == 422
    res = response.json()
    assert "source_errors" in res
    assert any(
        error["loc"] == ["body", "definition"] and error["type"] == "missing"
        for error in res["source_errors"]
    )


def test_create_spec_missing_type(client, project_and_task):
    project, task = project_and_task

    spec_data = {
        "name": "Test Spec",
        "definition": "The system should always respond politely",
        "priority": "high",
        "status": "not_started",
        "tags": [],
        "eval_id": None,
    }

    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.post(
            f"/api/projects/{project.id}/tasks/{task.id}/spec", json=spec_data
        )

    assert response.status_code == 422
    res = response.json()
    assert "source_errors" in res
    assert any(
        error["loc"] == ["body", "type"] and error["type"] == "missing"
        for error in res["source_errors"]
    )


def test_create_spec_missing_priority(client, project_and_task):
    project, task = project_and_task

    spec_data = {
        "name": "Test Spec",
        "definition": "The system should always respond politely",
        "type": "desired_behaviour",
        "status": "not_started",
        "tags": [],
        "eval_id": None,
    }

    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.post(
            f"/api/projects/{project.id}/tasks/{task.id}/spec", json=spec_data
        )

    assert response.status_code == 422
    res = response.json()
    assert "source_errors" in res
    assert any(
        error["loc"] == ["body", "priority"] and error["type"] == "missing"
        for error in res["source_errors"]
    )


def test_create_spec_missing_status(client, project_and_task):
    project, task = project_and_task

    spec_data = {
        "name": "Test Spec",
        "definition": "The system should always respond politely",
        "type": "desired_behaviour",
        "priority": "high",
        "tags": [],
        "eval_id": None,
    }

    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.post(
            f"/api/projects/{project.id}/tasks/{task.id}/spec", json=spec_data
        )

    assert response.status_code == 422
    res = response.json()
    assert "source_errors" in res
    assert any(
        error["loc"] == ["body", "status"] and error["type"] == "missing"
        for error in res["source_errors"]
    )


def test_create_spec_missing_tags(client, project_and_task):
    project, task = project_and_task

    spec_data = {
        "name": "Test Spec",
        "definition": "The system should always respond politely",
        "type": "desired_behaviour",
        "priority": "high",
        "status": "not_started",
        "eval_id": None,
    }

    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.post(
            f"/api/projects/{project.id}/tasks/{task.id}/spec", json=spec_data
        )

    assert response.status_code == 422
    res = response.json()
    assert "source_errors" in res
    assert any(
        error["loc"] == ["body", "tags"] and error["type"] == "missing"
        for error in res["source_errors"]
    )


def test_create_spec_invalid_type_enum(client, project_and_task):
    project, task = project_and_task

    spec_data = {
        "name": "Test Spec",
        "definition": "The system should always respond politely",
        "type": "invalid_type_value",
        "priority": "high",
        "status": "not_started",
        "tags": [],
        "eval_id": None,
    }

    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.post(
            f"/api/projects/{project.id}/tasks/{task.id}/spec", json=spec_data
        )

    assert response.status_code == 422
    res = response.json()
    assert "source_errors" in res
    assert any(
        error["loc"] == ["body", "type"] and error["type"] == "enum"
        for error in res["source_errors"]
    )


def test_create_spec_invalid_priority_enum(client, project_and_task):
    project, task = project_and_task

    spec_data = {
        "name": "Test Spec",
        "definition": "The system should always respond politely",
        "type": "desired_behaviour",
        "priority": "ultra_high",
        "status": "not_started",
        "tags": [],
        "eval_id": None,
    }

    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.post(
            f"/api/projects/{project.id}/tasks/{task.id}/spec", json=spec_data
        )

    assert response.status_code == 422
    res = response.json()
    assert "source_errors" in res
    assert any(
        error["loc"] == ["body", "priority"] and error["type"] == "enum"
        for error in res["source_errors"]
    )


def test_create_spec_invalid_status_enum(client, project_and_task):
    project, task = project_and_task

    spec_data = {
        "name": "Test Spec",
        "definition": "The system should always respond politely",
        "type": "desired_behaviour",
        "priority": "high",
        "status": "pending",
        "tags": [],
        "eval_id": None,
    }

    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.post(
            f"/api/projects/{project.id}/tasks/{task.id}/spec", json=spec_data
        )

    assert response.status_code == 422
    res = response.json()
    assert "source_errors" in res
    assert any(
        error["loc"] == ["body", "status"] and error["type"] == "enum"
        for error in res["source_errors"]
    )


def test_create_spec_invalid_name_type(client, project_and_task):
    project, task = project_and_task

    spec_data = {
        "name": 12345,
        "definition": "The system should always respond politely",
        "type": "desired_behaviour",
        "priority": "high",
        "status": "not_started",
        "tags": [],
        "eval_id": None,
    }

    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.post(
            f"/api/projects/{project.id}/tasks/{task.id}/spec", json=spec_data
        )

    assert response.status_code == 422
    res = response.json()
    assert "source_errors" in res
    assert any(error["loc"] == ["body", "name"] for error in res["source_errors"])


def test_create_spec_invalid_tags_type(client, project_and_task):
    project, task = project_and_task

    spec_data = {
        "name": "Test Spec",
        "definition": "The system should always respond politely",
        "type": "desired_behaviour",
        "priority": "high",
        "status": "not_started",
        "tags": "not_a_list",
        "eval_id": None,
    }

    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.post(
            f"/api/projects/{project.id}/tasks/{task.id}/spec", json=spec_data
        )

    assert response.status_code == 422
    res = response.json()
    assert "source_errors" in res
    assert any(error["loc"] == ["body", "tags"] for error in res["source_errors"])


def test_update_spec_missing_required_fields(client, project_and_task):
    project, task = project_and_task

    spec = Spec(
        name="Test Spec",
        definition="System should behave correctly",
        type=SpecType.desired_behaviour,
        parent=task,
    )
    spec.save_to_file()

    update_data = {"name": "Updated Name"}

    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.patch(
            f"/api/projects/{project.id}/tasks/{task.id}/specs/{spec.id}",
            json=update_data,
        )

    assert response.status_code == 422
    res = response.json()
    assert "source_errors" in res


def test_update_spec_invalid_priority_enum(client, project_and_task):
    project, task = project_and_task

    spec = Spec(
        name="Test Spec",
        definition="System should behave correctly",
        type=SpecType.desired_behaviour,
        parent=task,
    )
    spec.save_to_file()

    update_data = {
        "name": "Test Spec",
        "definition": "System should behave correctly",
        "priority": "critical",
        "status": "not_started",
        "tags": [],
        "eval_id": None,
    }

    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.patch(
            f"/api/projects/{project.id}/tasks/{task.id}/specs/{spec.id}",
            json=update_data,
        )

    assert response.status_code == 422
    res = response.json()
    assert "source_errors" in res
    assert any(
        error["loc"] == ["body", "priority"] and error["type"] == "enum"
        for error in res["source_errors"]
    )


def test_update_spec_invalid_status_enum(client, project_and_task):
    project, task = project_and_task

    spec = Spec(
        name="Test Spec",
        definition="System should behave correctly",
        type=SpecType.desired_behaviour,
        parent=task,
    )
    spec.save_to_file()

    update_data = {
        "name": "Test Spec",
        "definition": "System should behave correctly",
        "priority": "high",
        "status": "finished",
        "tags": [],
        "eval_id": None,
    }

    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.patch(
            f"/api/projects/{project.id}/tasks/{task.id}/specs/{spec.id}",
            json=update_data,
        )

    assert response.status_code == 422
    res = response.json()
    assert "source_errors" in res
    assert any(
        error["loc"] == ["body", "status"] and error["type"] == "enum"
        for error in res["source_errors"]
    )


def test_update_spec_invalid_name_type(client, project_and_task):
    project, task = project_and_task

    spec = Spec(
        name="Test Spec",
        definition="System should behave correctly",
        type=SpecType.desired_behaviour,
        parent=task,
    )
    spec.save_to_file()

    update_data = {
        "name": 12345,
        "definition": "System should behave correctly",
        "priority": "high",
        "status": "not_started",
        "tags": [],
        "eval_id": None,
    }

    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.patch(
            f"/api/projects/{project.id}/tasks/{task.id}/specs/{spec.id}",
            json=update_data,
        )

    assert response.status_code == 422
    res = response.json()
    assert "source_errors" in res
    assert any(error["loc"] == ["body", "name"] for error in res["source_errors"])


def test_update_spec_invalid_tags_type(client, project_and_task):
    project, task = project_and_task

    spec = Spec(
        name="Test Spec",
        definition="System should behave correctly",
        type=SpecType.desired_behaviour,
        parent=task,
    )
    spec.save_to_file()

    update_data = {
        "name": "Test Spec",
        "definition": "System should behave correctly",
        "priority": "high",
        "status": "not_started",
        "tags": {"not": "a list"},
        "eval_id": None,
    }

    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.patch(
            f"/api/projects/{project.id}/tasks/{task.id}/specs/{spec.id}",
            json=update_data,
        )

    assert response.status_code == 422
    res = response.json()
    assert "source_errors" in res
    assert any(error["loc"] == ["body", "tags"] for error in res["source_errors"])
