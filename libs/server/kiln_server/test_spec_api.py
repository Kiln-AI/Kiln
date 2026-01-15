from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.datamodel import Project, Task
from kiln_ai.datamodel.datamodel_enums import Priority
from kiln_ai.datamodel.eval import Eval, EvalOutputScore, TaskOutputRatingType
from kiln_ai.datamodel.spec import Spec, SpecStatus
from kiln_ai.datamodel.spec_properties import (
    DesiredBehaviourProperties,
    HallucinationsProperties,
    SpecType,
    ToneProperties,
    ToxicityProperties,
)

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


def create_tone_properties_dict():
    """Helper to create valid tone properties for API tests."""
    return {
        "spec_type": SpecType.tone.value,
        "core_requirement": "Test instruction",
        "tone_description": "Professional and friendly",
    }


def create_toxicity_properties_dict():
    """Helper to create valid toxicity properties for API tests."""
    return {
        "spec_type": SpecType.toxicity.value,
        "core_requirement": "Test instruction",
        "toxicity_examples": "Example toxicity content",
    }


def create_reference_answer_accuracy_properties_dict():
    """Helper to create valid reference answer accuracy properties for API tests."""
    return {
        "spec_type": SpecType.reference_answer_accuracy.value,
        "core_requirement": "Test instruction",
        "reference_answer_accuracy_description": "Must match reference",
        "accurate_examples": "Accurate example",
        "inaccurate_examples": "Inaccurate example",
    }


@pytest.fixture
def sample_tone_properties():
    """Fixture for creating complete ToneProperties objects for direct Spec creation."""
    return ToneProperties(
        spec_type=SpecType.tone,
        core_requirement="Test instruction",
        tone_description="Professional and friendly",
    )


@pytest.fixture
def sample_hallucinations_properties():
    """Fixture for creating complete HallucinationsProperties objects."""
    return HallucinationsProperties(
        spec_type=SpecType.hallucinations,
        core_requirement="Test instruction",
        hallucinations_examples="Example hallucination",
    )


@pytest.fixture
def sample_toxicity_properties():
    """Fixture for creating complete ToxicityProperties objects."""
    return ToxicityProperties(
        spec_type=SpecType.toxicity,
        core_requirement="Test instruction",
        toxicity_examples="Example toxicity",
    )


@pytest.fixture
def sample_desired_behaviour_properties():
    """Fixture for creating complete DesiredBehaviourProperties objects."""
    return DesiredBehaviourProperties(
        spec_type=SpecType.desired_behaviour,
        core_requirement="Test instruction",
        desired_behaviour_description="Avoid toxic content",
        correct_behaviour_examples=None,
        incorrect_behaviour_examples=None,
    )


def test_create_spec_success(client, project_and_task):
    project, task = project_and_task

    spec_data = {
        "name": "Test Spec",
        "definition": "The system should always respond politely",
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": ["test", "important"],
        "properties": create_tone_properties_dict(),
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
    assert res["properties"]["spec_type"] == SpecType.tone.value
    assert res["priority"] == 1
    assert res["status"] == "active"
    assert res["tags"] == ["test", "important"]

    # Check that the spec was saved to the task/file
    specs = task.specs()
    assert len(specs) == 1
    assert specs[0].name == "Test Spec"
    assert specs[0].definition == "The system should always respond politely"
    assert specs[0].properties["spec_type"] == SpecType.tone
    assert specs[0].priority == Priority.p1
    assert specs[0].status == SpecStatus.active


def test_create_spec_with_eval_id_none(client, project_and_task):
    project, task = project_and_task

    spec_data = {
        "name": "Minimal Spec",
        "definition": "No toxic content allowed",
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": [],
        "properties": create_toxicity_properties_dict(),
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
    assert res["properties"]["spec_type"] == SpecType.toxicity.value
    assert res["priority"] == 1
    assert res["status"] == "active"
    assert res["tags"] == []
    assert res["eval_id"] is None


def test_create_spec_task_not_found(client):
    spec_data = {
        "name": "Test Spec",
        "definition": "System should behave correctly",
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": [],
        "properties": create_tone_properties_dict(),
        "eval_id": None,
    }

    response = client.post(
        "/api/projects/project-id/tasks/fake-task-id/spec", json=spec_data
    )
    assert response.status_code == 404


def test_get_specs_success(
    client, project_and_task, sample_tone_properties, sample_toxicity_properties
):
    project, task = project_and_task

    spec1 = Spec(
        name="Spec 1",
        definition="System should respond appropriately",
        properties=sample_tone_properties,
        parent=task,
    )
    spec1.save_to_file()

    spec2 = Spec(
        name="Spec 2",
        definition="No toxic responses",
        priority=Priority.p3,
        properties=sample_toxicity_properties,
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


def test_get_spec_success(client, project_and_task, sample_hallucinations_properties):
    project, task = project_and_task

    spec = Spec(
        name="Test Spec",
        definition="System should not hallucinate facts",
        priority=Priority.p2,
        status=SpecStatus.active,
        tags=["validation", "safety"],
        properties=sample_hallucinations_properties,
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
    assert res["properties"]["spec_type"] == SpecType.hallucinations.value
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


def test_update_spec_success(client, project_and_task, sample_tone_properties):
    project, task = project_and_task

    spec = Spec(
        name="Original Name",
        definition="Original definition",
        priority=Priority.p3,
        status=SpecStatus.active,
        tags=["old_tag"],
        properties=sample_tone_properties,
        parent=task,
    )
    spec.save_to_file()

    update_data = {
        "name": "Updated Name",
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
    # Verify other fields remain unchanged
    assert res["definition"] == "Original definition"
    assert res["priority"] == 3
    assert res["status"] == "active"
    assert res["tags"] == ["old_tag"]
    assert res["properties"]["spec_type"] == SpecType.tone.value

    # Verify the spec was updated in the task/file
    updated_spec = next((s for s in task.specs() if s.id == spec.id), None)
    assert updated_spec is not None
    assert updated_spec.name == "Updated Name"
    # Verify other fields remain unchanged
    assert updated_spec.definition == "Original definition"
    assert updated_spec.priority == Priority.p3
    assert updated_spec.status == SpecStatus.active
    assert updated_spec.tags == ["old_tag"]


def test_update_spec_with_existing_eval_id(
    client, project_and_task, sample_toxicity_properties
):
    """Test that updating a spec's name doesn't affect its eval_id."""
    project, task = project_and_task

    spec = Spec(
        name="Original Name",
        definition="Original definition",
        priority=Priority.p2,
        status=SpecStatus.active,
        tags=["old_tag"],
        eval_id="original_eval_id",
        properties=sample_toxicity_properties,
        parent=task,
    )
    spec.save_to_file()

    update_data = {
        "name": "Updated Name",
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
    # Verify other fields including eval_id remain unchanged
    assert res["definition"] == "Original definition"
    assert res["properties"]["spec_type"] == SpecType.toxicity.value
    assert res["priority"] == 2
    assert res["status"] == "active"
    assert res["eval_id"] == "original_eval_id"


def test_update_spec_tags_only(client, project_and_task, sample_tone_properties):
    """Test updating only tags field (save_tags use case)."""
    project, task = project_and_task

    spec = Spec(
        name="Original Name",
        definition="Original definition",
        priority=Priority.p3,
        status=SpecStatus.active,
        tags=["old_tag"],
        eval_id="original_eval_id",
        properties=sample_tone_properties,
        parent=task,
    )
    spec.save_to_file()

    # Simulate save_tags function sending only tags
    update_data = {
        "tags": ["new_tag", "updated_tag"],
    }

    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.patch(
            f"/api/projects/{project.id}/tasks/{task.id}/specs/{spec.id}",
            json=update_data,
        )

    assert response.status_code == 200
    res = response.json()
    assert res["tags"] == ["new_tag", "updated_tag"]
    # Verify other fields remain unchanged
    assert res["name"] == "Original Name"
    assert res["definition"] == "Original definition"
    assert res["priority"] == 3
    assert res["status"] == "active"
    assert res["eval_id"] == "original_eval_id"

    # Verify the change persisted
    updated_spec = next((s for s in task.specs() if s.id == spec.id), None)
    assert updated_spec is not None
    assert updated_spec.tags == ["new_tag", "updated_tag"]


def test_update_spec_status_only(client, project_and_task, sample_tone_properties):
    """Test updating only status field (archive use case)."""
    project, task = project_and_task

    spec = Spec(
        name="Test Spec",
        definition="Test definition",
        priority=Priority.p2,
        status=SpecStatus.active,
        tags=["test"],
        properties=sample_tone_properties,
        parent=task,
    )
    spec.save_to_file()

    # Update only status to archived
    update_data = {
        "status": SpecStatus.archived.value,
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
    # Verify other fields remain unchanged
    assert res["name"] == "Test Spec"
    assert res["definition"] == "Test definition"
    assert res["priority"] == 2
    assert res["tags"] == ["test"]

    # Verify the change persisted
    updated_spec = next((s for s in task.specs() if s.id == spec.id), None)
    assert updated_spec is not None
    assert updated_spec.status == SpecStatus.archived


def test_update_spec_not_found(client, project_and_task):
    project, task = project_and_task

    update_data = {
        "name": "Updated Name",
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
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": [],
        "properties": create_reference_answer_accuracy_properties_dict(),
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
        "name": "Desired Behaviour Spec",
        "definition": "System should avoid toxic language",
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": [],
        "properties": {
            "spec_type": SpecType.desired_behaviour.value,
            "core_requirement": "Test instruction",
            "desired_behaviour_description": "Avoid toxic language and offensive content",
            "incorrect_behaviour_examples": "Example 1: Don't use slurs\nExample 2: Don't be rude",
        },
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
    assert res["properties"]["spec_type"] == SpecType.desired_behaviour.value
    assert (
        res["properties"]["desired_behaviour_description"]
        == "Avoid toxic language and offensive content"
    )
    assert (
        res["properties"]["incorrect_behaviour_examples"]
        == "Example 1: Don't use slurs\nExample 2: Don't be rude"
    )

    specs = task.specs()
    assert len(specs) == 1
    assert specs[0].properties is not None
    assert specs[0].properties["spec_type"] == SpecType.desired_behaviour


def test_create_spec_with_archived_status(client, project_and_task):
    """Test creating a spec with archived status."""
    project, task = project_and_task

    spec_data = {
        "name": "Archived Spec",
        "definition": "This spec is archived",
        "priority": Priority.p1,
        "status": SpecStatus.archived.value,
        "tags": [],
        "properties": create_tone_properties_dict(),
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


def test_get_spec_with_archived_status(
    client, project_and_task, sample_tone_properties
):
    """Test getting a spec with archived status."""
    project, task = project_and_task

    spec = Spec(
        name="Archived Spec",
        definition="This spec is archived",
        status=SpecStatus.archived,
        properties=sample_tone_properties,
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
        "definition": "The system should always respond politely",
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": [],
        "properties": create_tone_properties_dict(),
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
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": [],
        "properties": create_tone_properties_dict(),
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


def test_create_spec_missing_properties(client, project_and_task):
    project, task = project_and_task

    spec_data = {
        "name": "Test Spec",
        "definition": "The system should always respond politely",
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
    # Properties is required now, so missing it gives model_attributes_type error
    assert any(error["loc"] == ["body", "properties"] for error in res["source_errors"])


def test_create_spec_missing_priority(client, project_and_task):
    project, task = project_and_task

    spec_data = {
        "name": "Test Spec",
        "definition": "The system should always respond politely",
        "status": SpecStatus.active.value,
        "tags": [],
        "properties": create_tone_properties_dict(),
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
        "priority": Priority.p1,
        "tags": [],
        "properties": create_tone_properties_dict(),
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
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "properties": create_tone_properties_dict(),
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


def test_create_spec_invalid_spec_type_in_properties(client, project_and_task):
    project, task = project_and_task

    spec_data = {
        "name": "Test Spec",
        "definition": "The system should always respond politely",
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": [],
        "properties": {"spec_type": "invalid_type_value"},
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
    # Check that properties validation failed with invalid spec_type
    assert any(
        "properties" in str(error.get("loc", [])) for error in res["source_errors"]
    )


def test_create_spec_invalid_priority_enum(client, project_and_task):
    project, task = project_and_task

    spec_data = {
        "name": "Test Spec",
        "definition": "The system should always respond politely",
        "priority": "p99",
        "status": SpecStatus.active.value,
        "tags": [],
        "properties": create_tone_properties_dict(),
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
        "priority": Priority.p1,
        "status": "pending",
        "tags": [],
        "properties": create_tone_properties_dict(),
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
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": [],
        "properties": create_tone_properties_dict(),
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
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": "not_a_list",
        "properties": create_tone_properties_dict(),
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
        "definition": "The system should always respond politely",
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": [""],
        "properties": create_tone_properties_dict(),
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
        "definition": "The system should always respond politely",
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": ["tag with space"],
        "properties": create_tone_properties_dict(),
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


def test_update_spec_invalid_name_type(
    client, project_and_task, sample_tone_properties
):
    """Test that updating a spec with invalid name type fails."""
    project, task = project_and_task

    spec = Spec(
        name="Test Spec",
        definition="System should behave correctly",
        properties=sample_tone_properties,
        parent=task,
    )
    spec.save_to_file()

    update_data = {
        "name": 12345,
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


def test_create_spec_with_empty_tool_function_name(client, project_and_task):
    project, task = project_and_task

    spec_data = {
        "name": "Tool Use Spec",
        "definition": "Tool use validation test",
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": [],
        "properties": {
            "spec_type": "appropriate_tool_use",
            "core_requirement": "Test instruction",
            "tool_id": "test_tool",
            "tool_function_name": "",
            "tool_use_guidelines": "Use this tool when needed",
            "appropriate_tool_use_examples": "examples",
            "inappropriate_tool_use_examples": "examples",
        },
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
        "tool_function_name" in error.get("msg", "").lower()
        for error in res["source_errors"]
    )


def test_create_spec_with_empty_tool_use_guidelines(client, project_and_task):
    project, task = project_and_task

    spec_data = {
        "name": "Tool Use Spec",
        "definition": "Tool use validation test",
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": [],
        "properties": {
            "spec_type": "appropriate_tool_use",
            "core_requirement": "Test instruction",
            "tool_id": "test_tool",
            "tool_function_name": "test_tool_function",
            "tool_use_guidelines": "",
            "appropriate_tool_use_examples": "examples",
            "inappropriate_tool_use_examples": "examples",
        },
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
        "tool_use_guidelines" in error.get("msg", "").lower()
        for error in res["source_errors"]
    )


def test_create_spec_with_empty_behavior_description(client, project_and_task):
    project, task = project_and_task

    spec_data = {
        "name": "Desired Behaviour Spec",
        "definition": "Desired behaviour validation test",
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": [],
        "properties": {
            "spec_type": "desired_behaviour",
            "core_requirement": "Test instruction",
            "desired_behaviour_description": "",
            "incorrect_behaviour_examples": "Example 1: Don't do this",
        },
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
        "desired_behaviour_description" in error.get("msg", "").lower()
        for error in res["source_errors"]
    )


def test_create_spec_with_empty_core_requirement(client, project_and_task):
    project, task = project_and_task

    spec_data = {
        "name": "Desired Behaviour Spec",
        "definition": "Desired behaviour validation test",
        "priority": Priority.p1,
        "status": SpecStatus.active.value,
        "tags": [],
        "properties": {
            "spec_type": "desired_behaviour",
            "core_requirement": "",
            "desired_behaviour_description": "Avoid toxic content",
        },
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
        "core_requirement" in error.get("msg", "").lower()
        for error in res["source_errors"]
    )


def test_delete_spec_success(client, project_and_task, sample_tone_properties):
    project, task = project_and_task

    spec = Spec(
        name="Test Spec",
        definition="System should behave correctly",
        properties=sample_tone_properties,
        parent=task,
    )
    spec.save_to_file()

    specs = task.specs()
    assert len(specs) == 1

    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.delete(
            f"/api/projects/{project.id}/tasks/{task.id}/specs/{spec.id}"
        )

    assert response.status_code == 200

    specs = task.specs()
    assert len(specs) == 0


def test_delete_spec_not_found(client, project_and_task):
    project, task = project_and_task

    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.delete(
            f"/api/projects/{project.id}/tasks/{task.id}/specs/nonexistent_id"
        )

    assert response.status_code == 404
    assert "Spec not found" in response.json()["message"]


def test_delete_spec_with_associated_eval(
    client, project_and_task, sample_tone_properties
):
    """Test that deleting a spec also deletes its associated eval."""
    project, task = project_and_task

    # Create an eval with required fields (using 'rag' template to avoid needing eval_configs_filter_id)
    eval = Eval(
        name="Test Eval",
        description="Test eval description",
        template="rag",
        eval_set_filter_id="tag::test_eval",
        output_scores=[
            EvalOutputScore(
                name="Quality",
                type=TaskOutputRatingType.five_star,
            )
        ],
        parent=task,
    )
    eval.save_to_file()

    # Create a spec with the eval_id
    spec = Spec(
        name="Test Spec",
        definition="System should behave correctly",
        properties=sample_tone_properties,
        eval_id=eval.id,
        parent=task,
    )
    spec.save_to_file()

    # Verify both exist
    specs = task.specs()
    evals = task.evals()
    assert len(specs) == 1
    assert len(evals) == 1

    # Delete the spec
    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.delete(
            f"/api/projects/{project.id}/tasks/{task.id}/specs/{spec.id}"
        )

    assert response.status_code == 200

    # Verify both spec and eval are deleted
    specs = task.specs()
    evals = task.evals()
    assert len(specs) == 0
    assert len(evals) == 0


def test_delete_spec_without_associated_eval(
    client, project_and_task, sample_tone_properties
):
    """Test that deleting a spec without an eval works correctly."""
    project, task = project_and_task

    spec = Spec(
        name="Test Spec",
        definition="System should behave correctly",
        properties=sample_tone_properties,
        eval_id=None,
        parent=task,
    )
    spec.save_to_file()

    specs = task.specs()
    assert len(specs) == 1

    with patch("kiln_server.spec_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.delete(
            f"/api/projects/{project.id}/tasks/{task.id}/specs/{spec.id}"
        )

    assert response.status_code == 200

    specs = task.specs()
    assert len(specs) == 0
