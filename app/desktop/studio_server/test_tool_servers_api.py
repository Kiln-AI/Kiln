from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.datamodel.external_tool import ToolServerType
from kiln_ai.datamodel.project import Project
from mcp import ListToolsResult
from mcp.types import Tool

from app.desktop.studio_server.tool_servers_api import connect_tool_servers_api


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
        "app.desktop.studio_server.tool_servers_api.project_from_id"
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
        "app.desktop.studio_server.tool_servers_api.project_from_id"
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
        "app.desktop.studio_server.tool_servers_api.project_from_id"
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
        "app.desktop.studio_server.tool_servers_api.project_from_id"
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
        "app.desktop.studio_server.tool_servers_api.project_from_id"
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
        "app.desktop.studio_server.tool_servers_api.project_from_id"
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
        "app.desktop.studio_server.tool_servers_api.project_from_id"
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
        "app.desktop.studio_server.tool_servers_api.project_from_id"
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
        "app.desktop.studio_server.tool_servers_api.project_from_id"
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

        # Now get the tool server
        response = client.get(
            f"/api/projects/{test_project.id}/tool_servers/{tool_server_id}"
        )

        assert response.status_code == 200
        result = response.json()
        assert result["id"] == tool_server_id
        assert result["name"] == "test_get_tool"
        assert result["type"] == "remote_mcp"
        assert result["description"] == "Tool for get test"
        assert result["properties"]["server_url"] == "https://example.com/api"
        assert result["properties"]["headers"]["Authorization"] == "Bearer token"


def test_get_tool_server_not_found(client, test_project):
    with patch(
        "app.desktop.studio_server.tool_servers_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        # Try to get a non-existent tool server
        response = client.get(
            f"/api/projects/{test_project.id}/tool_servers/nonexistent-tool-server-id"
        )

        assert response.status_code == 404
        result = response.json()
        assert result["detail"] == "Tool not found"


def test_get_available_tools_success(client, test_project):
    """Test successful case where remote_mcp tool server returns tools"""
    # First create a tool server
    tool_data = {
        "name": "test_mcp_tool",
        "server_url": "https://example.com/mcp",
        "headers": {"Authorization": "Bearer test-token"},
        "description": "Test MCP tool",
    }

    with patch(
        "app.desktop.studio_server.tool_servers_api.project_from_id"
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

        # Mock MCPServer.list_tools to return a list of tools
        mock_tools = [
            Tool(name="test_tool_1", description="First test tool", inputSchema={}),
            Tool(name="test_tool_2", description="Second test tool", inputSchema={}),
            Tool(name="calculator", description="Math calculations", inputSchema={}),
        ]
        mock_result = ListToolsResult(tools=mock_tools)

        with patch(
            "app.desktop.studio_server.tool_servers_api.MCPServer"
        ) as mock_mcp_class:
            mock_mcp_instance = AsyncMock()
            mock_mcp_instance.list_tools.return_value = mock_result
            mock_mcp_class.return_value = mock_mcp_instance

            # Test the endpoint
            response = client.get(
                f"/api/projects/{test_project.id}/tool_servers/{tool_server_id}/available_tools"
            )

            assert response.status_code == 200
            result = response.json()
            assert isinstance(result, dict)
            assert "tools" in result
            assert len(result["tools"]) == 3

            tool_names = [tool["name"] for tool in result["tools"]]
            assert "test_tool_1" in tool_names
            assert "test_tool_2" in tool_names
            assert "calculator" in tool_names

            # Verify MCPServer was initialized with the correct tool server
            mock_mcp_class.assert_called_once()
            args = mock_mcp_class.call_args[0]
            assert args[0].id == tool_server_id
            assert args[0].type == ToolServerType.remote_mcp
            mock_mcp_instance.list_tools.assert_called_once()


def test_get_available_tools_non_mcp_type(client, test_project):
    """Test case where tool server is not remote_mcp type returns empty list"""
    # Create a tool server and then mock its type to be different
    # First create a tool server normally
    tool_data = {
        "name": "non_mcp_tool",
        "server_url": "https://example.com",
        "headers": {},
        "description": "Non MCP tool",
    }

    with patch(
        "app.desktop.studio_server.tool_servers_api.project_from_id"
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

        # Now get the created tool server and manually change its type for testing
        created_tool_obj = None
        for tool in test_project.external_tool_servers():
            if tool.id == tool_server_id:
                created_tool_obj = tool
                break

        assert created_tool_obj is not None

        # Temporarily change the type to something other than remote_mcp
        original_type = created_tool_obj.type
        created_tool_obj.__dict__["type"] = ToolServerType.__members__.get(
            "local_mcp", "other_type"
        )

        try:
            response = client.get(
                f"/api/projects/{test_project.id}/tool_servers/{tool_server_id}/available_tools"
            )

            assert response.status_code == 200
            result = response.json()
            assert result is None
        finally:
            # Restore original type
            created_tool_obj.__dict__["type"] = original_type


def test_get_available_tools_tool_not_found(client, test_project):
    """Test case where tool server is not found (404 error)"""
    with patch(
        "app.desktop.studio_server.tool_servers_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        # Try to get available tools for a non-existent tool server
        response = client.get(
            f"/api/projects/{test_project.id}/tool_servers/nonexistent-tool-server-id/available_tools"
        )

        assert response.status_code == 404
        result = response.json()
        assert result["detail"] == "Tool not found"


def test_get_available_tools_mcp_server_error(client, test_project):
    """Test case where MCPServer.list_tools() raises an exception"""
    # First create a tool server
    tool_data = {
        "name": "failing_mcp_tool",
        "server_url": "https://example.com/mcp",
        "headers": {},
        "description": "MCP tool that will fail",
    }

    with patch(
        "app.desktop.studio_server.tool_servers_api.project_from_id"
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

        # Mock MCPServer.list_tools to raise an exception
        with patch(
            "app.desktop.studio_server.tool_servers_api.MCPServer"
        ) as mock_mcp_class:
            mock_mcp_instance = AsyncMock()
            mock_mcp_instance.list_tools.side_effect = Exception("Connection failed")
            mock_mcp_class.return_value = mock_mcp_instance

            # Test the endpoint - the exception should propagate
            # Since FastAPI doesn't catch unhandled exceptions in test client, we need to catch it
            with pytest.raises(Exception, match="Connection failed"):
                client.get(
                    f"/api/projects/{test_project.id}/tool_servers/{tool_server_id}/available_tools"
                )
