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
    @classmethod
    def prompt_builder_name(cls):
        return "MockPromptBuilder"

    def build_prompt(self):
        return "Mock prompt"


@pytest.fixture
def mock_task():
    return MagicMock(spec=Task)


@pytest.fixture
def mock_prompt_builder_from_ui_name(client):
    with patch(
        "app.desktop.studio_server.prompt_api.prompt_builder_from_ui_name"
    ) as mock:
        mock.return_value = MockPromptBuilder
        yield mock


@pytest.fixture
def mock_task_from_id(client):
    with patch("app.desktop.studio_server.prompt_api.task_from_id") as mock:
        mock.return_value = MagicMock(spec=Task)
        yield mock


def test_generate_prompt_success(
    client, mock_task, mock_prompt_builder_from_ui_name, mock_task_from_id
):
    response = client.get(
        "/api/projects/project123/task/task456/gen_prompt/mock_generator"
    )

    assert response.status_code == 200
    data = response.json()
    assert data == {
        "prompt": "Mock prompt",
        "prompt_builder_name": "MockPromptBuilder",
        "ui_generator_name": "mock_generator",
    }

    mock_task_from_id.assert_called_once_with("project123", "task456")
    mock_prompt_builder_from_ui_name.assert_called_once_with("mock_generator")


def test_generate_prompt_exception(
    client, mock_task, mock_prompt_builder_from_ui_name, mock_task_from_id
):
    mock_prompt_builder_from_ui_name.side_effect = ValueError(
        "Invalid prompt generator"
    )

    response = client.get(
        "/api/projects/project123/task/task456/gen_prompt/invalid_generator"
    )

    assert response.status_code == 400
    data = response.json()
    assert data == {"detail": "Invalid prompt generator"}

    mock_task_from_id.assert_called_once_with("project123", "task456")
    mock_prompt_builder_from_ui_name.assert_called_once_with("invalid_generator")
