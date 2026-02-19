import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from mcp.types import CallToolResult, TextContent

from kiln_ai.adapters.model_adapters.mcp_adapter import MCPAdapter
from kiln_ai.datamodel import DataSourceType, Task
from kiln_ai.datamodel.external_tool_server import ExternalToolServer, ToolServerType
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.run_config import McpRunConfigProperties, MCPToolReference
from kiln_ai.datamodel.tool_id import MCP_LOCAL_TOOL_ID_PREFIX
from kiln_ai.run_context import get_agent_run_id


@pytest.fixture
def project_with_local_mcp_server(tmp_path):
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

    return project, tool_server


@pytest.fixture
def local_mcp_tool_id(project_with_local_mcp_server):
    _, tool_server = project_with_local_mcp_server
    return f"{MCP_LOCAL_TOOL_ID_PREFIX}{tool_server.id}::test_file_python"


def _mock_mcp_call(mock_session_manager, text_output: str):
    mock_session = AsyncMock()
    mock_session_manager.shared.return_value.get_or_create_session = AsyncMock(
        return_value=mock_session
    )
    mock_session.call_tool.return_value = CallToolResult(
        content=[TextContent(type="text", text=text_output)],
        isError=False,  # type: ignore[arg-type]
    )
    return mock_session


@pytest.mark.asyncio
@patch("kiln_ai.tools.mcp_server_tool.get_agent_run_id", return_value="test_run_id")
@patch("kiln_ai.tools.mcp_server_tool.MCPSessionManager")
async def test_mcp_adapter_struct_in_string_out(
    mock_session_manager, _mock_run_id, project_with_local_mcp_server, local_mcp_tool_id
):
    project, _ = project_with_local_mcp_server
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

    run_config = McpRunConfigProperties(
        tool_reference=MCPToolReference(tool_id=local_mcp_tool_id)
    )

    mock_session = _mock_mcp_call(mock_session_manager, "ok")

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
@patch("kiln_ai.tools.mcp_server_tool.get_agent_run_id", return_value="test_run_id")
@patch("kiln_ai.tools.mcp_server_tool.MCPSessionManager")
async def test_mcp_adapter_string_in_struct_out(
    mock_session_manager, _mock_run_id, project_with_local_mcp_server, local_mcp_tool_id
):
    project, _ = project_with_local_mcp_server
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

    run_config = McpRunConfigProperties(
        tool_reference=MCPToolReference(tool_id=local_mcp_tool_id)
    )

    mock_session = _mock_mcp_call(mock_session_manager, '{"status":"ok"}')

    adapter = MCPAdapter(task=task, run_config=run_config)
    run, run_output = await adapter.invoke_returning_run_output("input")

    assert run_output.output == {"status": "ok"}
    assert run.output.output == '{"status": "ok"}'
    mock_session.call_tool.assert_called_once_with(
        name="test_file_python",
        arguments={"input": "input"},
    )


@pytest.mark.asyncio
@patch("kiln_ai.tools.mcp_server_tool.get_agent_run_id", return_value="test_run_id")
@patch("kiln_ai.tools.mcp_server_tool.MCPSessionManager")
async def test_mcp_adapter_string_in_string_out(
    mock_session_manager, _mock_run_id, project_with_local_mcp_server, local_mcp_tool_id
):
    project, _ = project_with_local_mcp_server
    task = Task(
        name="Plaintext Task",
        parent=project,
        instruction="Echo input",
    )

    run_config = McpRunConfigProperties(
        tool_reference=MCPToolReference(tool_id=local_mcp_tool_id)
    )

    mock_session = _mock_mcp_call(mock_session_manager, "ok")

    adapter = MCPAdapter(task=task, run_config=run_config)
    run, run_output = await adapter.invoke_returning_run_output("input")

    assert run_output.output == "ok"
    assert run.output.output == "ok"
    assert run.output.source.type == DataSourceType.tool_call
    mock_session.call_tool.assert_called_once_with(
        name="test_file_python",
        arguments={"input": "input"},
    )


@pytest.mark.asyncio
@patch("kiln_ai.tools.mcp_server_tool.get_agent_run_id", return_value="test_run_id")
@patch("kiln_ai.tools.mcp_server_tool.MCPSessionManager")
async def test_mcp_adapter_struct_in_struct_out(
    mock_session_manager, _mock_run_id, project_with_local_mcp_server, local_mcp_tool_id
):
    project, _ = project_with_local_mcp_server
    task = Task(
        name="Structured Task",
        parent=project,
        instruction="Return JSON",
        input_json_schema=json.dumps(
            {
                "type": "object",
                "properties": {"TEST_PATH": {"type": "string"}},
                "required": ["TEST_PATH"],
            }
        ),
        output_json_schema=json.dumps(
            {
                "type": "object",
                "properties": {"status": {"type": "string"}},
                "required": ["status"],
            }
        ),
    )

    run_config = McpRunConfigProperties(
        tool_reference=MCPToolReference(tool_id=local_mcp_tool_id)
    )

    mock_session = _mock_mcp_call(mock_session_manager, '{"status":"ok"}')

    adapter = MCPAdapter(task=task, run_config=run_config)
    run, run_output = await adapter.invoke_returning_run_output(
        {"TEST_PATH": "libs/core/kiln_ai/datamodel/test_run_config.py"}
    )

    assert run_output.output == {"status": "ok"}
    assert run.output.output == '{"status": "ok"}'
    mock_session.call_tool.assert_called_once_with(
        name="test_file_python",
        arguments={"TEST_PATH": "libs/core/kiln_ai/datamodel/test_run_config.py"},
    )


@pytest.mark.asyncio
@patch("kiln_ai.tools.mcp_server_tool.get_agent_run_id", return_value="test_run_id")
@patch("kiln_ai.tools.mcp_server_tool.MCPSessionManager")
async def test_mcp_adapter_emits_single_turn_trace(
    mock_session_manager, _mock_run_id, project_with_local_mcp_server, local_mcp_tool_id
):
    project, _ = project_with_local_mcp_server
    task = Task(
        name="Trace Task",
        parent=project,
        instruction="Echo input",
    )

    run_config = McpRunConfigProperties(
        tool_reference=MCPToolReference(tool_id=local_mcp_tool_id)
    )

    _mock_mcp_call(mock_session_manager, "ok")

    adapter = MCPAdapter(task=task, run_config=run_config)
    run, _ = await adapter.invoke_returning_run_output("input")

    assert run.trace == [
        {"role": "user", "content": "input"},
        {"role": "assistant", "content": "ok"},
    ]


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
    run_config = McpRunConfigProperties(
        tool_reference=MCPToolReference(tool_id=tool_id)
    )

    adapter = MCPAdapter(task=task, run_config=run_config)
    run, run_output = await adapter.invoke_returning_run_output(
        {"TEST_PATH": "libs/core/kiln_ai/datamodel/test_run_config.py"}
    )

    assert isinstance(run_output.output, str)
    assert run_output.output.strip()
    assert isinstance(run.output.output, str)
    assert run.output.output.strip()


@pytest.mark.asyncio
@patch("kiln_ai.tools.mcp_server_tool.MCPSessionManager")
async def test_mcp_adapter_sets_and_clears_run_context(
    mock_session_manager, project_with_local_mcp_server, local_mcp_tool_id
):
    project, _ = project_with_local_mcp_server
    task = Task(
        name="Run Context Task",
        parent=project,
        instruction="Echo input",
    )

    run_config = McpRunConfigProperties(
        tool_reference=MCPToolReference(tool_id=local_mcp_tool_id)
    )

    _mock_mcp_call(mock_session_manager, "ok")

    adapter = MCPAdapter(task=task, run_config=run_config)
    assert get_agent_run_id() is None

    await adapter.invoke_returning_run_output("input")

    assert get_agent_run_id() is None
