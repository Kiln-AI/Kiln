from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.datamodel.eval import EvalInput, SingleTurnEvalInputData, UserMessage
from kiln_ai.datamodel.openenv import OpenEnvReset, OpenEnvServer
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.tool_id import build_openenv_tool_id
from kiln_ai.openenv.session_manager import OpenEnvSessionManager
from kiln_ai.openenv.testing import (
    ENV_NAME,
    ENV_VERSION,
    free_port,
    serve_in_thread,
)
from kiln_server.custom_errors import connect_custom_errors

from app.desktop.studio_server.openenv_server_api import connect_openenv_server_api

SESSION_MANAGER_PATCH = (
    "app.desktop.studio_server.openenv_server_api.shared_session_manager"
)


@pytest.fixture
def app():
    test_app = FastAPI()
    connect_custom_errors(test_app)
    connect_openenv_server_api(test_app)
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
        "app.desktop.studio_server.openenv_server_api.project_from_id",
        return_value=project,
    ):
        yield


@pytest.fixture
def openenv_server_id(client):
    r = client.post(
        "/api/projects/p1/openenv_servers",
        json={"name": "Environment A", "url": "http://localhost:8123"},
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


def _load_openenv_server(project, openenv_server_id) -> OpenEnvServer:
    openenv_server = OpenEnvServer.from_id_and_parent_path(
        openenv_server_id, project.path
    )
    assert openenv_server is not None
    return openenv_server


class TestOpenEnvServers:
    def test_create_list_get(self, client, project, openenv_server_id):
        assert (project.path.parent / "openenv_servers").is_dir()
        listed = client.get("/api/projects/p1/openenv_servers").json()
        assert [item["id"] for item in listed] == [openenv_server_id]
        got = client.get(f"/api/projects/p1/openenv_servers/{openenv_server_id}").json()
        assert set(got) == {
            "id",
            "name",
            "description",
            "url",
            "created_at",
            "created_by",
        }
        assert got["name"] == "Environment A"
        assert got["url"] == "http://localhost:8123"

    def test_create_defaults(self, client):
        r = client.post("/api/projects/p1/openenv_servers", json={"name": "Bare"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["url"] is None
        assert body["description"] is None

    def test_update(self, client, project, openenv_server_id):
        r = client.patch(
            f"/api/projects/p1/openenv_servers/{openenv_server_id}",
            json={"description": "d", "url": None},
        )
        assert r.status_code == 200, r.text
        assert r.json()["description"] == "d"
        assert r.json()["url"] is None
        openenv_server = _load_openenv_server(project, openenv_server_id)
        assert openenv_server.url is None
        r = client.patch(
            f"/api/projects/p1/openenv_servers/{openenv_server_id}", json={"unknown": 1}
        )
        assert r.status_code == 422
        r = client.patch(
            f"/api/projects/p1/openenv_servers/{openenv_server_id}", json={"name": "  "}
        )
        assert r.status_code == 422
        r = client.patch(
            f"/api/projects/p1/openenv_servers/{openenv_server_id}",
            json={"url": "not a url"},
        )
        assert r.status_code == 400
        assert "url must be an http:// or https:// URL" in r.json()["message"]

    def test_delete(self, client, openenv_server_id):
        assert (
            client.delete(
                f"/api/projects/p1/openenv_servers/{openenv_server_id}"
            ).status_code
            == 200
        )
        assert (
            client.get(
                f"/api/projects/p1/openenv_servers/{openenv_server_id}"
            ).status_code
            == 404
        )
        assert client.get("/api/projects/p1/openenv_servers").json() == []

    def test_delete_refused_while_an_eval_input_resets_into_the_openenv_server(
        self, client, project, openenv_server_id
    ):
        task = Task(name="t", instruction="i", parent=project)
        task.save_to_file()
        eval_input = EvalInput(
            parent=task,
            data=SingleTurnEvalInputData(user_message=UserMessage(text="hi")),
            openenv_reset=OpenEnvReset(openenv_server_id=openenv_server_id),
        )
        eval_input.save_to_file()
        EvalInput(
            parent=task,
            data=SingleTurnEvalInputData(
                user_message=UserMessage(text="no environment")
            ),
        ).save_to_file()

        r = client.delete(f"/api/projects/p1/openenv_servers/{openenv_server_id}")
        assert r.status_code == 409
        assert "1 eval input(s)" in r.json()["message"]
        assert (
            client.get(
                f"/api/projects/p1/openenv_servers/{openenv_server_id}"
            ).status_code
            == 200
        )

        eval_input.delete()
        assert (
            client.delete(
                f"/api/projects/p1/openenv_servers/{openenv_server_id}"
            ).status_code
            == 200
        )

    def test_invalid_name(self, client):
        r = client.post("/api/projects/p1/openenv_servers", json={"name": "   "})
        assert r.status_code == 422

    @pytest.mark.parametrize("url", ["ftp://host", "localhost:8000", "http://"])
    def test_invalid_url(self, client, url):
        r = client.post(
            "/api/projects/p1/openenv_servers", json={"name": "Notes", "url": url}
        )
        assert r.status_code == 400

    def test_missing_openenv_server(self, client):
        assert client.get("/api/projects/p1/openenv_servers/nope").status_code == 404
        assert (
            client.patch(
                "/api/projects/p1/openenv_servers/nope", json={"description": "x"}
            ).status_code
            == 404
        )
        assert client.delete("/api/projects/p1/openenv_servers/nope").status_code == 404


class TestTools:
    def test_list_tools_without_url_is_400(self, client, project):
        r = client.post("/api/projects/p1/openenv_servers", json={"name": "Empty"})
        openenv_server_id = r.json()["id"]
        r = client.get(f"/api/projects/p1/openenv_servers/{openenv_server_id}/tools")
        assert r.status_code == 400
        assert "no url" in r.json()["message"]

    def test_unreachable_url_is_502(self, client, session_manager):
        r = client.post(
            "/api/projects/p1/openenv_servers",
            json={"name": "Down", "url": f"http://127.0.0.1:{free_port()}"},
        )
        openenv_server_id = r.json()["id"]
        r = client.get(f"/api/projects/p1/openenv_servers/{openenv_server_id}/tools")
        assert r.status_code == 502
        assert "/metadata" in r.json()["message"]

    def test_lists_openenv_server_tools(self, client, session_manager):
        with serve_in_thread() as base_url:
            r = client.post(
                "/api/projects/p1/openenv_servers",
                json={"name": "Live", "url": base_url},
            )
            openenv_server_id = r.json()["id"]
            r = client.get(
                f"/api/projects/p1/openenv_servers/{openenv_server_id}/tools"
            )
            assert r.status_code == 200, r.text
            tools = r.json()
            assert [t["name"] for t in tools] == [
                "append_note",
                "read_notes",
                "explode",
                "sleep",
            ]
            assert tools[0]["tool_id"] == build_openenv_tool_id(
                openenv_server_id, "append_note"
            )
            assert tools[0]["description"] == "Append a note to the episode's notebook."
            assert tools[0]["input_schema"]["required"] == ["note"]
            assert tools[1]["input_schema"] == {"type": "object", "properties": {}}
            server = session_manager._servers[openenv_server_id]
            assert server.openenv_version == f"{ENV_NAME}@{ENV_VERSION}"
