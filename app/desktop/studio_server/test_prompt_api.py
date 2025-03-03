from unittest.mock import MagicMock, patch

import pytest

# Create a FastAPI app and connect the prompt_api
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.adapters.prompt_builders import BasePromptBuilder
from kiln_ai.datamodel import Task

from app.desktop.studio_server.prompt_api import connect_prompt_api


@pytest.fixture
def client():
    app = FastAPI()
    connect_prompt_api(app)
    return TestClient(app)


# Mock prompt builder class
class MockPromptBuilder(BasePromptBuilder):
    def build_base_prompt(self):
        return "Mock prompt"

    def build_prompt_for_ui(self):
        return "Mock prompt for UI"


@pytest.fixture
def mock_task():
    return MagicMock(spec=Task)


@pytest.fixture
def mock_prompt_builder_from_id(mock_task):
    with patch("app.desktop.studio_server.prompt_api.prompt_builder_from_id") as mock:
        mock.return_value = MockPromptBuilder(mock_task)
        yield mock


@pytest.fixture
def mock_task_from_id(mock_task):
    with patch("app.desktop.studio_server.prompt_api.task_from_id") as mock:
        mock.return_value = mock_task
        yield mock


def test_generate_prompt_success(
    client, mock_task, mock_prompt_builder_from_id, mock_task_from_id
):
    response = client.get(
        "/api/projects/project123/task/task456/gen_prompt/simple_prompt_builder"
    )

    assert response.status_code == 200
    data = response.json()
    assert data == {
        "prompt": "Mock prompt for UI",
        "prompt_id": "simple_prompt_builder",
    }

    mock_task_from_id.assert_called_once_with("project123", "task456")
    mock_prompt_builder_from_id.assert_called_once_with(
        "simple_prompt_builder", mock_task
    )


def test_generate_prompt_exception(
    client, mock_task, mock_prompt_builder_from_id, mock_task_from_id
):
    mock_prompt_builder_from_id.side_effect = ValueError("Invalid prompt generator")

    response = client.get(
        "/api/projects/project123/task/task456/gen_prompt/simple_prompt_builder"
    )

    assert response.status_code == 400
    assert "Invalid prompt generator" in response.text


def test_generate_prompt_id_format(client, mock_task, mock_task_from_id):
    response = client.get(
        "/api/projects/project123/task/task456/gen_prompt/invalid_generator_id"
    )

    assert response.status_code == 422
    assert "Value error, Invalid prompt ID: invalid_generator_id" in response.text
