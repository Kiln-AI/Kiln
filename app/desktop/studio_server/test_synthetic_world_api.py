from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.datamodel.code_tool import CodeTool
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.synthetic_world import SyntheticWorld
from kiln_server.custom_errors import connect_custom_errors

from app.desktop.studio_server.synthetic_world_api import connect_synthetic_world_api

SCHEMA = {"type": "object", "properties": {"x": {"type": "integer"}}}
CODE = "def run(x):\n    return str(x)\n"
TRUST_PATCH = "app.desktop.studio_server.synthetic_world_api.has_add_code_trust"


@pytest.fixture
def app():
    test_app = FastAPI()
    connect_custom_errors(test_app)
    connect_synthetic_world_api(test_app)
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
        "app.desktop.studio_server.synthetic_world_api.project_from_id",
        return_value=project,
    ):
        yield


@pytest.fixture
def world_id(client):
    r = client.post(
        "/api/projects/p1/synthetic_worlds",
        json={"name": "World A", "framework_content_hash": "eng1"},
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _tool_body(replaces="kiln_tool::code::real1", fn="lookup"):
    return {
        "name": f"synthetic {fn}",
        "replaces_tool_id": replaces,
        "tool_function_name": fn,
        "tool_description": "plays lookup",
        "parameters_schema": SCHEMA,
        "code": CODE,
        "timeout_seconds": 10,
    }


class TestWorlds:
    def test_create_list_get(self, client, project, world_id):
        assert (project.path.parent / "synthetic_worlds").is_dir()
        world = SyntheticWorld.from_id_and_parent_path(world_id, project.path)
        assert world is not None and world.lib_dir().is_dir()
        listed = client.get("/api/projects/p1/synthetic_worlds").json()
        assert [w["id"] for w in listed] == [world_id]
        got = client.get(f"/api/projects/p1/synthetic_worlds/{world_id}").json()
        assert got["name"] == "World A"
        assert got["framework_content_hash"] == "eng1"
        assert got["tool_count"] == 0 and got["fixture_count"] == 0

    def test_update(self, client, world_id):
        r = client.patch(
            f"/api/projects/p1/synthetic_worlds/{world_id}",
            json={"strict": True, "description": "d"},
        )
        assert r.status_code == 200
        assert r.json()["strict"] is True
        assert r.json()["description"] == "d"
        r = client.patch(
            f"/api/projects/p1/synthetic_worlds/{world_id}", json={"unknown": 1}
        )
        assert r.status_code == 422

    def test_delete(self, client, world_id):
        assert (
            client.delete(f"/api/projects/p1/synthetic_worlds/{world_id}").status_code
            == 200
        )
        assert (
            client.get(f"/api/projects/p1/synthetic_worlds/{world_id}").status_code
            == 404
        )

    def test_invalid_name(self, client):
        r = client.post("/api/projects/p1/synthetic_worlds", json={"name": "   "})
        assert r.status_code == 400

    def test_missing_world(self, client):
        assert client.get("/api/projects/p1/synthetic_worlds/nope").status_code == 404


class TestTools:
    def test_create_requires_trust(self, client, world_id):
        with patch(TRUST_PATCH, return_value=False):
            r = client.post(
                f"/api/projects/p1/synthetic_worlds/{world_id}/tools", json=_tool_body()
            )
        assert r.status_code == 200
        assert r.json()["not_trusted"] is True
        assert (
            client.get(f"/api/projects/p1/synthetic_worlds/{world_id}/tools").json()
            == []
        )

    def test_create_list_update_delete(self, client, world_id):
        with patch(TRUST_PATCH, return_value=True):
            r = client.post(
                f"/api/projects/p1/synthetic_worlds/{world_id}/tools", json=_tool_body()
            )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["not_trusted"] is False
        assert body["replaces_tool_id"] == "kiln_tool::code::real1"
        assert body["code"] == CODE
        tool_id = body["id"]

        listed = client.get(
            f"/api/projects/p1/synthetic_worlds/{world_id}/tools"
        ).json()
        assert [t["id"] for t in listed] == [tool_id]
        assert (
            client.get(f"/api/projects/p1/synthetic_worlds/{world_id}").json()[
                "tool_count"
            ]
            == 1
        )

        r = client.patch(
            f"/api/projects/p1/synthetic_worlds/{world_id}/tools/{tool_id}",
            json={"name": "renamed"},
        )
        assert r.json()["name"] == "renamed"

        assert (
            client.delete(
                f"/api/projects/p1/synthetic_worlds/{world_id}/tools/{tool_id}"
            ).status_code
            == 200
        )
        assert (
            client.get(f"/api/projects/p1/synthetic_worlds/{world_id}/tools").json()
            == []
        )

    def test_duplicate_binding_rejected(self, client, world_id):
        with patch(TRUST_PATCH, return_value=True):
            assert (
                client.post(
                    f"/api/projects/p1/synthetic_worlds/{world_id}/tools",
                    json=_tool_body(),
                ).status_code
                == 200
            )
            r = client.post(
                f"/api/projects/p1/synthetic_worlds/{world_id}/tools",
                json=_tool_body(fn="other"),
            )
        assert r.status_code == 400
        assert "already replaces" in r.json()["message"]

    @pytest.mark.parametrize(
        "bad",
        [
            {"replaces_tool_id": "kiln_tool::synthetic::w::t"},
            {"code": "def nope():\n    pass\n"},
            {"tool_function_name": "Not Valid"},
        ],
    )
    def test_invalid_tool_rejected(self, client, world_id, bad):
        with patch(TRUST_PATCH, return_value=True):
            r = client.post(
                f"/api/projects/p1/synthetic_worlds/{world_id}/tools",
                json={**_tool_body(), **bad},
            )
        assert r.status_code in (400, 422)

    def test_validate_reports_warnings(self, client, project, world_id):
        real = CodeTool(
            name="real",
            parent=project,
            tool_function_name="lookup",
            tool_description="d",
            parameters_schema=SCHEMA,
            code=CODE,
        )
        real.save_to_file()
        with patch(TRUST_PATCH, return_value=True):
            client.post(
                f"/api/projects/p1/synthetic_worlds/{world_id}/tools",
                json=_tool_body(replaces=f"kiln_tool::code::{real.id}", fn="lookup"),
            )
            client.post(
                f"/api/projects/p1/synthetic_worlds/{world_id}/tools",
                json=_tool_body(replaces="kiln_tool::code::missing", fn="gone"),
            )
        r = client.get(f"/api/projects/p1/synthetic_worlds/{world_id}/validate")
        assert r.status_code == 200
        assert r.json()["warnings"] == [
            "kiln_tool::code::missing: real code tool not found in project"
        ]


class TestFixtures:
    def test_create_upload_list_delete(self, client, project, world_id):
        frozen = datetime(2026, 7, 14, tzinfo=timezone.utc)
        r = client.post(
            f"/api/projects/p1/synthetic_worlds/{world_id}/fixtures",
            json={"name": "Fixture A", "frozen_time": frozen.isoformat()},
        )
        assert r.status_code == 200, r.text
        fixture_id = r.json()["id"]
        assert r.json()["data_files"] == []
        assert datetime.fromisoformat(r.json()["frozen_time"]) == frozen

        r = client.post(
            f"/api/projects/p1/synthetic_worlds/{world_id}/fixtures/{fixture_id}/data",
            files={"file": ("fixture.db", b"sqlite bytes", "application/octet-stream")},
        )
        assert r.status_code == 200, r.text
        assert r.json()["data_files"] == ["fixture.db"]

        world = SyntheticWorld.from_id_and_parent_path(world_id, project.path)
        fixture = world.fixture_by_id(fixture_id)
        assert (fixture.data_dir() / "fixture.db").read_bytes() == b"sqlite bytes"

        listed = client.get(
            f"/api/projects/p1/synthetic_worlds/{world_id}/fixtures"
        ).json()
        assert [f["id"] for f in listed] == [fixture_id]

        assert (
            client.delete(
                f"/api/projects/p1/synthetic_worlds/{world_id}/fixtures/{fixture_id}"
            ).status_code
            == 200
        )
        assert (
            client.get(f"/api/projects/p1/synthetic_worlds/{world_id}/fixtures").json()
            == []
        )

    def test_upload_rejects_traversal_names(self, client, world_id):
        fixture_id = client.post(
            f"/api/projects/p1/synthetic_worlds/{world_id}/fixtures", json={"name": "F"}
        ).json()["id"]
        r = client.post(
            f"/api/projects/p1/synthetic_worlds/{world_id}/fixtures/{fixture_id}/data",
            files={"file": (".hidden", b"x", "application/octet-stream")},
        )
        assert r.status_code == 400
        r = client.post(
            f"/api/projects/p1/synthetic_worlds/{world_id}/fixtures/{fixture_id}/data",
            files={"file": ("../escape.db", b"x", "application/octet-stream")},
        )
        assert r.status_code == 200
        assert r.json()["data_files"] == ["escape.db"]

    def test_naive_frozen_time_rejected(self, client, world_id):
        r = client.post(
            f"/api/projects/p1/synthetic_worlds/{world_id}/fixtures",
            json={"name": "F", "frozen_time": "2026-07-14T00:00:00"},
        )
        assert r.status_code == 400

    def test_missing_fixture(self, client, world_id):
        assert (
            client.delete(
                f"/api/projects/p1/synthetic_worlds/{world_id}/fixtures/nope"
            ).status_code
            == 404
        )
