import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from kiln_ai.datamodel import (
    DataSource,
    DataSourceType,
    Project,
    Task,
    TaskOutput,
    TaskRun,
)
from kiln_server.custom_errors import connect_custom_errors

from app.desktop.studio_server.batch_plan_api import (
    _build_batch_plan_input,
    connect_batch_plan_api,
)


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
    task = Task(name="Test Task", instruction="Test Instruction", parent=test_project)
    task.save_to_file()
    return task


@pytest.fixture
def data_source():
    return DataSource(
        type=DataSourceType.synthetic,
        properties={
            "model_name": "claude_sonnet_4_6",
            "model_provider": "openrouter",
            "adapter_name": "kiln_data_gen",
        },
    )


@pytest.fixture
def mock_copilot_key():
    with patch("app.desktop.studio_server.batch_plan_api.get_copilot_api_key") as mock:
        mock.return_value = "copilot-key"
        yield mock


@pytest.fixture
def mock_project_from_id(test_project):
    with patch("app.desktop.studio_server.batch_plan_api.project_from_id") as mock:
        mock.return_value = test_project
        yield mock


@pytest.fixture
def mock_task_from_id(test_task):
    with patch("app.desktop.studio_server.batch_plan_api.task_from_id") as mock:
        mock.return_value = test_task
        yield mock


def _mock_adapter(run: TaskRun):
    adapter = AsyncMock()
    adapter.invoke = AsyncMock(return_value=run)
    return adapter


def test_build_batch_plan_input_ordering_and_tags():
    composite = _build_batch_plan_input(
        task_prompt="do the thing",
        task_input_schema='{"type":"object"}',
        task_output_schema='{"type":"string"}',
        input_data_guide="the guide",
        user_guidance="make 3 spicy ones",
        count=3,
    )
    # Section order: profile → input schema → output schema → instruction → guidance → count
    assert composite.index("<input_data_guide>") < composite.index(
        "<task_input_schema>"
    )
    assert composite.index("<task_input_schema>") < composite.index(
        "<task_output_schema>"
    )
    assert composite.index("<task_output_schema>") < composite.index(
        "<task_instruction>"
    )
    assert composite.index("<task_instruction>") < composite.index("<user_guidance>")
    assert composite.index("<user_guidance>") < composite.index("<count>")
    assert "<count>\n3\n</count>" in composite


def test_build_batch_plan_input_omits_absent_sections():
    composite = _build_batch_plan_input(
        task_prompt="p",
        task_input_schema=None,
        task_output_schema=None,
        input_data_guide=None,
        user_guidance="g",
        count=5,
    )
    assert "<input_data_guide>" not in composite
    assert "<task_input_schema>" not in composite
    assert "<task_output_schema>" not in composite
    assert "<task_instruction>" in composite


def test_batch_plan_success(
    mock_copilot_key,
    mock_project_from_id,
    mock_task_from_id,
    client,
    data_source,
    test_task,
):
    run = TaskRun(
        output=TaskOutput(
            output=json.dumps(
                {
                    "prompts": ["prompt a", "prompt b"],
                    "summary": "Two spicy inputs.",
                }
            ),
            source=data_source,
        ),
        input="x",
        input_source=data_source,
        parent=test_task,
    )
    with (
        patch("app.desktop.studio_server.batch_plan_api.RUN_BATCH_PLAN_LOCALLY", True),
        patch(
            "app.desktop.studio_server.batch_plan_api.adapter_for_task"
        ) as mock_adapter_for_task,
    ):
        mock_adapter_for_task.return_value = _mock_adapter(run)
        resp = client.post(
            "/api/projects/proj-ID/tasks/task-ID/copilot/batch_plan",
            json={"guidance": "spicy", "count": 2, "data_guide": "guide text"},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["prompts"] == ["prompt a", "prompt b"]
    assert body["summary"] == "Two spicy inputs."


def test_batch_plan_requires_copilot_key(
    mock_project_from_id, mock_task_from_id, client
):
    with patch(
        "app.desktop.studio_server.batch_plan_api.get_copilot_api_key"
    ) as mock_key:
        mock_key.side_effect = HTTPException(status_code=401, detail="no key")
        resp = client.post(
            "/api/projects/proj-ID/tasks/task-ID/copilot/batch_plan",
            json={"guidance": "x", "count": 2},
        )
    assert resp.status_code == 401


def test_batch_plan_malformed_output(
    mock_copilot_key,
    mock_project_from_id,
    mock_task_from_id,
    client,
    data_source,
    test_task,
):
    run = TaskRun(
        output=TaskOutput(output="not json", source=data_source),
        input="x",
        input_source=data_source,
        parent=test_task,
    )
    with (
        patch("app.desktop.studio_server.batch_plan_api.RUN_BATCH_PLAN_LOCALLY", True),
        patch(
            "app.desktop.studio_server.batch_plan_api.adapter_for_task"
        ) as mock_adapter_for_task,
    ):
        mock_adapter_for_task.return_value = _mock_adapter(run)
        resp = client.post(
            "/api/projects/proj-ID/tasks/task-ID/copilot/batch_plan",
            json={"guidance": "x", "count": 2},
        )
    assert resp.status_code == 500


def test_batch_plan_kiln_server_proxy(mock_copilot_key, mock_task_from_id, client):
    """With the toggle off, the route proxies to kiln_server and maps the
    generated BatchPlanOutput back to the API output."""
    from app.desktop.studio_server.api_client.kiln_ai_server_client.models import (
        BatchPlanOutput as BatchPlanOutputClient,
    )

    proxied = BatchPlanOutputClient(prompts=["x", "y"], summary="proxied")
    with (
        patch("app.desktop.studio_server.batch_plan_api.RUN_BATCH_PLAN_LOCALLY", False),
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
