from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.datamodel import Project, Prompt, PromptGenerators, Task

from kiln_server.custom_errors import connect_custom_errors
from kiln_server.prompt_api import _prompt_generators, connect_prompt_api


@pytest.fixture
def app():
    app = FastAPI()
    connect_prompt_api(app)
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


def test_create_prompt_success(client, project_and_task):
    project, task = project_and_task

    prompt_data = {
        "name": "Test Prompt",
        "prompt": "This is a test prompt",
        "description": "This is a test prompt description",
        "chain_of_thought_instructions": "Think step by step, explaining your reasoning.",
    }

    with patch("kiln_server.prompt_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.post(
            f"/api/projects/{project.id}/task/{task.id}/prompt", json=prompt_data
        )

    assert response.status_code == 200
    res = response.json()
    assert res["name"] == "Test Prompt"
    assert res["description"] == "This is a test prompt description"
    assert res["prompt"] == "This is a test prompt"

    # Check that the prompt was saved to the task/file
    prompts = task.prompts()
    assert len(prompts) == 1
    assert prompts[0].name == "Test Prompt"
    assert prompts[0].prompt == "This is a test prompt"
    assert (
        prompts[0].chain_of_thought_instructions
        == "Think step by step, explaining your reasoning."
    )


def test_create_prompt_task_not_found(client):
    prompt_data = {
        "name": "Test Prompt",
        "prompt": "This is a test prompt",
    }

    response = client.post(
        "/api/projects/project-id/task/fake-task-id/prompt", json=prompt_data
    )
    assert response.status_code == 404


def test_get_prompts_success(client, project_and_task):
    project, task = project_and_task

    test_prompt = Prompt(
        name="Test Prompt", prompt="This is a test prompt", parent=task
    )
    test_prompt.save_to_file()

    with patch("kiln_server.prompt_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.get(f"/api/projects/{project.id}/task/{task.id}/prompts")

    assert response.status_code == 200
    res = response.json()
    assert isinstance(res, dict)
    assert "generators" in res
    assert "prompts" in res
    assert len(res["generators"]) > 0  # Should have our predefined generators
    assert len(res["prompts"]) == 1
    assert res["prompts"][0]["name"] == "Test Prompt"


def test_get_prompts_task_not_found(client):
    response = client.get("/api/projects/project-id/task/fake-task-id/prompts")
    assert response.status_code == 404


def test_prompt_generators_content():
    """Test that our predefined prompt generators have the expected structure"""
    from kiln_server.prompt_api import _prompt_generators

    # Test a few key generators
    basic = next(g for g in _prompt_generators if g.id == "simple_prompt_builder")
    assert basic.chain_of_thought is False
    assert "zero-shot" in basic.description.lower()

    cot = next(
        g
        for g in _prompt_generators
        if g.id == "simple_chain_of_thought_prompt_builder"
    )
    assert cot.chain_of_thought is True
    assert "Chain of Thought" in cot.name


# Check our nice UI list with descriptions covers all our generators
def test_all_ids_are_covered():
    generators = [e.value for e in PromptGenerators]
    api_list = [g.id for g in _prompt_generators]

    assert set(api_list) == set(generators)


def test_update_prompt_success(client, project_and_task):
    project, task = project_and_task

    # First create a prompt
    test_prompt = Prompt(
        name="Original Name",
        prompt="This is a test prompt",
        description="Original description",
        parent=task,
    )
    test_prompt.save_to_file()

    # Prepare update data
    update_data = {"name": "Updated Name", "description": "Updated description"}

    with patch("kiln_server.prompt_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.patch(
            f"/api/projects/{project.id}/tasks/{task.id}/prompts/id::{test_prompt.id}",
            json=update_data,
        )

    assert response.status_code == 200
    res = response.json()
    assert res["name"] == "Updated Name"
    assert res["description"] == "Updated description"

    # Verify the prompt was updated in the task/file
    updated_prompt = next((p for p in task.prompts() if p.id == test_prompt.id), None)
    assert updated_prompt is not None
    assert updated_prompt.name == "Updated Name"
    assert updated_prompt.description == "Updated description"
    # Ensure the prompt content wasn't changed
    assert updated_prompt.prompt == "This is a test prompt"


def test_update_prompt_not_found(client, project_and_task):
    project, task = project_and_task

    update_data = {"name": "Updated Name", "description": "Updated description"}

    with patch("kiln_server.prompt_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.patch(
            f"/api/projects/{project.id}/tasks/{task.id}/prompts/id::nonexistent_id",
            json=update_data,
        )

    assert response.status_code == 404
    assert "Prompt not found" in response.json()["message"]


def test_update_prompt_non_custom(client, project_and_task):
    project, task = project_and_task

    update_data = {"name": "Updated Name", "description": "Updated description"}

    with patch("kiln_server.prompt_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        # Try to update a non-custom prompt (doesn't start with "id::")
        response = client.patch(
            f"/api/projects/{project.id}/tasks/{task.id}/prompts/task_run_config::some_id",
            json=update_data,
        )

    assert response.status_code == 400
    assert "Only custom prompts can be updated" in response.json()["message"]


def test_delete_prompt_success(client, project_and_task):
    project, task = project_and_task

    # First create a prompt
    test_prompt = Prompt(
        name="Test Prompt",
        prompt="This is a test prompt",
        description="This is a test prompt description",
        parent=task,
    )
    test_prompt.save_to_file()

    # Verify the prompt exists
    prompts_before = task.prompts()
    assert len(prompts_before) == 1
    assert prompts_before[0].id == test_prompt.id

    # Store the path to check if file is deleted
    prompt_path = test_prompt.path

    with patch("kiln_server.prompt_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.delete(
            f"/api/projects/{project.id}/tasks/{task.id}/prompts/id::{test_prompt.id}"
        )

    assert response.status_code == 200

    # Verify the prompt was deleted from the task
    prompts_after = task.prompts()
    assert len(prompts_after) == 0

    # Verify the file was actually deleted, including the parent directory
    assert not prompt_path.exists()
    assert not prompt_path.parent.exists()
