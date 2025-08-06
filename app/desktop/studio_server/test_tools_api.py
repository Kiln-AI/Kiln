from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.datamodel.project import Project

from app.desktop.studio_server.tools_api import connect_tools_api


@pytest.fixture
def app():
    test_app = FastAPI()
    connect_tools_api(test_app)
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


def test_create_tool_success(client, test_project):
    tool_data = {
        "name": "test_mcp_tool",
        "type": "remote_mcp",
        "description": "A test MCP tool",
        "properties": {
            "server_url": "https://example.com/mcp",
            "headers": {"Authorization": "Bearer test-token"},
        },
    }

    with patch(
        "app.desktop.studio_server.tools_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        response = client.post(
            f"/api/projects/{test_project.id}/create_tool",
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


def test_create_tool_missing_headers(client, test_project):
    tool_data = {
        "name": "test_tool",
        "type": "remote_mcp",
        "description": "A test tool",
        "properties": {
            "server_url": "https://example.com/api"
            # Missing required "headers" property
        },
    }

    with patch(
        "app.desktop.studio_server.tools_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        response = client.post(
            f"/api/projects/{test_project.id}/create_tool",
            json=tool_data,
        )

        assert response.status_code == 422  # Validation error


def test_create_tool_empty_headers(client, test_project):
    tool_data = {
        "name": "test_tool",
        "type": "remote_mcp",
        "description": "A test tool",
        "properties": {
            "server_url": "https://example.com/api",
            "headers": {},  # Empty headers should fail validation
        },
    }

    with patch(
        "app.desktop.studio_server.tools_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        response = client.post(
            f"/api/projects/{test_project.id}/create_tool",
            json=tool_data,
        )

        assert response.status_code == 422  # Validation error


def test_create_tool_missing_server_url(client, test_project):
    tool_data = {
        "name": "test_tool",
        "type": "remote_mcp",
        "description": "A test tool",
        "properties": {
            # Missing required "server_url" property
            "headers": {"Authorization": "Bearer token"},
        },
    }

    with patch(
        "app.desktop.studio_server.tools_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        response = client.post(
            f"/api/projects/{test_project.id}/create_tool",
            json=tool_data,
        )

        assert response.status_code == 422  # Validation error


def test_create_tool_empty_server_url(client, test_project):
    tool_data = {
        "name": "test_tool",
        "type": "remote_mcp",
        "description": "A test tool",
        "properties": {
            "server_url": "",  # Empty server_url should fail validation
            "headers": {"Authorization": "Bearer token"},
        },
    }

    with patch(
        "app.desktop.studio_server.tools_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        response = client.post(
            f"/api/projects/{test_project.id}/create_tool",
            json=tool_data,
        )

        assert response.status_code == 422  # Validation error


def test_get_available_tools_empty(client, test_project):
    with patch(
        "app.desktop.studio_server.tools_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        response = client.get(f"/api/projects/{test_project.id}/available_tools")

        assert response.status_code == 200
        result = response.json()
        assert result == []


def test_get_available_tools_with_tool(client, test_project):
    # First create a tool
    tool_data = {
        "name": "my_tool",
        "type": "remote_mcp",
        "description": "My awesome tool",
        "properties": {
            "server_url": "https://api.example.com",
            "headers": {"X-API-Key": "secret"},
        },
    }

    with patch(
        "app.desktop.studio_server.tools_api.project_from_id"
    ) as mock_project_from_id:
        mock_project_from_id.return_value = test_project

        create_response = client.post(
            f"/api/projects/{test_project.id}/create_tool",
            json=tool_data,
        )
        assert create_response.status_code == 200
        created_tool = create_response.json()

        # Then get the list of tools
        response = client.get(f"/api/projects/{test_project.id}/available_tools")

        assert response.status_code == 200
        result = response.json()
        assert len(result) == 1
        assert result[0]["name"] == "my_tool"
        assert result[0]["id"] == created_tool["id"]
        assert result[0]["description"] == "My awesome tool"
