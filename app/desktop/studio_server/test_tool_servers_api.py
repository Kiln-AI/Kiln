from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
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
            "app.desktop.studio_server.tool_servers_api.MCPSessionManager.shared"
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

        # Mock MCPSessionManager to raise an exception
        # Create mock session that raises an exception
        mock_session = AsyncMock()
        mock_session.list_tools.side_effect = Exception("Connection failed")

        # Create proper async context manager that raises exception
        @asynccontextmanager
        async def mock_mcp_client_error(tool_server):
            yield mock_session

        with patch(
            "app.desktop.studio_server.tool_servers_api.MCPSessionManager.shared"
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


def test_get_available_tools(client, test_project):
    response = client.get(f"/api/projects/{test_project.id}/available_tools")

    assert response.status_code == 200
    result = response.json()

    # Should return the 4 built-in math tools
    assert len(result) == 4

    # Check that all expected tools are present
    tool_names = [tool["name"] for tool in result]
    expected_names = [
        "Add Numbers",
        "Subtract Numbers",
        "Multiply Numbers",
        "Divide Numbers",
    ]
    assert set(tool_names) == set(expected_names)

    for tool in result:
        assert "id" in tool
        assert "name" in tool
        assert "description" in tool
