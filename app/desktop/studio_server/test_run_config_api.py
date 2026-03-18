import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
from app.desktop.studio_server.run_config_api import (
    _create_mcp_run_config_properties,
    _load_mcp_input_schema,
    _load_mcp_output_schema,
    _load_mcp_tool,
    _normalize_schema,
    _resolve_mcp_tool_from_id,
    _schemas_compatible,
    _validate_mcp_input_schema,
    _validate_mcp_output_schema,
    connect_run_config_api,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_server.custom_errors import connect_custom_errors
from kiln_ai.datamodel import Project, Task
from kiln_ai.datamodel.basemodel import string_to_valid_name
from kiln_ai.tools.mcp_server_tool import MCPServerTool


@pytest.fixture
def app():
    app = FastAPI()
    connect_custom_errors(app)
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
            json={
                "tool_id": "mcp::local::server::fake_tool",
                "task_name": "New Task",
                "instruction": "Use the tool to complete the task.",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "New Task"
    assert data["instruction"] == "Use the tool to complete the task."
    # Single string input MCP tools map to plaintext tasks.
    assert data["input_json_schema"] is None
    assert data["output_json_schema"] is None
    assert data["default_run_config_id"] is not None

    created_task = next(
        (task for task in project.tasks() if task.name == "New Task"),
        None,
    )
    assert created_task is not None
    run_configs = created_task.run_configs()
    assert len(run_configs) == 1
    rc = run_configs[0]
    assert rc.run_config_properties.type == "mcp"
    assert rc.run_config_properties.tool_reference.tool_name == "fake_tool"
    assert rc.run_config_properties.tool_reference.input_schema == tool_input_schema
    assert rc.run_config_properties.tool_reference.output_schema is None


def test_create_task_from_tool_structured(client, tmp_path):
    project = Project(
        id="project3",
        name="Structured Project",
        path=tmp_path / "project3.kiln",
    )
    project.save_to_file()

    tool_input_schema = {
        "type": "object",
        "properties": {
            "message": {"type": "string"},
            "priority": {"type": "integer"},
        },
        "required": ["message", "priority"],
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
                "instruction": "Use the tool to complete the task.",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Structured Task"
    assert data["default_run_config_id"] is not None

    # Verify the task was created with the correct input and output schemas
    created_task = next(
        (task for task in project.tasks() if task.name == "Structured Task"),
        None,
    )
    assert created_task is not None
    assert created_task.input_json_schema is not None
    assert created_task.output_json_schema is not None

    # Verify the run config was created with the correct input and output schemas
    run_configs = created_task.run_configs()
    assert len(run_configs) == 1
    rc = run_configs[0]
    assert rc.run_config_properties.type == "mcp"
    assert rc.run_config_properties.tool_reference.tool_name == "fake_tool"
    assert rc.run_config_properties.tool_reference.input_schema == tool_input_schema
    assert rc.run_config_properties.tool_reference.output_schema == tool_output_schema


def test_create_task_from_tool_sanitizes_names(client, tmp_path):
    project = Project(
        id="project_sanitize",
        name="Sanitize Project",
        path=tmp_path / "project_sanitize.kiln",
    )
    project.save_to_file()

    tool_input_schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    class FakeMcpToolWithInvalidName(FakeMcpTool):
        async def name(self) -> str:
            return "mcp_tool__sample"

    fake_tool = FakeMcpToolWithInvalidName(tool_input_schema, None)

    with (
        patch(
            "app.desktop.studio_server.run_config_api.project_from_id"
        ) as mock_project_from_id,
        patch(
            "app.desktop.studio_server.run_config_api._resolve_mcp_tool_from_id",
            return_value=fake_tool,
        ),
        patch(
            "app.desktop.studio_server.run_config_api.generate_memorable_name",
            return_value="Dazzling Panther",
        ),
    ):
        mock_project_from_id.return_value = project
        response = client.post(
            "/api/projects/project_sanitize/create_task_from_tool",
            json={
                "tool_id": "mcp::local::server::fake_tool",
                "task_name": "mcp_tool__sample",
                "instruction": "Use the tool to complete the task.",
            },
        )

    assert response.status_code == 200
    data = response.json()
    expected_task_name = string_to_valid_name(
        "mcp_tool__sample", truncate_to_max_length=True
    )
    assert data["name"] == expected_task_name
    assert string_to_valid_name(data["name"]) == data["name"]

    created_task = next(
        (task for task in project.tasks() if task.name == expected_task_name),
        None,
    )
    assert created_task is not None
    run_configs = created_task.run_configs()
    assert len(run_configs) == 1
    expected_run_config_name = string_to_valid_name(
        "MCP mcp_tool__sample - Dazzling Panther",
        truncate_to_max_length=True,
    )
    assert run_configs[0].name == expected_run_config_name
    assert string_to_valid_name(run_configs[0].name) == run_configs[0].name


def test_create_task_from_tool_invalid_tool(client, tmp_path):
    project = Project(
        id="project_err",
        name="Error Project",
        path=tmp_path / "project_err.kiln",
    )
    project.save_to_file()

    with (
        patch(
            "app.desktop.studio_server.run_config_api.project_from_id"
        ) as mock_project_from_id,
        patch(
            "app.desktop.studio_server.run_config_api._resolve_mcp_tool_from_id",
            side_effect=ValueError("Tool selected is not an MCP tool."),
        ),
    ):
        mock_project_from_id.return_value = project
        response = client.post(
            "/api/projects/project_err/create_task_from_tool",
            json={
                "tool_id": "not_mcp",
                "task_name": "Should Fail",
                "instruction": "Use the tool to complete the task.",
            },
        )

    assert response.status_code == 400
    assert "Tool selected is not an MCP tool." in response.text


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
    assert data["run_config_properties"]["type"] == "mcp"
    assert data["run_config_properties"]["tool_reference"]["tool_name"] == "fake_tool"

    run_configs = task.run_configs()
    assert len(run_configs) == 1
    rc = run_configs[0]
    assert rc.run_config_properties.type == "mcp"
    assert rc.run_config_properties.tool_reference.tool_name == "fake_tool"
    assert rc.run_config_properties.tool_reference.input_schema == task_input_schema
    assert rc.run_config_properties.tool_reference.output_schema is None


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
                "description": "A test description",
                "tool_id": "mcp::local::server123::test_tool",
            },
        )

    assert response.status_code == 200
    result = response.json()
    assert result["name"] == "Plaintext MCP Config"
    assert result["description"] == "A test description"
    assert result["run_config_properties"]["type"] == "mcp"
    assert result["run_config_properties"]["tool_reference"]["tool_name"] == "test_tool"

    # Verify the run config was created with the correct input and output schemas
    run_configs = task.run_configs()
    assert len(run_configs) == 1
    rc = run_configs[0]
    assert rc.description == "A test description"
    assert rc.run_config_properties.type == "mcp"
    assert rc.run_config_properties.tool_reference.tool_name == "test_tool"
    assert rc.run_config_properties.tool_reference.input_schema == {
        "type": "object",
        "properties": {"message": {"type": "string"}},
    }
    assert rc.run_config_properties.tool_reference.output_schema is None


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
    assert by_name["Plaintext Task"]["incompatibility_reason"] is None
    assert by_name["Plaintext Task"]["task_id"] == "task_plaintext"

    assert by_name["Structured OK Task"]["compatible"] is True
    assert by_name["Structured OK Task"]["incompatibility_reason"] is None
    assert by_name["Structured OK Task"]["task_id"] == "task_structured_ok"

    assert by_name["Bad Input Task"]["compatible"] is False
    assert by_name["Bad Input Task"]["task_id"] == "task_bad_input"
    assert (
        "Task input schema must be compatible with the MCP tool."
        in by_name["Bad Input Task"]["incompatibility_reason"]
    )

    assert by_name["Bad Output Task"]["compatible"] is False
    assert by_name["Bad Output Task"]["task_id"] == "task_bad_output"
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
    assert response.json()["message"] == "Tool selected is not an MCP tool."


def test_tasks_compatible_with_tool_empty_project(client, tmp_path):
    project = Project(
        id="project_empty",
        name="Empty Project",
        path=tmp_path / "project_empty.kiln",
    )
    project.save_to_file()

    fake_tool = FakeMcpTool(
        {"type": "object", "properties": {"x": {"type": "string"}}}, None
    )

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
        response = client.get(
            "/api/projects/project_empty/tasks_compatible_with_tool",
            params={"tool_id": "mcp::local::server::fake_tool"},
        )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize(
    "schema,expected",
    [
        # Removes additionalProperties from dict
        (
            {
                "type": "object",
                "properties": {"x": {"type": "string"}},
                "additionalProperties": False,
            },
            {"type": "object", "properties": {"x": {"type": "string"}}},
        ),
        # Returns dict unchanged if no additionalProperties
        (
            {"type": "object", "properties": {"x": {"type": "string"}}},
            {"type": "object", "properties": {"x": {"type": "string"}}},
        ),
        # Returns non-dict types unchanged
        ("string", "string"),
        # Only removes top-level additionalProperties, not nested
        (
            {
                "type": "object",
                "properties": {
                    "nested": {"type": "object", "additionalProperties": False}
                },
                "additionalProperties": True,
            },
            {
                "type": "object",
                "properties": {
                    "nested": {"type": "object", "additionalProperties": False}
                },
            },
        ),
    ],
)
def test_normalize_schema(schema, expected):
    result = _normalize_schema(schema)
    assert result == expected
    # Ensure it returns a copy, not modifying the original
    if isinstance(schema, dict):
        assert result is not schema


@pytest.mark.parametrize(
    "task_schema, tool_schema, description",
    [
        (
            {"type": "object", "properties": {"name": {"type": "string"}}},
            {"type": "object", "properties": {"name": {"type": "string"}}},
            "identical_schemas",
        ),
        (
            {
                "type": "object",
                "properties": {"x": {"type": "string"}},
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {"x": {"type": "string"}},
                "additionalProperties": True,
            },
            "different_additionalProperties",
        ),
        (
            {"type": "string", "minLength": 1},
            {"type": "string", "minLength": 1},
            "non_object_matching",
        ),
    ],
)
def test_schemas_compatible_true(task_schema, tool_schema, description):
    assert _schemas_compatible(task_schema, tool_schema)


@pytest.mark.parametrize(
    "task_schema, tool_schema, description",
    [
        (
            {"type": "object", "properties": {"x": {"type": "string"}}},
            {"type": "string"},
            "different_types",
        ),
        (
            {"type": "object", "properties": {"name": {"type": "string"}}},
            {
                "type": "object",
                "properties": {"name": {"type": "string"}, "age": {"type": "number"}},
                "required": ["name", "age"],
            },
            "missing_required_field",
        ),
        (
            {
                "type": "object",
                "properties": {"name": {"type": "string"}, "extra": {"type": "string"}},
            },
            {"type": "object", "properties": {"name": {"type": "string"}}},
            "unaccepted_field",
        ),
        (
            {"type": "object", "properties": {"age": {"type": "string"}}},
            {"type": "object", "properties": {"age": {"type": "number"}}},
            "field_type_mismatch",
        ),
        (
            {"type": "number", "minimum": 0},
            {"type": "number", "minimum": 10},
            "non_object_different_constraints",
        ),
    ],
)
def test_schemas_compatible_false(task_schema, tool_schema, description):
    assert not _schemas_compatible(task_schema, tool_schema)


def test_resolve_mcp_tool_from_id_success():
    mock_server = Mock()
    with (
        patch(
            "app.desktop.studio_server.run_config_api.is_mcp_tool_id", return_value=True
        ),
        patch(
            "app.desktop.studio_server.run_config_api.mcp_server_and_tool_name_from_id",
            return_value=("server123", "my_tool"),
        ),
        patch(
            "app.desktop.studio_server.run_config_api.tool_server_from_id",
            return_value=mock_server,
        ),
        patch(
            "app.desktop.studio_server.run_config_api.MCPServerTool"
        ) as mock_mcp_class,
    ):
        mock_mcp_class.return_value = Mock(spec=MCPServerTool)
        result = _resolve_mcp_tool_from_id("proj1", "mcp::local::server123::my_tool")

        mock_mcp_class.assert_called_once_with(mock_server, "my_tool")
        assert isinstance(result, MCPServerTool)


def test_resolve_mcp_tool_from_id_not_mcp():
    with patch(
        "app.desktop.studio_server.run_config_api.is_mcp_tool_id", return_value=False
    ):
        with pytest.raises(ValueError, match="not an MCP tool"):
            _resolve_mcp_tool_from_id("proj1", "not_mcp_tool")


def test_create_mcp_run_config_properties():
    tool_input_schema = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
    }
    tool_output_schema = {
        "type": "object",
        "properties": {"result": {"type": "string"}},
    }

    result = _create_mcp_run_config_properties(
        tool_id="mcp::local::server::my_tool",
        tool_name="my_tool",
        tool_input_schema=tool_input_schema,
        tool_output_schema=tool_output_schema,
    )

    assert result.type == "mcp"
    assert result.tool_reference.tool_id == "mcp::local::server::my_tool"
    assert result.tool_reference.tool_name == "my_tool"
    assert result.tool_reference.input_schema == tool_input_schema
    assert result.tool_reference.output_schema == tool_output_schema


def test_create_mcp_run_config_properties_no_output_schema():
    tool_input_schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
    }

    result = _create_mcp_run_config_properties(
        tool_id="mcp::local::server::tool2",
        tool_name="tool2",
        tool_input_schema=tool_input_schema,
        tool_output_schema=None,
    )

    assert result.type == "mcp"
    assert result.tool_reference.output_schema is None
