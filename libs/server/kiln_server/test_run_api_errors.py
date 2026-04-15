"""Integration tests for /run endpoint error handling.

Verifies the interaction between the `/run` endpoint, the adapter's
`KilnRunError` wrapping (Phase 1), and the FastAPI exception handler
(Phase 2). The handler must turn `KilnRunError` into a 500 `ErrorWithTrace`
body while leaving unrelated error paths (pre-run validation, generic
fallback) unchanged.

Note: the `client` fixture uses `raise_server_exceptions=False` so the
registered exception handlers actually dispatch (otherwise the test client
re-raises inside `TestClient`, bypassing them).
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from kiln_ai.adapters.errors import KilnRunError
from kiln_ai.adapters.model_adapters.litellm_adapter import LiteLlmAdapter
from kiln_ai.datamodel import Project, Task
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam
from openai.types.chat import (
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from kiln_server.custom_errors import connect_custom_errors
from kiln_server.run_api import connect_run_api


@pytest.fixture
def app():
    app = FastAPI()
    connect_run_api(app)
    connect_custom_errors(app)
    return app


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def task_setup(tmp_path):
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

    run_task_request = {
        "run_config_properties": {
            "model_name": "gpt_4o",
            "model_provider_name": "ollama",
            "prompt_id": "simple_prompt_builder",
            "structured_output_mode": "json_schema",
        },
        "plaintext_input": "Test input",
    }

    return {
        "project": project,
        "task": task,
        "run_task_request": run_task_request,
    }


@pytest.mark.asyncio
async def test_run_endpoint_wraps_adapter_kiln_run_error(client, task_setup):
    """Adapter raising KilnRunError → 500 with ErrorWithTrace body."""
    task = task_setup["task"]
    run_task_request = task_setup["run_task_request"]

    original = RuntimeError("downstream failure")
    partial_trace: list[ChatCompletionMessageParam] = [
        ChatCompletionSystemMessageParam(
            role="system", content="You are a helpful assistant."
        ),
        ChatCompletionUserMessageParam(role="user", content="Test input"),
    ]

    with (
        patch("kiln_server.run_api.task_from_id") as mock_task_from_id,
        patch.object(LiteLlmAdapter, "invoke", new_callable=AsyncMock) as mock_invoke,
        patch("kiln_ai.utils.config.Config.shared") as MockConfig,
    ):
        mock_task_from_id.return_value = task
        mock_invoke.side_effect = KilnRunError(
            message="Something user-friendly went wrong.",
            partial_trace=partial_trace,
            original=original,
        )
        mock_config_instance = MockConfig.return_value
        mock_config_instance.ollama_base_url = "http://localhost:11434/v1"

        response = client.post(
            f"/api/projects/project-1/tasks/{task.id}/run", json=run_task_request
        )

    assert response.status_code == 500
    body = response.json()
    assert set(body.keys()) == {"message", "error_type", "trace"}
    assert body["message"] == "Something user-friendly went wrong."
    assert body["error_type"] == "RuntimeError"
    assert body["trace"] == partial_trace
    # The legacy HTTPException shape must NOT leak through.
    assert "detail" not in body


@pytest.mark.asyncio
async def test_run_endpoint_kiln_run_error_without_trace(client, task_setup):
    """When the failure happens before any trace is built, trace=None is
    round-tripped rather than coerced to an empty list."""
    task = task_setup["task"]
    run_task_request = task_setup["run_task_request"]

    with (
        patch("kiln_server.run_api.task_from_id") as mock_task_from_id,
        patch.object(LiteLlmAdapter, "invoke", new_callable=AsyncMock) as mock_invoke,
        patch("kiln_ai.utils.config.Config.shared") as MockConfig,
    ):
        mock_task_from_id.return_value = task
        mock_invoke.side_effect = KilnRunError(
            message="Auth failed.",
            partial_trace=None,
            original=ValueError("bad api key"),
        )
        MockConfig.return_value.ollama_base_url = "http://localhost:11434/v1"

        response = client.post(
            f"/api/projects/project-1/tasks/{task.id}/run", json=run_task_request
        )

    assert response.status_code == 500
    body = response.json()
    assert body["trace"] is None
    assert body["error_type"] == "ValueError"


@pytest.mark.asyncio
async def test_run_endpoint_pre_run_http_exception_unchanged(client, task_setup):
    """Pre-run HTTPException (missing input) must still produce the legacy
    `{message: ...}` shape — NOT the new ErrorWithTrace shape.

    This guards the contract in the functional spec: pre-run errors stay as
    plain HTTPException because there's no trace to preserve.
    """
    task = task_setup["task"]

    run_task_request_missing_input = {
        "run_config_properties": {
            "model_name": "gpt_4o",
            "model_provider_name": "openai",
            "prompt_id": "simple_prompt_builder",
            "structured_output_mode": "json_schema",
        }
        # no plaintext_input, no structured_input
    }

    with patch("kiln_server.run_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = task
        response = client.post(
            f"/api/projects/project-1/tasks/{task.id}/run",
            json=run_task_request_missing_input,
        )

    assert response.status_code == 400
    body = response.json()
    # Legacy shape from the HTTPException handler in custom_errors.py
    assert "message" in body
    assert "No input provided" in body["message"]
    # ErrorWithTrace keys must NOT appear
    assert "error_type" not in body
    assert "trace" not in body


@pytest.mark.asyncio
async def test_run_endpoint_http_exception_from_adapter_unchanged(client, task_setup):
    """If the adapter itself raises an HTTPException (e.g., a 4xx surfaced
    from pre-run validation inside the adapter), it should flow through the
    HTTPException handler — NOT get wrapped as ErrorWithTrace.

    Documents that ONLY KilnRunError produces the new shape.
    """
    task = task_setup["task"]
    run_task_request = task_setup["run_task_request"]

    with (
        patch("kiln_server.run_api.task_from_id") as mock_task_from_id,
        patch.object(LiteLlmAdapter, "invoke", new_callable=AsyncMock) as mock_invoke,
        patch("kiln_ai.utils.config.Config.shared") as MockConfig,
    ):
        mock_task_from_id.return_value = task
        mock_invoke.side_effect = HTTPException(
            status_code=404, detail="Something not found"
        )
        MockConfig.return_value.ollama_base_url = "http://localhost:11434/v1"

        response = client.post(
            f"/api/projects/project-1/tasks/{task.id}/run", json=run_task_request
        )

    assert response.status_code == 404
    body = response.json()
    assert body["message"] == "Something not found"
    assert "error_type" not in body
    assert "trace" not in body


@pytest.mark.asyncio
async def test_run_endpoint_generic_exception_uses_fallback_handler(client, task_setup):
    """A plain (unwrapped) Exception from the adapter flows through the
    generic fallback handler — NOT the KilnRunError handler. This documents
    the contract: adapters must wrap runtime failures in KilnRunError to opt
    into the ErrorWithTrace response shape.
    """
    task = task_setup["task"]
    run_task_request = task_setup["run_task_request"]

    with (
        patch("kiln_server.run_api.task_from_id") as mock_task_from_id,
        patch.object(LiteLlmAdapter, "invoke", new_callable=AsyncMock) as mock_invoke,
        patch("kiln_ai.utils.config.Config.shared") as MockConfig,
    ):
        mock_task_from_id.return_value = task
        mock_invoke.side_effect = RuntimeError("raw adapter failure")
        MockConfig.return_value.ollama_base_url = "http://localhost:11434/v1"

        response = client.post(
            f"/api/projects/project-1/tasks/{task.id}/run", json=run_task_request
        )

    assert response.status_code == 500
    body = response.json()
    # Fallback handler shape
    assert "message" in body
    assert "raw_error" in body
    # NOT the ErrorWithTrace shape
    assert "error_type" not in body
    assert "trace" not in body
