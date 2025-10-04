from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from kiln_ai.datamodel.external_tool_server import ExternalToolServer, ToolServerType
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.rag import RagConfig
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.tool_id import KILN_TASK_TOOL_ID_PREFIX
from kiln_ai.utils.config import MCP_SECRETS_KEY
from mcp.types import ListToolsResult, Tool
from pydantic import ValidationError

from app.desktop.studio_server.tool_api import (
    ExternalToolApiDescription,
    available_mcp_tools,
    connect_tool_servers_api,
    tool_server_from_id,
    validate_tool_server_connectivity,
)


@pytest.fixture
def mock_project_from_id(test_project):
    with patch(
        "app.desktop.studio_server.tool_api.project_from_id",
        return_value=test_project,
    ) as mock:
        yield mock


def create_mcp_session_manager_patch(
    mock_tools=None, connection_error=None, list_tools_error=None
):
    """
    Creates a mock MCP session manager patch with various scenarios.

    Args:
        mock_tools: List of Tool objects to return from list_tools (defaults to empty list)
        connection_error: Exception to raise when creating MCP client connection
        list_tools_error: Exception to raise when calling list_tools

    Returns:
        Context manager that patches MCPSessionManager.shared
    """
    if mock_tools is None:
        mock_tools = []

    @asynccontextmanager
    async def mock_mcp_client(
        tool_server, force_oauth=False, oauth_callback_base_url=None
    ):
        if connection_error:
            raise connection_error

        mock_session = AsyncMock()
        if list_tools_error:
            mock_session.list_tools.side_effect = list_tools_error
        else:
            mock_session.list_tools.return_value = ListToolsResult(tools=mock_tools)

        yield mock_session

    return patch(
        "app.desktop.studio_server.tool_api.MCPSessionManager.shared"
    ), mock_mcp_client


@asynccontextmanager
async def mock_mcp_success(tools=None):
    """Context manager for successful MCP operations with optional tools."""
    tools = tools or []
    patch_obj, mock_client = create_mcp_session_manager_patch(mock_tools=tools)

    with patch_obj as mock_session_manager_shared:
        mock_session_manager = Mock()
        mock_session_manager.mcp_client = mock_client
        mock_session_manager_shared.return_value = mock_session_manager
        yield


@asynccontextmanager
async def mock_mcp_connection_error(error_message="Connection failed"):
    """Context manager for MCP connection errors."""
    error = Exception(error_message)
    patch_obj, mock_client = create_mcp_session_manager_patch(connection_error=error)

    with patch_obj as mock_session_manager_shared:
        mock_session_manager = Mock()
        mock_session_manager.mcp_client = mock_client
        mock_session_manager_shared.return_value = mock_session_manager
        yield


@asynccontextmanager
async def mock_mcp_list_tools_error(error_message="list_tools failed"):
    """Context manager for MCP list_tools errors."""
    error = Exception(error_message)
    patch_obj, mock_client = create_mcp_session_manager_patch(list_tools_error=error)

    with patch_obj as mock_session_manager_shared:
        mock_session_manager = Mock()
        mock_session_manager.mcp_client = mock_client
        mock_session_manager_shared.return_value = mock_session_manager
        yield


@pytest.fixture
def app():
    test_app = FastAPI()
    connect_tool_servers_api(test_app)
    return test_app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def test_project(tmp_path):
    project_path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()

    project = Project(name="Test Project", path=project_path)
    project.save_to_file()
    return project


@pytest.fixture
def mock_mcp_validation():
    """Fixture that provides a context manager for mocking MCP validation during tool creation"""
    return mock_mcp_success


async def test_create_tool_server_success(client, test_project):
    tool_data = {
        "name": "test_mcp_tool",
        "server_url": "https://example.com/mcp",
        "headers": {"Authorization": "Bearer test-token"},
        "description": "A test MCP tool",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_success():
            response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )

            assert response.status_code == 200
            result = response.json()
            assert result["name"] == "test_mcp_tool"
            assert result["type"] == "remote_mcp"
            assert result["description"] == "A test MCP tool"
            assert result["properties"]["server_url"] == "https://example.com/mcp"
            assert (
                result["properties"]["headers"]["Authorization"] == "Bearer test-token"
            )
            assert "id" in result
            assert "created_at" in result


async def test_create_tool_server_validation_success(client, test_project):
    """Test successful tool server creation with MCP validation"""
    tool_data = {
        "name": "validated_tool",
        "server_url": "https://example.com/mcp",
        "headers": {"Authorization": "Bearer token"},
        "description": "A validated MCP tool",
    }

    tools = [Tool(name="test_tool", description="Test tool", inputSchema={})]

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_success(tools=tools):
            response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )

            assert response.status_code == 200
            result = response.json()
            assert result["name"] == "validated_tool"
            assert result["type"] == "remote_mcp"


async def test_create_tool_server_validation_connection_failed(client, test_project):
    """Test tool server creation fails when MCP server is unreachable"""
    tool_data = {
        "name": "failing_tool",
        "server_url": "https://unreachable.example.com/mcp",
        "headers": {},
        "description": "Tool that will fail validation",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_connection_error():
            # Unhandled exception is now raised instead of returning 422
            with pytest.raises(Exception, match="Connection failed"):
                client.post(
                    f"/api/projects/{test_project.id}/connect_remote_mcp",
                    json=tool_data,
                )


async def test_create_tool_server_validation_list_tools_failed(client, test_project):
    """Test tool server creation fails when MCP list_tools fails"""
    tool_data = {
        "name": "list_tools_failing",
        "server_url": "https://example.com/mcp",
        "headers": {},
        "description": "Tool where list_tools fails",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_list_tools_error():
            # Unhandled exception is now raised instead of returning 422
            with pytest.raises(Exception, match="list_tools failed"):
                client.post(
                    f"/api/projects/{test_project.id}/connect_remote_mcp",
                    json=tool_data,
                )


def test_create_tool_server_validation_empty_name(client, test_project):
    """Test tool server creation fails when name is empty"""
    tool_data = {
        "name": "",  # Empty name should fail validation
        "server_url": "https://example.com/mcp",
        "headers": {},
        "description": "Tool with empty name",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        # ValidationError should be raised during ExternalToolServer creation
        with pytest.raises(ValidationError) as exc_info:
            client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )

        # Check that the error mentions name length or requirement
        error_str = str(exc_info.value)
        assert "too short" in error_str or "Name is required" in error_str


async def test_create_tool_server_no_headers(client, test_project):
    tool_data = {
        "name": "test_tool",
        "server_url": "https://example.com/api",
        "description": "A test tool",
        # headers defaults to empty dict, which is allowed
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_success():
            response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )

            assert response.status_code == 200  # Empty headers are allowed
            result = response.json()
            assert result["name"] == "test_tool"
            assert result["properties"]["headers"] == {}


async def test_create_tool_server_empty_headers(
    client, test_project, mock_mcp_validation
):
    tool_data = {
        "name": "test_tool",
        "server_url": "https://example.com/api",
        "headers": {},  # Empty headers are allowed
        "description": "A test tool",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_validation():
            response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )

            assert response.status_code == 200  # Empty headers are allowed
            result = response.json()
            assert result["name"] == "test_tool"
            assert result["properties"]["headers"] == {}


def test_create_tool_server_missing_server_url(client, test_project):
    tool_data = {
        "name": "test_tool",
        "headers": {"Authorization": "Bearer token"},
        "description": "A test tool",
        # Missing required server_url
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        response = client.post(
            f"/api/projects/{test_project.id}/connect_remote_mcp",
            json=tool_data,
        )

        assert response.status_code == 422  # Validation error


def test_create_tool_server_missing_name(client, test_project):
    tool_data = {
        "server_url": "https://example.com/api",
        "headers": {"Authorization": "Bearer token"},
        "description": "A test tool",
        # Missing required name
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        response = client.post(
            f"/api/projects/{test_project.id}/connect_remote_mcp",
            json=tool_data,
        )

        assert response.status_code == 422  # Validation error


async def test_create_tool_server_no_description(
    client, test_project, mock_mcp_validation
):
    tool_data = {
        "name": "test_tool",
        "server_url": "https://example.com/api",
        "headers": {"Authorization": "Bearer token"},
        # description is optional
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_validation():
            response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )

            assert response.status_code == 200
            result = response.json()
            assert result["description"] is None


def test_get_available_tool_servers_empty(client, test_project):
    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        response = client.get(f"/api/projects/{test_project.id}/available_tool_servers")

        assert response.status_code == 200
        result = response.json()
        assert result == []


async def test_get_available_tool_servers_with_tool_server(client, test_project):
    # First create a tool server
    tool_data = {
        "name": "my_tool",
        "server_url": "https://api.example.com",
        "headers": {"X-API-Key": "secret"},
        "description": "My awesome tool",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_success():
            create_response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )
            assert create_response.status_code == 200
        created_tool = create_response.json()

        # Then get the list of tool servers
        response = client.get(f"/api/projects/{test_project.id}/available_tool_servers")

        assert response.status_code == 200
        result = response.json()
        assert len(result) == 1
        assert result[0]["name"] == "my_tool"
        assert result[0]["id"] == created_tool["id"]
        assert result[0]["description"] == "My awesome tool"
        assert "missing_secrets" in result[0]
        assert isinstance(result[0]["missing_secrets"], list)
        assert "missing_oauth" in result[0]
        assert result[0]["missing_oauth"] is False


async def test_get_available_tool_servers_with_missing_secrets(client, test_project):
    """Test that get_available_tool_servers includes missing_secrets field"""
    tool_data = {
        "name": "tool_with_missing_secrets",
        "server_url": "https://api.example.com",
        "headers": {"Authorization": "Bearer token", "X-API-Key": "secret"},
        "secret_header_keys": ["Authorization", "X-API-Key"],
        "description": "Tool with missing secrets",
        "is_archived": False,
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_success():
            create_response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )
            assert create_response.status_code == 200
        created_tool = create_response.json()

        # Mock the tool server to have missing secrets
        with patch("app.desktop.studio_server.tool_api.tool_server_from_id"):
            mock_tool_server = Mock()
            mock_tool_server.id = created_tool["id"]
            mock_tool_server.name = "tool_with_missing_secrets"
            mock_tool_server.type = ToolServerType.remote_mcp
            mock_tool_server.description = "Tool with missing secrets"
            mock_tool_server.retrieve_secrets.return_value = (
                {},
                ["Authorization", "X-API-Key"],
            )
            # Mock properties.get to return False for is_archived
            mock_tool_server.properties = {"is_archived": False}

            # Mock the project's external_tool_servers method
            mock_project = Mock()
            mock_project.external_tool_servers.return_value = [mock_tool_server]
            mock_project_from_id.return_value = mock_project

            # Get the list of tool servers
            response = client.get(
                f"/api/projects/{test_project.id}/available_tool_servers"
            )

            assert response.status_code == 200
            result = response.json()
            assert len(result) == 1
            assert result[0]["name"] == "tool_with_missing_secrets"
            assert result[0]["id"] == created_tool["id"]
            assert result[0]["description"] == "Tool with missing secrets"
            assert "missing_secrets" in result[0]
            assert set(result[0]["missing_secrets"]) == {"Authorization", "X-API-Key"}
            assert "missing_oauth" in result[0]
            assert result[0]["missing_oauth"] is False


async def test_get_available_tool_servers_local_mcp_with_missing_secrets(
    client, test_project
):
    """Test that get_available_tool_servers includes missing_secrets field for local MCP servers"""
    tool_data = {
        "name": "local_tool_with_missing_secrets",
        "command": "python",
        "args": ["-m", "my_mcp_server"],
        "env_vars": {"DATABASE_URL": "postgres://localhost", "API_KEY": "secret"},
        "secret_env_var_keys": ["API_KEY"],
        "description": "Local tool with missing secrets",
        "is_archived": False,
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        # Mock MCPSessionManager for shell path cache clearing
        with patch(
            "app.desktop.studio_server.tool_api.MCPSessionManager.shared"
        ) as mock_session_manager_shared:
            mock_session_manager = Mock()
            mock_session_manager.clear_shell_path_cache = Mock()
            mock_session_manager_shared.return_value = mock_session_manager

            async with mock_mcp_success():
                create_response = client.post(
                    f"/api/projects/{test_project.id}/connect_local_mcp",
                    json=tool_data,
                )
                assert create_response.status_code == 200
            created_tool = create_response.json()

            # Mock the tool server to have missing secrets
            mock_tool_server = Mock()
            mock_tool_server.id = created_tool["id"]
            mock_tool_server.name = "local_tool_with_missing_secrets"
            mock_tool_server.type = ToolServerType.local_mcp
            mock_tool_server.description = "Local tool with missing secrets"
            mock_tool_server.retrieve_secrets.return_value = ({}, ["API_KEY"])
            # Mock properties.get to return False for is_archived
            mock_tool_server.properties = {"is_archived": False}

            # Mock the project's external_tool_servers method
            mock_project = Mock()
            mock_project.external_tool_servers.return_value = [mock_tool_server]
            mock_project_from_id.return_value = mock_project

            # Get the list of tool servers
            response = client.get(
                f"/api/projects/{test_project.id}/available_tool_servers"
            )

            assert response.status_code == 200
            result = response.json()
            assert len(result) == 1
            assert result[0]["name"] == "local_tool_with_missing_secrets"
            assert result[0]["id"] == created_tool["id"]
            assert result[0]["description"] == "Local tool with missing secrets"
            assert "missing_secrets" in result[0]
            assert result[0]["missing_secrets"] == ["API_KEY"]
            assert "missing_oauth" in result[0]
            assert result[0]["missing_oauth"] is False


async def test_get_tool_server_success(client, test_project):
    # First create a tool server
    tool_data = {
        "name": "test_get_tool",
        "server_url": "https://example.com/api",
        "headers": {"Authorization": "Bearer token"},
        "description": "Tool for get test",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        # Create the tool with empty tools
        async with mock_mcp_success():
            create_response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )
            assert create_response.status_code == 200
        created_tool = create_response.json()
        tool_server_id = created_tool["id"]

        # Mock retrieval with specific tools
        mock_tools = [
            Tool(name="test_tool_1", description="First test tool", inputSchema={}),
            Tool(name="calculator", description="Math calculations", inputSchema={}),
        ]

        async with mock_mcp_success(tools=mock_tools):
            # Now get the tool server
            response = client.get(
                f"/api/projects/{test_project.id}/tool_servers/{tool_server_id}"
            )

            assert response.status_code == 200
            result = response.json()
            # Verify the tool server details match what we created
            assert result["name"] == "test_get_tool"
            assert result["type"] == "remote_mcp"
            assert result["description"] == "Tool for get test"
            assert result["properties"]["server_url"] == "https://example.com/api"
            assert result["properties"]["headers"]["Authorization"] == "Bearer token"
            assert "id" in result  # Just verify ID exists, don't check exact value

            # Verify available_tools is populated
            assert "available_tools" in result
            assert len(result["available_tools"]) == 2
            tool_names = [tool["name"] for tool in result["available_tools"]]
            assert "test_tool_1" in tool_names
            assert "calculator" in tool_names


async def test_get_tool_server_mcp_error_handling(client, test_project):
    """Test that MCP server errors are handled gracefully and return empty tools"""
    # First create a tool server
    tool_data = {
        "name": "failing_mcp_tool",
        "server_url": "https://example.com/api",
        "headers": {},
        "description": "MCP tool that will fail",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        # Create the tool with successful validation
        async with mock_mcp_success():
            create_response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )
            assert create_response.status_code == 200
        created_tool = create_response.json()
        tool_server_id = created_tool["id"]

        # Mock retrieval with list_tools error
        async with mock_mcp_list_tools_error("Connection failed"):
            # The API should handle the exception gracefully
            # For now, let's test that it raises the exception since that's the current behavior
            with pytest.raises(Exception, match="Connection failed"):
                client.get(
                    f"/api/projects/{test_project.id}/tool_servers/{tool_server_id}"
                )


def test_get_tool_server_not_found(client, test_project):
    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        # Try to get a non-existent tool server
        response = client.get(
            f"/api/projects/{test_project.id}/tool_servers/nonexistent-tool-server-id"
        )

        assert response.status_code == 404
        result = response.json()
        assert result["detail"] == "Tool server not found"


def test_get_available_tools_empty(client, test_project):
    """Test get_available_tools with no tool servers returns empty list"""
    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        response = client.get(f"/api/projects/{test_project.id}/available_tools")

        assert response.status_code == 200
        result = response.json()
        assert result == []


async def test_get_available_tools_success(client, test_project):
    """Test get_available_tools successfully retrieves tools from MCP servers"""
    # First create a tool server
    tool_data = {
        "name": "test_available_tools",
        "server_url": "https://example.com/mcp",
        "headers": {"Authorization": "Bearer token"},
        "description": "Test MCP server",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        # Create the tool server
        async with mock_mcp_success():
            create_response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )
            assert create_response.status_code == 200
        created_tool = create_response.json()
        server_id = created_tool["id"]

        # Mock retrieval with specific tools
        mock_tools = [
            Tool(name="echo", description="Echo tool", inputSchema={}),
            Tool(name="calculator", description="Math calculator", inputSchema={}),
            Tool(
                name="weather", description=None, inputSchema={}
            ),  # Test None description
        ]

        async with mock_mcp_success(tools=mock_tools):
            # Get available tools
            response = client.get(f"/api/projects/{test_project.id}/available_tools")

            assert response.status_code == 200
            set_result = response.json()
            assert len(set_result) == 1
            assert set_result[0]["set_name"] == "MCP Server: test_available_tools"
            result = set_result[0]["tools"]
            assert len(result) == 3

            # Verify tool details
            tool_names = [tool["name"] for tool in result]
            assert "echo" in tool_names
            assert "calculator" in tool_names
            assert "weather" in tool_names

            # Verify tool IDs are properly formatted
            for tool in result:
                assert tool["id"].startswith(f"mcp::remote::{server_id}::")
                assert tool["name"] in ["echo", "calculator", "weather"]

            # Find specific tools and check their descriptions
            echo_tool = next(t for t in result if t["name"] == "echo")
            assert echo_tool["description"] == "Echo tool"

            weather_tool = next(t for t in result if t["name"] == "weather")
            assert weather_tool["description"] is None


async def test_get_available_tools_multiple_servers(client, test_project):
    """Test get_available_tools with multiple tool servers including kiln task tools"""

    # Create first MCP tool server
    tool_data_1 = {
        "name": "mcp_server_1",
        "server_url": "https://example1.com/mcp",
        "headers": {},
        "description": "First MCP server",
    }

    # Create second MCP tool server
    tool_data_2 = {
        "name": "mcp_server_2",
        "server_url": "https://example2.com/mcp",
        "headers": {},
        "description": "Second MCP server",
    }

    # Create kiln task tool servers
    kiln_task_server_1 = ExternalToolServer(
        name="kiln_task_server_1",
        type=ToolServerType.kiln_task,
        description="First kiln task server",
        properties={
            "name": "test_task_tool_1",
            "description": "First test task tool",
            "task_id": "task_1",
            "run_config_id": "run_config_1",
            "is_archived": False,
        },
        parent=test_project,
    )

    kiln_task_server_2 = ExternalToolServer(
        name="kiln_task_server_2",
        type=ToolServerType.kiln_task,
        description="Second kiln task server",
        properties={
            "name": "test_task_tool_2",
            "description": "Second test task tool",
            "task_id": "task_2",
            "run_config_id": "run_config_2",
            "is_archived": False,
        },
        parent=test_project,
    )

    # Save the kiln task tool servers
    kiln_task_server_1.save_to_file()
    kiln_task_server_2.save_to_file()

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        # Create both tool servers
        async with mock_mcp_success():
            response1 = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data_1,
            )
            assert response1.status_code == 200
            server1_id = response1.json()["id"]

            response2 = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data_2,
            )
            assert response2.status_code == 200
            server2_id = response2.json()["id"]

        # Mock tools for both servers
        mock_tools_1 = [
            Tool(name="tool_a", description="Tool A from server 1", inputSchema={}),
            Tool(name="tool_b", description="Tool B from server 1", inputSchema={}),
        ]
        mock_tools_2 = [
            Tool(name="tool_x", description="Tool X from server 2", inputSchema={}),
        ]

        # Create a mapping of server URLs to their tools
        tools_by_server = {
            "https://example1.com/mcp": ListToolsResult(tools=mock_tools_1),
            "https://example2.com/mcp": ListToolsResult(tools=mock_tools_2),
        }

        @asynccontextmanager
        async def mock_mcp_client(
            tool_server, force_oauth=False, oauth_callback_base_url=None
        ):
            mock_session = AsyncMock()
            # Use the server URL to determine which tools to return
            mock_session.list_tools.return_value = tools_by_server[
                tool_server.properties["server_url"]
            ]
            yield mock_session

        with patch(
            "app.desktop.studio_server.tool_api.MCPSessionManager.shared"
        ) as mock_session_manager_shared:
            mock_session_manager = AsyncMock()
            mock_session_manager.mcp_client = mock_mcp_client
            mock_session_manager_shared.return_value = mock_session_manager

            # Get available tools
            response = client.get(f"/api/projects/{test_project.id}/available_tools")

            assert response.status_code == 200
            set_result = response.json()
            assert len(set_result) == 3  # 2 MCP servers + 1 kiln task set

            # Find sets by name instead of assuming order
            server1_set = next(
                (s for s in set_result if s["set_name"] == "MCP Server: mcp_server_1"),
                None,
            )
            server2_set = next(
                (s for s in set_result if s["set_name"] == "MCP Server: mcp_server_2"),
                None,
            )
            kiln_task_set = next(
                (s for s in set_result if s["set_name"] == "Kiln Tasks as Tools"),
                None,
            )

            assert server1_set is not None, (
                "Could not find MCP Server: mcp_server_1 in results"
            )
            assert server2_set is not None, (
                "Could not find MCP Server: mcp_server_2 in results"
            )
            assert kiln_task_set is not None, (
                "Could not find Kiln Tasks as Tools in results"
            )

            assert len(server1_set["tools"]) == 2  # 2 from server1
            assert len(server2_set["tools"]) == 1  # 1 from server2
            assert len(kiln_task_set["tools"]) == 2  # 2 kiln task tools

            for tool in server1_set["tools"]:
                assert tool["id"].startswith(f"mcp::remote::{server1_id}::")
            for tool in server2_set["tools"]:
                assert tool["id"].startswith(f"mcp::remote::{server2_id}::")
            for tool in kiln_task_set["tools"]:
                assert tool["id"].startswith(KILN_TASK_TOOL_ID_PREFIX)

            # Verify MCP tools from both servers are present
            tool_names = [tool["name"] for tool in server1_set["tools"]]
            assert "tool_a" in tool_names
            assert "tool_b" in tool_names
            tool_names = [tool["name"] for tool in server2_set["tools"]]
            assert "tool_x" in tool_names

            # Verify kiln task tool names
            kiln_tool_names = [tool["name"] for tool in kiln_task_set["tools"]]
            assert "test_task_tool_1" in kiln_tool_names
            assert "test_task_tool_2" in kiln_tool_names

            # Verify kiln task tool IDs
            tool1 = next(
                t for t in kiln_task_set["tools"] if t["name"] == "test_task_tool_1"
            )
            assert tool1["id"] == f"{KILN_TASK_TOOL_ID_PREFIX}{kiln_task_server_1.id}"
            tool2 = next(
                t for t in kiln_task_set["tools"] if t["name"] == "test_task_tool_2"
            )
            assert tool2["id"] == f"{KILN_TASK_TOOL_ID_PREFIX}{kiln_task_server_2.id}"


async def test_get_available_tools_mcp_error_handling(client, test_project):
    """Test get_available_tools handles MCP connection errors gracefully"""
    # Create a tool server
    tool_data = {
        "name": "failing_mcp_server",
        "server_url": "https://failing.example.com/mcp",
        "headers": {},
        "description": "MCP server that will fail",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        # Create the tool server
        async with mock_mcp_success():
            create_response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )
            assert create_response.status_code == 200

        # Mock retrieval with error
        async with mock_mcp_list_tools_error("MCP connection failed"):
            # The API should handle the exception gracefully and return an empty list
            # The failing server should be skipped and not appear in the results
            response = client.get(f"/api/projects/{test_project.id}/available_tools")

            assert response.status_code == 200
            result = response.json()

            # Should return an empty list since the MCP server failed
            assert len(result) == 0


def test_get_available_tools_demo_tools_enabled(client, test_project):
    """Test get_available_tools includes demo tools when enabled"""
    with (
        patch(
            "app.desktop.studio_server.tool_api.project_from_id"
        ) as mock_project_from_id,
        patch("app.desktop.studio_server.tool_api.Config.shared") as mock_config,
    ):
        mock_project_from_id.return_value = test_project

        # Mock config to enable demo tools
        mock_config_instance = Mock()
        mock_config_instance.enable_demo_tools = True
        mock_config_instance.user_id = "test_user"
        mock_config.return_value = mock_config_instance

        response = client.get(f"/api/projects/{test_project.id}/available_tools")

        assert response.status_code == 200
        result = response.json()

        # Should have one tool set for demo tools
        assert len(result) == 1
        demo_set = result[0]
        assert demo_set["set_name"] == "Kiln Demo Tools"
        assert len(demo_set["tools"]) == 4

        # Verify all demo tools are present with correct IDs and names
        tool_names = [tool["name"] for tool in demo_set["tools"]]
        tool_ids = [tool["id"] for tool in demo_set["tools"]]

        assert "Addition" in tool_names
        assert "Subtraction" in tool_names
        assert "Multiplication" in tool_names
        assert "Division" in tool_names

        assert "kiln_tool::add_numbers" in tool_ids
        assert "kiln_tool::subtract_numbers" in tool_ids
        assert "kiln_tool::multiply_numbers" in tool_ids
        assert "kiln_tool::divide_numbers" in tool_ids

        # Verify descriptions
        for tool in demo_set["tools"]:
            assert tool["description"] is not None
            if tool["name"] == "Addition":
                assert tool["description"] == "Add two numbers together"
            elif tool["name"] == "Subtraction":
                assert tool["description"] == "Subtract two numbers"
            elif tool["name"] == "Multiplication":
                assert tool["description"] == "Multiply two numbers"
            elif tool["name"] == "Division":
                assert tool["description"] == "Divide two numbers"


def test_get_available_tools_demo_tools_disabled(client, test_project):
    """Test get_available_tools excludes demo tools when disabled"""
    with (
        patch(
            "app.desktop.studio_server.tool_api.project_from_id"
        ) as mock_project_from_id,
        patch("app.desktop.studio_server.tool_api.Config.shared") as mock_config,
    ):
        mock_project_from_id.return_value = test_project

        # Mock config to disable demo tools (default behavior)
        mock_config_instance = Mock()
        mock_config_instance.enable_demo_tools = False
        mock_config_instance.user_id = "test_user"
        mock_config.return_value = mock_config_instance

        response = client.get(f"/api/projects/{test_project.id}/available_tools")

        assert response.status_code == 200
        result = response.json()

        # Should have no tool sets when demo tools are disabled and no MCP servers
        assert len(result) == 0


async def test_create_tool_server_whitespace_handling(
    client, test_project, mock_mcp_validation
):
    """Test that whitespace is properly handled from inputs"""
    tool_data = {
        "name": "test_tool",  # Frontend trims whitespace before sending
        "server_url": "https://example.com/api",
        "headers": {"Authorization": "Bearer token"},
        "description": "A test tool",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_validation():
            response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )

        assert response.status_code == 200
        result = response.json()
        assert result["name"] == "test_tool"
        assert result["properties"]["server_url"] == "https://example.com/api"
        assert result["properties"]["headers"]["Authorization"] == "Bearer token"
        assert result["description"] == "A test tool"


async def test_create_tool_server_complex_headers(
    client, test_project, mock_mcp_validation
):
    """Test creation with complex header configurations"""
    tool_data = {
        "name": "complex_headers_tool",
        "server_url": "https://api.example.com",
        "headers": {
            "Authorization": "Bearer abc123def456",
            "X-API-Key": "my-secret-key",
            "Content-Type": "application/json",
            "User-Agent": "Kiln-AI/1.0",
            "X-Custom-Header": "custom-value",
        },
        "description": "Tool with complex headers",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_validation():
            response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )

        assert response.status_code == 200
        result = response.json()
        assert result["name"] == "complex_headers_tool"
        assert len(result["properties"]["headers"]) == 5
        assert result["properties"]["headers"]["Authorization"] == "Bearer abc123def456"
        assert result["properties"]["headers"]["X-API-Key"] == "my-secret-key"
        assert result["properties"]["headers"]["Content-Type"] == "application/json"


async def test_create_tool_server_valid_special_characters_in_name(
    client, test_project
):
    """Test tool server creation with valid special characters in name"""
    tool_data = {
        "name": "my-tool_server_test",  # Uses valid characters (no dots)
        "server_url": "https://example.com/api",
        "headers": {},
        "description": "Tool with valid special chars in name",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_success():
            response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )

        assert response.status_code == 200
        result = response.json()
        assert result["name"] == "my-tool_server_test"


async def test_create_tool_server_https_url(client, test_project):
    """Test successful creation with HTTPS URL"""
    tool_data = {
        "name": "secure_tool",
        "server_url": "https://secure.example.com:8443/mcp/api",
        "headers": {"Authorization": "Bearer secure-token"},
        "description": "Secure HTTPS tool",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_success():
            response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )

        assert response.status_code == 200
        result = response.json()
        assert (
            result["properties"]["server_url"]
            == "https://secure.example.com:8443/mcp/api"
        )


async def test_create_tool_server_http_url(client, test_project):
    """Test successful creation with HTTP URL"""
    tool_data = {
        "name": "http_tool",
        "server_url": "http://localhost:3000/api",
        "headers": {},
        "description": "Local HTTP tool",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_success():
            response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )

        assert response.status_code == 200
        result = response.json()
        assert result["properties"]["server_url"] == "http://localhost:3000/api"


async def test_create_tool_server_long_description(client, test_project):
    """Test creation with very long description"""
    long_description = "This is a very long description " * 50  # ~1500 characters
    tool_data = {
        "name": "long_desc_tool",
        "server_url": "https://example.com/api",
        "headers": {},
        "description": long_description,
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_success():
            response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )

        assert response.status_code == 200
        result = response.json()
        assert result["description"] == long_description


async def test_create_tool_server_unicode_characters(client, test_project):
    """Test creation with Unicode characters in name and description"""
    tool_data = {
        "name": "测试工具",
        "server_url": "https://example.com/api",
        "headers": {"Authorization": "Bearer token"},
        "description": "This is a test tool with émojis 🚀 and spéciàl characters",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_success():
            response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )

            assert response.status_code == 200
            result = response.json()
            assert result["name"] == "测试工具"
            assert "émojis 🚀" in result["description"]


async def test_create_tool_server_header_value_with_special_characters(
    client, test_project
):
    """Test creation with header values containing special characters"""
    tool_data = {
        "name": "special_header_tool",
        "server_url": "https://example.com/api",
        "headers": {
            "Authorization": "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9",
            "X-API-Key": "key_with-dashes_and.dots",
            "X-User-Agent": "Mozilla/5.0 (compatible; Kiln/1.0)",
        },
        "description": "Tool with special header values",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_success():
            response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )

            assert response.status_code == 200
            result = response.json()
            headers = result["properties"]["headers"]
            assert (
                headers["Authorization"]
                == "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9"
            )
            assert headers["X-API-Key"] == "key_with-dashes_and.dots"
            assert headers["X-User-Agent"] == "Mozilla/5.0 (compatible; Kiln/1.0)"


async def test_create_tool_server_update_workflow(client, test_project):
    """Test the complete workflow of creating, listing, and retrieving a tool server"""
    # Step 1: Create a tool server
    tool_data = {
        "name": "workflow_test_tool",
        "server_url": "https://workflow.example.com/api",
        "headers": {"Authorization": "Bearer workflow-token"},
        "description": "Tool for testing complete workflow",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        # Step 1: Create the tool server
        async with mock_mcp_success():
            create_response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )
            assert create_response.status_code == 200

        created_tool = create_response.json()
        tool_server_id = created_tool["id"]

        # Step 2: Verify it appears in the list
        list_response = client.get(
            f"/api/projects/{test_project.id}/available_tool_servers"
        )
        assert list_response.status_code == 200
        tool_servers = list_response.json()
        assert len(tool_servers) == 1
        assert tool_servers[0]["id"] == tool_server_id
        assert tool_servers[0]["name"] == "workflow_test_tool"

        # Step 3 & 4: Get detailed view with mock tools
        mock_tools = [
            Tool(name="workflow_tool", description="Workflow tool", inputSchema={}),
        ]

        async with mock_mcp_success(tools=mock_tools):
            detail_response = client.get(
                f"/api/projects/{test_project.id}/tool_servers/{tool_server_id}"
            )
            assert detail_response.status_code == 200
            detailed_tool = detail_response.json()
            assert detailed_tool["id"] == tool_server_id
            assert detailed_tool["name"] == "workflow_test_tool"
            assert len(detailed_tool["available_tools"]) == 1
            assert detailed_tool["available_tools"][0]["name"] == "workflow_tool"


async def test_create_tool_server_concurrent_creation(client, test_project):
    """Test creating multiple tool servers concurrently"""
    tool_servers = [
        {
            "name": f"concurrent_tool_{i}",
            "server_url": f"https://example{i}.com/api",
            "headers": {"X-Server-ID": str(i)},
            "description": f"Concurrent tool server {i}",
        }
        for i in range(3)
    ]

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_success():
            created_tools = []
            for tool_data in tool_servers:
                response = client.post(
                    f"/api/projects/{test_project.id}/connect_remote_mcp",
                    json=tool_data,
                )
                assert response.status_code == 200
                created_tools.append(response.json())

            # Verify all tools were created with unique IDs
            tool_ids = [tool["id"] for tool in created_tools]
            assert len(set(tool_ids)) == 3  # All IDs should be unique

        # Verify they all appear in the list
        list_response = client.get(
            f"/api/projects/{test_project.id}/available_tool_servers"
        )
        assert list_response.status_code == 200
        tool_servers_list = list_response.json()
        assert len(tool_servers_list) == 3

        # Verify correct names
        server_names = {server["name"] for server in tool_servers_list}
        expected_names = {"concurrent_tool_0", "concurrent_tool_1", "concurrent_tool_2"}
        assert server_names == expected_names


async def test_create_tool_server_duplicate_names_allowed(client, test_project):
    """Test that creating tool servers with duplicate names is allowed"""
    tool_data = {
        "name": "duplicate_name_tool",
        "server_url": "https://example1.com/api",
        "headers": {},
        "description": "First tool with this name",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_success():
            # Create first tool
            response1 = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )
            assert response1.status_code == 200
            tool1 = response1.json()

            # Create second tool with same name but different URL
            tool_data["server_url"] = "https://example2.com/api"
            tool_data["description"] = "Second tool with this name"

            response2 = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )
            assert response2.status_code == 200
            tool2 = response2.json()

            # Verify they have different IDs
            assert tool1["id"] != tool2["id"]
        assert tool1["name"] == tool2["name"] == "duplicate_name_tool"

        # Verify both appear in list
        list_response = client.get(
            f"/api/projects/{test_project.id}/available_tool_servers"
        )
        assert list_response.status_code == 200
        tool_servers = list_response.json()
        assert len(tool_servers) == 2


async def test_create_tool_server_max_length_name(client, test_project):
    """Test creation with maximum allowed name length (120 characters)"""
    max_length_name = "a" * 120  # 120 character name (the max allowed)
    tool_data = {
        "name": max_length_name,
        "server_url": "https://example.com/api",
        "headers": {},
        "description": "Tool with maximum length name",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_success():
            response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )

            assert response.status_code == 200
            result = response.json()
            assert result["name"] == max_length_name


def test_create_tool_server_name_too_long_validation(client, test_project):
    """Test that names longer than 120 characters are rejected"""
    too_long_name = "a" * 121  # 121 character name (exceeds max)
    tool_data = {
        "name": too_long_name,
        "server_url": "https://example.com/api",
        "headers": {},
        "description": "Tool with name that's too long",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        # ValidationError should be raised during ExternalToolServer creation
        with pytest.raises(ValidationError) as exc_info:
            client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )

        error_str = str(exc_info.value)
        assert "too long" in error_str or "120" in error_str


def test_create_tool_server_invalid_name_characters(client, test_project):
    """Test that names with forbidden characters are rejected"""
    forbidden_chars = [".", "/", "\\", "?", "%", "*", ":", "|", "<", ">", ",", ";", "="]

    for char in forbidden_chars[:3]:  # Test just a few to avoid too many test cases
        tool_data = {
            "name": f"invalid{char}name",
            "server_url": "https://example.com/api",
            "headers": {},
            "description": f"Tool with forbidden character {char}",
        }

        with patch(
            "app.desktop.studio_server.tool_api.project_from_id"
        ) as mock_project_from_id:
            mock_project_from_id.return_value = test_project

            # ValidationError should be raised during ExternalToolServer creation
            with pytest.raises(ValidationError) as exc_info:
                client.post(
                    f"/api/projects/{test_project.id}/connect_remote_mcp",
                    json=tool_data,
                )

            error_str = str(exc_info.value)
            assert (
                "invalid" in error_str.lower()
                or "forbidden" in error_str.lower()
                or "cannot contain" in error_str.lower()
            )


def test_create_tool_server_url_with_query_params(client, test_project):
    """Test creation with URL containing query parameters"""
    tool_data = {
        "name": "query_param_tool",
        "server_url": "https://api.example.com/mcp?version=v1&timeout=30",
        "headers": {"Authorization": "Bearer token"},
        "description": "Tool with query parameters in URL",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        # Mock successful MCP validation
        mock_session = AsyncMock()
        mock_session.list_tools.return_value = ListToolsResult(tools=[])

        @asynccontextmanager
        async def mock_mcp_client(
            tool_server, force_oauth=False, oauth_callback_base_url=None
        ):
            yield mock_session

        with patch(
            "app.desktop.studio_server.tool_api.MCPSessionManager.shared"
        ) as mock_session_manager_shared:
            mock_session_manager = AsyncMock()
            mock_session_manager.mcp_client = mock_mcp_client
            mock_session_manager_shared.return_value = mock_session_manager

            response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )

        assert response.status_code == 200
        result = response.json()
        assert (
            result["properties"]["server_url"]
            == "https://api.example.com/mcp?version=v1&timeout=30"
        )


def test_create_tool_server_empty_string_description(client, test_project):
    """Test creation with empty string description (should be treated as None)"""
    tool_data = {
        "name": "empty_desc_tool",
        "server_url": "https://example.com/api",
        "headers": {},
        "description": "",  # Empty string
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        # Mock successful MCP validation
        mock_session = AsyncMock()
        mock_session.list_tools.return_value = ListToolsResult(tools=[])

        @asynccontextmanager
        async def mock_mcp_client(
            tool_server, force_oauth=False, oauth_callback_base_url=None
        ):
            yield mock_session

        with patch(
            "app.desktop.studio_server.tool_api.MCPSessionManager.shared"
        ) as mock_session_manager_shared:
            mock_session_manager = AsyncMock()
            mock_session_manager.mcp_client = mock_mcp_client
            mock_session_manager_shared.return_value = mock_session_manager

            response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )

        assert response.status_code == 200
        result = response.json()
        # Backend should preserve empty string, frontend converts to null
        assert result["description"] == ""


def test_get_tool_server_with_many_tools(client, test_project):
    """Test getting tool server details when MCP server returns many tools"""
    # Create a tool server
    tool_data = {
        "name": "many_tools_server",
        "server_url": "https://example.com/api",
        "headers": {},
        "description": "Server with many tools",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        # Mock successful MCP validation for creation
        mock_session_create = AsyncMock()
        mock_session_create.list_tools.return_value = ListToolsResult(tools=[])

        @asynccontextmanager
        async def mock_mcp_client_create(
            tool_server, force_oauth=False, oauth_callback_base_url=None
        ):
            yield mock_session_create

        with patch(
            "app.desktop.studio_server.tool_api.MCPSessionManager.shared"
        ) as mock_session_manager_shared_create:
            mock_session_manager_create = Mock()
            mock_session_manager_create.mcp_client = mock_mcp_client_create
            mock_session_manager_shared_create.return_value = (
                mock_session_manager_create
            )

            create_response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )
            assert create_response.status_code == 200
        created_tool = create_response.json()
        tool_server_id = created_tool["id"]

        # Mock MCP server with many tools
        mock_tools = [
            Tool(name=f"tool_{i}", description=f"Tool number {i}", inputSchema={})
            for i in range(20)
        ]
        mock_result = ListToolsResult(tools=mock_tools)
        mock_session = AsyncMock()
        mock_session.list_tools.return_value = mock_result

        @asynccontextmanager
        async def mock_mcp_client(
            tool_server, force_oauth=False, oauth_callback_base_url=None
        ):
            yield mock_session

        with patch(
            "app.desktop.studio_server.tool_api.MCPSessionManager.shared"
        ) as mock_session_manager_shared:
            mock_session_manager = AsyncMock()
            mock_session_manager.mcp_client = mock_mcp_client
            mock_session_manager_shared.return_value = mock_session_manager

            response = client.get(
                f"/api/projects/{test_project.id}/tool_servers/{tool_server_id}"
            )

            assert response.status_code == 200
            result = response.json()
            assert len(result["available_tools"]) == 20

            # Verify tool names are correct
            tool_names = [tool["name"] for tool in result["available_tools"]]
            expected_names = [f"tool_{i}" for i in range(20)]
            assert tool_names == expected_names


@pytest.mark.asyncio
async def test_available_mcp_tools_remote_success():
    """Test available_mcp_tools successfully retrieves tools from remote MCP server"""

    # Create a mock ExternalToolServer
    server = ExternalToolServer(
        name="test_server",
        type=ToolServerType.remote_mcp,
        description="Test MCP server",
        properties={
            "server_url": "https://example.com/mcp",
            "headers": {"Authorization": "Bearer token"},
        },
    )

    # Mock tools that the MCP server should return
    mock_tools = [
        Tool(name="echo", description="Echo tool", inputSchema={}),
        Tool(name="calculator", description="Math calculator", inputSchema={}),
        Tool(name="weather", description=None, inputSchema={}),  # Test None description
    ]

    async with mock_mcp_success(tools=mock_tools):
        # Call the function
        result = await available_mcp_tools(server)

        # Verify the result
        assert len(result) == 3

        # Check tool details
        tool_names = [tool.name for tool in result]
        assert "echo" in tool_names
        assert "calculator" in tool_names
        assert "weather" in tool_names

        # Check tool IDs are properly formatted
        for tool in result:
            assert tool.id.startswith(f"mcp::remote::{server.id}::")
            assert tool.name in ["echo", "calculator", "weather"]

        # Check descriptions
        echo_tool = next(t for t in result if t.name == "echo")
        assert echo_tool.description == "Echo tool"

        weather_tool = next(t for t in result if t.name == "weather")
        assert weather_tool.description is None


@pytest.mark.asyncio
async def test_available_mcp_tools_connection_error():
    """Test available_mcp_tools throws exception on connection errors"""

    # Create a mock ExternalToolServer
    server = ExternalToolServer(
        name="failing_server",
        type=ToolServerType.remote_mcp,
        description="Failing MCP server",
        properties={"server_url": "https://failing.example.com/mcp", "headers": {}},
    )

    async with mock_mcp_connection_error():
        # Call the function - should throw exception on error
        with pytest.raises(Exception, match="Connection failed"):
            await available_mcp_tools(server)


@pytest.mark.asyncio
async def test_available_mcp_tools_list_tools_error():
    """Test available_mcp_tools throws exception on list_tools errors"""

    # Create a mock ExternalToolServer
    server = ExternalToolServer(
        name="error_server",
        type=ToolServerType.remote_mcp,
        description="MCP server with list_tools error",
        properties={"server_url": "https://error.example.com/mcp", "headers": {}},
    )

    async with mock_mcp_list_tools_error():
        # Call the function - should throw exception on error
        with pytest.raises(Exception, match="list_tools failed"):
            await available_mcp_tools(server)


@pytest.mark.asyncio
async def test_available_mcp_tools_empty_tools():
    """Test available_mcp_tools handles empty tools list"""

    # Create a mock ExternalToolServer
    server = ExternalToolServer(
        name="empty_server",
        type=ToolServerType.remote_mcp,
        description="MCP server with no tools",
        properties={"server_url": "https://empty.example.com/mcp", "headers": {}},
    )

    async with mock_mcp_success():  # Empty tools by default
        # Call the function
        result = await available_mcp_tools(server)

        # Verify empty list is returned
        assert result == []


@pytest.mark.asyncio
async def test_available_mcp_tools_local_success():
    """Test available_mcp_tools successfully retrieves tools from local MCP server"""

    # Create a mock ExternalToolServer for local MCP
    server = ExternalToolServer(
        name="local_test_server",
        type=ToolServerType.local_mcp,
        description="Test local MCP server",
        properties={
            "command": "python",
            "args": ["-m", "test_mcp_server"],
            "env_vars": {},
        },
    )

    # Mock tools that the MCP server should return
    mock_tools = [
        Tool(name="local_echo", description="Local echo tool", inputSchema={}),
        Tool(name="local_calc", description="Local calculator", inputSchema={}),
    ]

    async with mock_mcp_success(tools=mock_tools):
        # Call the function
        result = await available_mcp_tools(server)

        # Verify the result
        assert len(result) == 2

        # Check tool details
        tool_names = [tool.name for tool in result]
        assert "local_echo" in tool_names
        assert "local_calc" in tool_names

        # Check tool IDs are properly formatted with local prefix
        for tool in result:
            assert tool.id.startswith(f"mcp::local::{server.id}::")
            assert tool.name in ["local_echo", "local_calc"]

        # Check descriptions
        echo_tool = next(t for t in result if t.name == "local_echo")
        assert echo_tool.description == "Local echo tool"


@pytest.mark.asyncio
async def test_available_mcp_tools_kiln_task_raises_value_error():
    """Test available_mcp_tools raises ValueError when called with kiln_task server type"""

    # Create a mock ExternalToolServer with kiln_task type
    server = ExternalToolServer(
        name="test_kiln_task",
        type=ToolServerType.kiln_task,
        description="Test Kiln task server",
        properties={
            "name": "test_task",
            "description": "Test task description",
            "is_archived": False,
            "task_id": "test_task_id",
            "run_config_id": "test_run_config_id",
        },
    )

    # Test that ValueError is raised
    with pytest.raises(
        ValueError, match="Kiln task tools are not available from an MCP server"
    ):
        await available_mcp_tools(server)


# Unit tests for validate_tool_server_connectivity function
@pytest.mark.asyncio
async def test_validate_tool_server_connectivity_success():
    """Test validate_tool_server_connectivity succeeds when MCP server is reachable"""
    # Create a valid ExternalToolServer
    tool_server = ExternalToolServer(
        name="test_server",
        type=ToolServerType.remote_mcp,
        description="Test MCP server",
        properties={
            "server_url": "https://example.com/mcp",
            "headers": {"Authorization": "Bearer token"},
        },
    )

    async with mock_mcp_success():
        # Should not raise any exception
        await validate_tool_server_connectivity(tool_server)


@pytest.mark.asyncio
async def test_validate_tool_server_connectivity_connection_failed():
    """Test validate_tool_server_connectivity raises error when MCP connection fails"""

    tool_server = ExternalToolServer(
        name="failing_server",
        type=ToolServerType.remote_mcp,
        description="Failing MCP server",
        properties={"server_url": "https://failing.example.com/mcp", "headers": {}},
    )

    async with mock_mcp_connection_error():
        # Should raise the raw exception
        with pytest.raises(Exception, match="Connection failed"):
            await validate_tool_server_connectivity(tool_server)


@pytest.mark.asyncio
async def test_validate_tool_server_connectivity_list_tools_failed():
    """Test validate_tool_server_connectivity raises error when list_tools fails"""

    tool_server = ExternalToolServer(
        name="list_tools_failing",
        type=ToolServerType.remote_mcp,
        description="MCP server with list_tools error",
        properties={"server_url": "https://example.com/mcp", "headers": {}},
    )

    async with mock_mcp_list_tools_error():
        # Should raise the raw exception
        with pytest.raises(Exception, match="list_tools failed"):
            await validate_tool_server_connectivity(tool_server)


@pytest.mark.asyncio
async def test_validate_tool_server_connectivity_pydantic_prevents_empty_name():
    """Test that Pydantic prevents creation of tool servers with empty names"""
    # This test demonstrates that Pydantic validation prevents empty names
    # which means our validation function doesn't need to handle this case
    with pytest.raises(Exception):  # Pydantic validation error
        ExternalToolServer(
            name="",  # Empty name
            type=ToolServerType.remote_mcp,
            description="Tool with empty name",
            properties={"server_url": "https://example.com/mcp", "headers": {}},
        )


@pytest.mark.asyncio
async def test_validate_tool_server_connectivity_mcp_with_minimal_properties():
    """Test validate_tool_server_connectivity works with minimal required properties"""
    tool_server = ExternalToolServer(
        name="minimal_server",
        type=ToolServerType.remote_mcp,
        description=None,  # Optional field
        properties={
            "server_url": "https://minimal.example.com/mcp",
            "headers": {},  # Empty headers are allowed
        },
    )

    async with mock_mcp_success():
        # Should succeed with minimal properties
        await validate_tool_server_connectivity(tool_server)


@pytest.mark.asyncio
async def test_validate_tool_server_connectivity_kiln_task():
    """Test validate_tool_server_connectivity does nothing for kiln_task type"""
    tool_server = ExternalToolServer(
        name="kiln_task_server",
        type=ToolServerType.kiln_task,
        description="Kiln task tool server",
        properties={
            "name": "kiln_task_server",
            "description": "Kiln task tool server",
            "task_id": "test_task_id",
            "run_config_id": "test_run_config_id",
            "is_archived": False,
        },
    )

    # Should complete without any exceptions or network calls
    await validate_tool_server_connectivity(tool_server)


@pytest.mark.asyncio
async def test_validate_tool_server_connectivity_with_headers():
    """Test validate_tool_server_connectivity works correctly with custom headers"""
    tool_server = ExternalToolServer(
        name="server_with_headers",
        type=ToolServerType.remote_mcp,
        description="MCP server with custom headers",
        properties={
            "server_url": "https://example.com/mcp",
            "headers": {
                "Authorization": "Bearer custom-token",
                "X-API-Key": "secret-key",
                "Content-Type": "application/json",
            },
        },
    )

    tools = [Tool(name="test_tool", description="Test tool", inputSchema={})]
    async with mock_mcp_success(tools=tools):
        # Should succeed
        await validate_tool_server_connectivity(tool_server)


@pytest.mark.asyncio
async def test_validate_tool_server_connectivity_empty_headers():
    """Test validate_tool_server_connectivity works correctly with empty headers"""
    tool_server = ExternalToolServer(
        name="server_no_headers",
        type=ToolServerType.remote_mcp,
        description="MCP server with no headers",
        properties={
            "server_url": "https://example.com/mcp",
            "headers": {},  # Empty headers
        },
    )

    async with mock_mcp_success():
        # Should succeed even with empty headers
        await validate_tool_server_connectivity(tool_server)


@pytest.mark.asyncio
async def test_validate_tool_server_connectivity_valid_complex_headers():
    """Test validate_tool_server_connectivity accepts valid complex headers"""
    tool_server = ExternalToolServer(
        name="complex_headers_server",
        type=ToolServerType.remote_mcp,
        description="Server with valid complex headers",
        properties={
            "server_url": "https://example.com/mcp",
            "headers": {
                "Authorization": "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9",
                "X-API-Key": "key_with-dashes_and.dots",
                "Content-Type": "application/json",
                "User-Agent": "Kiln-AI/1.0",
                "X-Custom-123": "value_with_123",
            },
        },
    )

    async with mock_mcp_success():
        # Should succeed with valid complex headers
        await validate_tool_server_connectivity(tool_server)


# Tests for connect_local_mcp endpoint
async def test_create_local_tool_server_success(client, test_project):
    """Test successful local tool server creation"""
    tool_data = {
        "name": "test_local_mcp_tool",
        "command": "python",
        "args": ["-m", "test_mcp_server"],
        "env_vars": {"DEBUG": "true"},
        "description": "A test local MCP tool",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_success():
            response = client.post(
                f"/api/projects/{test_project.id}/connect_local_mcp",
                json=tool_data,
            )

            assert response.status_code == 200
            result = response.json()
            assert result["name"] == "test_local_mcp_tool"
            assert result["type"] == "local_mcp"
            assert result["description"] == "A test local MCP tool"
            assert result["properties"]["command"] == "python"
            assert result["properties"]["args"] == ["-m", "test_mcp_server"]
            assert result["properties"]["env_vars"]["DEBUG"] == "true"
            assert "id" in result
            assert "created_at" in result


async def test_create_local_tool_server_validation_success(client, test_project):
    """Test successful local tool server creation with MCP validation"""
    tool_data = {
        "name": "validated_local_tool",
        "command": "/usr/bin/python3",
        "args": ["-m", "validated_server", "--config", "config.json"],
        "env_vars": {"PATH": "/usr/bin"},
        "description": "A validated local MCP tool",
    }

    tools = [
        Tool(name="local_test_tool", description="Local test tool", inputSchema={})
    ]

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_success(tools=tools):
            response = client.post(
                f"/api/projects/{test_project.id}/connect_local_mcp",
                json=tool_data,
            )

            assert response.status_code == 200
            result = response.json()
            assert result["name"] == "validated_local_tool"
            assert result["type"] == "local_mcp"


async def test_create_local_tool_server_validation_failed(client, test_project):
    """Test local tool server creation fails when MCP server validation fails"""
    tool_data = {
        "name": "failing_local_tool",
        "command": "python",
        "args": ["-m", "nonexistent_server"],
        "env_vars": {},
        "description": "Local tool that will fail validation",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_connection_error():
            # Unhandled exception is now raised instead of returning 422
            with pytest.raises(Exception, match="Connection failed"):
                client.post(
                    f"/api/projects/{test_project.id}/connect_local_mcp",
                    json=tool_data,
                )


def test_create_local_tool_server_missing_command(client, test_project):
    """Test local tool server creation fails when command is missing"""
    tool_data = {
        "name": "missing_command_tool",
        "args": ["-m", "server"],
        "description": "Tool with missing command",
        # Missing required command
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        response = client.post(
            f"/api/projects/{test_project.id}/connect_local_mcp",
            json=tool_data,
        )

        assert response.status_code == 422  # Validation error


def test_create_local_tool_server_missing_args(client, test_project):
    """Test local tool server creation fails when args are missing"""
    tool_data = {
        "name": "missing_args_tool",
        "command": "python",
        "description": "Tool with missing args",
        # Missing required args
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        response = client.post(
            f"/api/projects/{test_project.id}/connect_local_mcp",
            json=tool_data,
        )

        assert response.status_code == 422  # Validation error


async def test_create_local_tool_server_empty_args(client, test_project):
    """Test local tool server creation succeeds when args are empty"""
    tool_data = {
        "name": "empty_args_tool",
        "command": "python",
        "args": [],  # Empty args should now be allowed
        "description": "Tool with empty args",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_success():
            response = client.post(
                f"/api/projects/{test_project.id}/connect_local_mcp",
                json=tool_data,
            )

            assert response.status_code == 200  # Should succeed now
            result = response.json()
            assert result["name"] == "empty_args_tool"
            assert result["properties"]["args"] == []


async def test_create_local_tool_server_no_description(client, test_project):
    """Test local tool server creation works without description (optional field)"""
    tool_data = {
        "name": "no_desc_local_tool",
        "command": "python",
        "args": ["-m", "server"],
        # description is optional
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_success():
            response = client.post(
                f"/api/projects/{test_project.id}/connect_local_mcp",
                json=tool_data,
            )

            assert response.status_code == 200
            result = response.json()
            assert result["description"] is None


async def test_create_local_tool_server_no_env_vars(client, test_project):
    """Test local tool server creation works without env_vars (defaults to empty dict)"""
    tool_data = {
        "name": "no_env_local_tool",
        "command": "python",
        "args": ["-m", "server"],
        # env_vars defaults to empty dict
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_success():
            response = client.post(
                f"/api/projects/{test_project.id}/connect_local_mcp",
                json=tool_data,
            )

            assert response.status_code == 200
            result = response.json()
            assert result["properties"]["env_vars"] == {}


async def test_create_local_tool_server_complex_command(client, test_project):
    """Test local tool server creation with complex command and arguments"""
    tool_data = {
        "name": "complex_local_tool",
        "command": "/opt/miniconda3/envs/mcp/bin/python",
        "args": [
            "-m",
            "custom_mcp_server",
            "--config",
            "/etc/mcp/config.yaml",
            "--verbose",
            "--log-level",
            "debug",
            "--port",
            "8080",
        ],
        "env_vars": {
            "PYTHONPATH": "/opt/custom/lib",
            "CONFIG_PATH": "/etc/mcp",
            "LOG_LEVEL": "debug",
            "MCP_SERVER_MODE": "production",
        },
        "description": "Complex local MCP tool with detailed configuration",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_success():
            response = client.post(
                f"/api/projects/{test_project.id}/connect_local_mcp",
                json=tool_data,
            )

            assert response.status_code == 200
            result = response.json()
            assert result["name"] == "complex_local_tool"
            assert (
                result["properties"]["command"] == "/opt/miniconda3/envs/mcp/bin/python"
            )
            assert len(result["properties"]["args"]) == 9
            assert result["properties"]["args"][0] == "-m"
            assert result["properties"]["args"][1] == "custom_mcp_server"
            assert result["properties"]["env_vars"]["PYTHONPATH"] == "/opt/custom/lib"
            assert result["properties"]["env_vars"]["MCP_SERVER_MODE"] == "production"


async def test_create_local_tool_server_missing_name(client, test_project):
    """Test local tool server creation fails when name is missing"""
    tool_data = {
        "command": "python",
        "args": ["-m", "server"],
        "description": "Tool with missing name",
        # Missing required name
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        response = client.post(
            f"/api/projects/{test_project.id}/connect_local_mcp",
            json=tool_data,
        )

        assert response.status_code == 422  # Validation error


async def test_create_local_tool_server_clean_inputs(client, test_project):
    """Test local tool server creation with clean inputs (no leading/trailing whitespace)"""
    tool_data = {
        "name": "clean_tool",  # Name without whitespace
        "command": "python",
        "args": ["-m", "server"],
        "description": "Tool with clean description",
        "env_vars": {"VALID_KEY": "clean_value"},
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_success():
            response = client.post(
                f"/api/projects/{test_project.id}/connect_local_mcp",
                json=tool_data,
            )

            assert response.status_code == 200
            result = response.json()
            # Values should be preserved as-is
            assert result["name"] == "clean_tool"
            assert result["description"] == "Tool with clean description"


async def test_create_local_tool_server_unicode_characters(client, test_project):
    """Test local tool server creation works with unicode characters"""
    tool_data = {
        "name": "测试工具_🚀",  # Unicode name with emoji
        "command": "python",
        "args": ["-m", "server"],
        "description": "Тест c юникодом и émojis 🎉",
        "env_vars": {"UNICODE_VAR": "测试值"},
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_success():
            response = client.post(
                f"/api/projects/{test_project.id}/connect_local_mcp",
                json=tool_data,
            )

            assert response.status_code == 200
            result = response.json()
            assert result["name"] == "测试工具_🚀"
            assert result["description"] == "Тест c юникодом и émojis 🎉"
            assert result["properties"]["env_vars"]["UNICODE_VAR"] == "测试值"


async def test_create_local_tool_server_long_description(client, test_project):
    """Test local tool server creation works with very long descriptions"""
    long_description = "A" * 1000  # 1000 character description
    tool_data = {
        "name": "long_desc_tool",
        "command": "python",
        "args": ["-m", "server"],
        "description": long_description,
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_success():
            response = client.post(
                f"/api/projects/{test_project.id}/connect_local_mcp",
                json=tool_data,
            )

            assert response.status_code == 200
            result = response.json()
            assert result["description"] == long_description


async def test_create_local_tool_server_concurrent_creation(client, test_project):
    """Test concurrent local tool server creation works correctly"""
    tool_servers = [
        {
            "name": f"concurrent_tool_{i}",
            "command": "python",
            "args": ["-m", f"server_{i}"],
            "description": f"Concurrent tool {i}",
            "env_vars": {f"VAR_{i}": f"value_{i}"},
        }
        for i in range(5)
    ]

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_success():
            created_tools = []
            for tool_data in tool_servers:
                response = client.post(
                    f"/api/projects/{test_project.id}/connect_local_mcp",
                    json=tool_data,
                )
                assert response.status_code == 200
                created_tools.append(response.json())

            # Verify all tools were created with unique IDs
            tool_ids = [tool["id"] for tool in created_tools]
            assert len(set(tool_ids)) == 5  # All IDs should be unique


async def test_create_local_tool_server_duplicate_names_allowed(client, test_project):
    """Test local tool server creation allows duplicate names (like remote MCP)"""
    tool_data = {
        "name": "duplicate_name_tool",
        "command": "python",
        "args": ["-m", "server1"],
        "description": "First tool with this name",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_success():
            # Create first tool
            response1 = client.post(
                f"/api/projects/{test_project.id}/connect_local_mcp",
                json=tool_data,
            )
            assert response1.status_code == 200
            tool1_id = response1.json()["id"]

            # Create second tool with same name but different properties
            tool_data["args"] = ["-m", "server2"]
            tool_data["description"] = "Second tool with this name"

            response2 = client.post(
                f"/api/projects/{test_project.id}/connect_local_mcp",
                json=tool_data,
            )
            assert response2.status_code == 200
            tool2_id = response2.json()["id"]

            # Both should exist with different IDs
            assert tool1_id != tool2_id


async def test_create_local_tool_server_max_length_name(client, test_project):
    """Test local tool server creation works with maximum length names"""
    max_length_name = "a" * 120  # 120 character name (assuming same max as remote)
    tool_data = {
        "name": max_length_name,
        "command": "python",
        "args": ["-m", "server"],
        "description": "Tool with maximum length name",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_success():
            response = client.post(
                f"/api/projects/{test_project.id}/connect_local_mcp",
                json=tool_data,
            )

            assert response.status_code == 200
            result = response.json()
            assert result["name"] == max_length_name


async def test_create_local_tool_server_list_tools_failed(client, test_project):
    """Test local tool server creation fails when MCP list_tools fails"""
    tool_data = {
        "name": "list_tools_failing_local",
        "command": "python",
        "args": ["-m", "failing_server"],
        "description": "Local tool where list_tools fails",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        async with mock_mcp_list_tools_error("list_tools failed"):
            # Unhandled exception is now raised instead of returning 422
            with pytest.raises(Exception, match="list_tools failed"):
                client.post(
                    f"/api/projects/{test_project.id}/connect_local_mcp",
                    json=tool_data,
                )


# Test validation of local MCP with validate_tool_server_connectivity
@pytest.mark.asyncio
async def test_validate_tool_server_connectivity_local_mcp_success():
    """Test validate_tool_server_connectivity succeeds for local MCP server"""
    tool_server = ExternalToolServer(
        name="test_local_server",
        type=ToolServerType.local_mcp,
        description="Test local MCP server",
        properties={
            "command": "python",
            "args": ["-m", "test_mcp_server"],
            "env_vars": {"DEBUG": "true"},
        },
    )

    async with mock_mcp_success():
        # Should not raise any exception
        await validate_tool_server_connectivity(tool_server)


@pytest.mark.asyncio
async def test_validate_tool_server_connectivity_local_mcp_failed():
    """Test validate_tool_server_connectivity raises error when local MCP fails"""
    tool_server = ExternalToolServer(
        name="failing_local_server",
        type=ToolServerType.local_mcp,
        description="Failing local MCP server",
        properties={
            "command": "python",
            "args": ["-m", "nonexistent_server"],
            "env_vars": {},
        },
    )

    async with mock_mcp_list_tools_error("Local MCP server failed"):
        # Should raise the raw exception
        with pytest.raises(Exception, match="Local MCP server failed"):
            await validate_tool_server_connectivity(tool_server)


# Tests for tool_server_from_id function
def test_tool_server_from_id_success(test_project):
    """Test tool_server_from_id returns correct tool server when found"""

    # Create a tool server
    tool_server = ExternalToolServer(
        name="test_tool_server",
        type=ToolServerType.remote_mcp,
        description="Test tool server",
        properties={
            "server_url": "https://example.com/mcp",
            "headers": {"Authorization": "Bearer token"},
        },
        parent=test_project,
    )
    tool_server.save_to_file()

    # Test that we can find it with mocked project_from_id
    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project
        found_server = tool_server_from_id(test_project.id, str(tool_server.id))
        assert found_server.id == tool_server.id
        assert found_server.name == "test_tool_server"
        assert found_server.type == ToolServerType.remote_mcp


def test_tool_server_from_id_not_found(test_project):
    """Test tool_server_from_id raises HTTPException when tool server not found"""

    # Try to find a non-existent tool server with mocked project_from_id
    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project
        with pytest.raises(HTTPException) as exc_info:
            tool_server_from_id(test_project.id, "non-existent-id")

        assert exc_info.value.status_code == 404
        assert "Tool server not found" in str(exc_info.value.detail)


def test_tool_server_from_id_project_not_found():
    """Test tool_server_from_id raises HTTPException when project not found"""

    # Try to find a tool server in a non-existent project
    with pytest.raises(HTTPException) as exc_info:
        tool_server_from_id("non-existent-project", "some-tool-id")

    assert exc_info.value.status_code == 404
    assert "Project not found" in str(exc_info.value.detail)


def test_tool_server_from_id_multiple_servers(test_project):
    """Test tool_server_from_id finds correct server when multiple exist"""

    # Create multiple tool servers
    server1 = ExternalToolServer(
        name="server1",
        type=ToolServerType.remote_mcp,
        description="First server",
        properties={"server_url": "https://server1.com", "headers": {}},
        parent=test_project,
    )
    server1.save_to_file()

    server2 = ExternalToolServer(
        name="server2",
        type=ToolServerType.local_mcp,
        description="Second server",
        properties={"command": "python", "args": ["-m", "server"], "env_vars": {}},
        parent=test_project,
    )
    server2.save_to_file()

    # Test that we can find the correct one with mocked project_from_id
    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project
        found_server1 = tool_server_from_id(test_project.id, str(server1.id))
        found_server2 = tool_server_from_id(test_project.id, str(server2.id))

        assert found_server1.id == server1.id
        assert found_server1.name == "server1"
        assert found_server1.type == ToolServerType.remote_mcp

        assert found_server2.id == server2.id
        assert found_server2.name == "server2"
        assert found_server2.type == ToolServerType.local_mcp


# Tests for DELETE /api/projects/{project_id}/tool_servers/{tool_server_id} endpoint
async def test_delete_tool_server_success(client, test_project):
    """Test successful deletion of a tool server"""
    # First create a tool server
    tool_data = {
        "name": "test_delete_tool",
        "server_url": "https://example.com/api",
        "headers": {"Authorization": "Bearer token"},
        "description": "Tool to be deleted",
    }

    async with mock_mcp_success():
        with patch(
            "app.desktop.studio_server.tool_api.project_from_id"
        ) as mock_project_from_id:
            mock_project_from_id.return_value = test_project

            # Create the tool server
            create_response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )
            assert create_response.status_code == 200
            created_tool = create_response.json()
            tool_server_id = created_tool["id"]

            # Verify it exists by getting it
            get_response = client.get(
                f"/api/projects/{test_project.id}/tool_servers/{tool_server_id}"
            )
            assert get_response.status_code == 200

            # Now delete it
            delete_response = client.delete(
                f"/api/projects/{test_project.id}/tool_servers/{tool_server_id}"
            )
            assert delete_response.status_code == 200

            # Verify it's been deleted by trying to get it again
            get_after_delete_response = client.get(
                f"/api/projects/{test_project.id}/tool_servers/{tool_server_id}"
            )
            assert get_after_delete_response.status_code == 404


def test_delete_tool_server_not_found(client, test_project):
    """Test deletion of non-existent tool server returns 404"""
    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        # Try to delete a non-existent tool server
        response = client.delete(
            f"/api/projects/{test_project.id}/tool_servers/non-existent-id"
        )
        assert response.status_code == 404
        assert "Tool server not found" in response.json()["detail"]


def test_delete_tool_server_project_not_found(client):
    """Test deletion with non-existent project returns 404"""
    # Try to delete from a non-existent project
    response = client.delete(
        "/api/projects/non-existent-project/tool_servers/some-tool-id"
    )
    assert response.status_code == 404
    assert "Project not found" in response.json()["detail"]


async def test_delete_tool_server_local_mcp(client, test_project):
    """Test successful deletion of a local MCP tool server"""
    # First create a local MCP tool server
    tool_data = {
        "name": "test_delete_local",
        "command": "python",
        "args": ["-m", "test_server"],
        "env_vars": {"DEBUG": "true"},
        "description": "Local tool to be deleted",
    }

    async with mock_mcp_success():
        with patch(
            "app.desktop.studio_server.tool_api.project_from_id"
        ) as mock_project_from_id:
            mock_project_from_id.return_value = test_project

            # Create the local tool server
            create_response = client.post(
                f"/api/projects/{test_project.id}/connect_local_mcp",
                json=tool_data,
            )
            assert create_response.status_code == 200
            created_tool = create_response.json()
            tool_server_id = created_tool["id"]

            # Verify it exists
            get_response = client.get(
                f"/api/projects/{test_project.id}/tool_servers/{tool_server_id}"
            )
            assert get_response.status_code == 200
            assert get_response.json()["type"] == "local_mcp"

            # Now delete it
            delete_response = client.delete(
                f"/api/projects/{test_project.id}/tool_servers/{tool_server_id}"
            )
            assert delete_response.status_code == 200

            # Verify it's been deleted
            get_after_delete_response = client.get(
                f"/api/projects/{test_project.id}/tool_servers/{tool_server_id}"
            )
            assert get_after_delete_response.status_code == 404


async def test_delete_tool_server_affects_available_servers_list(client, test_project):
    """Test that deleting a tool server removes it from the available servers list"""
    # Create two tool servers
    tool_data_1 = {
        "name": "tool_server_1",
        "server_url": "https://server1.com/api",
        "headers": {},
        "description": "First server",
    }

    tool_data_2 = {
        "name": "tool_server_2",
        "server_url": "https://server2.com/api",
        "headers": {},
        "description": "Second server",
    }

    async with mock_mcp_success():
        with patch(
            "app.desktop.studio_server.tool_api.project_from_id"
        ) as mock_project_from_id:
            mock_project_from_id.return_value = test_project

            # Create both servers
            create_response_1 = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data_1,
            )
            assert create_response_1.status_code == 200
            server_1_id = create_response_1.json()["id"]

            create_response_2 = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data_2,
            )
            assert create_response_2.status_code == 200
            server_2_id = create_response_2.json()["id"]

            # Verify both appear in available servers list
            list_response = client.get(
                f"/api/projects/{test_project.id}/available_tool_servers"
            )
            assert list_response.status_code == 200
            servers = list_response.json()
            assert len(servers) == 2
            server_ids = [server["id"] for server in servers]
            assert server_1_id in server_ids
            assert server_2_id in server_ids

            # Delete one server
            delete_response = client.delete(
                f"/api/projects/{test_project.id}/tool_servers/{server_1_id}"
            )
            assert delete_response.status_code == 200

            # Verify only one remains in the list
            list_after_delete_response = client.get(
                f"/api/projects/{test_project.id}/available_tool_servers"
            )
            assert list_after_delete_response.status_code == 200
            remaining_servers = list_after_delete_response.json()
            assert len(remaining_servers) == 1
            assert remaining_servers[0]["id"] == server_2_id
            assert remaining_servers[0]["name"] == "tool_server_2"


async def test_delete_tool_server_with_secret_headers(client, test_project):
    """Test that deleting a tool server removes secret headers from Config"""
    # Create a tool server with secret headers
    tool_data = {
        "name": "tool_with_secrets",
        "server_url": "https://example.com/api",
        "headers": {
            "Authorization": "Bearer secret-token-123",
            "X-API-Key": "api-key-456",
            "Content-Type": "application/json",
        },
        "secret_header_keys": ["Authorization", "X-API-Key"],
        "description": "Tool with secret headers",
    }

    async with mock_mcp_success():
        with patch(
            "app.desktop.studio_server.tool_api.project_from_id"
        ) as mock_project_from_id:
            mock_project_from_id.return_value = test_project

            # Create the tool server first (without mocking Config to avoid interference)
            create_response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )
            assert create_response.status_code == 200
            created_tool = create_response.json()
            tool_server_id = created_tool["id"]

            # Verify the tool server was created with secret headers
            assert "secret_header_keys" in created_tool["properties"]
            assert created_tool["properties"]["secret_header_keys"] == [
                "Authorization",
                "X-API-Key",
            ]

            # Now mock Config for the delete operation
            with patch(
                "app.desktop.studio_server.tool_api.Config.shared"
            ) as mock_config_shared:
                mock_config = mock_config_shared.return_value
                mock_config.get_value.return_value = {
                    f"{tool_server_id}::Authorization": "Bearer secret-token-123",
                    f"{tool_server_id}::X-API-Key": "api-key-456",
                    "other_server::some_header": "other_value",  # Should not be deleted
                }
                mock_config.update_settings = Mock()

                # Delete the tool server
                delete_response = client.delete(
                    f"/api/projects/{test_project.id}/tool_servers/{tool_server_id}"
                )
                assert delete_response.status_code == 200

                # Verify that secret headers were removed from config
                mock_config.update_settings.assert_called_once()
                call_args = mock_config.update_settings.call_args[0][0]

                # Check that the updated mcp_secrets no longer contains the deleted server's secrets
                expected_remaining_secrets = {
                    "other_server::some_header": "other_value"
                }
                assert call_args[MCP_SECRETS_KEY] == expected_remaining_secrets


async def test_delete_tool_server_no_secret_headers(client, test_project):
    """Test that deleting a tool server without secret headers works correctly"""
    # Create a tool server without secret headers
    tool_data = {
        "name": "tool_without_secrets",
        "server_url": "https://example.com/api",
        "headers": {"Content-Type": "application/json"},
        "secret_header_keys": [],
        "description": "Tool without secret headers",
    }

    async with mock_mcp_success():
        with patch(
            "app.desktop.studio_server.tool_api.project_from_id"
        ) as mock_project_from_id:
            mock_project_from_id.return_value = test_project

            # Create the tool server first (without mocking Config to avoid interference)
            create_response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )
            assert create_response.status_code == 200
            created_tool = create_response.json()
            tool_server_id = created_tool["id"]

            # Verify the tool server was created without secret headers
            assert created_tool["properties"]["secret_header_keys"] == []

            # Now mock Config for the delete operation
            with patch(
                "app.desktop.studio_server.tool_api.Config.shared"
            ) as mock_config_shared:
                mock_config = mock_config_shared.return_value
                mock_config.get_value.return_value = {
                    "other_server::some_header": "other_value"
                }
                mock_config.update_settings = Mock()

                # Delete the tool server
                delete_response = client.delete(
                    f"/api/projects/{test_project.id}/tool_servers/{tool_server_id}"
                )
                assert delete_response.status_code == 200

                # Verify that config update was still called (even with empty secret_header_keys)
                mock_config.update_settings.assert_called_once()
                call_args = mock_config.update_settings.call_args[0][0]

                # Check that existing secrets remain unchanged
                expected_remaining_secrets = {
                    "other_server::some_header": "other_value"
                }
                assert call_args[MCP_SECRETS_KEY] == expected_remaining_secrets


async def test_delete_tool_server_missing_secret_header_keys_property(
    client, test_project
):
    """Test that deleting a tool server handles missing secret_header_keys property gracefully"""
    # Create a tool server first
    tool_data = {
        "name": "tool_without_secret_keys_prop",
        "server_url": "https://example.com/api",
        "headers": {"Content-Type": "application/json"},
        "secret_header_keys": [],
        "description": "Tool for testing missing property",
    }

    async with mock_mcp_success():
        with patch(
            "app.desktop.studio_server.tool_api.project_from_id"
        ) as mock_project_from_id:
            mock_project_from_id.return_value = test_project

            # Create the tool server first (without mocking Config to avoid interference)
            create_response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )
            assert create_response.status_code == 200
            created_tool = create_response.json()
            tool_server_id = created_tool["id"]

            # Manually remove the secret_header_keys property to simulate old data
            # This requires directly modifying the tool server's properties
            tool_server = tool_server_from_id(test_project.id, tool_server_id)
            del tool_server.properties["secret_header_keys"]
            tool_server.save_to_file()

            # Now mock Config for the delete operation
            with patch(
                "app.desktop.studio_server.tool_api.Config.shared"
            ) as mock_config_shared:
                mock_config = mock_config_shared.return_value
                mock_config.get_value.return_value = {
                    "other_server::some_header": "other_value"
                }
                mock_config.update_settings = Mock()

                # Delete the tool server - this should handle the missing property gracefully
                delete_response = client.delete(
                    f"/api/projects/{test_project.id}/tool_servers/{tool_server_id}"
                )
                assert delete_response.status_code == 200

                # Verify that config update was still called
                mock_config.update_settings.assert_called_once()
                call_args = mock_config.update_settings.call_args[0][0]

                # Check that existing secrets remain unchanged since no secret keys were found
                expected_remaining_secrets = {
                    "other_server::some_header": "other_value"
                }
                assert call_args[MCP_SECRETS_KEY] == expected_remaining_secrets


async def test_delete_tool_server_secret_key_not_in_config(client, test_project):
    """Test that deleting a tool server handles cases where secret keys are not in config"""
    # Create a tool server with secret headers
    tool_data = {
        "name": "tool_with_missing_secrets",
        "server_url": "https://example.com/api",
        "headers": {
            "Authorization": "Bearer secret-token-123",
            "X-API-Key": "api-key-456",
            "Content-Type": "application/json",
        },
        "secret_header_keys": ["Authorization", "X-API-Key"],
        "description": "Tool with secret headers not in config",
    }

    async with mock_mcp_success():
        with patch(
            "app.desktop.studio_server.tool_api.project_from_id"
        ) as mock_project_from_id:
            mock_project_from_id.return_value = test_project

            # Create the tool server first (without mocking Config to avoid interference)
            create_response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )
            assert create_response.status_code == 200
            created_tool = create_response.json()
            tool_server_id = created_tool["id"]

            # Now mock Config for delete - but don't include this server's secrets
            with patch(
                "app.desktop.studio_server.tool_api.Config.shared"
            ) as mock_config_shared:
                mock_config = mock_config_shared.return_value
                # Config doesn't have the secret keys for this tool server
                mock_config.get_value.return_value = {
                    "other_server::some_header": "other_value"
                }
                mock_config.update_settings = Mock()

                # Delete the tool server - this should handle missing secrets gracefully
                delete_response = client.delete(
                    f"/api/projects/{test_project.id}/tool_servers/{tool_server_id}"
                )
                assert delete_response.status_code == 200

                # Verify that config update was still called
                mock_config.update_settings.assert_called_once()
                call_args = mock_config.update_settings.call_args[0][0]

                # Check that existing secrets remain unchanged since the secret keys weren't in config
                expected_remaining_secrets = {
                    "other_server::some_header": "other_value"
                }
                assert call_args[MCP_SECRETS_KEY] == expected_remaining_secrets


async def test_delete_tool_server_local_mcp_no_secret_headers(client, test_project):
    """Test that deleting a local MCP tool server (which doesn't have secret headers) works correctly"""
    # Create a local MCP tool server
    tool_data = {
        "name": "local_tool_no_secrets",
        "command": "python",
        "args": ["-m", "test_server"],
        "env_vars": {"DEBUG": "true"},
        "description": "Local tool without secret headers",
    }

    async with mock_mcp_success():
        with patch(
            "app.desktop.studio_server.tool_api.project_from_id"
        ) as mock_project_from_id:
            mock_project_from_id.return_value = test_project

            # Create the local tool server first (without mocking Config to avoid interference)
            create_response = client.post(
                f"/api/projects/{test_project.id}/connect_local_mcp",
                json=tool_data,
            )
            assert create_response.status_code == 200
            created_tool = create_response.json()
            tool_server_id = created_tool["id"]

            # Verify it's a local MCP server (no secret_header_keys property expected)
            assert created_tool["type"] == "local_mcp"

            # Now mock Config for the delete operation
            with patch(
                "app.desktop.studio_server.tool_api.Config.shared"
            ) as mock_config_shared:
                mock_config = mock_config_shared.return_value
                mock_config.get_value.return_value = {
                    "other_server::some_header": "other_value"
                }
                mock_config.update_settings = Mock()

                # Delete the tool server
                delete_response = client.delete(
                    f"/api/projects/{test_project.id}/tool_servers/{tool_server_id}"
                )
                assert delete_response.status_code == 200

                # Verify that config update was still called
                mock_config.update_settings.assert_called_once()
                call_args = mock_config.update_settings.call_args[0][0]

                # Check that existing secrets remain unchanged
                expected_remaining_secrets = {
                    "other_server::some_header": "other_value"
                }
                assert call_args[MCP_SECRETS_KEY] == expected_remaining_secrets


# Tests for demo tools API endpoints
def test_get_demo_tools_enabled(client):
    """Test GET /api/demo_tools returns True when demo tools are enabled"""
    with patch("app.desktop.studio_server.tool_api.Config.shared") as mock_config:
        mock_config_instance = mock_config.return_value
        mock_config_instance.enable_demo_tools = True

        response = client.get("/api/demo_tools")

        assert response.status_code == 200
        assert response.json() is True


def test_get_demo_tools_disabled(client):
    """Test GET /api/demo_tools returns False when demo tools are disabled"""
    with patch("app.desktop.studio_server.tool_api.Config.shared") as mock_config:
        mock_config_instance = mock_config.return_value
        mock_config_instance.enable_demo_tools = False

        response = client.get("/api/demo_tools")

        assert response.status_code == 200
        assert response.json() is False


def test_set_demo_tools_enable(client):
    """Test POST /api/demo_tools enables demo tools"""
    with patch("app.desktop.studio_server.tool_api.Config.shared") as mock_config:
        mock_config_instance = mock_config.return_value
        mock_config_instance.enable_demo_tools = False  # Initially disabled

        response = client.post("/api/demo_tools?enable_demo_tools=true")

        assert response.status_code == 200
        assert response.json() is True
        # Verify the config was updated
        assert mock_config_instance.enable_demo_tools is True


def test_set_demo_tools_disable(client):
    """Test POST /api/demo_tools disables demo tools"""
    with patch("app.desktop.studio_server.tool_api.Config.shared") as mock_config:
        mock_config_instance = mock_config.return_value
        mock_config_instance.enable_demo_tools = True  # Initially enabled

        response = client.post("/api/demo_tools?enable_demo_tools=false")

        assert response.status_code == 200
        assert response.json() is False
        # Verify the config was updated
        assert mock_config_instance.enable_demo_tools is False


# Tests for secret headers functionality
async def test_connect_remote_mcp_with_secret_headers(client, test_project):
    """Test connect_remote_mcp endpoint stores secret headers correctly"""
    tool_data = {
        "name": "secret_tool",
        "server_url": "https://example.com/api",
        "headers": {
            "Authorization": "Bearer secret-token-123",
            "X-API-Key": "api-key-456",
            "Content-Type": "application/json",
        },
        "secret_header_keys": ["Authorization", "X-API-Key"],
        "description": "Tool with secret headers",
    }

    with (
        patch(
            "app.desktop.studio_server.tool_api.project_from_id"
        ) as mock_project_from_id,
        patch("app.desktop.studio_server.tool_api.Config.shared") as mock_config,
    ):
        mock_project_from_id.return_value = test_project

        # Mock config for storing secrets
        mock_config_instance = mock_config.return_value
        mock_config_instance.get_value.return_value = {}  # Empty mcp_secrets initially
        mock_config_instance.user_id = "test_user"

        async with mock_mcp_success():
            response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )

        assert response.status_code == 200
        result = response.json()

        # Verify the tool server was created correctly
        assert result["name"] == "secret_tool"
        assert result["properties"]["server_url"] == "https://example.com/api"

        # Verify secret headers were removed from properties and only non-secret headers remain
        stored_headers = result["properties"]["headers"]
        assert "Content-Type" in stored_headers
        assert stored_headers["Content-Type"] == "application/json"
        assert "Authorization" not in stored_headers
        assert "X-API-Key" not in stored_headers

        # Verify secret header keys were stored
        assert result["properties"]["secret_header_keys"] == [
            "Authorization",
            "X-API-Key",
        ]

        # Verify config.update_settings was called to store secrets
        mock_config_instance.update_settings.assert_called_once()
        call_args = mock_config_instance.update_settings.call_args[0][0]
        assert MCP_SECRETS_KEY in call_args

        # Verify secret values were stored with correct keys
        mcp_secrets = call_args[MCP_SECRETS_KEY]
        server_id = result["id"]
        assert f"{server_id}::Authorization" in mcp_secrets
        assert f"{server_id}::X-API-Key" in mcp_secrets
        assert mcp_secrets[f"{server_id}::Authorization"] == "Bearer secret-token-123"
        assert mcp_secrets[f"{server_id}::X-API-Key"] == "api-key-456"


async def test_connect_remote_mcp_no_secret_headers(client, test_project):
    """Test connect_remote_mcp endpoint without secret headers"""
    tool_data = {
        "name": "no_secret_tool",
        "server_url": "https://example.com/api",
        "headers": {
            "Content-Type": "application/json",
            "User-Agent": "Kiln-AI/1.0",
        },
        "secret_header_keys": [],  # Empty list
        "description": "Tool without secret headers",
    }

    with (
        patch(
            "app.desktop.studio_server.tool_api.project_from_id"
        ) as mock_project_from_id,
        patch("app.desktop.studio_server.tool_api.Config.shared") as mock_config,
    ):
        mock_project_from_id.return_value = test_project
        mock_config_instance = mock_config.return_value
        mock_config_instance.user_id = "test_user"

        async with mock_mcp_success():
            response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )

        assert response.status_code == 200
        result = response.json()

        # Verify all headers remain in properties
        stored_headers = result["properties"]["headers"]
        assert stored_headers["Content-Type"] == "application/json"
        assert stored_headers["User-Agent"] == "Kiln-AI/1.0"
        assert result["properties"]["secret_header_keys"] == []

        # Verify config.update_settings was NOT called since no secrets
        mock_config_instance.update_settings.assert_not_called()


async def test_connect_remote_mcp_existing_mcp_secrets(client, test_project):
    """Test connect_remote_mcp endpoint merges with existing mcp_secrets"""
    tool_data = {
        "name": "merge_secret_tool",
        "server_url": "https://example.com/api",
        "headers": {
            "Authorization": "Bearer new-token",
            "Content-Type": "application/json",
        },
        "secret_header_keys": ["Authorization"],
        "description": "Tool that merges with existing secrets",
    }

    existing_secrets = {
        "other_server_id::X-API-Key": "existing-api-key",
        "another_server::Token": "existing-token",
    }

    with (
        patch(
            "app.desktop.studio_server.tool_api.project_from_id"
        ) as mock_project_from_id,
        patch("app.desktop.studio_server.tool_api.Config.shared") as mock_config,
    ):
        mock_project_from_id.return_value = test_project

        # Mock config with existing secrets
        mock_config_instance = mock_config.return_value
        mock_config_instance.get_value.return_value = existing_secrets.copy()
        mock_config_instance.user_id = "test_user"

        async with mock_mcp_success():
            response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )

        assert response.status_code == 200
        result = response.json()

        # Verify config.update_settings was called to merge secrets
        mock_config_instance.update_settings.assert_called_once()
        call_args = mock_config_instance.update_settings.call_args[0][0]

        # Verify existing secrets are preserved and new ones added
        mcp_secrets = call_args[MCP_SECRETS_KEY]
        server_id = result["id"]

        # Existing secrets should still be there
        assert "other_server_id::X-API-Key" in mcp_secrets
        assert "another_server::Token" in mcp_secrets
        assert mcp_secrets["other_server_id::X-API-Key"] == "existing-api-key"
        assert mcp_secrets["another_server::Token"] == "existing-token"

        # New secret should be added
        assert f"{server_id}::Authorization" in mcp_secrets
        assert mcp_secrets[f"{server_id}::Authorization"] == "Bearer new-token"


async def test_delete_tool_server_config_update_fixed(client, test_project):
    """Test that deleting a tool server with secret headers properly saves config changes"""
    # Create a tool server with secret headers
    tool_data = {
        "name": "tool_with_config_bug",
        "server_url": "https://example.com/api",
        "headers": {
            "Authorization": "Bearer secret-token-123",
            "Content-Type": "application/json",
        },
        "secret_header_keys": ["Authorization"],
        "description": "Tool to test config update bug",
    }

    async with mock_mcp_success():
        with patch(
            "app.desktop.studio_server.tool_api.project_from_id"
        ) as mock_project_from_id:
            mock_project_from_id.return_value = test_project

            # Create the tool server first (without mocking Config to avoid interference)
            create_response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )
            assert create_response.status_code == 200
            created_tool = create_response.json()
            tool_server_id = created_tool["id"]

            # Now mock Config for the delete operation
            with patch(
                "app.desktop.studio_server.tool_api.Config.shared"
            ) as mock_config_shared:
                mock_config = mock_config_shared.return_value
                mock_config.get_value.return_value = {
                    f"{tool_server_id}::Authorization": "Bearer secret-token-123",
                    "other_server::some_header": "other_value",
                }
                mock_config.update_settings = Mock()

                # Delete the tool server
                delete_response = client.delete(
                    f"/api/projects/{test_project.id}/tool_servers/{tool_server_id}"
                )
                assert delete_response.status_code == 200

                # FIXED: The implementation now properly calls update_settings after removing secrets
                mock_config.update_settings.assert_called_once()
                call_args = mock_config.update_settings.call_args[0][0]

                # Verify that the secret for this tool server was removed
                expected_remaining_secrets = {
                    "other_server::some_header": "other_value"
                }
                assert call_args[MCP_SECRETS_KEY] == expected_remaining_secrets


async def test_delete_tool_server_missing_secret_key_in_config(client, test_project):
    """Test that deleting a tool server handles gracefully when secret keys are not in config"""
    # Create a tool server with secret headers
    tool_data = {
        "name": "tool_missing_secret_key",
        "server_url": "https://example.com/api",
        "headers": {
            "Authorization": "Bearer secret-token-123",
            "Content-Type": "application/json",
        },
        "secret_header_keys": ["Authorization"],
        "description": "Tool to test missing secret key handling",
    }

    async with mock_mcp_success():
        with patch(
            "app.desktop.studio_server.tool_api.project_from_id"
        ) as mock_project_from_id:
            mock_project_from_id.return_value = test_project

            # Create the tool server first
            create_response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )
            assert create_response.status_code == 200
            created_tool = create_response.json()
            tool_server_id = created_tool["id"]

            # Mock Config for delete - but don't include this server's secrets
            with patch(
                "app.desktop.studio_server.tool_api.Config.shared"
            ) as mock_config_shared:
                mock_config = mock_config_shared.return_value
                # The secret for this tool server is NOT in the config (maybe it was manually deleted)
                mock_config.get_value.return_value = {
                    "other_server::some_header": "other_value",
                }
                mock_config.update_settings = Mock()

                # Delete should work without error even if secret key is missing
                delete_response = client.delete(
                    f"/api/projects/{test_project.id}/tool_servers/{tool_server_id}"
                )
                assert delete_response.status_code == 200

                # Config should still be updated (even though no secrets were removed)
                mock_config.update_settings.assert_called_once()
                call_args = mock_config.update_settings.call_args[0][0]

                # Other secrets should remain unchanged
                expected_remaining_secrets = {
                    "other_server::some_header": "other_value"
                }
                assert call_args[MCP_SECRETS_KEY] == expected_remaining_secrets


# Tests for local MCP secret environment variables functionality
async def test_connect_local_mcp_with_secret_env_vars(client, test_project):
    """Test connect_local_mcp endpoint stores secret environment variables correctly"""
    tool_data = {
        "name": "secret_env_tool",
        "command": "python",
        "args": ["-m", "my_server"],
        "env_vars": {
            "PUBLIC_VAR": "public_value",
            "SECRET_API_KEY": "secret_key_123",
            "ANOTHER_SECRET": "another_secret_value",
            "DEBUG": "true",
        },
        "secret_env_var_keys": ["SECRET_API_KEY", "ANOTHER_SECRET"],
        "description": "Tool with secret environment variables",
    }

    with (
        patch(
            "app.desktop.studio_server.tool_api.project_from_id"
        ) as mock_project_from_id,
        patch("app.desktop.studio_server.tool_api.Config.shared") as mock_config,
    ):
        mock_project_from_id.return_value = test_project

        # Mock config for storing secrets
        mock_config_instance = mock_config.return_value
        mock_config_instance.get_value.return_value = {}  # Empty mcp_secrets initially
        mock_config_instance.user_id = "test_user"

        async with mock_mcp_success():
            response = client.post(
                f"/api/projects/{test_project.id}/connect_local_mcp",
                json=tool_data,
            )

        assert response.status_code == 200
        result = response.json()

        # Verify the tool server was created correctly
        assert result["name"] == "secret_env_tool"
        assert result["properties"]["command"] == "python"
        assert result["properties"]["args"] == ["-m", "my_server"]

        # Verify secret env vars were removed from properties and only non-secret env vars remain
        stored_env_vars = result["properties"]["env_vars"]
        assert "PUBLIC_VAR" in stored_env_vars
        assert stored_env_vars["PUBLIC_VAR"] == "public_value"
        assert "DEBUG" in stored_env_vars
        assert stored_env_vars["DEBUG"] == "true"
        assert "SECRET_API_KEY" not in stored_env_vars
        assert "ANOTHER_SECRET" not in stored_env_vars

        # Verify secret env var keys were stored
        assert result["properties"]["secret_env_var_keys"] == [
            "SECRET_API_KEY",
            "ANOTHER_SECRET",
        ]

        # Verify config.update_settings was called to store secrets
        mock_config_instance.update_settings.assert_called_once()
        call_args = mock_config_instance.update_settings.call_args[0][0]
        assert MCP_SECRETS_KEY in call_args

        # Verify secret values were stored with correct keys
        mcp_secrets = call_args[MCP_SECRETS_KEY]
        server_id = result["id"]
        assert f"{server_id}::SECRET_API_KEY" in mcp_secrets
        assert f"{server_id}::ANOTHER_SECRET" in mcp_secrets
        assert mcp_secrets[f"{server_id}::SECRET_API_KEY"] == "secret_key_123"
        assert mcp_secrets[f"{server_id}::ANOTHER_SECRET"] == "another_secret_value"


async def test_connect_local_mcp_no_secret_env_vars(client, test_project):
    """Test connect_local_mcp endpoint without secret environment variables"""
    tool_data = {
        "name": "no_secret_env_tool",
        "command": "python",
        "args": ["-m", "my_server"],
        "env_vars": {
            "PUBLIC_VAR": "public_value",
            "DEBUG": "true",
        },
        "secret_env_var_keys": [],  # Empty list
        "description": "Tool without secret environment variables",
    }

    with (
        patch(
            "app.desktop.studio_server.tool_api.project_from_id"
        ) as mock_project_from_id,
        patch("app.desktop.studio_server.tool_api.Config.shared") as mock_config,
    ):
        mock_project_from_id.return_value = test_project
        mock_config_instance = mock_config.return_value
        mock_config_instance.user_id = "test_user"

        async with mock_mcp_success():
            response = client.post(
                f"/api/projects/{test_project.id}/connect_local_mcp",
                json=tool_data,
            )

        assert response.status_code == 200
        result = response.json()

        # Verify all env vars remain in properties
        stored_env_vars = result["properties"]["env_vars"]
        assert stored_env_vars["PUBLIC_VAR"] == "public_value"
        assert stored_env_vars["DEBUG"] == "true"
        assert result["properties"]["secret_env_var_keys"] == []

        # Verify config.update_settings was NOT called since no secrets
        mock_config_instance.update_settings.assert_not_called()


async def test_connect_local_mcp_existing_mcp_secrets(client, test_project):
    """Test connect_local_mcp endpoint merges with existing mcp_secrets"""
    tool_data = {
        "name": "merge_secret_env_tool",
        "command": "python",
        "args": ["-m", "my_server"],
        "env_vars": {
            "PUBLIC_VAR": "public_value",
            "NEW_SECRET": "new_secret_value",
        },
        "secret_env_var_keys": ["NEW_SECRET"],
        "description": "Tool that merges with existing secrets",
    }

    existing_secrets = {
        "other_server_id::OLD_SECRET": "existing_secret",
        "another_server::TOKEN": "existing_token",
    }

    with (
        patch(
            "app.desktop.studio_server.tool_api.project_from_id"
        ) as mock_project_from_id,
        patch("app.desktop.studio_server.tool_api.Config.shared") as mock_config,
    ):
        mock_project_from_id.return_value = test_project

        # Mock config with existing secrets
        mock_config_instance = mock_config.return_value
        mock_config_instance.get_value.return_value = existing_secrets.copy()
        mock_config_instance.user_id = "test_user"

        async with mock_mcp_success():
            response = client.post(
                f"/api/projects/{test_project.id}/connect_local_mcp",
                json=tool_data,
            )

        assert response.status_code == 200
        result = response.json()

        # Verify config.update_settings was called to merge secrets
        mock_config_instance.update_settings.assert_called_once()
        call_args = mock_config_instance.update_settings.call_args[0][0]

        # Verify existing secrets are preserved and new ones added
        mcp_secrets = call_args[MCP_SECRETS_KEY]
        server_id = result["id"]

        # Existing secrets should still be there
        assert "other_server_id::OLD_SECRET" in mcp_secrets
        assert "another_server::TOKEN" in mcp_secrets
        assert mcp_secrets["other_server_id::OLD_SECRET"] == "existing_secret"
        assert mcp_secrets["another_server::TOKEN"] == "existing_token"

        # New secret should be added
        assert f"{server_id}::NEW_SECRET" in mcp_secrets
        assert mcp_secrets[f"{server_id}::NEW_SECRET"] == "new_secret_value"


async def test_delete_local_mcp_tool_server_with_secret_env_vars(client, test_project):
    """Test that deleting a local MCP tool server removes secret environment variables from Config"""
    # Create a local MCP tool server with secret env vars
    tool_data = {
        "name": "local_tool_with_secrets",
        "command": "python",
        "args": ["-m", "my_server"],
        "env_vars": {
            "PUBLIC_VAR": "public_value",
            "SECRET_API_KEY": "secret_key_123",
            "ANOTHER_SECRET": "another_secret_value",
        },
        "secret_env_var_keys": ["SECRET_API_KEY", "ANOTHER_SECRET"],
        "description": "Local tool with secret env vars",
    }

    async with mock_mcp_success():
        with patch(
            "app.desktop.studio_server.tool_api.project_from_id"
        ) as mock_project_from_id:
            mock_project_from_id.return_value = test_project

            # Create the tool server first (without mocking Config to avoid interference)
            create_response = client.post(
                f"/api/projects/{test_project.id}/connect_local_mcp",
                json=tool_data,
            )
            assert create_response.status_code == 200
            created_tool = create_response.json()
            tool_server_id = created_tool["id"]

            # Verify the tool server was created with secret env vars
            assert "secret_env_var_keys" in created_tool["properties"]
            assert created_tool["properties"]["secret_env_var_keys"] == [
                "SECRET_API_KEY",
                "ANOTHER_SECRET",
            ]

            # Now mock Config for the delete operation
            with patch(
                "app.desktop.studio_server.tool_api.Config.shared"
            ) as mock_config_shared:
                mock_config = mock_config_shared.return_value
                mock_config.get_value.return_value = {
                    f"{tool_server_id}::SECRET_API_KEY": "secret_key_123",
                    f"{tool_server_id}::ANOTHER_SECRET": "another_secret_value",
                    "other_server::some_env_var": "other_value",  # Should not be deleted
                }
                mock_config.update_settings = Mock()

                # Delete the tool server
                delete_response = client.delete(
                    f"/api/projects/{test_project.id}/tool_servers/{tool_server_id}"
                )
                assert delete_response.status_code == 200

                # Verify that secret env vars were removed from config
                mock_config.update_settings.assert_called_once()
                call_args = mock_config.update_settings.call_args[0][0]

                # Check that the updated mcp_secrets no longer contains the deleted server's secrets
                expected_remaining_secrets = {
                    "other_server::some_env_var": "other_value"
                }
                assert call_args[MCP_SECRETS_KEY] == expected_remaining_secrets


async def test_delete_local_mcp_tool_server_no_secret_env_vars(client, test_project):
    """Test that deleting a local MCP tool server without secret env vars works correctly"""
    # Create a local MCP tool server without secret env vars
    tool_data = {
        "name": "local_tool_without_secrets",
        "command": "python",
        "args": ["-m", "my_server"],
        "env_vars": {"PUBLIC_VAR": "public_value"},
        "secret_env_var_keys": [],
        "description": "Local tool without secret env vars",
    }

    async with mock_mcp_success():
        with patch(
            "app.desktop.studio_server.tool_api.project_from_id"
        ) as mock_project_from_id:
            mock_project_from_id.return_value = test_project

            # Create the tool server first (without mocking Config to avoid interference)
            create_response = client.post(
                f"/api/projects/{test_project.id}/connect_local_mcp",
                json=tool_data,
            )
            assert create_response.status_code == 200
            created_tool = create_response.json()
            tool_server_id = created_tool["id"]

            # Verify the tool server was created without secret env vars
            assert created_tool["properties"]["secret_env_var_keys"] == []

            # Now mock Config for the delete operation
            with patch(
                "app.desktop.studio_server.tool_api.Config.shared"
            ) as mock_config_shared:
                mock_config = mock_config_shared.return_value
                mock_config.get_value.return_value = {
                    "other_server::some_env_var": "other_value"  # Should remain
                }
                mock_config.update_settings = Mock()

                # Delete the tool server
                delete_response = client.delete(
                    f"/api/projects/{test_project.id}/tool_servers/{tool_server_id}"
                )
                assert delete_response.status_code == 200

                # Config should still be updated (even though no secrets were removed)
                mock_config.update_settings.assert_called_once()
                call_args = mock_config.update_settings.call_args[0][0]

                # Other secrets should remain unchanged
                expected_remaining_secrets = {
                    "other_server::some_env_var": "other_value"
                }
                assert call_args[MCP_SECRETS_KEY] == expected_remaining_secrets


async def test_delete_local_mcp_tool_server_secret_key_not_in_config(
    client, test_project
):
    """Test that deleting a local MCP tool server handles cases where secret keys are not in config"""
    # Create a local MCP tool server with secret env vars
    tool_data = {
        "name": "local_tool_with_missing_secrets",
        "command": "python",
        "args": ["-m", "my_server"],
        "env_vars": {
            "PUBLIC_VAR": "public_value",
            "SECRET_API_KEY": "secret_key_123",
            "ANOTHER_SECRET": "another_secret_value",
        },
        "secret_env_var_keys": ["SECRET_API_KEY", "ANOTHER_SECRET"],
        "description": "Local tool with secret env vars not in config",
    }

    async with mock_mcp_success():
        with patch(
            "app.desktop.studio_server.tool_api.project_from_id"
        ) as mock_project_from_id:
            mock_project_from_id.return_value = test_project

            # Create the tool server first (without mocking Config to avoid interference)
            create_response = client.post(
                f"/api/projects/{test_project.id}/connect_local_mcp",
                json=tool_data,
            )
            assert create_response.status_code == 200
            created_tool = create_response.json()
            tool_server_id = created_tool["id"]

            # Now mock Config for the delete operation with missing secrets
            with patch(
                "app.desktop.studio_server.tool_api.Config.shared"
            ) as mock_config_shared:
                mock_config = mock_config_shared.return_value
                # Config doesn't contain the server's secrets (they were never saved or were deleted)
                mock_config.get_value.return_value = {
                    "other_server::some_env_var": "other_value"  # Should remain
                }
                mock_config.update_settings = Mock()

                # Delete the tool server - should not raise an exception
                delete_response = client.delete(
                    f"/api/projects/{test_project.id}/tool_servers/{tool_server_id}"
                )
                assert delete_response.status_code == 200

                # Config should still be updated
                mock_config.update_settings.assert_called_once()
                call_args = mock_config.update_settings.call_args[0][0]

                # Other secrets should remain unchanged
                expected_remaining_secrets = {
                    "other_server::some_env_var": "other_value"
                }
                assert call_args[MCP_SECRETS_KEY] == expected_remaining_secrets


async def test_delete_local_mcp_tool_server_missing_secret_env_var_keys_property(
    client, test_project
):
    """Test that deleting a local MCP tool server handles missing secret_env_var_keys property gracefully"""
    # Create a local MCP tool server first
    tool_data = {
        "name": "local_tool_without_secret_keys_prop",
        "command": "python",
        "args": ["-m", "test_server"],
        "env_vars": {"DEBUG": "true"},
        "secret_env_var_keys": [],
        "description": "Local tool for testing missing property",
    }

    async with mock_mcp_success():
        with patch(
            "app.desktop.studio_server.tool_api.project_from_id"
        ) as mock_project_from_id:
            mock_project_from_id.return_value = test_project

            # Create the local tool server first (without mocking Config to avoid interference)
            create_response = client.post(
                f"/api/projects/{test_project.id}/connect_local_mcp",
                json=tool_data,
            )
            assert create_response.status_code == 200
            created_tool = create_response.json()
            tool_server_id = created_tool["id"]

            # Manually remove the secret_env_var_keys property to simulate old data
            # This requires directly modifying the tool server's properties
            tool_server = tool_server_from_id(test_project.id, tool_server_id)
            del tool_server.properties["secret_env_var_keys"]
            tool_server.save_to_file()

            # Now mock Config for the delete operation
            with patch(
                "app.desktop.studio_server.tool_api.Config.shared"
            ) as mock_config_shared:
                mock_config = mock_config_shared.return_value
                mock_config.get_value.return_value = {
                    "other_server::some_env_var": "other_value"
                }
                mock_config.update_settings = Mock()

                # Delete the tool server - this should handle the missing property gracefully
                delete_response = client.delete(
                    f"/api/projects/{test_project.id}/tool_servers/{tool_server_id}"
                )
                assert delete_response.status_code == 200

                # Verify that config update was still called
                mock_config.update_settings.assert_called_once()
                call_args = mock_config.update_settings.call_args[0][0]

                # Check that existing secrets remain unchanged since no secret keys were found
                expected_remaining_secrets = {
                    "other_server::some_env_var": "other_value"
                }
                assert call_args[MCP_SECRETS_KEY] == expected_remaining_secrets


async def test_get_tool_server_with_missing_secrets(client, test_project):
    """Test get_tool_server returns missing_secrets when secrets are not configured"""
    # First create a tool server with secret headers
    tool_data = {
        "name": "test_missing_secrets_tool",
        "server_url": "https://example.com/api",
        "headers": {"Authorization": "Bearer token", "X-API-Key": "key"},
        "secret_header_keys": ["Authorization", "X-API-Key"],
        "description": "Tool with missing secrets",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        # Create the tool with successful validation
        async with mock_mcp_success():
            create_response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )
            assert create_response.status_code == 200
        created_tool = create_response.json()
        tool_server_id = created_tool["id"]

        # Mock the missing_secrets method to return missing secrets
        with patch(
            "app.desktop.studio_server.tool_api.tool_server_from_id"
        ) as mock_tool_server_from_id:
            mock_tool_server = Mock()
            mock_tool_server.id = tool_server_id
            mock_tool_server.name = "test_missing_secrets_tool"
            mock_tool_server.type = ToolServerType.remote_mcp
            mock_tool_server.description = "Tool with missing secrets"
            mock_tool_server.created_at = datetime.now()
            mock_tool_server.created_by = None
            mock_tool_server.properties = {
                "server_url": "https://example.com/api",
                "headers": {"Authorization": "Bearer token", "X-API-Key": "key"},
                "secret_header_keys": ["Authorization", "X-API-Key"],
            }
            mock_tool_server.retrieve_secrets.return_value = (
                {},
                ["Authorization", "X-API-Key"],
            )
            mock_tool_server_from_id.return_value = mock_tool_server

            # Get the tool server - should return with missing_secrets and no available_tools
            response = client.get(
                f"/api/projects/{test_project.id}/tool_servers/{tool_server_id}"
            )

            assert response.status_code == 200
            result = response.json()

            # Verify the tool server details
            assert result["name"] == "test_missing_secrets_tool"
            assert result["type"] == "remote_mcp"
            assert result["description"] == "Tool with missing secrets"

            # Verify missing_secrets is populated
            assert "missing_secrets" in result
            assert set(result["missing_secrets"]) == {"Authorization", "X-API-Key"}

            # Verify available_tools is empty when secrets are missing
            assert "available_tools" in result
            assert result["available_tools"] == []
            assert "missing_oauth" in result
            assert result["missing_oauth"] is False


async def test_get_tool_server_with_missing_oauth(client, test_project):
    """Test get_tool_server reports missing OAuth tokens when required."""

    tool_data = {
        "name": "test_missing_oauth_tool",
        "server_url": "https://example.com/api",
        "headers": {},
        "secret_header_keys": [],
        "description": "Tool requiring OAuth",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id",
        return_value=test_project,
    ):
        async with mock_mcp_success():
            create_response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )
            assert create_response.status_code == 200
        created_tool = create_response.json()
        tool_server_id = created_tool["id"]

    with (
        patch("app.desktop.studio_server.tool_api.tool_server_from_id") as mock_from_id,
        patch(
            "app.desktop.studio_server.tool_api.MCPSessionManager.shared"
        ) as mock_session_shared,
    ):
        mock_tool_server = Mock()
        mock_tool_server.id = tool_server_id
        mock_tool_server.name = "test_missing_oauth_tool"
        mock_tool_server.type = ToolServerType.remote_mcp
        mock_tool_server.description = "Tool requiring OAuth"
        mock_tool_server.created_at = datetime.now()
        mock_tool_server.created_by = None
        mock_tool_server.properties = {
            "server_url": "https://example.com/api",
            "headers": {},
            "secret_header_keys": [],
            "oauth_required": True,
        }
        mock_tool_server.retrieve_secrets.return_value = ({}, [])
        mock_from_id.return_value = mock_tool_server

        mock_session_manager = Mock()
        mock_session_manager.has_oauth_tokens.return_value = False
        mock_session_shared.return_value = mock_session_manager

        response = client.get(
            f"/api/projects/{test_project.id}/tool_servers/{tool_server_id}"
        )

        assert response.status_code == 200
        result = response.json()
        assert result["missing_secrets"] == []
        assert result["missing_oauth"] is True
        assert result["available_tools"] == []


async def test_get_tool_server_with_some_missing_secrets(client, test_project):
    """Test get_tool_server returns partial missing_secrets when some secrets are missing"""
    # First create a tool server with secret headers
    tool_data = {
        "name": "test_partial_missing_secrets_tool",
        "server_url": "https://example.com/api",
        "headers": {
            "Authorization": "Bearer token",
            "X-API-Key": "key",
            "Content-Type": "application/json",
        },
        "secret_header_keys": ["Authorization", "X-API-Key"],
        "description": "Tool with some missing secrets",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        # Create the tool with successful validation
        async with mock_mcp_success():
            create_response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )
            assert create_response.status_code == 200
        created_tool = create_response.json()
        tool_server_id = created_tool["id"]

        # Mock the missing_secrets method to return only one missing secret
        with patch(
            "app.desktop.studio_server.tool_api.tool_server_from_id"
        ) as mock_tool_server_from_id:
            mock_tool_server = Mock()
            mock_tool_server.id = tool_server_id
            mock_tool_server.name = "test_partial_missing_secrets_tool"
            mock_tool_server.type = ToolServerType.remote_mcp
            mock_tool_server.description = "Tool with some missing secrets"
            mock_tool_server.created_at = datetime.now()
            mock_tool_server.created_by = None
            mock_tool_server.properties = {
                "server_url": "https://example.com/api",
                "headers": {
                    "Authorization": "Bearer token",
                    "X-API-Key": "key",
                    "Content-Type": "application/json",
                },
                "secret_header_keys": ["Authorization", "X-API-Key"],
            }
            mock_tool_server.retrieve_secrets.return_value = (
                {"Authorization": "Bearer token"},
                ["X-API-Key"],
            )  # Only one missing
            mock_tool_server_from_id.return_value = mock_tool_server

            # Get the tool server - should return with missing_secrets and no available_tools
            response = client.get(
                f"/api/projects/{test_project.id}/tool_servers/{tool_server_id}"
            )

            assert response.status_code == 200
            result = response.json()

            # Verify missing_secrets contains only the missing secret
            assert "missing_secrets" in result
            assert result["missing_secrets"] == ["X-API-Key"]
            assert "missing_oauth" in result
            assert result["missing_oauth"] is False

            # Verify available_tools is empty when any secrets are missing
            assert "available_tools" in result
            assert result["available_tools"] == []


async def test_get_tool_server_no_missing_secrets(client, test_project):
    """Test get_tool_server returns available_tools when no secrets are missing"""
    # First create a tool server with secret headers
    tool_data = {
        "name": "test_no_missing_secrets_tool",
        "server_url": "https://example.com/api",
        "headers": {"Authorization": "Bearer token", "X-API-Key": "key"},
        "secret_header_keys": ["Authorization", "X-API-Key"],
        "description": "Tool with no missing secrets",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        # Create the tool with successful validation
        async with mock_mcp_success():
            create_response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )
            assert create_response.status_code == 200
        created_tool = create_response.json()
        tool_server_id = created_tool["id"]

        # Mock the missing_secrets method to return no missing secrets
        with patch(
            "app.desktop.studio_server.tool_api.tool_server_from_id"
        ) as mock_tool_server_from_id:
            mock_tool_server = Mock()
            mock_tool_server.id = tool_server_id
            mock_tool_server.name = "test_no_missing_secrets_tool"
            mock_tool_server.type = ToolServerType.remote_mcp
            mock_tool_server.description = "Tool with no missing secrets"
            mock_tool_server.created_at = datetime.now()
            mock_tool_server.created_by = None
            mock_tool_server.properties = {
                "server_url": "https://example.com/api",
                "headers": {"Authorization": "Bearer token", "X-API-Key": "key"},
                "secret_header_keys": ["Authorization", "X-API-Key"],
            }
            mock_tool_server.retrieve_secrets.return_value = (
                {"Authorization": "Bearer token", "X-API-Key": "key"},
                [],
            )  # No missing secrets
            mock_tool_server_from_id.return_value = mock_tool_server

            # Mock successful tool retrieval
            mock_tools = [
                Tool(name="test_tool", description="Test tool", inputSchema={}),
                Tool(name="calculator", description="Math tool", inputSchema={}),
            ]

            async with mock_mcp_success(tools=mock_tools):
                # Get the tool server - should return available_tools when no secrets are missing
                response = client.get(
                    f"/api/projects/{test_project.id}/tool_servers/{tool_server_id}"
                )

                assert response.status_code == 200
                result = response.json()

                # Verify missing_secrets is empty
                assert "missing_secrets" in result
                assert result["missing_secrets"] == []
                assert "missing_oauth" in result
                assert result["missing_oauth"] is False

                # Verify available_tools is populated when no secrets are missing
                assert "available_tools" in result
                assert len(result["available_tools"]) == 2
                tool_names = [tool["name"] for tool in result["available_tools"]]
                assert "test_tool" in tool_names
                assert "calculator" in tool_names


async def test_get_tool_server_local_mcp_with_missing_secrets(client, test_project):
    """Test get_tool_server returns missing_secrets for local MCP servers"""
    # First create a local MCP tool server
    tool_data = {
        "name": "test_local_missing_secrets",
        "command": "python",
        "args": ["-m", "my_server"],
        "env_vars": {
            "API_KEY": "secret_key",
            "PORT": "3000",
            "DATABASE_PASSWORD": "placeholder",
        },
        "secret_env_var_keys": ["API_KEY", "DATABASE_PASSWORD"],
        "description": "Local MCP tool with missing secrets",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        # Create the local MCP tool server
        async with mock_mcp_success():
            create_response = client.post(
                f"/api/projects/{test_project.id}/connect_local_mcp",
                json=tool_data,
            )
            assert create_response.status_code == 200
        created_tool = create_response.json()
        tool_server_id = created_tool["id"]

        # Mock the missing_secrets method to return missing secrets
        with patch(
            "app.desktop.studio_server.tool_api.tool_server_from_id"
        ) as mock_tool_server_from_id:
            mock_tool_server = Mock()
            mock_tool_server.id = tool_server_id
            mock_tool_server.name = "test_local_missing_secrets"
            mock_tool_server.type = ToolServerType.local_mcp
            mock_tool_server.description = "Local MCP tool with missing secrets"
            mock_tool_server.created_at = datetime.now()
            mock_tool_server.created_by = None
            mock_tool_server.properties = {
                "command": "python",
                "args": ["-m", "my_server"],
                "env_vars": {
                    "API_KEY": "secret_key",
                    "PORT": "3000",
                    "DATABASE_PASSWORD": "placeholder",
                },
                "secret_env_var_keys": ["API_KEY", "DATABASE_PASSWORD"],
            }
            mock_tool_server.retrieve_secrets.return_value = (
                {"API_KEY": "secret_key"},
                ["DATABASE_PASSWORD"],
            )  # Missing secret
            mock_tool_server_from_id.return_value = mock_tool_server

            # Get the tool server - should return with missing_secrets
            response = client.get(
                f"/api/projects/{test_project.id}/tool_servers/{tool_server_id}"
            )

            assert response.status_code == 200
            result = response.json()

            # Verify the tool server details
            assert result["name"] == "test_local_missing_secrets"
            assert result["type"] == "local_mcp"
            assert result["description"] == "Local MCP tool with missing secrets"

            # Verify missing_secrets is populated
            assert "missing_secrets" in result
            assert result["missing_secrets"] == ["DATABASE_PASSWORD"]
            assert "missing_oauth" in result
            assert result["missing_oauth"] is False

            # Verify available_tools is empty when secrets are missing
            assert "available_tools" in result
            assert result["available_tools"] == []


async def test_get_tool_server_kiln_task_success(client, test_project):
    """Test get_tool_server successfully retrieves a Kiln task tool server"""

    with (
        patch(
            "app.desktop.studio_server.tool_api.project_from_id"
        ) as mock_project_from_id,
        patch("app.desktop.studio_server.tool_api.task_from_id") as mock_task_from_id,
        patch(
            "kiln_ai.tools.kiln_task_tool.project_from_id"
        ) as mock_kiln_project_from_id,
    ):
        mock_project_from_id.return_value = test_project
        mock_kiln_project_from_id.return_value = test_project

        # Create a test task
        task = Task(
            name="Test Task",
            description="Test task for Kiln task tool",
            instruction="Complete the test task",
            parent=test_project,
        )
        task.save_to_file()

        # Set up task_from_id mock to return the task
        def mock_task_from_id_func(project_id, task_id):
            if task_id == str(task.id):
                return task
            else:
                raise HTTPException(status_code=404, detail="Task not found")

        mock_task_from_id.side_effect = mock_task_from_id_func

        # Create a Kiln task tool server
        kiln_task_server = ExternalToolServer(
            name="kiln_task_server",
            type=ToolServerType.kiln_task,
            description="Kiln task server for testing",
            properties={
                "name": "test_kiln_task_tool",
                "description": "Test Kiln task tool",
                "task_id": str(task.id),
                "run_config_id": "default",
                "is_archived": False,
            },
            parent=test_project,
        )
        kiln_task_server.save_to_file()

        # Get the tool server
        response = client.get(
            f"/api/projects/{test_project.id}/tool_servers/{kiln_task_server.id}"
        )

        assert response.status_code == 200
        result = response.json()

        # Verify the tool server details
        assert result["name"] == "kiln_task_server"
        assert result["type"] == "kiln_task"
        assert result["description"] == "Kiln task server for testing"
        assert result["properties"]["name"] == "test_kiln_task_tool"
        assert result["properties"]["description"] == "Test Kiln task tool"
        assert result["properties"]["task_id"] == str(task.id)
        assert result["properties"]["run_config_id"] == "default"
        assert "id" in result

        # Verify available_tools is populated with the Kiln task tool
        assert "available_tools" in result
        assert len(result["available_tools"]) == 1

        tool = result["available_tools"][0]
        assert tool["name"] == "test_kiln_task_tool"
        assert tool["description"] == "Test Kiln task tool"
        assert "inputSchema" in tool


@pytest.fixture
def edit_local_server_data():
    return {
        "name": "edited name",
        "command": "python",
        "args": ["-m", "my_server"],
        "env_vars": {
            "PORT": "3000",
            "DATABASE_PASSWORD": "1234",
        },
        "secret_env_var_keys": ["DATABASE_PASSWORD"],
        "description": "edited description",
    }


async def test_edit_local_mcp_404(client, test_project, edit_local_server_data):
    """Test edit_local_mcp returns 404 when the tool server does not exist"""
    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project
        response = client.patch(
            f"/api/projects/{test_project.id}/edit_local_mcp/123",
            json=edit_local_server_data,
        )
        assert response.status_code == 404
        assert response.json() == {"detail": "Tool server not found"}


@pytest.fixture
def existing_local_tool_server(test_project):
    existing_tool_server = ExternalToolServer(
        parent=test_project,
        type=ToolServerType.local_mcp,
        name="test_local_mcp",
        properties={
            "command": "echo",
            "args": ["hello"],
        },
    )
    existing_tool_server.save_to_file()
    return existing_tool_server


@pytest.fixture
def existing_remote_tool_server(test_project):
    existing_tool_server = ExternalToolServer(
        parent=test_project,
        type=ToolServerType.remote_mcp,
        name="test_remote_mcp",
        properties={
            "server_url": "https://example.com",
            "headers": {},
        },
    )
    existing_tool_server.save_to_file()
    return existing_tool_server


async def test_edit_local_mcp_wrong_type(
    client, test_project, edit_local_server_data, existing_remote_tool_server
):
    """Test edit_local_mcp returns 400 when the tool server is not a local MCP server"""

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project
        response = client.patch(
            f"/api/projects/{test_project.id}/edit_local_mcp/{existing_remote_tool_server.id}",
            json=edit_local_server_data,
        )
        assert response.status_code == 400
        assert response.json() == {
            "detail": "Existing tool server is not a local MCP server. You can't edit a non-local MCP server with this endpoint."
        }


async def test_edit_local_mcp(
    client, test_project, edit_local_server_data, existing_local_tool_server
):
    """Test edit_local_mcp updates the tool server"""
    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        # Create the local MCP tool server
        async with mock_mcp_success():
            edit_response = client.patch(
                f"/api/projects/{test_project.id}/edit_local_mcp/{existing_local_tool_server.id}",
                json=edit_local_server_data,
            )
            assert edit_response.status_code == 200
            response_json = edit_response.json()
            assert response_json["name"] == "edited name"
            assert response_json["type"] == ToolServerType.local_mcp
            assert response_json["description"] == "edited description"
            assert response_json["properties"]["command"] == "python"
            assert response_json["properties"]["args"] == ["-m", "my_server"]
            assert response_json["properties"]["env_vars"].keys() == {
                "PORT",
            }
            assert response_json["properties"]["env_vars"]["PORT"] == "3000"
            assert response_json["properties"]["secret_env_var_keys"] == [
                "DATABASE_PASSWORD",
            ]

            # Verify the tool server changes were saved to file
            loaded_tool_server = ExternalToolServer.load_from_file(
                existing_local_tool_server.path
            )
            assert loaded_tool_server.name == "edited name"
            assert loaded_tool_server.type == ToolServerType.local_mcp
            assert loaded_tool_server.description == "edited description"
            assert loaded_tool_server.properties["command"] == "python"
            assert loaded_tool_server.properties["args"] == ["-m", "my_server"]
            assert loaded_tool_server.properties["env_vars"].keys() == {
                "PORT",
            }
            assert loaded_tool_server.properties["env_vars"]["PORT"] == "3000"
            assert loaded_tool_server.properties["secret_env_var_keys"] == [
                "DATABASE_PASSWORD",
            ]


@pytest.fixture
def edit_remote_server_data():
    return {
        "name": "edited name",
        "description": "edited description",
        "server_url": "https://example.com/edited",
        "headers": {
            "Content-Type": "application/json",
            "Authorization": "Bearer token",
        },
        "secret_header_keys": ["Authorization"],
    }


async def test_edit_remote_mcp_404(client, test_project, edit_remote_server_data):
    """Test edit_remote_mcp returns 404 when the tool server does not exist"""
    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project
        response = client.patch(
            f"/api/projects/{test_project.id}/edit_remote_mcp/123",
            json=edit_remote_server_data,
        )
        assert response.status_code == 404
        assert response.json() == {"detail": "Tool server not found"}


async def test_edit_remote_mcp_wrong_type(
    client, test_project, edit_remote_server_data, existing_local_tool_server
):
    """Test edit_local_mcp returns 400 when the tool server is not a local MCP server"""

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project
        response = client.patch(
            f"/api/projects/{test_project.id}/edit_remote_mcp/{existing_local_tool_server.id}",
            json=edit_remote_server_data,
        )
        assert response.status_code == 400
        assert response.json() == {
            "detail": "Existing tool server is not a remote MCP server. You can't edit a non-remote MCP server with this endpoint."
        }


async def test_edit_remote_mcp(
    client, test_project, edit_remote_server_data, existing_remote_tool_server
):
    """Test edit_local_mcp updates the tool server"""
    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        # Create the local MCP tool server
        async with mock_mcp_success():
            edit_response = client.patch(
                f"/api/projects/{test_project.id}/edit_remote_mcp/{existing_remote_tool_server.id}",
                json=edit_remote_server_data,
            )
            assert edit_response.status_code == 200
            response_json = edit_response.json()
            assert response_json["name"] == "edited name"
            assert response_json["type"] == ToolServerType.remote_mcp
            assert response_json["description"] == "edited description"
            assert (
                response_json["properties"]["server_url"]
                == "https://example.com/edited"
            )
            assert response_json["properties"]["headers"] == {
                "Content-Type": "application/json",
            }
            assert response_json["properties"]["secret_header_keys"] == [
                "Authorization"
            ]

            # Verify the tool server changes were saved to file
            loaded_tool_server = ExternalToolServer.load_from_file(
                existing_remote_tool_server.path
            )
            assert loaded_tool_server.name == "edited name"
            assert loaded_tool_server.type == ToolServerType.remote_mcp
            assert loaded_tool_server.description == "edited description"
            assert (
                loaded_tool_server.properties["server_url"]
                == "https://example.com/edited"
            )
            assert loaded_tool_server.properties["headers"] == {
                "Content-Type": "application/json",
            }
            assert loaded_tool_server.properties["secret_header_keys"] == [
                "Authorization",
            ]


@pytest.mark.parametrize(
    "fixture_name, endpoint, property_key, bad_data",
    [
        # Test 1: Remote MCP with bad url
        (
            "existing_remote_tool_server",
            "edit_remote_mcp",
            "server_url",
            {"server_url": "http://invalid-url.com"},
        ),
        # Test 2: Local MCP with bad command
        (
            "existing_local_tool_server",
            "edit_local_mcp",
            "command",
            {"command": "invalid-command", "args": []},
        ),
    ],
    ids=["remote_mcp", "local_mcp"],
)
async def test_edit_mcp_does_not_keep_bad_data_in_memory(
    client,
    test_project,
    request,
    mock_project_from_id,
    fixture_name,
    endpoint,
    property_key,
    bad_data,
):
    """Test editing mcp servers with validation failure will not keep bad data in memory"""

    test_server = request.getfixturevalue(fixture_name)

    # Load ExternalToolServer in memory via tool_server_from_id and store the original value
    # tool_server_from_id needs project_from_id to be mocked to return properly
    mock_project_from_id(test_project)
    original_server = tool_server_from_id(test_project.id, test_server.id)
    original_value = original_server.properties[property_key]

    # Call patch endpoint with bad data and force validation failure
    bad_data = {
        "name": test_server.name,
        "description": test_server.description,
        **bad_data,
    }
    async with mock_mcp_connection_error():
        with pytest.raises(Exception, match="Connection failed"):
            await client.patch(
                f"/api/projects/{test_project.id}/{endpoint}/{test_server.id}",
                json=bad_data,
            )

    # Read the server from memory again and ensure it's not changed
    post_validation_server = tool_server_from_id(test_project.id, test_server.id)
    assert post_validation_server.properties[property_key] == original_value


def test_get_search_tools_success(client, test_project, mock_project_from_id):
    """Test get_search_tools returns RAG configs as search tools"""

    # Create some RAG configs
    rag_config_1 = RagConfig(
        parent=test_project,
        name="Test Search Tool 1",
        tool_name="test_search_tool_1",
        tool_description="First test search tool",
        description="First test search tool",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
        vector_store_config_id="vector_store123",
    )

    rag_config_2 = RagConfig(
        parent=test_project,
        name="Test Search Tool 2",
        description=None,
        tool_name="test_search_tool_2",
        tool_description="Second test search tool",
        extractor_config_id="extractor456",
        chunker_config_id="chunker789",
        embedding_config_id="embedding123",
        vector_store_config_id="vector_store456",
    )

    # Save the RAG configs
    rag_config_1.save_to_file()
    rag_config_2.save_to_file()

    # Get search tools
    response = client.get(f"/api/projects/{test_project.id}/search_tools")
    assert response.status_code == 200

    search_tools = response.json()
    assert len(search_tools) == 2

    # Check first search tool
    tool1 = next(t for t in search_tools if t["tool_name"] == "test_search_tool_1")
    assert tool1["id"] == str(rag_config_1.id)
    assert tool1["name"] == "Test Search Tool 1"
    assert tool1["description"] == "First test search tool"

    # Check second search tool
    tool2 = next(t for t in search_tools if t["tool_name"] == "test_search_tool_2")
    assert tool2["id"] == str(rag_config_2.id)
    assert tool2["description"] == "Second test search tool"
    assert tool2["name"] == "Test Search Tool 2"


# RAG-specific tests
async def test_get_available_tools_with_rag_configs(client, test_project):
    """Test get_available_tools includes RAG configs when there's an external tool server"""

    # Create some RAG configs
    rag_config_1 = RagConfig(
        parent=test_project,
        name="Test RAG Config 1",
        description="First test RAG configuration",
        tool_name="test_rag_config_1",
        tool_description="First test RAG configuration",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
        vector_store_config_id="vector_store123",
    )

    rag_config_2 = RagConfig(
        parent=test_project,
        name="Test RAG Config 2",
        description=None,  # Test None description
        tool_name="test_rag_config_2",
        tool_description="Second test RAG configuration",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
        vector_store_config_id="vector_store456",
    )

    # Save the RAG configs
    rag_config_1.save_to_file()
    rag_config_2.save_to_file()

    # Create an MCP tool server to trigger the RAG set inclusion
    tool_data = {
        "name": "test_server",
        "server_url": "https://example.com/mcp",
        "headers": {},
        "description": "Test server",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        # Create the MCP server
        async with mock_mcp_success():
            create_response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )
            assert create_response.status_code == 200

        # Mock no tools from MCP server
        async with mock_mcp_success():
            response = client.get(f"/api/projects/{test_project.id}/available_tools")

            assert response.status_code == 200
            result = response.json()

            # Should have one tool set for RAG (since MCP server has no tools, only RAG set is added)
            assert len(result) == 1
            rag_set = result[0]
            assert rag_set["set_name"] == "Search Tools (RAG)"
            assert len(rag_set["tools"]) == 2

            # Verify RAG tool details
            tool_names = [tool["name"] for tool in rag_set["tools"]]

            assert "test_rag_config_1" in tool_names
            assert "test_rag_config_2" in tool_names

            # Verify tool IDs are properly formatted
            for tool in rag_set["tools"]:
                assert tool["id"].startswith("kiln_tool::rag::")

            # Find specific tools and check their descriptions
            config1_tool = next(
                t for t in rag_set["tools"] if t["name"] == "test_rag_config_1"
            )
            assert (
                config1_tool["description"]
                == "Test RAG Config 1: First test RAG configuration"
            )

            config2_tool = next(
                t for t in rag_set["tools"] if t["name"] == "test_rag_config_2"
            )
            assert (
                config2_tool["description"]
                == "Test RAG Config 2: Second test RAG configuration"
            )


async def test_get_available_tools_with_rag_and_mcp(client, test_project):
    """Test get_available_tools with both RAG configs and MCP servers"""
    from kiln_ai.datamodel.rag import RagConfig

    # Create a RAG config
    rag_config = RagConfig(
        parent=test_project,
        name="mixed_test_rag",
        description="RAG config for mixed test",
        tool_name="mixed_test_rag",
        tool_description="RAG config for mixed test",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
        vector_store_config_id="vector_store123",
    )
    rag_config.save_to_file()

    # Create an MCP tool server
    tool_data = {
        "name": "mixed_test_server",
        "server_url": "https://example.com/mcp",
        "headers": {"Authorization": "Bearer token"},
        "description": "MCP server for mixed test",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        # Create the MCP server
        async with mock_mcp_success():
            create_response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )
            assert create_response.status_code == 200
        created_tool = create_response.json()
        server_id = created_tool["id"]

        # Mock tools for the MCP server
        mock_tools = [
            Tool(name="mcp_tool", description="MCP tool", inputSchema={}),
        ]

        async with mock_mcp_success(tools=mock_tools):
            # Get available tools
            response = client.get(f"/api/projects/{test_project.id}/available_tools")

            assert response.status_code == 200
            result = response.json()

            # Should have two tool sets: MCP Server and RAG
            assert len(result) == 2

            # Find both sets
            mcp_set = next(
                (s for s in result if s["set_name"] == "MCP Server: mixed_test_server"),
                None,
            )
            rag_set = next(
                (s for s in result if s["set_name"] == "Search Tools (RAG)"),
                None,
            )

            assert mcp_set is not None
            assert rag_set is not None

            # Verify MCP tools
            assert len(mcp_set["tools"]) == 1
            assert mcp_set["tools"][0]["name"] == "mcp_tool"
            assert mcp_set["tools"][0]["id"].startswith(f"mcp::remote::{server_id}::")

            # Verify RAG tools
            assert len(rag_set["tools"]) == 1
            assert rag_set["tools"][0]["name"] == "mixed_test_rag"
            assert rag_set["tools"][0]["id"].startswith("kiln_tool::rag::")


def test_get_search_tools_excludes_archived(client, test_project, mock_project_from_id):
    """Archived RAG configs should not be returned by /search_tools."""

    active = RagConfig(
        parent=test_project,
        name="Active Search Tool",
        tool_name="active_tool",
        tool_description="Active",
        extractor_config_id="e1",
        chunker_config_id="c1",
        embedding_config_id="em1",
        vector_store_config_id="v1",
        is_archived=False,
    )
    archived = RagConfig(
        parent=test_project,
        name="Archived Search Tool",
        tool_name="archived_tool",
        tool_description="Archived",
        extractor_config_id="e2",
        chunker_config_id="c2",
        embedding_config_id="em2",
        vector_store_config_id="v2",
        is_archived=True,
    )
    active.save_to_file()
    archived.save_to_file()

    response = client.get(f"/api/projects/{test_project.id}/search_tools")
    assert response.status_code == 200
    tools = response.json()
    # Only the active one should be returned
    assert len(tools) == 1
    assert tools[0]["tool_name"] == "active_tool"
    assert tools[0]["name"] == "Active Search Tool"


async def test_available_tools_excludes_archived_rag_and_kiln_task_tools(
    client, test_project
):
    """Archived RAG configs and kiln task tools should be excluded from their respective sets in /available_tools."""

    # Create active and archived RAG configs
    active = RagConfig(
        parent=test_project,
        name="Active RAG",
        description="",
        tool_name="active_rag",
        tool_description="Active desc",
        extractor_config_id="e1",
        chunker_config_id="c1",
        embedding_config_id="em1",
        vector_store_config_id="v1",
        is_archived=False,
    )
    archived = RagConfig(
        parent=test_project,
        name="Archived RAG",
        description="",
        tool_name="archived_rag",
        tool_description="Archived desc",
        extractor_config_id="e2",
        chunker_config_id="c2",
        embedding_config_id="em2",
        vector_store_config_id="v2",
        is_archived=True,
    )
    active.save_to_file()
    archived.save_to_file()

    # Create active and archived kiln task tool servers
    active_kiln_task = ExternalToolServer(
        name="active_kiln_task_server",
        type=ToolServerType.kiln_task,
        description="Active kiln task server",
        properties={
            "name": "active_task_tool",
            "description": "Active task tool",
            "task_id": "task_1",
            "run_config_id": "run_config_1",
            "is_archived": False,
        },
        parent=test_project,
    )

    archived_kiln_task = ExternalToolServer(
        name="archived_kiln_task_server",
        type=ToolServerType.kiln_task,
        description="Archived kiln task server",
        properties={
            "name": "archived_task_tool",
            "description": "Archived task tool",
            "task_id": "task_2",
            "run_config_id": "run_config_2",
            "is_archived": True,
        },
        parent=test_project,
    )
    active_kiln_task.save_to_file()
    archived_kiln_task.save_to_file()

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        response = client.get(f"/api/projects/{test_project.id}/available_tools")
        assert response.status_code == 200
        result = response.json()

        # Should have two tool sets: RAG and Kiln Task
        assert len(result) == 2

        rag_set = next(
            (s for s in result if s["set_name"] == "Search Tools (RAG)"), None
        )
        kiln_task_set = next(
            (s for s in result if s["set_name"] == "Kiln Tasks as Tools"), None
        )

        assert rag_set is not None
        assert kiln_task_set is not None

        # Only the active RAG config should be present
        assert len(rag_set["tools"]) == 1
        assert rag_set["tools"][0]["name"] == "active_rag"

        # Only the active kiln task tool should be present
        assert len(kiln_task_set["tools"]) == 1
        assert kiln_task_set["tools"][0]["name"] == "active_task_tool"


class TestExternalToolApiDescription:
    """Test cases for ExternalToolApiDescription class methods."""

    def test_tool_from_mcp_tool_with_all_fields(self):
        """Test creating ExternalToolApiDescription from MCP Tool with all fields."""
        mcp_tool = Tool(
            name="test_tool",
            description="A test tool description",
            inputSchema={
                "type": "object",
                "properties": {
                    "param1": {"type": "string", "description": "First parameter"},
                    "param2": {"type": "number", "description": "Second parameter"},
                },
                "required": ["param1"],
            },
        )

        result = ExternalToolApiDescription.tool_from_mcp_tool(mcp_tool)

        assert result.name == "test_tool"
        assert result.description == "A test tool description"
        assert result.inputSchema == {
            "type": "object",
            "properties": {
                "param1": {"type": "string", "description": "First parameter"},
                "param2": {"type": "number", "description": "Second parameter"},
            },
            "required": ["param1"],
        }

    def test_tool_from_mcp_tool_with_minimal_fields(self):
        """Test creating ExternalToolApiDescription from MCP Tool with minimal fields."""
        mcp_tool = Tool(
            name="minimal_tool",
            description=None,
            inputSchema={},
        )

        result = ExternalToolApiDescription.tool_from_mcp_tool(mcp_tool)

        assert result.name == "minimal_tool"
        assert result.description is None
        assert result.inputSchema == {}

    @pytest.mark.asyncio
    async def test_tool_from_kiln_task_tool_with_all_fields(self):
        """Test creating ExternalToolApiDescription from KilnTaskTool with all fields."""
        # Create a mock KilnTaskTool
        mock_tool = AsyncMock()
        mock_tool.name.return_value = "kiln_task_tool"
        mock_tool.description.return_value = "A Kiln task tool description"
        mock_tool.parameters_schema = {
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Input parameter"},
            },
            "required": ["input"],
        }

        result = await ExternalToolApiDescription.tool_from_kiln_task_tool(mock_tool)

        # Verify that the async methods were called
        mock_tool.name.assert_called_once()
        mock_tool.description.assert_called_once()

        assert result.name == "kiln_task_tool"
        assert result.description == "A Kiln task tool description"
        assert result.inputSchema == {
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Input parameter"},
            },
            "required": ["input"],
        }

    @pytest.mark.asyncio
    async def test_tool_from_kiln_task_tool_with_minimal_fields(self):
        """Test creating ExternalToolApiDescription from KilnTaskTool with minimal fields."""
        # Create a mock KilnTaskTool with minimal fields
        mock_tool = AsyncMock()
        mock_tool.name.return_value = "minimal_kiln_tool"
        mock_tool.description.return_value = ""
        mock_tool.parameters_schema = None

        result = await ExternalToolApiDescription.tool_from_kiln_task_tool(mock_tool)

        assert result.name == "minimal_kiln_tool"
        assert result.description == ""
        assert result.inputSchema == {}


@pytest.mark.asyncio
async def test_get_kiln_task_tools_success(client, test_project):
    """Test get_kiln_task_tools successfully retrieves kiln task tools"""

    with (
        patch(
            "app.desktop.studio_server.tool_api.project_from_id"
        ) as mock_project_from_id,
        patch("app.desktop.studio_server.tool_api.task_from_id") as mock_task_from_id,
    ):
        mock_project_from_id.return_value = test_project

        # Create test tasks
        task1 = Task(
            name="Test Task 1",
            description="First test task",
            instruction="Complete the first test task",
            parent=test_project,
        )
        task1.save_to_file()

        task2 = Task(
            name="Test Task 2",
            description="Second test task",
            instruction="Complete the second test task",
            parent=test_project,
        )
        task2.save_to_file()

        # Set up task_from_id mock to return the appropriate tasks
        def mock_task_from_id_func(project_id, task_id):
            if task_id == str(task1.id):
                return task1
            elif task_id == str(task2.id):
                return task2
            else:
                raise HTTPException(status_code=404, detail="Task not found")

        mock_task_from_id.side_effect = mock_task_from_id_func

        # Create kiln task tool servers
        kiln_task_server_1 = ExternalToolServer(
            name="kiln_task_server_1",
            type=ToolServerType.kiln_task,
            description="First kiln task server",
            properties={
                "name": "test_task_tool_1",
                "description": "First test task tool",
                "task_id": str(task1.id),
                "run_config_id": "run_config_1",
                "is_archived": False,
            },
            parent=test_project,
        )
        kiln_task_server_1.save_to_file()

        kiln_task_server_2 = ExternalToolServer(
            name="kiln_task_server_2",
            type=ToolServerType.kiln_task,
            description="Second kiln task server",
            properties={
                "name": "test_task_tool_2",
                "description": "Second test task tool",
                "task_id": str(task2.id),
                "run_config_id": "run_config_2",
                "is_archived": True,
            },
            parent=test_project,
        )
        kiln_task_server_2.save_to_file()

        # Create a non-kiln task server to ensure it's filtered out
        mcp_server = ExternalToolServer(
            name="mcp_server",
            type=ToolServerType.remote_mcp,
            description="MCP server",
            properties={
                "server_url": "https://example.com/mcp",
            },
            parent=test_project,
        )
        mcp_server.save_to_file()

        # Make the API call
        response = client.get(f"/api/projects/{test_project.id}/kiln_task_tools")

        assert response.status_code == 200
        results = response.json()

        # Should return 2 kiln task tools
        assert len(results) == 2

        # Find tools by their names since order may vary
        tool1_result = next(t for t in results if t["tool_name"] == "test_task_tool_1")
        tool2_result = next(t for t in results if t["tool_name"] == "test_task_tool_2")

        # Verify first tool
        assert tool1_result["tool_server_id"] == str(kiln_task_server_1.id)
        assert tool1_result["tool_name"] == "test_task_tool_1"
        assert tool1_result["tool_description"] == "First test task tool"
        assert tool1_result["task_id"] == str(task1.id)
        assert tool1_result["task_name"] == "Test Task 1"
        assert tool1_result["task_description"] == "First test task"
        assert tool1_result["is_archived"] is False
        assert "created_at" in tool1_result

        # Verify second tool
        assert tool2_result["tool_server_id"] == str(kiln_task_server_2.id)
        assert tool2_result["tool_name"] == "test_task_tool_2"
        assert tool2_result["tool_description"] == "Second test task tool"
        assert tool2_result["task_id"] == str(task2.id)
        assert tool2_result["task_name"] == "Test Task 2"
        assert tool2_result["task_description"] == "Second test task"
        assert tool2_result["is_archived"] is True
        assert "created_at" in tool2_result


@pytest.mark.asyncio
async def test_get_kiln_task_tools_no_tools(client, test_project):
    """Test get_kiln_task_tools returns empty list when no kiln task tools exist"""
    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        # Create a non-kiln task server
        mcp_server = ExternalToolServer(
            name="mcp_server",
            type=ToolServerType.remote_mcp,
            description="MCP server",
            properties={
                "server_url": "https://example.com/mcp",
            },
            parent=test_project,
        )
        mcp_server.save_to_file()

        # Make the API call
        response = client.get(f"/api/projects/{test_project.id}/kiln_task_tools")

        assert response.status_code == 200
        results = response.json()
        assert len(results) == 0


@pytest.mark.asyncio
async def test_get_kiln_task_tools_invalid_task_reference(client, test_project):
    """Test get_kiln_task_tools handles invalid task references gracefully"""

    with (
        patch(
            "app.desktop.studio_server.tool_api.project_from_id"
        ) as mock_project_from_id,
        patch("app.desktop.studio_server.tool_api.task_from_id") as mock_task_from_id,
    ):
        mock_project_from_id.return_value = test_project

        # Create a valid task first
        valid_task = Task(
            name="Valid Task",
            description="Valid test task",
            instruction="Complete the valid test task",
            parent=test_project,
        )
        valid_task.save_to_file()

        # Set up task_from_id mock to raise HTTPException for invalid task_id
        def mock_task_from_id_func(project_id, task_id):
            if task_id == "non_existent_task_id":
                raise HTTPException(status_code=404, detail="Task not found")
            elif task_id == str(valid_task.id):
                return valid_task
            else:
                # This shouldn't be called in this test
                raise HTTPException(status_code=404, detail="Unexpected task_id")

        mock_task_from_id.side_effect = mock_task_from_id_func

        # Create kiln task server with invalid task_id
        kiln_task_server = ExternalToolServer(
            name="kiln_task_server_invalid",
            type=ToolServerType.kiln_task,
            description="Kiln task server with invalid task",
            properties={
                "name": "invalid_task_tool",
                "description": "Tool with invalid task reference",
                "task_id": "non_existent_task_id",
                "run_config_id": "run_config_invalid",
                "is_archived": False,
            },
            parent=test_project,
        )
        kiln_task_server.save_to_file()

        # Create a valid kiln task server
        valid_kiln_task_server = ExternalToolServer(
            name="kiln_task_server_valid",
            type=ToolServerType.kiln_task,
            description="Valid kiln task server",
            properties={
                "name": "valid_task_tool",
                "description": "Tool with valid task reference",
                "task_id": str(valid_task.id),
                "run_config_id": "run_config_valid",
                "is_archived": False,
            },
            parent=test_project,
        )
        valid_kiln_task_server.save_to_file()

        # Make the API call
        response = client.get(f"/api/projects/{test_project.id}/kiln_task_tools")

        assert response.status_code == 200
        results = response.json()

        # Should only return the valid tool, invalid one should be skipped
        assert len(results) == 1
        assert results[0]["tool_server_id"] == str(valid_kiln_task_server.id)
        assert results[0]["tool_name"] == "valid_task_tool"


@pytest.mark.asyncio
async def test_get_kiln_task_tools_empty_task_id(client, test_project):
    """Test get_kiln_task_tools handles empty task_id in properties"""
    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        # Create kiln task server with empty task_id (this will pass validation but be skipped by endpoint)
        kiln_task_server = ExternalToolServer(
            name="kiln_task_server_empty_task_id",
            type=ToolServerType.kiln_task,
            description="Kiln task server with empty task_id",
            properties={
                "name": "empty_task_id_tool",
                "description": "Tool with empty task_id",
                "task_id": "",  # Empty string
                "run_config_id": "run_config_empty_task",
                "is_archived": False,
            },
            parent=test_project,
        )
        kiln_task_server.save_to_file()

        # Make the API call
        response = client.get(f"/api/projects/{test_project.id}/kiln_task_tools")

        assert response.status_code == 200
        results = response.json()

        # Should return empty list since empty task_id is falsy
        assert len(results) == 0


@pytest.mark.asyncio
async def test_add_kiln_task_tool_validation_success(client, test_project):
    """Test add_kiln_task_tool succeeds with valid task and run config (validates _validate_kiln_task_tool_task_and_run_config)"""

    # Create a test task
    task = Task(
        name="Test Task",
        description="Test task for validation",
        instruction="Complete the test task",
        parent=test_project,
    )
    task.save_to_file()

    # Create a run config with ID "default" for the task
    from kiln_ai.datamodel.datamodel_enums import StructuredOutputMode
    from kiln_ai.datamodel.prompt_id import PromptGenerators
    from kiln_ai.datamodel.run_config import RunConfigProperties
    from kiln_ai.datamodel.task import TaskRunConfig

    run_config = TaskRunConfig(
        name="default",
        run_config_properties=RunConfigProperties(
            model_name="gpt-4",
            model_provider_name="openai",
            prompt_id=PromptGenerators.SIMPLE,
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
        parent=task,
    )
    run_config.save_to_file()

    # Create tool data with valid task and run config
    tool_data = {
        "name": "test_tool",
        "description": "Test tool",
        "task_id": str(task.id),
        "run_config_id": str(run_config.id),
        "is_archived": False,
    }

    with (
        patch(
            "app.desktop.studio_server.tool_api.project_from_id"
        ) as mock_project_from_id,
        patch("app.desktop.studio_server.tool_api.task_from_id") as mock_task_from_id,
    ):
        mock_project_from_id.return_value = test_project
        mock_task_from_id.return_value = task

        # Should succeed without raising any exception
        response = client.post(
            f"/api/projects/{test_project.id}/kiln_task_tool", json=tool_data
        )

        assert response.status_code == 200
        result = response.json()
        assert result["name"] == "test_tool"
        assert result["type"] == "kiln_task"

        # Verify task_from_id was called with correct parameters (validates the validation function)
        mock_task_from_id.assert_called_once_with(str(test_project.id), str(task.id))


@pytest.mark.asyncio
async def test_add_kiln_task_tool_validation_task_not_found(client, test_project):
    """Test add_kiln_task_tool raises exception when task is not found (validates _validate_kiln_task_tool_task_and_run_config)"""

    # Create tool data with non-existent task
    tool_data = {
        "name": "test_tool",
        "description": "Test tool",
        "task_id": "non_existent_task_id",
        "run_config_id": "default",
        "is_archived": False,
    }

    with patch("app.desktop.studio_server.tool_api.task_from_id") as mock_task_from_id:
        # Mock task_from_id to raise HTTPException
        mock_task_from_id.side_effect = HTTPException(
            status_code=404, detail="Task not found"
        )

        # Should raise HTTPException
        response = client.post(
            f"/api/projects/{test_project.id}/kiln_task_tool", json=tool_data
        )

        assert response.status_code == 404
        assert "Task not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_add_kiln_task_tool_validation_run_config_not_found(client, test_project):
    """Test add_kiln_task_tool raises exception when run config is not found (validates _validate_kiln_task_tool_task_and_run_config)"""

    # Create a test task
    task = Task(
        name="Test Task",
        description="Test task for validation",
        instruction="Complete the test task",
        parent=test_project,
    )
    task.save_to_file()

    # Create a run config with ID "default" for the task
    from kiln_ai.datamodel.datamodel_enums import StructuredOutputMode
    from kiln_ai.datamodel.prompt_id import PromptGenerators
    from kiln_ai.datamodel.run_config import RunConfigProperties
    from kiln_ai.datamodel.task import TaskRunConfig

    run_config = TaskRunConfig(
        name="default",
        run_config_properties=RunConfigProperties(
            model_name="gpt-4",
            model_provider_name="openai",
            prompt_id=PromptGenerators.SIMPLE,
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
        parent=task,
    )
    run_config.save_to_file()

    # Create tool data with non-existent run config
    tool_data = {
        "name": "test_tool",
        "description": "Test tool",
        "task_id": str(task.id),
        "run_config_id": "non_existent_run_config",
        "is_archived": False,
    }

    with patch("app.desktop.studio_server.tool_api.task_from_id") as mock_task_from_id:
        # Mock task_from_id to return our test task
        mock_task_from_id.return_value = task

        # Should raise HTTPException for run config not found
        response = client.post(
            f"/api/projects/{test_project.id}/kiln_task_tool", json=tool_data
        )

        assert response.status_code == 400
        assert (
            "Run config not found for the specified task" in response.json()["detail"]
        )


@pytest.mark.asyncio
async def test_edit_kiln_task_tool_validation_success(client, test_project):
    """Test edit_kiln_task_tool succeeds with valid task and run config (validates _validate_kiln_task_tool_task_and_run_config)"""

    # Create a test task
    task = Task(
        name="Test Task",
        description="Test task for validation",
        instruction="Complete the test task",
        parent=test_project,
    )
    task.save_to_file()

    # Create a run config with ID "default" for the task
    from kiln_ai.datamodel.datamodel_enums import StructuredOutputMode
    from kiln_ai.datamodel.prompt_id import PromptGenerators
    from kiln_ai.datamodel.run_config import RunConfigProperties
    from kiln_ai.datamodel.task import TaskRunConfig

    run_config = TaskRunConfig(
        name="default",
        run_config_properties=RunConfigProperties(
            model_name="gpt-4",
            model_provider_name="openai",
            prompt_id=PromptGenerators.SIMPLE,
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
        parent=task,
    )
    run_config.save_to_file()

    # Create an existing kiln task tool server
    existing_tool_server = ExternalToolServer(
        name="existing_tool",
        type=ToolServerType.kiln_task,
        description="Existing tool",
        properties={
            "name": "existing_tool",
            "description": "Existing tool",
            "task_id": str(task.id),
            "run_config_id": str(run_config.id),
            "is_archived": False,
        },
        parent=test_project,
    )
    existing_tool_server.save_to_file()

    # Create updated tool data with valid task and run config
    tool_data = {
        "name": "updated_tool",
        "description": "Updated tool",
        "task_id": str(task.id),
        "run_config_id": str(run_config.id),
        "is_archived": False,
    }

    with (
        patch(
            "app.desktop.studio_server.tool_api.project_from_id"
        ) as mock_project_from_id,
        patch("app.desktop.studio_server.tool_api.task_from_id") as mock_task_from_id,
    ):
        mock_project_from_id.return_value = test_project
        mock_task_from_id.return_value = task

        # Should succeed without raising any exception
        response = client.patch(
            f"/api/projects/{test_project.id}/edit_kiln_task_tool/{existing_tool_server.id}",
            json=tool_data,
        )

        assert response.status_code == 200
        result = response.json()
        assert result["name"] == "updated_tool"
        assert result["type"] == "kiln_task"

        # Verify task_from_id was called with correct parameters (validates the validation function)
        mock_task_from_id.assert_called_once_with(str(test_project.id), str(task.id))


@pytest.mark.asyncio
async def test_edit_kiln_task_tool_validation_task_not_found(client, test_project):
    """Test edit_kiln_task_tool raises exception when task is not found (validates _validate_kiln_task_tool_task_and_run_config)"""

    # Create an existing kiln task tool server
    existing_tool_server = ExternalToolServer(
        name="existing_tool",
        type=ToolServerType.kiln_task,
        description="Existing tool",
        properties={
            "name": "existing_tool",
            "description": "Existing tool",
            "task_id": "old_task_id",
            "run_config_id": "default",
            "is_archived": False,
        },
        parent=test_project,
    )
    existing_tool_server.save_to_file()

    # Create tool data with non-existent task
    tool_data = {
        "name": "updated_tool",
        "description": "Updated tool",
        "task_id": "non_existent_task_id",
        "run_config_id": "default",
        "is_archived": False,
    }

    with patch("app.desktop.studio_server.tool_api.task_from_id") as mock_task_from_id:
        # Mock task_from_id to raise HTTPException
        mock_task_from_id.side_effect = HTTPException(
            status_code=404, detail="Task not found"
        )

        # Should raise HTTPException
        response = client.patch(
            f"/api/projects/{test_project.id}/edit_kiln_task_tool/{existing_tool_server.id}",
            json=tool_data,
        )

        assert response.status_code == 404
        assert "Task not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_edit_kiln_task_tool_validation_run_config_not_found(
    client, test_project
):
    """Test edit_kiln_task_tool raises exception when run config is not found (validates _validate_kiln_task_tool_task_and_run_config)"""

    # Create a test task
    task = Task(
        name="Test Task",
        description="Test task for validation",
        instruction="Complete the test task",
        parent=test_project,
    )
    task.save_to_file()

    # Create a run config with ID "default" for the task
    from kiln_ai.datamodel.datamodel_enums import StructuredOutputMode
    from kiln_ai.datamodel.prompt_id import PromptGenerators
    from kiln_ai.datamodel.run_config import RunConfigProperties
    from kiln_ai.datamodel.task import TaskRunConfig

    run_config = TaskRunConfig(
        name="default",
        run_config_properties=RunConfigProperties(
            model_name="gpt-4",
            model_provider_name="openai",
            prompt_id=PromptGenerators.SIMPLE,
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
        parent=task,
    )
    run_config.save_to_file()

    # Create an existing kiln task tool server
    existing_tool_server = ExternalToolServer(
        name="existing_tool",
        type=ToolServerType.kiln_task,
        description="Existing tool",
        properties={
            "name": "existing_tool",
            "description": "Existing tool",
            "task_id": str(task.id),
            "run_config_id": str(run_config.id),
            "is_archived": False,
        },
        parent=test_project,
    )
    existing_tool_server.save_to_file()

    # Create tool data with non-existent run config
    tool_data = {
        "name": "updated_tool",
        "description": "Updated tool",
        "task_id": str(task.id),
        "run_config_id": "non_existent_run_config",
        "is_archived": False,
    }

    with patch("app.desktop.studio_server.tool_api.task_from_id") as mock_task_from_id:
        # Mock task_from_id to return our test task
        mock_task_from_id.return_value = task

        # Should raise HTTPException for run config not found
        response = client.patch(
            f"/api/projects/{test_project.id}/edit_kiln_task_tool/{existing_tool_server.id}",
            json=tool_data,
        )

        assert response.status_code == 400
        assert (
            "Run config not found for the specified task" in response.json()["detail"]
        )
