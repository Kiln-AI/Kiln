import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from mcp.types import CallToolResult, TextContent

from kiln_ai.adapters.model_adapters.mcp_adapter import MCPAdapter
from kiln_ai.datamodel import Task
from kiln_ai.datamodel.external_tool_server import ExternalToolServer, ToolServerType
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.run_config import (
    MCPToolReference,
    RunConfigKind,
    RunConfigProperties,
)
from kiln_ai.datamodel.tool_id import MCP_LOCAL_TOOL_ID_PREFIX


@pytest.mark.asyncio
@patch("kiln_ai.tools.mcp_server_tool.MCPSessionManager")
async def test_mcp_adapter_invokes_tool_from_external_server(
    mock_session_manager, tmp_path
):
    project_path = tmp_path / "test_project" / Project.base_filename()
    project = Project(name="Test Project", path=str(project_path))
    project.save_to_file()

    tool_server = ExternalToolServer(
        name="Hooks MCP",
        type=ToolServerType.local_mcp,
        properties={
            "command": "uvx",
            "args": ["hooks-mcp"],
            "env_vars": {},
            "is_archived": False,
        },
    )
    tool_server.parent = project
    tool_server.save_to_file()

    task = Task(
        name="Test Task",
        parent=project,
        instruction="Run tests",
        input_json_schema=json.dumps(
            {
                "type": "object",
                "properties": {"TEST_PATH": {"type": "string"}},
                "required": ["TEST_PATH"],
            }
        ),
    )

    tool_id = f"{MCP_LOCAL_TOOL_ID_PREFIX}{tool_server.id}::test_file_python"
    run_config = RunConfigProperties(
        kind=RunConfigKind.mcp, mcp_tool=MCPToolReference(tool_id=tool_id)
    )

    mock_session = AsyncMock()
    mock_session_manager.shared.return_value.mcp_client.return_value.__aenter__.return_value = mock_session
    mock_session.call_tool.return_value = CallToolResult(
        content=[TextContent(type="text", text="ok")],
        isError=False,  # type: ignore[arg-type]
    )

    adapter = MCPAdapter(task=task, run_config=run_config)
    run, run_output = await adapter.invoke_returning_run_output(
        {"TEST_PATH": "libs/core/kiln_ai/datamodel/test_run_config.py"}
    )

    assert run_output.output == "ok"
    assert run.output.output == "ok"
    mock_session.call_tool.assert_called_once_with(
        name="test_file_python",
        arguments={"TEST_PATH": "libs/core/kiln_ai/datamodel/test_run_config.py"},
    )


@pytest.mark.asyncio
@patch("kiln_ai.tools.mcp_server_tool.MCPSessionManager")
async def test_mcp_adapter_structured_output(mock_session_manager, tmp_path):
    """Test that the MCPAdapter can handle structured output from the task"""
    project_path = tmp_path / "test_project" / Project.base_filename()
    project = Project(name="Test Project", path=str(project_path))
    project.save_to_file()

    tool_server = ExternalToolServer(
        name="Hooks MCP",
        type=ToolServerType.local_mcp,
        properties={
            "command": "uvx",
            "args": ["hooks-mcp"],
            "env_vars": {},
            "is_archived": False,
        },
    )
    tool_server.parent = project
    tool_server.save_to_file()

    task = Task(
        name="Structured Output Task",
        parent=project,
        instruction="Return JSON with status.",
        output_json_schema=json.dumps(
            {
                "type": "object",
                "properties": {"status": {"type": "string"}},
                "required": ["status"],
            }
        ),
    )

    tool_id = f"{MCP_LOCAL_TOOL_ID_PREFIX}{tool_server.id}::test_file_python"
    run_config = RunConfigProperties(
        kind=RunConfigKind.mcp, mcp_tool=MCPToolReference(tool_id=tool_id)
    )

    mock_session = AsyncMock()
    mock_session_manager.shared.return_value.mcp_client.return_value.__aenter__.return_value = mock_session
    mock_session.call_tool.return_value = CallToolResult(
        content=[TextContent(type="text", text='{"status":"ok"}')],
        isError=False,  # type: ignore[arg-type]
    )

    adapter = MCPAdapter(task=task, run_config=run_config)
    run, run_output = await adapter.invoke_returning_run_output("input")

    assert run_output.output == {"status": "ok"}
    assert run.output.output == '{"status": "ok"}'
    mock_session.call_tool.assert_called_once_with(
        name="test_file_python",
        arguments={"input": "input"},
    )


@pytest.mark.slow
@pytest.mark.asyncio
async def test_mcp_adapter_hooks_mcp_integration():
    project_path = Path(
        "/Users/daniel/Kiln Projects/New Project Tool Test/project.kiln"
    )
    if not project_path.exists():
        pytest.skip("Hooks MCP project not available on this machine.")

    project = Project.load_from_file(project_path)
    if not any(
        server.id == "444800067879" for server in project.external_tool_servers()
    ):
        pytest.skip("Hooks MCP external tool server not configured for this project.")

    task = Task(
        name="Hooks MCP Task",
        parent=project,
        instruction="Run tests",
        input_json_schema=json.dumps(
            {
                "type": "object",
                "properties": {"TEST_PATH": {"type": "string"}},
                "required": ["TEST_PATH"],
            }
        ),
    )

    tool_id = f"{MCP_LOCAL_TOOL_ID_PREFIX}444800067879::test_file_python"
    run_config = RunConfigProperties(
        kind=RunConfigKind.mcp, mcp_tool=MCPToolReference(tool_id=tool_id)
    )

    adapter = MCPAdapter(task=task, run_config=run_config)
    run, run_output = await adapter.invoke_returning_run_output(
        {"TEST_PATH": "libs/core/kiln_ai/datamodel/test_run_config.py"}
    )

    assert isinstance(run_output.output, str)
    assert run_output.output.strip()
    assert isinstance(run.output.output, str)
    assert run.output.output.strip()
