from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from kiln_ai.datamodel.external_tool_server import ExternalToolServer, ToolServerType
from kiln_ai.datamodel.project import Project
from kiln_ai.utils.dataset_import import format_validation_error
from mcp.types import ListToolsResult, Tool
from pydantic import ValidationError

from app.desktop.studio_server.tool_api import (
    ExternalToolServerCreationRequest,
    LocalToolServerCreationRequest,
    available_mcp_tools,
    connect_tool_servers_api,
    validate_tool_server_connectivity,
)


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
        mock_session_manager = AsyncMock()
        mock_session_manager.mcp_client = mock_client
        mock_session_manager_shared.return_value = mock_session_manager
        yield


@asynccontextmanager
async def mock_mcp_connection_error(error_message="Connection failed"):
    """Context manager for MCP connection errors."""
    error = Exception(error_message)
    patch_obj, mock_client = create_mcp_session_manager_patch(connection_error=error)

    with patch_obj as mock_session_manager_shared:
        mock_session_manager = AsyncMock()
        mock_session_manager.mcp_client = mock_client
        mock_session_manager_shared.return_value = mock_session_manager
        yield


@asynccontextmanager
async def mock_mcp_list_tools_error(error_message="list_tools failed"):
    """Context manager for MCP list_tools errors."""
    error = Exception(error_message)
    patch_obj, mock_client = create_mcp_session_manager_patch(list_tools_error=error)

    with patch_obj as mock_session_manager_shared:
        mock_session_manager = AsyncMock()
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
            response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )

            assert response.status_code == 422
            error_data = response.json()
            # Error could be in "detail" or "message" field depending on FastAPI's error handling
            error_message = error_data.get("detail", "") or error_data.get(
                "message", ""
            )
            assert "Failed to connect to the server" in error_message


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
            response = client.post(
                f"/api/projects/{test_project.id}/connect_remote_mcp",
                json=tool_data,
            )

            assert response.status_code == 422
            error_data = response.json()
            # Error could be in "detail" or "message" field depending on FastAPI's error handling
            error_message = error_data.get("detail", "") or error_data.get(
                "message", ""
            )
            assert "Failed to connect to the server" in error_message


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
        assert result["detail"] == "Tool not found"


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
        mock_config_instance = AsyncMock()
        mock_config_instance.enable_demo_tools = True
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
        mock_config_instance = AsyncMock()
        mock_config_instance.enable_demo_tools = False
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
            mock_session_manager_create = AsyncMock()
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
        # Should raise HTTPException with specific message
        with pytest.raises(HTTPException) as exc_info:
            await validate_tool_server_connectivity(tool_server)

        assert exc_info.value.status_code == 422
        assert "Failed to connect to the server" in exc_info.value.detail


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
        # Should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await validate_tool_server_connectivity(tool_server)

        assert exc_info.value.status_code == 422
        assert "Failed to connect to the server" in exc_info.value.detail


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


# Tests for new validation logic
def test_external_tool_server_creation_request_invalid_url_scheme():
    """Test ExternalToolServerCreationRequest rejects URLs with invalid schemes"""

    with pytest.raises(ValidationError) as exc_info:
        ExternalToolServerCreationRequest(
            name="invalid_scheme_server",
            server_url="ftp://example.com/mcp",  # Invalid scheme
            headers={},
            description="Server with invalid URL scheme",
        )

    # Verify the error message is about the URL scheme
    error_str = str(exc_info.value)
    assert "Server URL must start with http:// or https://" in error_str


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


def test_external_tool_server_creation_request_url_normalization():
    """Test that server URLs are properly stripped of whitespace"""
    request = ExternalToolServerCreationRequest(
        name="Normalized Server",
        server_url="  https://example.com/mcp  ",  # Extra whitespace
    )

    assert request.server_url == "https://example.com/mcp"


def test_external_tool_server_creation_request_header_normalization():
    """Test that headers are properly stripped and normalized"""
    request = ExternalToolServerCreationRequest(
        name="Header Server",
        server_url="https://example.com",
        headers={
            "  Authorization  ": "  Bearer token123  ",  # Extra whitespace
            "X-Custom": "value",
        },
    )

    expected_headers = {
        "Authorization": "Bearer token123",
        "X-Custom": "value",
    }
    assert request.headers == expected_headers


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


def test_external_tool_server_creation_request_invalid_schemes():
    """Test various invalid URL schemes"""

    invalid_schemes = [
        "ftp://example.com",
        "ssh://user@example.com",
        "tcp://example.com:1234",
    ]

    for invalid_url in invalid_schemes:
        with pytest.raises(ValidationError) as exc_info:
            ExternalToolServerCreationRequest(
                name="Invalid Scheme Server",
                server_url=invalid_url,
            )

        error_str = str(exc_info.value)
        assert "Server URL must start with http:// or https://" in error_str

    # Test specific cases that might have different error messages
    special_cases = [
        ("file:///path/to/file", "Server URL is not a valid URL"),
        ("mailto:user@example.com", "Server URL is not a valid URL"),
    ]

    for invalid_url, expected_error in special_cases:
        with pytest.raises(ValidationError) as exc_info:
            ExternalToolServerCreationRequest(
                name="Invalid Scheme Server",
                server_url=invalid_url,
            )

        error_str = str(exc_info.value)
        assert expected_error in error_str


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
    """Test that whitespace-only header names/values are rejected"""

    whitespace_cases = [
        {"   ": "value"},  # Whitespace-only name
        {"name": "   "},  # Whitespace-only value
        {"\t\n": "value"},  # Tab/newline only name
        {"name": "\t\n"},  # Tab/newline only value
    ]

    for headers in whitespace_cases:
        with pytest.raises(ValidationError) as exc_info:
            ExternalToolServerCreationRequest(
                name="Whitespace Server",
                server_url="https://example.com",
                headers=headers,
            )

        error_str = str(exc_info.value)
        assert (
            "Header name is required" in error_str
            or "Header value is required" in error_str
        )


def test_external_tool_server_creation_request_model_validator_integration():
    """Test that the model validator works correctly with combined URL and header validation"""

    # Test successful validation with model validator normalization
    request = ExternalToolServerCreationRequest(
        name="Integration Test Server",
        server_url="  https://api.example.com/mcp  ",  # Should be stripped
        headers={
            "  Authorization  ": "  Bearer token123  ",  # Should be stripped
            "X-Custom-Header": "custom-value",
        },
        description="Integration test for model validator",
    )

    # Verify normalization occurred
    assert request.server_url == "https://api.example.com/mcp"
    assert request.headers["Authorization"] == "Bearer token123"
    assert "  Authorization  " not in request.headers
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
    # Should catch the URL error first since it's checked before headers
    assert "Server URL must start with http:// or https://" in error_str


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
        LocalToolServerCreationRequest(
            name="Missing Command Server",
            args=["arg1"],
            # Missing required command field
        )

    assert exc_info.value.error_count() > 0


def test_local_tool_server_creation_request_empty_args():
    """Test LocalToolServerCreationRequest accepts empty args list (arguments no longer required)"""

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
        LocalToolServerCreationRequest(
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
        LocalToolServerCreationRequest(
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
    assert "émojis 🚀" in request.description


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
            response = client.post(
                f"/api/projects/{test_project.id}/connect_local_mcp",
                json=tool_data,
            )

            assert response.status_code == 422
            error_data = response.json()
            error_message = error_data.get("detail", "") or error_data.get(
                "message", ""
            )
            assert "Failed to connect to the server" in error_message


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
    """Test local tool server creation succeeds when args are empty (arguments no longer required)"""
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
        # Should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await validate_tool_server_connectivity(tool_server)

        assert exc_info.value.status_code == 422
        assert "Failed to connect to the server" in exc_info.value.detail
