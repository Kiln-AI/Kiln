import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
from app.desktop.studio_server.run_config_api import (
    _load_mcp_input_schema,
    _load_mcp_output_schema,
    _load_mcp_tool,
    _validate_mcp_input_schema,
    _validate_mcp_output_schema,
    connect_run_config_api,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.datamodel import Project, Task
from kiln_ai.tools.mcp_server_tool import MCPServerTool


@pytest.fixture
def app():
    app = FastAPI()
    connect_run_config_api(app)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class FakeMcpTool:
    def __init__(self, input_schema: dict, output_schema: dict | None):
        self._input_schema = input_schema
        self._output_schema = output_schema

    async def input_schema(self) -> dict:
        return self._input_schema

    async def output_schema(self) -> dict | None:
        return self._output_schema

    async def name(self) -> str:
        return "fake_tool"


@pytest.fixture
def project_and_tasks(tmp_path):
    project = Project(
        id="project1",
        name="Test Project",
        path=tmp_path / "project.kiln",
    )
    project.save_to_file()

    plaintext_task = Task(
        id="task_plaintext",
        name="Plaintext Task",
        instruction="Do the thing.",
        parent=project,
    )
    plaintext_task.save_to_file()

    compatible_input_schema = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
    }
    compatible_output_schema = {
        "type": "object",
        "properties": {"result": {"type": "string"}},
        "required": ["result"],
    }

    structured_compatible_task = Task(
        id="task_structured_ok",
        name="Structured OK Task",
        instruction="Do the thing.",
        input_json_schema=json.dumps(compatible_input_schema),
        output_json_schema=json.dumps(compatible_output_schema),
        parent=project,
    )
    structured_compatible_task.save_to_file()

    incompatible_input_schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }
    structured_incompatible_input_task = Task(
        id="task_bad_input",
        name="Bad Input Task",
        instruction="Do the thing.",
        input_json_schema=json.dumps(incompatible_input_schema),
        parent=project,
    )
    structured_incompatible_input_task.save_to_file()

    incompatible_output_schema = {
        "type": "object",
        "properties": {"score": {"type": "number"}},
        "required": ["score"],
    }
    structured_incompatible_output_task = Task(
        id="task_bad_output",
        name="Bad Output Task",
        instruction="Do the thing.",
        input_json_schema=json.dumps(compatible_input_schema),
        output_json_schema=json.dumps(incompatible_output_schema),
        parent=project,
    )
    structured_incompatible_output_task.save_to_file()

    return project


@pytest.fixture
def mock_task(tmp_path):
    project = Project(
        id="project_mock",
        name="Mock Project",
        path=tmp_path / "project_mock.kiln",
    )
    project.save_to_file()
    task = Task(
        id="task_mock",
        name="Mock Task",
        instruction="Test Instructions",
        path=tmp_path / "task_mock.kiln",
        parent=project,
    )
    task.save_to_file()
    return task


def test_validate_mcp_input_schema_plaintext_success(mock_task):
    mock_task.input_json_schema = None
    tool_schema = {"type": "object", "properties": {"message": {"type": "string"}}}
    _validate_mcp_input_schema(mock_task, tool_schema)


@pytest.mark.parametrize(
    "tool_schema, error_match",
    [
        (
            {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "count": {"type": "number"},
                },
            },
            "exactly one string input field",
        ),
        (
            {"type": "object", "properties": {"count": {"type": "number"}}},
            "exactly one string input field",
        ),
    ],
)
def test_validate_mcp_input_schema_plaintext_fails(mock_task, tool_schema, error_match):
    mock_task.input_json_schema = None
    with pytest.raises(ValueError, match=error_match):
        _validate_mcp_input_schema(mock_task, tool_schema)


def test_validate_mcp_input_schema_structured_success(mock_task):
    mock_task.input_json_schema = json.dumps(
        {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}
    )
    tool_schema = {
        "type": "object",
        "properties": {"x": {"type": "string"}},
        "required": ["x"],
    }
    _validate_mcp_input_schema(mock_task, tool_schema)


def test_validate_mcp_input_schema_structured_fails(mock_task):
    mock_task.input_json_schema = json.dumps(
        {"type": "object", "properties": {"x": {"type": "string"}}}
    )
    tool_schema = {"type": "object", "properties": {"y": {"type": "string"}}}
    with pytest.raises(ValueError, match="must be compatible"):
        _validate_mcp_input_schema(mock_task, tool_schema)


def test_validate_mcp_output_schema_success(mock_task):
    mock_task.output_json_schema = None
    _validate_mcp_output_schema(mock_task, None)

    mock_task.output_json_schema = None
    tool_schema = {"type": "object", "properties": {"result": {"type": "string"}}}
    _validate_mcp_output_schema(mock_task, tool_schema)

    mock_task.output_json_schema = json.dumps(
        {"type": "object", "properties": {"result": {"type": "string"}}}
    )
    _validate_mcp_output_schema(mock_task, None)

    mock_task.output_json_schema = json.dumps(
        {
            "type": "object",
            "properties": {"result": {"type": "string"}},
            "required": ["result"],
        }
    )
    tool_schema = {
        "type": "object",
        "properties": {"result": {"type": "string"}},
        "required": ["result"],
    }
    _validate_mcp_output_schema(mock_task, tool_schema)


def test_validate_mcp_output_schema_fails(mock_task):
    mock_task.output_json_schema = json.dumps(
        {"type": "object", "properties": {"x": {"type": "string"}}}
    )
    tool_schema = {"type": "object", "properties": {"y": {"type": "string"}}}
    with pytest.raises(ValueError, match="must be compatible"):
        _validate_mcp_output_schema(mock_task, tool_schema)


def test_load_mcp_tool_success(mock_task):
    tool_id = "mcp::local::server123::test_tool"
    mock_tool = Mock(spec=MCPServerTool)

    with (
        patch("app.desktop.studio_server.run_config_api.is_mcp_tool_id") as mock_is_mcp,
        patch(
            "app.desktop.studio_server.run_config_api.tool_from_id"
        ) as mock_tool_from_id,
    ):
        mock_is_mcp.return_value = True
        mock_tool_from_id.return_value = mock_tool

        result = _load_mcp_tool(tool_id, mock_task)

        assert result == mock_tool


def test_load_mcp_tool_fails_not_mcp_tool_id(mock_task):
    tool_id = "not_mcp_tool"

    with patch(
        "app.desktop.studio_server.run_config_api.is_mcp_tool_id"
    ) as mock_is_mcp:
        mock_is_mcp.return_value = False

        with pytest.raises(ValueError, match="not an MCP tool"):
            _load_mcp_tool(tool_id, mock_task)


def test_load_mcp_tool_fails_wrong_type(mock_task):
    tool_id = "mcp::local::server123::test_tool"

    with (
        patch("app.desktop.studio_server.run_config_api.is_mcp_tool_id") as mock_is_mcp,
        patch(
            "app.desktop.studio_server.run_config_api.tool_from_id"
        ) as mock_tool_from_id,
    ):
        mock_is_mcp.return_value = True
        mock_tool_from_id.return_value = Mock()

        with pytest.raises(ValueError, match="Failed to load MCP tool"):
            _load_mcp_tool(tool_id, mock_task)


@pytest.mark.asyncio
async def test_load_mcp_input_schema_success():
    mock_tool = Mock(spec=MCPServerTool)
    expected_schema = {"type": "object", "properties": {"x": {"type": "string"}}}
    mock_tool.input_schema = AsyncMock(return_value=expected_schema)

    result = await _load_mcp_input_schema(mock_tool)

    assert result == expected_schema


@pytest.mark.asyncio
async def test_load_mcp_input_schema_fails():
    mock_tool = Mock(spec=MCPServerTool)

    mock_tool.input_schema = AsyncMock(side_effect=ValueError("Invalid schema"))
    with pytest.raises(ValueError, match="missing a valid input schema"):
        await _load_mcp_input_schema(mock_tool)

    mock_tool.input_schema = AsyncMock(return_value="not a dict")
    with pytest.raises(ValueError, match="missing a valid input schema"):
        await _load_mcp_input_schema(mock_tool)


@pytest.mark.asyncio
async def test_load_mcp_output_schema_success():
    mock_tool = Mock(spec=MCPServerTool)

    expected_schema = {"type": "object", "properties": {"result": {"type": "string"}}}
    mock_tool.output_schema = AsyncMock(return_value=expected_schema)
    result = await _load_mcp_output_schema(mock_tool)
    assert result == expected_schema

    mock_tool.output_schema = AsyncMock(return_value=None)
    result = await _load_mcp_output_schema(mock_tool)
    assert result is None


@pytest.mark.asyncio
async def test_load_mcp_output_schema_fails():
    mock_tool = Mock(spec=MCPServerTool)
    mock_tool.output_schema = AsyncMock(side_effect=ValueError("Invalid schema"))

    with pytest.raises(ValueError, match="invalid output schema"):
        await _load_mcp_output_schema(mock_tool)


def test_create_task_from_tool_plaintext(client, tmp_path):
    project = Project(
        id="project2",
        name="Plaintext Project",
        path=tmp_path / "project2.kiln",
    )
    project.save_to_file()

    tool_input_schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }
    fake_tool = FakeMcpTool(tool_input_schema, None)

    with (
        patch(
            "app.desktop.studio_server.run_config_api.project_from_id"
        ) as mock_project_from_id,
        patch(
            "app.desktop.studio_server.run_config_api._resolve_mcp_tool_from_id",
            return_value=fake_tool,
        ),
    ):
        mock_project_from_id.return_value = project
        response = client.post(
            "/api/projects/project2/create_task_from_tool",
            json={"tool_id": "mcp::local::server::fake_tool", "task_name": "New Task"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "New Task"
    assert data["input_json_schema"] == json.dumps(tool_input_schema)
    assert data["output_json_schema"] is None
    assert data["default_run_config_id"] is not None


def test_create_task_from_tool_structured(client, tmp_path):
    project = Project(
        id="project3",
        name="Structured Project",
        path=tmp_path / "project3.kiln",
    )
    project.save_to_file()

    tool_input_schema = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
    }
    tool_output_schema = {
        "type": "object",
        "properties": {"result": {"type": "string"}},
        "required": ["result"],
    }
    fake_tool = FakeMcpTool(tool_input_schema, tool_output_schema)

    with (
        patch(
            "app.desktop.studio_server.run_config_api.project_from_id"
        ) as mock_project_from_id,
        patch(
            "app.desktop.studio_server.run_config_api._resolve_mcp_tool_from_id",
            return_value=fake_tool,
        ),
    ):
        mock_project_from_id.return_value = project
        response = client.post(
            "/api/projects/project3/create_task_from_tool",
            json={
                "tool_id": "mcp::local::server::fake_tool",
                "task_name": "Structured Task",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Structured Task"
    assert data["default_run_config_id"] is not None

    created_task = next(
        (task for task in project.tasks() if task.name == "Structured Task"),
        None,
    )
    assert created_task is not None
    assert created_task.input_json_schema is not None
    assert created_task.output_json_schema is not None


def test_create_mcp_run_config_success(client, tmp_path):
    project = Project(
        id="project4",
        name="RunConfig Project",
        path=tmp_path / "project4.kiln",
    )
    project.save_to_file()

    task_input_schema = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
    }
    task = Task(
        id="task_run_config",
        name="Run Config Task",
        instruction="Do the thing.",
        path=tmp_path / "task_run_config.kiln",
        input_json_schema=json.dumps(task_input_schema),
        parent=project,
    )
    task.save_to_file()

    fake_tool = FakeMcpTool(task_input_schema, None)

    with (
        patch(
            "app.desktop.studio_server.run_config_api.task_from_id"
        ) as mock_task_from_id,
        patch(
            "app.desktop.studio_server.run_config_api._load_mcp_tool",
            return_value=fake_tool,
        ),
    ):
        mock_task_from_id.return_value = task
        response = client.post(
            "/api/projects/project4/tasks/task_run_config/mcp_run_config",
            json={"tool_id": "mcp::local::server::fake_tool"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["run_config_properties"]["kind"] == "mcp"
    assert data["run_config_properties"]["mcp_tool"]["tool_name"] == "fake_tool"


def test_create_mcp_run_config_plaintext_success(client, tmp_path):
    project = Project(
        id="project5",
        name="Plaintext RunConfig Project",
        path=tmp_path / "project5.kiln",
    )
    project.save_to_file()

    task = Task(
        id="task_plaintext_rc",
        name="Plaintext RunConfig Task",
        instruction="Do the thing.",
        path=tmp_path / "task_plaintext_rc.kiln",
        parent=project,
    )
    task.save_to_file()

    tool = Mock(spec=MCPServerTool)
    tool.input_schema = AsyncMock(
        return_value={"type": "object", "properties": {"message": {"type": "string"}}}
    )
    tool.output_schema = AsyncMock(return_value=None)
    tool.name = AsyncMock(return_value="test_tool")

    with (
        patch(
            "app.desktop.studio_server.run_config_api.task_from_id"
        ) as mock_task_from_id,
        patch(
            "app.desktop.studio_server.run_config_api._load_mcp_tool",
            return_value=tool,
        ),
    ):
        mock_task_from_id.return_value = task

        response = client.post(
            "/api/projects/project5/tasks/task_plaintext_rc/mcp_run_config",
            json={
                "name": "Plaintext MCP Config",
                "tool_id": "mcp::local::server123::test_tool",
            },
        )

    assert response.status_code == 200
    result = response.json()
    assert result["name"] == "Plaintext MCP Config"
    assert result["run_config_properties"]["kind"] == "mcp"
    assert result["run_config_properties"]["mcp_tool"]["tool_name"] == "test_tool"


def test_create_mcp_run_config_input_schema_mismatch(client, tmp_path):
    project = Project(
        id="project6",
        name="Mismatch RunConfig Project",
        path=tmp_path / "project6.kiln",
    )
    project.save_to_file()

    task = Task(
        id="task_bad_input_rc",
        name="Bad Input RunConfig Task",
        instruction="Do the thing.",
        path=tmp_path / "task_bad_input_rc.kiln",
        input_json_schema=json.dumps(
            {
                "type": "object",
                "properties": {"x": {"type": "string"}},
                "required": ["x"],
            }
        ),
        parent=project,
    )
    task.save_to_file()

    tool = Mock(spec=MCPServerTool)
    tool.input_schema = AsyncMock(
        return_value={
            "type": "object",
            "properties": {"y": {"type": "string"}},
            "required": ["y"],
        }
    )
    tool.output_schema = AsyncMock(return_value=None)
    tool.name = AsyncMock(return_value="test_tool")

    with (
        patch(
            "app.desktop.studio_server.run_config_api.task_from_id"
        ) as mock_task_from_id,
        patch(
            "app.desktop.studio_server.run_config_api._load_mcp_tool",
            return_value=tool,
        ),
    ):
        mock_task_from_id.return_value = task

        response = client.post(
            "/api/projects/project6/tasks/task_bad_input_rc/mcp_run_config",
            json={
                "name": "MCP Config",
                "tool_id": "mcp::local::server123::test_tool",
            },
        )

    assert response.status_code == 400
    assert "Task input schema must be compatible with the MCP tool." in response.text


def test_tasks_compatible_with_tool_mixed_results(client, project_and_tasks):
    tool_input_schema = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
    }
    tool_output_schema = {
        "type": "object",
        "properties": {"result": {"type": "string"}},
        "required": ["result"],
    }
    fake_tool = FakeMcpTool(tool_input_schema, tool_output_schema)

    with (
        patch(
            "app.desktop.studio_server.run_config_api.project_from_id"
        ) as mock_project_from_id,
        patch(
            "app.desktop.studio_server.run_config_api._resolve_mcp_tool_from_id",
            return_value=fake_tool,
        ),
    ):
        mock_project_from_id.return_value = project_and_tasks
        response = client.get(
            "/api/projects/project1/tasks_compatible_with_tool",
            params={"tool_id": "mcp::local::server::fake_tool"},
        )

    assert response.status_code == 200
    data = response.json()
    by_name = {item["task_name"]: item for item in data}

    assert by_name["Plaintext Task"]["compatible"] is True
    assert by_name["Structured OK Task"]["compatible"] is True

    assert by_name["Bad Input Task"]["compatible"] is False
    assert (
        "Task input schema must be compatible with the MCP tool."
        in by_name["Bad Input Task"]["incompatibility_reason"]
    )

    assert by_name["Bad Output Task"]["compatible"] is False
    assert (
        "Task output schema must be compatible with the MCP tool."
        in by_name["Bad Output Task"]["incompatibility_reason"]
    )


def test_tasks_compatible_with_tool_invalid_tool(client, project_and_tasks):
    with (
        patch(
            "app.desktop.studio_server.run_config_api.project_from_id"
        ) as mock_project_from_id,
        patch(
            "app.desktop.studio_server.run_config_api._resolve_mcp_tool_from_id",
            side_effect=ValueError("Tool selected is not an MCP tool."),
        ),
    ):
        mock_project_from_id.return_value = project_and_tasks
        response = client.get(
            "/api/projects/project1/tasks_compatible_with_tool",
            params={"tool_id": "not_mcp"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Tool selected is not an MCP tool."
