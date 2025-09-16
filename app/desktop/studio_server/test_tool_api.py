from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from kiln_ai.datamodel.external_tool_server import ExternalToolServer, ToolServerType
from kiln_ai.datamodel.project import Project
from kiln_ai.utils.config import MCP_SECRETS_KEY
from kiln_ai.utils.dataset_import import format_validation_error
from mcp.types import ListToolsResult, Tool
from pydantic import ValidationError

from app.desktop.studio_server.tool_api import (
    ExternalToolServerCreationRequest,
    LocalToolServerCreationRequest,
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
    async def mock_mcp_client(tool_server):
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


async def test_get_available_tool_servers_with_missing_secrets(client, test_project):
    """Test that get_available_tool_servers includes missing_secrets field"""
    tool_data = {
        "name": "tool_with_missing_secrets",
        "server_url": "https://api.example.com",
        "headers": {"Authorization": "Bearer token", "X-API-Key": "secret"},
        "secret_header_keys": ["Authorization", "X-API-Key"],
        "description": "Tool with missing secrets",
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
        # Should return empty list when no tool servers and no demo tools
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
    """Test get_available_tools with multiple tool servers"""
    # Create first tool server
    tool_data_1 = {
        "name": "mcp_server_1",
        "server_url": "https://example1.com/mcp",
        "headers": {},
        "description": "First MCP server",
    }

    # Create second tool server
    tool_data_2 = {
        "name": "mcp_server_2",
        "server_url": "https://example2.com/mcp",
        "headers": {},
        "description": "Second MCP server",
    }

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
        async def mock_mcp_client(tool_server):
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
            assert len(set_result) == 2

            # Find sets by name instead of assuming order
            server1_set = next(
                (s for s in set_result if s["set_name"] == "MCP Server: mcp_server_1"),
                None,
            )
            server2_set = next(
                (s for s in set_result if s["set_name"] == "MCP Server: mcp_server_2"),
                None,
            )

            assert server1_set is not None, (
                "Could not find MCP Server: mcp_server_1 in results"
            )
            assert server2_set is not None, (
                "Could not find MCP Server: mcp_server_2 in results"
            )

            assert len(server1_set["tools"]) == 2  # 2 from server1
            assert len(server2_set["tools"]) == 1  # 1 from server2

            for tool in server1_set["tools"]:
                assert tool["id"].startswith(f"mcp::remote::{server1_id}::")
            for tool in server2_set["tools"]:
                assert tool["id"].startswith(f"mcp::remote::{server2_id}::")

            # Verify tools from both servers are present
            tool_names = [tool["name"] for tool in server1_set["tools"]]
            assert "tool_a" in tool_names
            assert "tool_b" in tool_names
            tool_names = [tool["name"] for tool in server2_set["tools"]]
            assert "tool_x" in tool_names


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

            # Should return empty list since the MCP server failed and no tools are available
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

        # Should have one tool set for demo tools (no external servers, so no RAG set)
        assert len(result) == 1

        # Find the demo tools set
        demo_set = next(
            (s for s in result if s["set_name"] == "Kiln Demo Tools"),
            None,
        )
        assert demo_set is not None
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

        # Should have empty list when demo tools are disabled and no MCP servers
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
        async def mock_mcp_client(tool_server):
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
        async def mock_mcp_client(tool_server):
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
        async def mock_mcp_client_create(tool_server):
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
        async def mock_mcp_client(tool_server):
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


def test_external_tool_server_creation_request_invalid_url_format():
    """Test ExternalToolServerCreationRequest rejects malformed URLs"""

    with pytest.raises(ValidationError) as exc_info:
        ExternalToolServerCreationRequest(
            name="invalid_url_server",
            server_url="https://",  # Invalid URL format - scheme without netloc
            headers={},
            description="Server with malformed URL",
        )

    error_str = str(exc_info.value)
    assert "Server URL is not a valid URL" in error_str


def test_external_tool_server_creation_request_invalid_header_name():
    """Test ExternalToolServerCreationRequest rejects invalid header names"""

    with pytest.raises(ValidationError) as exc_info:
        ExternalToolServerCreationRequest(
            name="invalid_header_server",
            server_url="https://example.com/mcp",
            headers={
                "invalid@header": "value",  # Invalid character in header name
            },
            description="Server with invalid header name",
        )

    error_str = str(exc_info.value)
    assert 'Invalid header name: "invalid@header"' in error_str


def test_external_tool_server_creation_request_header_with_cr_lf():
    """Test ExternalToolServerCreationRequest rejects headers with CR/LF characters"""

    with pytest.raises(ValidationError) as exc_info:
        ExternalToolServerCreationRequest(
            name="crlf_header_server",
            server_url="https://example.com/mcp",
            headers={
                "Authorization": "Bearer token\r\nX-Injected: evil",  # CR/LF injection
            },
            description="Server with CR/LF in headers",
        )

    error_str = str(exc_info.value)
    assert "Header names/values must not contain invalid characters" in error_str


def test_external_tool_server_creation_request_empty_header_name():
    """Test ExternalToolServerCreationRequest rejects empty header names"""

    with pytest.raises(ValidationError) as exc_info:
        ExternalToolServerCreationRequest(
            name="empty_header_name_server",
            server_url="https://example.com/mcp",
            headers={
                "": "some_value",  # Empty header name
            },
            description="Server with empty header name",
        )

    error_str = str(exc_info.value)
    assert "Header name is required" in error_str


def test_external_tool_server_creation_request_empty_header_value():
    """Test ExternalToolServerCreationRequest rejects empty header values"""

    with pytest.raises(ValidationError) as exc_info:
        ExternalToolServerCreationRequest(
            name="empty_header_value_server",
            server_url="https://example.com/mcp",
            headers={
                "Authorization": "",  # Empty header value
            },
            description="Server with empty header value",
        )

    error_str = str(exc_info.value)
    assert "Header value is required" in error_str


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


def test_external_tool_server_creation_request_invalid_url_simple_string():
    """Test ExternalToolServerCreationRequest rejects simple string URLs like 'asdf'"""

    with pytest.raises(ValidationError) as exc_info:
        ExternalToolServerCreationRequest(
            name="invalid_simple_url_server",
            server_url="asdf",  # Simple invalid URL like the user's case
            headers={},
            description="Server with simple invalid URL",
        )

    # Verify the error can be formatted properly and contains expected message
    formatted_error = format_validation_error(exc_info.value)
    assert "Server URL must start with http:// or https://" in formatted_error


# Comprehensive tests for ExternalToolServerCreationRequest validation
def test_external_tool_server_creation_request_valid_minimal():
    """Test ExternalToolServerCreationRequest with minimal valid data"""
    request = ExternalToolServerCreationRequest(
        name="Test Server",
        server_url="https://example.com",
    )

    assert request.name == "Test Server"
    assert request.server_url == "https://example.com"
    assert request.headers == {}
    assert request.description is None


def test_external_tool_server_creation_request_valid_complete():
    """Test ExternalToolServerCreationRequest with all valid fields"""
    headers = {"Authorization": "Bearer token123", "X-Custom": "value"}

    request = ExternalToolServerCreationRequest(
        name="Complete Server",
        server_url="https://api.example.com/mcp",
        headers=headers,
        description="A complete server configuration",
    )

    assert request.name == "Complete Server"
    assert request.server_url == "https://api.example.com/mcp"
    assert request.headers == headers
    assert request.description == "A complete server configuration"


def test_external_tool_server_creation_request_url_with_leading_whitespace_fails():
    """Test that server URLs with leading whitespace are rejected by stricter validation"""

    # Test URLs with leading whitespace (should fail)
    leading_whitespace_urls = [
        "  https://example.com/mcp",  # Leading spaces
        " https://example.com/mcp",  # Single leading space
        "\thttps://example.com/mcp",  # Leading tab
        "\nhttps://example.com/mcp",  # Leading newline
    ]

    for url in leading_whitespace_urls:
        with pytest.raises(ValidationError) as exc_info:
            ExternalToolServerCreationRequest(
                name="Leading Whitespace URL Server",
                server_url=url,
            )

        error_str = str(exc_info.value)
        assert "Server URL must not have leading whitespace" in error_str


def test_external_tool_server_creation_request_url_with_trailing_whitespace_succeeds():
    """Test that server URLs with trailing whitespace are accepted"""

    # Test URLs with trailing whitespace (should succeed)
    trailing_whitespace_urls = [
        "https://example.com/mcp ",  # Trailing space
        "https://example.com/mcp\t",  # Trailing tab
        "https://example.com/mcp  ",  # Multiple trailing spaces
    ]

    for url in trailing_whitespace_urls:
        request = ExternalToolServerCreationRequest(
            name="Trailing Whitespace URL Server",
            server_url=url,
        )
        # URL should be preserved as-is
        assert request.server_url == url


def test_external_tool_server_creation_request_header_with_whitespace_fails():
    """Test that headers with whitespace in keys are rejected"""
    with pytest.raises(ValidationError) as exc_info:
        ExternalToolServerCreationRequest(
            name="Whitespace Header Server",
            server_url="https://example.com",
            headers={
                "  Authorization  ": "Bearer token123",  # Whitespace in key should fail
                "X-Custom": "value",
            },
        )

    error_str = str(exc_info.value)
    assert 'Invalid header name: "  Authorization  "' in error_str


# RAG-specific tests
async def test_get_available_tools_with_rag_configs(client, test_project):
    """Test get_available_tools includes RAG configs when there's an external tool server"""
    from kiln_ai.datamodel.rag import RagConfig

    # Create some RAG configs
    rag_config_1 = RagConfig(
        parent=test_project,
        name="Test RAG Config 1",
        description="First test RAG configuration",
        extractor_config_id="extractor123",
        chunker_config_id="chunker456",
        embedding_config_id="embedding789",
        vector_store_config_id="vector_store123",
    )

    rag_config_2 = RagConfig(
        parent=test_project,
        name="Test RAG Config 2",
        description=None,  # Test None description
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

            assert "Test RAG Config 1" in tool_names
            assert "Test RAG Config 2" in tool_names

            # Verify tool IDs are properly formatted
            for tool in rag_set["tools"]:
                assert tool["id"].startswith("kiln_tool::rag::")

            # Find specific tools and check their descriptions
            config1_tool = next(
                t for t in rag_set["tools"] if t["name"] == "Test RAG Config 1"
            )
            assert config1_tool["description"] == "First test RAG configuration"

            config2_tool = next(
                t for t in rag_set["tools"] if t["name"] == "Test RAG Config 2"
            )
            assert config2_tool["description"] is None


async def test_get_available_tools_with_rag_and_mcp(client, test_project):
    """Test get_available_tools with both RAG configs and MCP servers"""
    from kiln_ai.datamodel.rag import RagConfig

    # Create a RAG config
    rag_config = RagConfig(
        parent=test_project,
        name="Mixed Test RAG",
        description="RAG config for mixed test",
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
            assert rag_set["tools"][0]["name"] == "Mixed Test RAG"
            assert rag_set["tools"][0]["id"].startswith("kiln_tool::rag::")


def test_external_tool_server_creation_request_http_scheme():
    """Test that HTTP scheme is also valid"""
    request = ExternalToolServerCreationRequest(
        name="HTTP Server",
        server_url="http://localhost:8080/mcp",
    )

    assert request.server_url == "http://localhost:8080/mcp"


def test_external_tool_server_creation_request_complex_valid_headers():
    """Test with complex but valid header names and values"""

    # Valid complex headers
    request = ExternalToolServerCreationRequest(
        name="Complex Headers Server",
        server_url="https://example.com",
        headers={
            "X-API-Key": "sk-1234567890abcdef",
            "Accept": "application/json",
            "User-Agent": "Kiln/1.0",
            "X-Rate-Limit": "1000",
            "Content-Type": "application/json; charset=utf-8",
        },
    )

    assert len(request.headers) == 5
    assert request.headers["X-API-Key"] == "sk-1234567890abcdef"


def test_external_tool_server_creation_request_secret_headers_valid():
    """Test ExternalToolServerCreationRequest with valid secret headers"""
    request = ExternalToolServerCreationRequest(
        name="Secret Headers Server",
        server_url="https://example.com",
        headers={
            "Authorization": "Bearer secret-token",
            "X-API-Key": "api-key-123",
            "Content-Type": "application/json",
        },
        secret_header_keys=["Authorization", "X-API-Key"],
    )

    assert request.name == "Secret Headers Server"
    assert request.server_url == "https://example.com"
    assert len(request.headers) == 3
    assert len(request.secret_header_keys) == 2
    assert "Authorization" in request.secret_header_keys
    assert "X-API-Key" in request.secret_header_keys


def test_external_tool_server_creation_request_secret_headers_empty_list():
    """Test ExternalToolServerCreationRequest with empty secret headers list"""
    request = ExternalToolServerCreationRequest(
        name="No Secret Headers Server",
        server_url="https://example.com",
        headers={"Content-Type": "application/json"},
        secret_header_keys=[],
    )

    assert request.secret_header_keys == []
    assert len(request.headers) == 1


def test_external_tool_server_creation_request_secret_headers_not_in_headers():
    """Test ExternalToolServerCreationRequest rejects secret header keys not in headers"""
    with pytest.raises(ValidationError) as exc_info:
        ExternalToolServerCreationRequest(
            name="Invalid Secret Server",
            server_url="https://example.com",
            headers={"Content-Type": "application/json"},
            secret_header_keys=["Authorization"],  # Not in headers
        )

    error_str = str(exc_info.value)
    assert "Secret header key Authorization is not in the headers" in error_str


def test_external_tool_server_creation_request_secret_headers_empty_key():
    """Test ExternalToolServerCreationRequest rejects empty secret header keys"""
    with pytest.raises(ValidationError) as exc_info:
        ExternalToolServerCreationRequest(
            name="Empty Secret Key Server",
            server_url="https://example.com",
            headers={"Authorization": "Bearer token"},
            secret_header_keys=[""],  # Empty key
        )

    error_str = str(exc_info.value)
    assert "Secret header key is required" in error_str


def test_external_tool_server_creation_request_secret_headers_with_whitespace_fails():
    """Test that secret header keys with whitespace are rejected"""
    with pytest.raises(ValidationError) as exc_info:
        ExternalToolServerCreationRequest(
            name="Whitespace Secret Headers Server",
            server_url="https://example.com",
            headers={
                "Authorization": "Bearer token",
                "X-API-Key": "key123",
            },
            secret_header_keys=[
                "  Authorization  ",
                " X-API-Key ",
            ],  # Whitespace should fail
        )

    error_str = str(exc_info.value)
    assert "Secret header key   Authorization   is not in the headers" in error_str


def test_external_tool_server_creation_request_secret_headers_multiple_validation_errors():
    """Test that multiple secret header validation errors are caught"""
    with pytest.raises(ValidationError) as exc_info:
        ExternalToolServerCreationRequest(
            name="Multiple Errors Server",
            server_url="https://example.com",
            headers={"Content-Type": "application/json"},
            secret_header_keys=["", "NonExistentHeader"],  # Empty and non-existent
        )

    error_str = str(exc_info.value)
    # Should catch the first error (empty key)
    assert "Secret header key is required" in error_str


def test_external_tool_server_creation_request_empty_url():
    """Test that empty server URL is rejected"""

    with pytest.raises(ValidationError) as exc_info:
        ExternalToolServerCreationRequest(
            name="Empty URL Server",
            server_url="",
        )

    error_str = str(exc_info.value)
    assert "Server URL is required" in error_str


def test_external_tool_server_creation_request_url_without_netloc():
    """Test various malformed URLs"""

    invalid_urls = [
        "https://",
        "http://",
        "https:///path",
        "http:///path",
    ]

    for invalid_url in invalid_urls:
        with pytest.raises(ValidationError) as exc_info:
            ExternalToolServerCreationRequest(
                name="Invalid URL Server",
                server_url=invalid_url,
            )

        error_str = str(exc_info.value)
        assert "Server URL is not a valid URL" in error_str


def test_external_tool_server_creation_request_various_schemes_accepted():
    """Test that various URL schemes are currently accepted (urlparse is lenient)"""

    # These schemes are currently accepted due to lenient urlparse validation
    invalid_schemes = [
        "ftp://example.com",
        "ssh://user@example.com",
        "tcp://example.com:1234",
        "file:///path/to/file",
        "mailto:user@example.com",
    ]

    for url in invalid_schemes:
        with pytest.raises(ValidationError) as exc_info:
            ExternalToolServerCreationRequest(
                name="Various Scheme Server",
                server_url=url,
            )
        assert "Server URL must start with http:// or https://" in str(exc_info.value)


def test_external_tool_server_creation_request_invalid_header_characters():
    """Test various invalid header name characters"""

    invalid_headers = [
        {"invalid header": "value"},  # Space in name
        {"invalid@header": "value"},  # @ symbol
        {"invalid(header)": "value"},  # Parentheses
        {"invalid[header]": "value"},  # Brackets
        {"invalid{header}": "value"},  # Braces
        {"invalid<header>": "value"},  # Angle brackets
        {"invalid/header": "value"},  # Forward slash
        {"invalid\\header": "value"},  # Backslash
        {"invalid:header": "value"},  # Colon
        {"invalid;header": "value"},  # Semicolon
        {"invalid=header": "value"},  # Equals
        {"invalid?header": "value"},  # Question mark
        {"invalid,header": "value"},  # Comma
    ]

    for headers in invalid_headers:
        with pytest.raises(ValidationError) as exc_info:
            ExternalToolServerCreationRequest(
                name="Invalid Header Server",
                server_url="https://example.com",
                headers=headers,
            )

        error_str = str(exc_info.value)
        assert "Invalid header name" in error_str


def test_external_tool_server_creation_request_header_injection():
    """Test prevention of header injection attacks"""

    # Test header value injection
    value_injection_attempts = [
        {"Authorization": "Bearer token\r\nX-Injected: evil"},
        {"Authorization": "Bearer token\nX-Injected: evil"},
    ]

    for headers in value_injection_attempts:
        with pytest.raises(ValidationError) as exc_info:
            ExternalToolServerCreationRequest(
                name="Injection Server",
                server_url="https://example.com",
                headers=headers,
            )

        error_str = str(exc_info.value)
        assert "Header names/values must not contain invalid characters" in error_str

    # Test header name injection (these will fail with invalid header name error)
    name_injection_attempts = [
        {"X-Header\r\nX-Injected": "value"},
        {"X-Header\nX-Injected": "value"},
    ]

    for headers in name_injection_attempts:
        with pytest.raises(ValidationError) as exc_info:
            ExternalToolServerCreationRequest(
                name="Injection Server",
                server_url="https://example.com",
                headers=headers,
            )

        error_str = str(exc_info.value)
        # Header names with CR/LF will be caught by the invalid header name regex
        assert (
            "Invalid header name" in error_str
            or "Header names/values must not contain invalid characters" in error_str
        )


def test_external_tool_server_creation_request_non_string_headers():
    """Test that non-string header keys and values are rejected by Pydantic"""

    # Non-string header keys should be rejected
    with pytest.raises(ValidationError) as exc_info:
        ExternalToolServerCreationRequest(
            name="Non-String Headers Server",
            server_url="https://example.com",
            headers={
                123: "value",  # Non-string key  # type: ignore
            },
        )

    error_str = str(exc_info.value)
    assert "Input should be a valid string" in error_str

    # Non-string header values should be rejected
    with pytest.raises(ValidationError) as exc_info:
        ExternalToolServerCreationRequest(
            name="Non-String Headers Server",
            server_url="https://example.com",
            headers={
                "key": 456,  # Non-string value  # type: ignore
            },
        )

    error_str = str(exc_info.value)
    assert "Input should be a valid string" in error_str


def test_external_tool_server_creation_request_whitespace_only_headers():
    """Test validation behavior for whitespace-only header names and values"""

    # Whitespace-only header names should be rejected (invalid header name format)
    whitespace_name_cases = [
        {"   ": "value"},  # Whitespace-only name
        {"\t\n": "value"},  # Tab/newline only name
    ]

    for headers in whitespace_name_cases:
        with pytest.raises(ValidationError) as exc_info:
            ExternalToolServerCreationRequest(
                name="Whitespace Header Name Server",
                server_url="https://example.com",
                headers=headers,
            )

        error_str = str(exc_info.value)
        assert "Invalid header name" in error_str

    # Whitespace-only header values are currently accepted (except CR/LF)
    whitespace_value_cases = [
        {"name": "   "},  # Whitespace-only value (spaces)
        {"name": "\t"},  # Tab only (no newlines)
    ]

    for headers in whitespace_value_cases:
        request = ExternalToolServerCreationRequest(
            name="Whitespace Header Value Server",
            server_url="https://example.com",
            headers=headers,
        )
        # Values are preserved as-is
        assert next(iter(headers.values())) in request.headers.values()

    # Header values with CR/LF are rejected
    invalid_value_cases = [
        {"name": "\t\n"},  # Tab/newline (contains \n)
        {"name": "\r"},  # Carriage return
    ]

    for headers in invalid_value_cases:
        with pytest.raises(ValidationError) as exc_info:
            ExternalToolServerCreationRequest(
                name="Invalid Header Value Server",
                server_url="https://example.com",
                headers=headers,
            )

        error_str = str(exc_info.value)
        assert "Header names/values must not contain invalid characters" in error_str


def test_external_tool_server_creation_request_model_validator_integration():
    """Test that the model validator works correctly with combined URL and header validation"""

    # Test successful validation with clean inputs (no whitespace)
    request = ExternalToolServerCreationRequest(
        name="Integration Test Server",
        server_url="https://api.example.com/mcp",  # Clean URL without whitespace
        headers={
            "Authorization": "Bearer token123",  # Clean headers without whitespace
            "X-Custom-Header": "custom-value",
        },
        description="Integration test for model validator",
    )

    # Verify values are preserved as-is
    assert request.server_url == "https://api.example.com/mcp"
    assert request.headers["Authorization"] == "Bearer token123"
    assert request.headers["X-Custom-Header"] == "custom-value"

    # Test that both URL and header validation work together
    with pytest.raises(ValidationError) as exc_info:
        ExternalToolServerCreationRequest(
            name="Bad Integration Server",
            server_url="ftp://invalid.com",  # Invalid scheme
            headers={
                "invalid@header": "value",  # Invalid header name
            },
        )

    error_str = str(exc_info.value)
    # Should catch validation errors (header validation happens first in this case)
    assert (
        "Invalid header name" in error_str
        or "Server URL must start with http:// or https://" in error_str
    )


# Tests for LocalToolServerCreationRequest validation
def test_local_tool_server_creation_request_valid_minimal():
    """Test LocalToolServerCreationRequest with minimal valid data"""
    request = LocalToolServerCreationRequest(
        name="Test Local Server",
        command="python",
        args=["-m", "test_server"],
    )

    assert request.name == "Test Local Server"
    assert request.command == "python"
    assert request.args == ["-m", "test_server"]
    assert request.env_vars == {}
    assert request.description is None


def test_local_tool_server_creation_request_valid_complete():
    """Test LocalToolServerCreationRequest with all valid fields"""
    env_vars = {"PATH": "/usr/bin", "ENV_VAR": "value"}

    request = LocalToolServerCreationRequest(
        name="Complete Local Server",
        command="/usr/bin/python3",
        args=["-m", "my_mcp_server", "--config", "config.json"],
        env_vars=env_vars,
        description="A complete local server configuration",
    )

    assert request.name == "Complete Local Server"
    assert request.command == "/usr/bin/python3"
    assert request.args == ["-m", "my_mcp_server", "--config", "config.json"]
    assert request.env_vars == env_vars
    assert request.description == "A complete local server configuration"


def test_local_tool_server_creation_request_empty_command():
    """Test LocalToolServerCreationRequest rejects empty command"""

    with pytest.raises(ValidationError) as exc_info:
        LocalToolServerCreationRequest(
            name="Empty Command Server",
            command="",  # Empty command should fail validation
            args=["arg1"],
        )

    error_str = str(exc_info.value)
    assert "Command is required" in error_str


def test_local_tool_server_creation_request_missing_command():
    """Test LocalToolServerCreationRequest rejects missing command"""

    with pytest.raises(ValidationError) as exc_info:
        LocalToolServerCreationRequest(  # type: ignore
            name="Missing Command Server",
            args=["arg1"],
            # Missing required command field
        )

    assert exc_info.value.error_count() > 0


def test_local_tool_server_creation_request_empty_args():
    """Test LocalToolServerCreationRequest accepts empty args list"""

    request = LocalToolServerCreationRequest(
        name="Empty Args Server",
        command="python",
        args=[],  # Empty args should now be allowed
    )

    assert request.name == "Empty Args Server"
    assert request.command == "python"
    assert request.args == []


def test_local_tool_server_creation_request_missing_args():
    """Test LocalToolServerCreationRequest rejects missing args"""

    with pytest.raises(ValidationError) as exc_info:
        LocalToolServerCreationRequest(  # type: ignore
            name="Missing Args Server",
            command="python",
            # Missing required args field
        )

    assert exc_info.value.error_count() > 0


def test_local_tool_server_creation_request_empty_name():
    """Test LocalToolServerCreationRequest accepts empty name (no validation on request)"""
    # Note: The API request classes don't validate names - validation happens on the domain objects
    request = LocalToolServerCreationRequest(
        name="",  # Empty name is allowed in request object
        command="python",
        args=["-m", "server"],
    )

    assert request.name == ""
    assert request.command == "python"
    assert request.args == ["-m", "server"]


def test_local_tool_server_creation_request_missing_name():
    """Test LocalToolServerCreationRequest rejects missing name"""

    with pytest.raises(ValidationError) as exc_info:
        LocalToolServerCreationRequest(  # type: ignore
            command="python",
            args=["-m", "server"],
            # Missing required name field
        )

    assert exc_info.value.error_count() > 0


def test_local_tool_server_creation_request_no_description():
    """Test LocalToolServerCreationRequest works without description (optional field)"""
    request = LocalToolServerCreationRequest(
        name="No Description Server",
        command="python",
        args=["-m", "server"],
        # description is optional
    )

    assert request.description is None


def test_local_tool_server_creation_request_empty_env_vars():
    """Test LocalToolServerCreationRequest works with empty env_vars (default)"""
    request = LocalToolServerCreationRequest(
        name="Default Env Server",
        command="python",
        args=["-m", "server"],
        # env_vars defaults to empty dict
    )

    assert request.env_vars == {}


def test_local_tool_server_creation_request_with_env_vars():
    """Test LocalToolServerCreationRequest with custom environment variables"""
    env_vars = {
        "PYTHON_PATH": "/opt/python/bin",
        "CONFIG_FILE": "/etc/config.json",
        "DEBUG": "true",
        "PORT": "8080",
    }

    request = LocalToolServerCreationRequest(
        name="Env Vars Server",
        command="python",
        args=["-m", "server"],
        env_vars=env_vars,
    )

    assert request.env_vars == env_vars


def test_local_tool_server_creation_request_various_commands():
    """Test LocalToolServerCreationRequest with various command formats"""
    test_cases = [
        ("python", ["-m", "server"]),
        ("/usr/bin/python3", ["script.py", "--verbose"]),
        ("node", ["index.js", "--port", "3000"]),
        ("./local_server", ["--config", "conf.yaml"]),
        ("/path/to/executable", ["--flag1", "--flag2", "value"]),
    ]

    for command, args in test_cases:
        request = LocalToolServerCreationRequest(
            name=f"Server for {command}",
            command=command,
            args=args,
        )

        assert request.command == command
        assert request.args == args


def test_local_tool_server_creation_request_unicode_name():
    """Test LocalToolServerCreationRequest with Unicode characters in name"""
    request = LocalToolServerCreationRequest(
        name="本地服务器",  # Chinese characters
        command="python",
        args=["-m", "server"],
        description="Local server with émojis 🚀 and spéciàl characters",
    )

    assert request.name == "本地服务器"
    assert request.description is not None and "émojis 🚀" in request.description


def test_local_tool_server_creation_request_valid_env_var_keys():
    """Test LocalToolServerCreationRequest with valid environment variable keys"""
    valid_env_vars = {
        "PATH": "/usr/bin",
        "HOME": "/home/user",
        "PYTHON_PATH": "/opt/python",
        "_PRIVATE_VAR": "private",
        "VAR_123": "value123",
        "a": "single_letter",
        "A": "single_uppercase",
        "_": "single_underscore",
        "VAR_WITH_UNDERSCORES": "value",
        "CamelCase": "mixed_case",
        "UPPER_CASE": "upper",
        "lower_case": "lower",
        "Mixed_Case_123": "mixed",
    }

    request = LocalToolServerCreationRequest(
        name="Valid Env Vars Server",
        command="python",
        args=["-m", "server"],
        env_vars=valid_env_vars,
    )

    assert request.env_vars == valid_env_vars


def test_local_tool_server_creation_request_invalid_env_var_key_start_digit():
    """Test LocalToolServerCreationRequest rejects env var keys starting with digits"""
    with pytest.raises(ValidationError) as exc_info:
        LocalToolServerCreationRequest(
            name="Invalid Env Key Server",
            command="python",
            args=["-m", "server"],
            env_vars={"123_INVALID": "value"},  # Starts with digit
        )

    error_str = str(exc_info.value)
    assert "Invalid environment variable key: 123_INVALID" in error_str
    assert "Must start with a letter or underscore" in error_str


def test_local_tool_server_creation_request_invalid_env_var_key_special_chars():
    """Test LocalToolServerCreationRequest rejects env var keys with invalid characters"""
    invalid_keys = [
        ("KEY-WITH-DASHES", "dash"),
        ("KEY.WITH.DOTS", "dot"),
        ("KEY WITH SPACES", "space"),
        ("KEY@SYMBOL", "at symbol"),
        ("KEY#HASH", "hash"),
        ("KEY$DOLLAR", "dollar sign"),
        ("KEY%PERCENT", "percent"),
        ("KEY&AMPERSAND", "ampersand"),
        ("KEY*ASTERISK", "asterisk"),
        ("KEY+PLUS", "plus"),
        ("KEY=EQUALS", "equals"),
        ("KEY[BRACKET]", "bracket"),
        ("KEY{BRACE}", "brace"),
        ("KEY(PAREN)", "parenthesis"),
        ("KEY|PIPE", "pipe"),
        ("KEY\\BACKSLASH", "backslash"),
        ("KEY/SLASH", "slash"),
        ("KEY:COLON", "colon"),
        ("KEY;SEMICOLON", "semicolon"),
        ("KEY<LESS>", "angle bracket"),
        ("KEY?QUESTION", "question mark"),
        ("KEY,COMMA", "comma"),
    ]

    for invalid_key, description in invalid_keys:
        with pytest.raises(ValidationError) as exc_info:
            LocalToolServerCreationRequest(
                name="Invalid Env Key Server",
                command="python",
                args=["-m", "server"],
                env_vars={invalid_key: "value"},
            )

        error_str = str(exc_info.value)
        assert f"Invalid environment variable key: {invalid_key}" in error_str
        assert "Can only contain letters, digits, and underscores" in error_str


def test_local_tool_server_creation_request_invalid_env_var_key_non_ascii():
    """Test LocalToolServerCreationRequest rejects env var keys with non-ASCII characters"""
    invalid_keys = [
        "KEY_WITH_ÉMOJI_🚀",
        "键名",  # Chinese characters
        "CLAVÉ",  # Accented characters
        "КЛЮЧ",  # Cyrillic characters
        "مفتاح",  # Arabic characters
    ]

    for invalid_key in invalid_keys:
        with pytest.raises(ValidationError) as exc_info:
            LocalToolServerCreationRequest(
                name="Invalid Env Key Server",
                command="python",
                args=["-m", "server"],
                env_vars={invalid_key: "value"},
            )

        error_str = str(exc_info.value)
        assert f"Invalid environment variable key: {invalid_key}" in error_str
        # Should match either error message depending on the character
        assert (
            "Must start with a letter or underscore" in error_str
            or "Can only contain letters, digits, and underscores" in error_str
        )


def test_local_tool_server_creation_request_empty_env_var_key():
    """Test LocalToolServerCreationRequest rejects empty environment variable keys"""
    with pytest.raises(ValidationError) as exc_info:
        LocalToolServerCreationRequest(
            name="Empty Env Key Server",
            command="python",
            args=["-m", "server"],
            env_vars={"": "value"},  # Empty key
        )

    error_str = str(exc_info.value)
    assert "Invalid environment variable key:" in error_str
    assert "Must start with a letter or underscore" in error_str


def test_local_tool_server_creation_request_env_var_key_edge_cases():
    """Test LocalToolServerCreationRequest with edge cases for environment variable keys"""
    # Test single character valid keys
    valid_single_chars = {
        "A": "uppercase_letter",
        "a": "lowercase_letter",
        "Z": "last_uppercase",
        "z": "last_lowercase",
        "_": "underscore_only",
    }

    request = LocalToolServerCreationRequest(
        name="Edge Case Env Server",
        command="python",
        args=["-m", "server"],
        env_vars=valid_single_chars,
    )
    assert request.env_vars == valid_single_chars

    # Test invalid single character keys
    invalid_single_chars = ["0", "9", "@", "#", "-", ".", " "]

    for invalid_char in invalid_single_chars:
        with pytest.raises(ValidationError) as exc_info:
            LocalToolServerCreationRequest(
                name="Invalid Single Char Env Server",
                command="python",
                args=["-m", "server"],
                env_vars={invalid_char: "value"},
            )

        error_str = str(exc_info.value)
        assert f"Invalid environment variable key: {invalid_char}" in error_str


def test_local_tool_server_creation_request_mixed_valid_invalid_env_vars():
    """Test LocalToolServerCreationRequest with mix of valid and invalid env var keys"""
    # Should fail on the first invalid key encountered
    with pytest.raises(ValidationError) as exc_info:
        LocalToolServerCreationRequest(
            name="Mixed Env Vars Server",
            command="python",
            args=["-m", "server"],
            env_vars={
                "VALID_KEY": "valid_value",
                "123_INVALID": "invalid_value",  # This should cause failure
                "ANOTHER_VALID": "another_valid",
            },
        )

    error_str = str(exc_info.value)
    assert "Invalid environment variable key: 123_INVALID" in error_str


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


def test_create_local_tool_server_empty_command(client, test_project):
    """Test local tool server creation fails when command is empty"""
    tool_data = {
        "name": "empty_command_tool",
        "command": "",  # Empty command
        "args": ["-m", "server"],
        "description": "Tool with empty command",
    }

    with patch(
        "app.desktop.studio_server.tool_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        response = client.post(
            f"/api/projects/{test_project.id}/connect_local_mcp",
            json=tool_data,
        )

        assert response.status_code == 422  # Validation error from Pydantic
        error_data = response.json()
        # The validation error should mention command
        assert "command" in str(error_data).lower()


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


async def test_connect_remote_mcp_secret_header_validation_error(client, test_project):
    """Test connect_remote_mcp endpoint handles secret header validation errors"""
    tool_data = {
        "name": "invalid_secret_tool",
        "server_url": "https://example.com/api",
        "headers": {
            "Content-Type": "application/json",
        },
        "secret_header_keys": ["Authorization"],  # Not in headers
        "description": "Tool with invalid secret header keys",
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
        error_detail = response.json()["detail"]
        assert any(
            "Secret header key Authorization is not in the headers" in str(error)
            for error in error_detail
        )


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


async def test_connect_local_mcp_secret_env_var_validation_error(client, test_project):
    """Test connect_local_mcp endpoint handles secret env var validation errors"""
    tool_data = {
        "name": "invalid_secret_env_tool",
        "command": "python",
        "args": ["-m", "my_server"],
        "env_vars": {
            "PUBLIC_VAR": "public_value",
        },
        "secret_env_var_keys": ["SECRET_API_KEY"],  # Not in env_vars
        "description": "Tool with invalid secret env var keys",
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
        error_detail = response.json()["detail"]
        assert any(
            "Secret environment variable key SECRET_API_KEY is not in the list of environment variables"
            in str(error)
            for error in error_detail
        )


async def test_connect_local_mcp_empty_secret_env_var_key_validation_error(
    client, test_project
):
    """Test connect_local_mcp endpoint handles empty secret env var key validation errors"""
    tool_data = {
        "name": "empty_secret_key_tool",
        "command": "python",
        "args": ["-m", "my_server"],
        "env_vars": {
            "PUBLIC_VAR": "public_value",
        },
        "secret_env_var_keys": [
            ""
        ],  # Empty key (not in env_vars, but will trigger empty key validation first)
        "description": "Tool with empty secret env var key",
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
        error_detail = response.json()["detail"]
        assert any(
            "Secret environment variable key is required" in str(error)
            for error in error_detail
        )


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


# Tests for LocalToolServerCreationRequest secret environment variable validation
def test_local_tool_server_creation_request_valid_secret_env_var_keys():
    """Test LocalToolServerCreationRequest with valid secret environment variable keys"""
    request = LocalToolServerCreationRequest(
        name="Secret Env Vars Server",
        command="python",
        args=["-m", "server"],
        env_vars={
            "PUBLIC_VAR": "public_value",
            "SECRET_API_KEY": "secret_key_123",
            "ANOTHER_SECRET": "another_secret_value",
        },
        secret_env_var_keys=["SECRET_API_KEY", "ANOTHER_SECRET"],
        description="Server with secret environment variables",
    )

    assert request.name == "Secret Env Vars Server"
    assert request.command == "python"
    assert request.args == ["-m", "server"]
    assert request.env_vars == {
        "PUBLIC_VAR": "public_value",
        "SECRET_API_KEY": "secret_key_123",
        "ANOTHER_SECRET": "another_secret_value",
    }
    assert request.secret_env_var_keys == ["SECRET_API_KEY", "ANOTHER_SECRET"]
    assert request.description == "Server with secret environment variables"


def test_local_tool_server_creation_request_empty_secret_env_var_keys():
    """Test LocalToolServerCreationRequest with empty secret_env_var_keys (default)"""
    request = LocalToolServerCreationRequest(
        name="No Secret Env Vars Server",
        command="python",
        args=["-m", "server"],
        env_vars={"PUBLIC_VAR": "public_value"},
        # secret_env_var_keys defaults to empty list
    )

    assert request.secret_env_var_keys == []


def test_local_tool_server_creation_request_secret_env_var_key_not_in_env_vars():
    """Test LocalToolServerCreationRequest rejects secret keys not in env_vars"""
    with pytest.raises(ValidationError) as exc_info:
        LocalToolServerCreationRequest(
            name="Invalid Secret Key Server",
            command="python",
            args=["-m", "server"],
            env_vars={"PUBLIC_VAR": "public_value"},
            secret_env_var_keys=["SECRET_API_KEY"],  # Not in env_vars
        )

    error_str = str(exc_info.value)
    assert (
        "Secret environment variable key SECRET_API_KEY is not in the list of environment variables"
        in error_str
    )


def test_local_tool_server_creation_request_empty_secret_env_var_key():
    """Test LocalToolServerCreationRequest rejects empty secret env var keys"""
    with pytest.raises(ValidationError) as exc_info:
        LocalToolServerCreationRequest(
            name="Empty Secret Key Server",
            command="python",
            args=["-m", "server"],
            env_vars={"PUBLIC_VAR": "public_value", "": "some_value"},
            secret_env_var_keys=[""],  # Empty key
        )

    error_str = str(exc_info.value)
    # The validation first catches invalid env var keys, then secret env var key validation
    assert (
        "Secret environment variable key is required" in error_str
        or "Invalid environment variable key" in error_str
    )


def test_local_tool_server_creation_request_whitespace_only_secret_env_var_key():
    """Test LocalToolServerCreationRequest rejects whitespace-only secret env var keys"""
    with pytest.raises(ValidationError) as exc_info:
        LocalToolServerCreationRequest(
            name="Whitespace Secret Key Server",
            command="python",
            args=["-m", "server"],
            env_vars={"PUBLIC_VAR": "public_value", "   ": "some_value"},
            secret_env_var_keys=["   "],  # Whitespace only
        )

    error_str = str(exc_info.value)
    # The validation first catches invalid env var keys, then secret env var key validation
    assert (
        "Secret environment variable key is required" in error_str
        or "Invalid environment variable key" in error_str
    )


def test_local_tool_server_creation_request_multiple_secret_env_var_key_validation_errors():
    """Test LocalToolServerCreationRequest handles multiple secret env var key validation errors"""
    with pytest.raises(ValidationError) as exc_info:
        LocalToolServerCreationRequest(
            name="Multiple Errors Server",
            command="python",
            args=["-m", "server"],
            env_vars={"PUBLIC_VAR": "public_value"},
            secret_env_var_keys=["", "NOT_IN_ENV_VARS", "   "],  # Multiple invalid keys
        )

    error_str = str(exc_info.value)
    # Should contain errors for all invalid keys
    # The validation first catches invalid env var keys, then secret env var key validation
    assert (
        "Secret environment variable key is required" in error_str
        or "Invalid environment variable key" in error_str
    )
    # Note: The first validation error (empty key) stops further validation, so NOT_IN_ENV_VARS error may not appear
    # assert "Secret environment variable key NOT_IN_ENV_VARS is not in the list of environment variables" in error_str


def test_local_tool_server_creation_request_secret_env_var_keys_with_whitespace_fails():
    """Test LocalToolServerCreationRequest rejects secret env var keys with whitespace"""
    with pytest.raises(ValidationError) as exc_info:
        LocalToolServerCreationRequest(
            name="Whitespace Secret Env Vars Server",
            command="python",
            args=["-m", "server"],
            env_vars={
                "PUBLIC_VAR": "public_value",
                "SECRET_KEY": "secret_value",
                "ANOTHER_SECRET": "another_value",
            },
            secret_env_var_keys=[
                "  SECRET_KEY  ",
                " ANOTHER_SECRET ",
            ],  # Whitespace should fail
        )

    error_str = str(exc_info.value)
    assert (
        "Secret environment variable key   SECRET_KEY   is not in the list of environment variables"
        in error_str
    )


def test_local_tool_server_creation_request_secret_env_var_keys_with_all_env_vars_secret():
    """Test LocalToolServerCreationRequest when all env vars are marked as secret"""
    request = LocalToolServerCreationRequest(
        name="All Secret Server",
        command="python",
        args=["-m", "server"],
        env_vars={
            "SECRET_API_KEY": "secret_key_123",
            "ANOTHER_SECRET": "another_secret_value",
            "DATABASE_PASSWORD": "db_password",
        },
        secret_env_var_keys=["SECRET_API_KEY", "ANOTHER_SECRET", "DATABASE_PASSWORD"],
    )

    assert set(request.secret_env_var_keys) == {
        "SECRET_API_KEY",
        "ANOTHER_SECRET",
        "DATABASE_PASSWORD",
    }
    assert set(request.secret_env_var_keys) == set(request.env_vars.keys())


def test_local_tool_server_creation_request_secret_env_var_keys_partial_overlap():
    """Test LocalToolServerCreationRequest with some env vars marked as secret"""
    request = LocalToolServerCreationRequest(
        name="Partial Secret Server",
        command="python",
        args=["-m", "server"],
        env_vars={
            "PUBLIC_VAR": "public_value",
            "DEBUG": "true",
            "SECRET_API_KEY": "secret_key_123",
            "ANOTHER_SECRET": "another_secret_value",
            "PORT": "8080",
        },
        secret_env_var_keys=["SECRET_API_KEY", "ANOTHER_SECRET"],
    )

    assert request.secret_env_var_keys == ["SECRET_API_KEY", "ANOTHER_SECRET"]
    # Verify all secret keys are in env_vars
    for secret_key in request.secret_env_var_keys:
        assert secret_key in request.env_vars


def test_local_tool_server_creation_request_duplicate_secret_env_var_keys():
    """Test LocalToolServerCreationRequest handles duplicate secret env var keys"""
    request = LocalToolServerCreationRequest(
        name="Duplicate Secret Keys Server",
        command="python",
        args=["-m", "server"],
        env_vars={
            "PUBLIC_VAR": "public_value",
            "SECRET_API_KEY": "secret_key_123",
        },
        secret_env_var_keys=[
            "SECRET_API_KEY",
            "SECRET_API_KEY",
            "SECRET_API_KEY",
        ],  # Duplicates
    )

    # Should preserve duplicates as provided (validation doesn't dedupe)
    assert request.secret_env_var_keys == [
        "SECRET_API_KEY",
        "SECRET_API_KEY",
        "SECRET_API_KEY",
    ]


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

            # Verify available_tools is empty when secrets are missing
            assert "available_tools" in result
            assert result["available_tools"] == []


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
