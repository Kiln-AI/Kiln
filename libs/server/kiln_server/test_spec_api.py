from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.datamodel import Project, Task
from kiln_ai.datamodel.datamodel_enums import Priority
from kiln_ai.datamodel.spec import Spec, SpecStatus, SpecType
from kiln_ai.datamodel.spec_properties import UndesiredBehaviourProperties

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
        "description": "The system should always respond politely",
        "type": SpecType.desired_behaviour.value,
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": ["test", "important"],
        "properties": None,
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
    assert res["description"] == "The system should always respond politely"
    assert res["type"] == "desired_behaviour"
    assert res["priority"] == 1
    assert res["status"] == "active"
    assert res["tags"] == ["test", "important"]

    # Check that the spec was saved to the task/file
    specs = task.specs()
    assert len(specs) == 1
    assert specs[0].name == "Test Spec"
    assert specs[0].description == "The system should always respond politely"
    assert specs[0].type == SpecType.desired_behaviour
    assert specs[0].priority == Priority.p1
    assert specs[0].status == SpecStatus.active


def test_create_spec_with_eval_id_none(client, project_and_task):
    project, task = project_and_task

    spec_data = {
        "name": "Minimal Spec",
        "description": "No toxic content allowed",
        "type": SpecType.toxicity.value,
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": [],
        "properties": None,
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
    assert res["description"] == "No toxic content allowed"
    assert res["type"] == "toxicity"
    assert res["priority"] == 1
    assert res["status"] == "active"
    assert res["tags"] == []
    assert res["eval_id"] is None


def test_create_spec_task_not_found(client):
    spec_data = {
        "name": "Test Spec",
        "description": "System should behave correctly",
        "type": SpecType.desired_behaviour.value,
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": [],
        "properties": None,
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
        description="System should respond appropriately",
        type=SpecType.desired_behaviour,
        parent=task,
    )
    spec1.save_to_file()

    spec2 = Spec(
        name="Spec 2",
        description="No toxic responses",
        type=SpecType.toxicity,
        priority=Priority.p3,
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
        description="System should not hallucinate facts",
        type=SpecType.hallucinations,
        priority=Priority.p2,
        status=SpecStatus.active,
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
    assert res["description"] == "System should not hallucinate facts"
    assert res["type"] == "hallucinations"
    assert res["priority"] == 2
    assert res["status"] == "active"
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
        description="Original description",
        type=SpecType.desired_behaviour,
        priority=Priority.p3,
        status=SpecStatus.active,
        tags=["old_tag"],
        parent=task,
    )
    spec.save_to_file()

    update_data = {
        "name": "Updated Name",
        "description": "Updated description",
        "type": SpecType.desired_behaviour.value,
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": ["new_tag", "updated"],
        "properties": None,
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
    assert res["description"] == "Updated description"
    assert res["priority"] == 1
    assert res["status"] == "active"
    assert res["tags"] == ["new_tag", "updated"]
    assert res["type"] == "desired_behaviour"

    # Verify the spec was updated in the task/file
    updated_spec = next((s for s in task.specs() if s.id == spec.id), None)
    assert updated_spec is not None
    assert updated_spec.name == "Updated Name"
    assert updated_spec.description == "Updated description"
    assert updated_spec.priority == Priority.p1
    assert updated_spec.status == SpecStatus.active
    assert updated_spec.tags == ["new_tag", "updated"]


def test_update_spec_with_eval_id_none(client, project_and_task):
    project, task = project_and_task

    spec = Spec(
        name="Original Name",
        description="Original description",
        type=SpecType.toxicity,
        priority=Priority.p2,
        status=SpecStatus.active,
        tags=["old_tag"],
        eval_id="original_eval_id",
        parent=task,
    )
    spec.save_to_file()

    update_data = {
        "name": "Original Name",
        "description": "Original description",
        "type": SpecType.toxicity.value,
        "priority": Priority.p2,
        "status": SpecStatus.active.value,
        "tags": ["old_tag"],
        "properties": None,
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
    assert res["description"] == "Original description"
    assert res["type"] == "toxicity"
    assert res["priority"] == 2
    assert res["status"] == "active"
    assert res["eval_id"] is None


def test_update_spec_not_found(client, project_and_task):
    project, task = project_and_task

    update_data = {
        "name": "Updated Name",
        "description": "Updated description",
        "type": SpecType.desired_behaviour.value,
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": [],
        "properties": None,
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
        "description": "Answers must match reference answers",
        "type": SpecType.reference_answer_accuracy.value,
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": [],
        "properties": None,
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


def test_create_spec_with_properties(client, project_and_task):
    project, task = project_and_task

    spec_data = {
        "name": "Undesired Behaviour Spec",
        "description": "System should avoid toxic language",
        "type": SpecType.undesired_behaviour.value,
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": [],
        "properties": UndesiredBehaviourProperties(
            spec_type="undesired_behaviour",
            undesired_behaviour_guidelines="Avoid toxic language and offensive content",
            examples="Example 1: Don't use slurs\nExample 2: Don't be rude",
        ),
        "eval_id": None,
    }

    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.post(
            f"/api/projects/{project.id}/tasks/{task.id}/spec", json=spec_data
        )

    assert response.status_code == 200
    res = response.json()
    assert res["properties"] is not None
    assert res["properties"]["spec_type"] == "undesired_behaviour"
    assert (
        res["properties"]["undesired_behaviour_guidelines"]
        == "Avoid toxic language and offensive content"
    )
    assert (
        res["properties"]["examples"]
        == "Example 1: Don't use slurs\nExample 2: Don't be rude"
    )

    specs = task.specs()
    assert len(specs) == 1
    assert specs[0].properties is not None
    assert specs[0].properties["spec_type"] == "undesired_behaviour"


def test_create_spec_with_archived_status(client, project_and_task):
    """Test creating a spec with archived status."""
    project, task = project_and_task

    spec_data = {
        "name": "Archived Spec",
        "description": "This spec is archived",
        "type": SpecType.desired_behaviour.value,
        "priority": Priority.p1,
        "status": SpecStatus.archived.value,
        "tags": [],
        "properties": None,
        "eval_id": None,
    }

    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.post(
            f"/api/projects/{project.id}/tasks/{task.id}/spec", json=spec_data
        )

    assert response.status_code == 200
    res = response.json()
    assert res["name"] == "Archived Spec"
    assert res["status"] == "archived"

    specs = task.specs()
    assert len(specs) == 1
    assert specs[0].status == SpecStatus.archived


def test_update_spec_to_archived_status(client, project_and_task):
    """Test updating a spec to archived status."""
    project, task = project_and_task

    spec = Spec(
        name="Active Spec",
        description="This spec is active",
        type=SpecType.desired_behaviour,
        status=SpecStatus.active,
        parent=task,
    )
    spec.save_to_file()

    update_data = {
        "name": "Active Spec",
        "description": "This spec is active",
        "type": SpecType.desired_behaviour.value,
        "priority": Priority.p1,
        "status": SpecStatus.archived.value,
        "tags": [],
        "properties": None,
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
    assert res["status"] == "archived"

    updated_spec = next((s for s in task.specs() if s.id == spec.id), None)
    assert updated_spec is not None
    assert updated_spec.status == SpecStatus.archived


def test_get_spec_with_archived_status(client, project_and_task):
    """Test getting a spec with archived status."""
    project, task = project_and_task

    spec = Spec(
        name="Archived Spec",
        description="This spec is archived",
        type=SpecType.desired_behaviour,
        status=SpecStatus.archived,
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
    assert res["name"] == "Archived Spec"
    assert res["status"] == "archived"


# Validation error tests (422 responses)


def test_create_spec_missing_name(client, project_and_task):
    project, task = project_and_task

    spec_data = {
        "description": "The system should always respond politely",
        "type": SpecType.desired_behaviour.value,
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": [],
        "properties": None,
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


def test_create_spec_missing_description(client, project_and_task):
    project, task = project_and_task

    spec_data = {
        "name": "Test Spec",
        "type": SpecType.desired_behaviour.value,
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": [],
        "properties": None,
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
        error["loc"] == ["body", "description"] and error["type"] == "missing"
        for error in res["source_errors"]
    )


def test_create_spec_missing_type(client, project_and_task):
    project, task = project_and_task

    spec_data = {
        "name": "Test Spec",
        "description": "The system should always respond politely",
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": [],
        "properties": None,
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
        "description": "The system should always respond politely",
        "type": SpecType.desired_behaviour.value,
        "status": SpecStatus.active.value,
        "tags": [],
        "properties": None,
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
        "description": "The system should always respond politely",
        "type": SpecType.desired_behaviour.value,
        "priority": Priority.p1,
        "tags": [],
        "properties": None,
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
        "description": "The system should always respond politely",
        "type": SpecType.desired_behaviour.value,
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "properties": None,
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
        "description": "The system should always respond politely",
        "type": "invalid_type_value",
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": [],
        "properties": None,
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
        "description": "The system should always respond politely",
        "type": SpecType.desired_behaviour.value,
        "priority": "p99",
        "status": SpecStatus.active.value,
        "tags": [],
        "properties": None,
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
        "description": "The system should always respond politely",
        "type": SpecType.desired_behaviour.value,
        "priority": Priority.p1,
        "status": "pending",
        "tags": [],
        "properties": None,
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
        "description": "The system should always respond politely",
        "type": SpecType.desired_behaviour.value,
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": [],
        "properties": None,
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
        "description": "The system should always respond politely",
        "type": SpecType.desired_behaviour.value,
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": "not_a_list",
        "properties": None,
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


def test_create_spec_empty_string_in_tags(client, project_and_task):
    project, task = project_and_task

    spec_data = {
        "name": "Test Spec",
        "description": "The system should always respond politely",
        "type": SpecType.desired_behaviour.value,
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": [""],
        "properties": None,
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
        "empty strings" in error.get("msg", "").lower()
        for error in res["source_errors"]
    )


def test_create_spec_tag_with_space(client, project_and_task):
    project, task = project_and_task

    spec_data = {
        "name": "Test Spec",
        "description": "The system should always respond politely",
        "type": SpecType.desired_behaviour.value,
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": ["tag with space"],
        "properties": None,
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
        (
            "spaces" in error.get("msg", "").lower()
            or "underscores" in error.get("msg", "").lower()
        )
        for error in res["source_errors"]
    )


def test_update_spec_missing_required_fields(client, project_and_task):
    project, task = project_and_task

    spec = Spec(
        name="Test Spec",
        description="System should behave correctly",
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
        description="System should behave correctly",
        type=SpecType.desired_behaviour,
        parent=task,
    )
    spec.save_to_file()

    update_data = {
        "name": "Test Spec",
        "description": "System should behave correctly",
        "type": SpecType.desired_behaviour.value,
        "priority": "critical",
        "status": SpecStatus.active.value,
        "tags": [],
        "properties": None,
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
        description="System should behave correctly",
        type=SpecType.desired_behaviour,
        parent=task,
    )
    spec.save_to_file()

    update_data = {
        "name": "Test Spec",
        "description": "System should behave correctly",
        "type": SpecType.desired_behaviour.value,
        "priority": Priority.p1,
        "status": "finished",
        "tags": [],
        "properties": None,
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
        description="System should behave correctly",
        type=SpecType.desired_behaviour,
        parent=task,
    )
    spec.save_to_file()

    update_data = {
        "name": 12345,
        "description": "System should behave correctly",
        "type": SpecType.desired_behaviour.value,
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": [],
        "properties": None,
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
        description="System should behave correctly",
        type=SpecType.desired_behaviour,
        parent=task,
    )
    spec.save_to_file()

    update_data = {
        "name": "Test Spec",
        "description": "System should behave correctly",
        "type": SpecType.desired_behaviour.value,
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": {"not": "a list"},
        "properties": None,
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
