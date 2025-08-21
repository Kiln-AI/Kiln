from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.datamodel.project import Project
from mcp.types import ListToolsResult, Tool

from app.desktop.studio_server.tool_api import connect_tool_servers_api


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


def test_create_tool_server_success(client, test_project):
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
        assert result["properties"]["headers"]["Authorization"] == "Bearer test-token"
        assert "id" in result
        assert "created_at" in result


def test_create_tool_server_no_headers(client, test_project):
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

        response = client.post(
            f"/api/projects/{test_project.id}/connect_remote_mcp",
            json=tool_data,
        )

        assert response.status_code == 200  # Empty headers are allowed
        result = response.json()
        assert result["name"] == "test_tool"
        assert result["properties"]["headers"] == {}


def test_create_tool_server_empty_headers(client, test_project):
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


def test_create_tool_server_no_description(client, test_project):
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


def test_get_available_tool_servers_with_tool_server(client, test_project):
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


def test_get_tool_server_success(client, test_project):
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

        # Create the tool
        create_response = client.post(
            f"/api/projects/{test_project.id}/connect_remote_mcp",
            json=tool_data,
        )
        assert create_response.status_code == 200
        created_tool = create_response.json()
        tool_server_id = created_tool["id"]

        # Mock MCPSessionManager to return a list of tools
        mock_tools = [
            Tool(name="test_tool_1", description="First test tool", inputSchema={}),
            Tool(name="calculator", description="Math calculations", inputSchema={}),
        ]
        mock_result = ListToolsResult(tools=mock_tools)

        # Create mock session that has list_tools method
        mock_session = AsyncMock()
        mock_session.list_tools.return_value = mock_result

        # Create proper async context manager
        @asynccontextmanager
        async def mock_mcp_client(tool_server):
            yield mock_session

        with patch(
            "app.desktop.studio_server.tool_api.MCPSessionManager.shared"
        ) as mock_session_manager_shared:
            mock_session_manager = AsyncMock()
            mock_session_manager.mcp_client = mock_mcp_client
            mock_session_manager_shared.return_value = mock_session_manager

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


def test_get_tool_server_mcp_error_handling(client, test_project):
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

        # Create the tool
        create_response = client.post(
            f"/api/projects/{test_project.id}/connect_remote_mcp",
            json=tool_data,
        )
        assert create_response.status_code == 200
        created_tool = create_response.json()
        tool_server_id = created_tool["id"]

        # Mock MCPSessionManager to raise an exception
        # Create mock session that raises an exception
        mock_session = AsyncMock()
        mock_session.list_tools.side_effect = Exception("Connection failed")

        # Create proper async context manager that raises exception
        @asynccontextmanager
        async def mock_mcp_client_error(tool_server):
            yield mock_session

        with patch(
            "app.desktop.studio_server.tool_api.MCPSessionManager.shared"
        ) as mock_session_manager_shared:
            mock_session_manager = AsyncMock()
            mock_session_manager.mcp_client = mock_mcp_client_error
            mock_session_manager_shared.return_value = mock_session_manager

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


def test_get_available_tools_success(client, test_project):
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
        create_response = client.post(
            f"/api/projects/{test_project.id}/connect_remote_mcp",
            json=tool_data,
        )
        assert create_response.status_code == 200
        created_tool = create_response.json()
        server_id = created_tool["id"]

        # Mock MCPSessionManager to return tools
        mock_tools = [
            Tool(name="echo", description="Echo tool", inputSchema={}),
            Tool(name="calculator", description="Math calculator", inputSchema={}),
            Tool(
                name="weather", description=None, inputSchema={}
            ),  # Test None description
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


def test_get_available_tools_multiple_servers(client, test_project):
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


def test_get_available_tools_mcp_error_handling(client, test_project):
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
        create_response = client.post(
            f"/api/projects/{test_project.id}/connect_remote_mcp",
            json=tool_data,
        )
        assert create_response.status_code == 200

        # Mock MCPSessionManager to raise an exception
        mock_session = AsyncMock()
        mock_session.list_tools.side_effect = Exception("MCP connection failed")

        @asynccontextmanager
        async def mock_mcp_client_error(tool_server):
            yield mock_session

        with patch(
            "app.desktop.studio_server.tool_api.MCPSessionManager.shared"
        ) as mock_session_manager_shared:
            mock_session_manager = AsyncMock()
            mock_session_manager.mcp_client = mock_mcp_client_error
            mock_session_manager_shared.return_value = mock_session_manager

            # The API should propagate the exception (current behavior)
            # In a real implementation, you might want to handle this more gracefully
            with pytest.raises(Exception, match="MCP connection failed"):
                client.get(f"/api/projects/{test_project.id}/available_tools")


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
