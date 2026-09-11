from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.tool_id import build_world_tool_id
from kiln_ai.datamodel.world import World
from kiln_ai.worlds.session_manager import OpenEnvSessionManager
from kiln_ai.worlds.testing import (
    ENV_NAME,
    ENV_VERSION,
    free_port,
    serve_in_thread,
)
from kiln_server.custom_errors import connect_custom_errors

from app.desktop.studio_server.world_api import connect_world_api

SESSION_MANAGER_PATCH = "app.desktop.studio_server.world_api.shared_session_manager"


@pytest.fixture
def app():
    test_app = FastAPI()
    connect_custom_errors(test_app)
    connect_world_api(test_app)
    return test_app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def project(tmp_path):
    path = tmp_path / "proj" / "project.kiln"
    path.parent.mkdir()
    p = Project(name="Proj", path=path)
    p.save_to_file()
    return p


@pytest.fixture(autouse=True)
def mock_project_from_id(project):
    with patch(
        "app.desktop.studio_server.world_api.project_from_id",
        return_value=project,
    ):
        yield


@pytest.fixture
def world_id(client):
    r = client.post(
        "/api/projects/p1/worlds",
        json={"name": "World A", "env_url": "http://localhost:8123"},
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.fixture
def session_manager(tmp_path):
    """A session manager standing in for the process-wide one."""
    instance = OpenEnvSessionManager()
    with patch(SESSION_MANAGER_PATCH, return_value=instance):
        yield instance
    import asyncio

    asyncio.run(instance.shutdown())


def _world(project, world_id) -> World:
    world = World.from_id_and_parent_path(world_id, project.path)
    assert world is not None
    return world


class TestWorlds:
    def test_create_list_get(self, client, project, world_id):
        assert (project.path.parent / "worlds").is_dir()
        listed = client.get("/api/projects/p1/worlds").json()
        assert [w["id"] for w in listed] == [world_id]
        got = client.get(f"/api/projects/p1/worlds/{world_id}").json()
        assert got["name"] == "World A"
        assert got["env_url"] == "http://localhost:8123"

    def test_create_defaults(self, client):
        r = client.post("/api/projects/p1/worlds", json={"name": "Bare"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["env_url"] is None
        assert body["description"] is None

    def test_update(self, client, project, world_id):
        r = client.patch(
            f"/api/projects/p1/worlds/{world_id}",
            json={"description": "d", "env_url": None},
        )
        assert r.status_code == 200, r.text
        assert r.json()["description"] == "d"
        assert r.json()["env_url"] is None
        world = _world(project, world_id)
        assert world.env_url is None
        r = client.patch(f"/api/projects/p1/worlds/{world_id}", json={"unknown": 1})
        assert r.status_code == 422
        r = client.patch(f"/api/projects/p1/worlds/{world_id}", json={"name": "  "})
        assert r.status_code == 400

    def test_delete(self, client, world_id):
        assert client.delete(f"/api/projects/p1/worlds/{world_id}").status_code == 200
        assert client.get(f"/api/projects/p1/worlds/{world_id}").status_code == 404
        assert client.get("/api/projects/p1/worlds").json() == []

    def test_invalid_name(self, client):
        r = client.post("/api/projects/p1/worlds", json={"name": "   "})
        assert r.status_code == 400

    def test_missing_world(self, client):
        assert client.get("/api/projects/p1/worlds/nope").status_code == 404
        assert (
            client.patch(
                "/api/projects/p1/worlds/nope", json={"description": "x"}
            ).status_code
            == 404
        )
        assert client.delete("/api/projects/p1/worlds/nope").status_code == 404


class TestTools:
    def test_no_environment_is_400(self, client, project):
        r = client.post("/api/projects/p1/worlds", json={"name": "Empty"})
        world_id = r.json()["id"]
        r = client.get(f"/api/projects/p1/worlds/{world_id}/tools")
        assert r.status_code == 400
        assert "no env_url" in r.json()["message"]

    def test_unreachable_env_url_is_502(self, client, session_manager):
        r = client.post(
            "/api/projects/p1/worlds",
            json={"name": "Down", "env_url": f"http://127.0.0.1:{free_port()}"},
        )
        world_id = r.json()["id"]
        r = client.get(f"/api/projects/p1/worlds/{world_id}/tools")
        assert r.status_code == 502
        assert "/metadata" in r.json()["message"]

    def test_lists_environment_tools(self, client, session_manager):
        with serve_in_thread() as base_url:
            r = client.post(
                "/api/projects/p1/worlds",
                json={"name": "Live", "env_url": base_url},
            )
            world_id = r.json()["id"]
            r = client.get(f"/api/projects/p1/worlds/{world_id}/tools")
            assert r.status_code == 200, r.text
            tools = r.json()
            assert [t["name"] for t in tools] == [
                "append_note",
                "read_notes",
                "explode",
            ]
            assert tools[0]["tool_id"] == build_world_tool_id(world_id, "append_note")
            assert tools[0]["description"] == "Append a note to the episode's notebook."
            assert tools[0]["input_schema"]["required"] == ["note"]
            assert tools[1]["input_schema"] == {"type": "object", "properties": {}}
            server = session_manager.server_for_world_id(world_id)
            assert server is not None
            assert server.env_name == ENV_NAME
            assert server.env_version == ENV_VERSION
