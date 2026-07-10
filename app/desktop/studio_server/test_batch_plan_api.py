from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from kiln_ai.datamodel import Project, Task
from kiln_server.custom_errors import connect_custom_errors

from app.desktop.studio_server.api_client.kiln_ai_server_client.models import (
    BatchPlanOutput as BatchPlanOutputClient,
)
from app.desktop.studio_server.batch_plan_api import connect_batch_plan_api


@pytest.fixture
def app():
    app = FastAPI()
    connect_custom_errors(app)
    connect_batch_plan_api(app)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def test_project(tmp_path) -> Project:
    project_path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()
    project = Project(name="Test Project", path=project_path)
    project.save_to_file()
    return project


@pytest.fixture
def test_task(test_project) -> Task:
    task = Task(
        name="Test Task",
        instruction="Test Instruction",
        parent=test_project,
        output_json_schema='{"type":"object","properties":{},"required":[]}',
    )
    task.save_to_file()
    return task


@pytest.fixture
def mock_copilot_key():
    with patch("app.desktop.studio_server.batch_plan_api.get_copilot_api_key") as mock:
        mock.return_value = "copilot-key"
        yield mock


@pytest.fixture
def mock_task_from_id(test_task):
    with patch("app.desktop.studio_server.batch_plan_api.task_from_id") as mock:
        mock.return_value = test_task
        yield mock


def test_batch_plan_requires_copilot_key(mock_task_from_id, client):
    with patch(
        "app.desktop.studio_server.batch_plan_api.get_copilot_api_key"
    ) as mock_key:
        mock_key.side_effect = HTTPException(status_code=401, detail="no key")
        resp = client.post(
            "/api/projects/proj-ID/tasks/task-ID/copilot/batch_plan",
            json={"guidance": "x", "count": 2},
        )
    assert resp.status_code == 401


def test_batch_plan_kiln_server_proxy(mock_copilot_key, mock_task_from_id, client):
    """The route proxies to kiln_server and maps the generated BatchPlanOutput
    back to the API output."""
    proxied = BatchPlanOutputClient(prompts=["x", "y"], summary="proxied")
    with (
        patch("app.desktop.studio_server.batch_plan_api.get_authenticated_client"),
        patch(
            "app.desktop.studio_server.batch_plan_api.batch_plan_v1_copilot_batch_plan_post.asyncio_detailed",
            new=AsyncMock(return_value="sentinel"),
        ),
        patch(
            "app.desktop.studio_server.batch_plan_api.unwrap_response",
            return_value=proxied,
        ),
    ):
        resp = client.post(
            "/api/projects/proj-ID/tasks/task-ID/copilot/batch_plan",
            json={"guidance": "g", "count": 2},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["prompts"] == ["x", "y"]
    assert body["summary"] == "proxied"


def test_batch_plan_sends_task_context_from_server(
    mock_copilot_key, mock_task_from_id, client, test_task
):
    """Task prompt and schemas are derived server-side, not sent by the client."""
    proxied = BatchPlanOutputClient(prompts=["x"], summary="s")
    post = AsyncMock(return_value="sentinel")
    with (
        patch("app.desktop.studio_server.batch_plan_api.get_authenticated_client"),
        patch(
            "app.desktop.studio_server.batch_plan_api.batch_plan_v1_copilot_batch_plan_post.asyncio_detailed",
            new=post,
        ),
        patch(
            "app.desktop.studio_server.batch_plan_api.unwrap_response",
            return_value=proxied,
        ),
    ):
        resp = client.post(
            "/api/projects/proj-ID/tasks/task-ID/copilot/batch_plan",
            json={"guidance": "g", "count": 1, "data_guide": "guide text"},
        )
    assert resp.status_code == 200, resp.text
    sent = post.call_args.kwargs["body"]
    assert sent.task_prompt == "Test Instruction"
    assert sent.count == 1
    assert sent.user_guidance == "g"
    assert sent.input_data_guide == "guide text"
    assert sent.task_input_schema is None
    assert sent.task_output_schema == test_task.output_json_schema


def test_batch_plan_unknown_response_is_500(
    mock_copilot_key, mock_task_from_id, client
):
    with (
        patch("app.desktop.studio_server.batch_plan_api.get_authenticated_client"),
        patch(
            "app.desktop.studio_server.batch_plan_api.batch_plan_v1_copilot_batch_plan_post.asyncio_detailed",
            new=AsyncMock(return_value="sentinel"),
        ),
        patch(
            "app.desktop.studio_server.batch_plan_api.unwrap_response",
            return_value="not a BatchPlanOutput",
        ),
    ):
        resp = client.post(
            "/api/projects/proj-ID/tasks/task-ID/copilot/batch_plan",
            json={"guidance": "g", "count": 2},
        )
    assert resp.status_code == 500
