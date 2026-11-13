from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.datamodel.eval import EvalInput, SingleTurnEvalInputData, UserMessage
from kiln_ai.datamodel.openenv import OpenEnvReset, OpenEnvServer
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.tool_id import build_openenv_tool_id
from kiln_ai.openenv.session_manager import OpenEnvError, OpenEnvSessionManager
from kiln_ai.openenv.testing import (
    ENV_NAME,
    ENV_VERSION,
    free_port,
    serve_in_thread,
)
from kiln_server.custom_errors import connect_custom_errors

from app.desktop.studio_server.openenv_server_api import connect_openenv_server_api

URL_ERROR = (
    "Enter a full URL starting with http:// or https://, like http://127.0.0.1:8004."
)
ACME_OPTIONS = [
    {
        "name": "Acme Manager",
        "description": "Acme's data, signed in as a manager",
        "reset_kwargs": {"company": "acme", "user": "manager"},
    },
    {
        "name": "Acme Tech",
        "description": None,
        "reset_kwargs": {"company": "acme", "user": {"id": 7}},
    },
]

_real_check_reachable = OpenEnvSessionManager.check_reachable

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


@pytest.fixture(autouse=True)
def check_reachable():
    """Every URL answers unless a test says otherwise. Saving checks the URL, and most
    tests save records whose server isn't running."""
    with patch.object(
        OpenEnvSessionManager, "check_reachable", new_callable=AsyncMock
    ) as check:
        yield check


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
            "named_reset_kwargs",
            "created_at",
            "created_by",
            "is_archived",
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
        assert r.json()["message"] == URL_ERROR

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
        assert r.json()["message"] == URL_ERROR

    def test_missing_openenv_server(self, client):
        assert client.get("/api/projects/p1/openenv_servers/nope").status_code == 404
        assert (
            client.patch(
                "/api/projects/p1/openenv_servers/nope", json={"description": "x"}
            ).status_code
            == 404
        )
        assert client.delete("/api/projects/p1/openenv_servers/nope").status_code == 404
        assert (
            client.post(
                "/api/projects/p1/openenv_servers/nope/archive",
                json={"is_archived": True},
            ).status_code
            == 404
        )


class TestReachableOnSave:
    def test_create_checks_the_url(self, client, project, check_reachable):
        r = client.post(
            "/api/projects/p1/openenv_servers",
            json={"name": "Acme", "url": "http://127.0.0.1:8004"},
        )
        assert r.status_code == 200, r.text
        (checked,) = check_reachable.await_args.args
        assert checked.url == "http://127.0.0.1:8004"

    def test_create_without_url_skips_the_check(self, client, check_reachable):
        r = client.post("/api/projects/p1/openenv_servers", json={"name": "Bare"})
        assert r.status_code == 200, r.text
        check_reachable.assert_not_awaited()

    def test_unreachable_url_is_not_saved(self, client, project, check_reachable):
        check_reachable.side_effect = OpenEnvError(
            "OpenEnv server 'Acme' points at http://127.0.0.1:1, which did not "
            "answer /metadata: refused"
        )
        r = client.post(
            "/api/projects/p1/openenv_servers",
            json={"name": "Acme", "url": "http://127.0.0.1:1"},
        )
        assert r.status_code == 400
        assert "did not answer /metadata" in r.json()["message"]
        assert project.openenv_servers() == []

    def test_unreachable_url_on_create_against_a_real_manager(self, client, project):
        with patch.object(
            OpenEnvSessionManager,
            "check_reachable",
            new=_real_check_reachable,
        ):
            r = client.post(
                "/api/projects/p1/openenv_servers",
                json={"name": "Down", "url": f"http://127.0.0.1:{free_port()}"},
            )
        assert r.status_code == 400
        assert "did not answer /metadata" in r.json()["message"]
        assert project.openenv_servers() == []

    def test_reachable_url_on_create_against_a_real_manager(self, client, project):
        with (
            serve_in_thread() as base_url,
            patch.object(
                OpenEnvSessionManager,
                "check_reachable",
                new=_real_check_reachable,
            ),
        ):
            r = client.post(
                "/api/projects/p1/openenv_servers",
                json={"name": "Up", "url": base_url},
            )
        assert r.status_code == 200, r.text
        assert len(project.openenv_servers()) == 1

    def test_update_checks_only_a_changed_url(
        self, client, project, openenv_server_id, check_reachable
    ):
        url = f"/api/projects/p1/openenv_servers/{openenv_server_id}"
        check_reachable.reset_mock()

        r = client.patch(
            url,
            json={
                "name": "Renamed",
                "description": "d",
                "url": "http://localhost:8123",
                "named_reset_kwargs": ACME_OPTIONS,
            },
        )
        assert r.status_code == 200, r.text
        check_reachable.assert_not_awaited()

        r = client.patch(url, json={"url": "http://localhost:9000"})
        assert r.status_code == 200, r.text
        (checked,) = check_reachable.await_args.args
        assert checked.url == "http://localhost:9000"

    def test_unreachable_new_url_leaves_the_record_unchanged(
        self, client, project, openenv_server_id, check_reachable
    ):
        check_reachable.side_effect = OpenEnvError("did not answer /metadata")
        r = client.patch(
            f"/api/projects/p1/openenv_servers/{openenv_server_id}",
            json={"url": "http://localhost:9000", "description": "changed"},
        )
        assert r.status_code == 400
        assert r.json()["message"] == "did not answer /metadata"
        openenv_server = _load_openenv_server(project, openenv_server_id)
        assert openenv_server.url == "http://localhost:8123"
        assert openenv_server.description is None
        got = client.get(f"/api/projects/p1/openenv_servers/{openenv_server_id}")
        assert got.json()["url"] == "http://localhost:8123"


class TestArchive:
    def test_archive_and_unarchive(self, client, project, openenv_server_id):
        url = f"/api/projects/p1/openenv_servers/{openenv_server_id}"
        assert client.get(url).json()["is_archived"] is False

        r = client.post(f"{url}/archive", json={"is_archived": True})
        assert r.status_code == 200, r.text
        assert r.json()["is_archived"] is True
        assert _load_openenv_server(project, openenv_server_id).is_archived is True
        listed = client.get("/api/projects/p1/openenv_servers").json()
        assert [item["is_archived"] for item in listed] == [True]

        r = client.post(f"{url}/archive", json={"is_archived": False})
        assert r.json()["is_archived"] is False
        assert _load_openenv_server(project, openenv_server_id).is_archived is False

    def test_archive_does_not_check_the_url(
        self, client, openenv_server_id, check_reachable
    ):
        check_reachable.reset_mock()
        r = client.post(
            f"/api/projects/p1/openenv_servers/{openenv_server_id}/archive",
            json={"is_archived": True},
        )
        assert r.status_code == 200, r.text
        check_reachable.assert_not_awaited()


class TestEnvironmentOptions:
    def test_create_with_named_reset_kwargs(self, client, project):
        r = client.post(
            "/api/projects/p1/openenv_servers",
            json={"name": "Acme", "named_reset_kwargs": ACME_OPTIONS},
        )
        assert r.status_code == 200, r.text
        assert r.json()["named_reset_kwargs"] == ACME_OPTIONS
        saved = _load_openenv_server(project, r.json()["id"]).named_reset_kwargs
        assert [o.model_dump() for o in saved] == ACME_OPTIONS
        got = client.get(f"/api/projects/p1/openenv_servers/{r.json()['id']}").json()
        assert got["named_reset_kwargs"] == ACME_OPTIONS

    def test_created_without_options_lists_none(self, client, openenv_server_id):
        got = client.get(f"/api/projects/p1/openenv_servers/{openenv_server_id}").json()
        assert got["named_reset_kwargs"] == []

    def test_option_without_reset_kwargs_defaults_to_empty_object(self, client):
        r = client.post(
            "/api/projects/p1/openenv_servers",
            json={"name": "Acme", "named_reset_kwargs": [{"name": "Default"}]},
        )
        assert r.status_code == 200, r.text
        assert r.json()["named_reset_kwargs"] == [
            {"name": "Default", "description": None, "reset_kwargs": {}}
        ]

    def test_patch_replaces_whole_list(self, client, project, openenv_server_id):
        url = f"/api/projects/p1/openenv_servers/{openenv_server_id}"
        r = client.patch(url, json={"named_reset_kwargs": ACME_OPTIONS})
        assert r.status_code == 200, r.text
        assert r.json()["named_reset_kwargs"] == ACME_OPTIONS

        reordered = [
            ACME_OPTIONS[1],
            {"name": "Beta", "description": None, "reset_kwargs": {}},
        ]
        r = client.patch(url, json={"named_reset_kwargs": reordered})
        assert r.json()["named_reset_kwargs"] == reordered

        r = client.patch(url, json={"description": "d"})
        assert r.json()["named_reset_kwargs"] == reordered

        r = client.patch(url, json={"named_reset_kwargs": []})
        assert r.json()["named_reset_kwargs"] == []
        assert _load_openenv_server(project, openenv_server_id).named_reset_kwargs == []

    def test_duplicate_name_on_create_is_400(self, client, project):
        r = client.post(
            "/api/projects/p1/openenv_servers",
            json={
                "name": "Acme",
                "named_reset_kwargs": [ACME_OPTIONS[0], ACME_OPTIONS[0]],
            },
        )
        assert r.status_code == 400
        assert (
            r.json()["message"]
            == "An Environment Preset named Acme Manager already exists."
        )
        assert project.openenv_servers() == []

    def test_duplicate_name_on_patch_is_400_and_leaves_disk_unchanged(
        self, client, project, openenv_server_id
    ):
        url = f"/api/projects/p1/openenv_servers/{openenv_server_id}"
        client.patch(url, json={"named_reset_kwargs": ACME_OPTIONS})
        duplicate = {"name": " Acme Tech ", "reset_kwargs": {}}
        r = client.patch(
            url,
            json={
                "description": "changed",
                "named_reset_kwargs": [*ACME_OPTIONS, duplicate],
            },
        )
        assert r.status_code == 400
        assert (
            r.json()["message"]
            == "An Environment Preset named Acme Tech already exists."
        )
        openenv_server = _load_openenv_server(project, openenv_server_id)
        assert [
            o.model_dump() for o in openenv_server.named_reset_kwargs
        ] == ACME_OPTIONS
        assert openenv_server.description is None

    @pytest.mark.parametrize("reset_kwargs", [[1, 2], "acme", 3, None])
    def test_non_object_reset_kwargs_is_400(
        self, client, openenv_server_id, reset_kwargs
    ):
        option = {"name": "Acme", "reset_kwargs": reset_kwargs}
        r = client.post(
            "/api/projects/p1/openenv_servers",
            json={"name": "Bad", "named_reset_kwargs": [option]},
        )
        assert r.status_code == 400
        assert r.json()["message"] == "Reset arguments must be a JSON object."
        r = client.patch(
            f"/api/projects/p1/openenv_servers/{openenv_server_id}",
            json={"named_reset_kwargs": [option]},
        )
        assert r.status_code == 400
        assert r.json()["message"] == "Reset arguments must be a JSON object."

    def test_blank_option_name_is_400(self, client):
        r = client.post(
            "/api/projects/p1/openenv_servers",
            json={"name": "Bad", "named_reset_kwargs": [{"name": "  "}]},
        )
        assert r.status_code == 400


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


RESET_SCHEMA = {
    "type": "object",
    "properties": {"company": {"type": "string", "enum": ["acme", "beta"]}},
}


class TestResetSchema:
    def _url(self, openenv_server_id: str) -> str:
        return f"/api/projects/p1/openenv_servers/{openenv_server_id}/reset_schema"

    def _create(self, client, url: str | None) -> str:
        body = {"name": "Live"} if url is None else {"name": "Live", "url": url}
        r = client.post("/api/projects/p1/openenv_servers", json=body)
        return r.json()["id"]

    def test_no_url_is_400(self, client, session_manager):
        r = client.get(self._url(self._create(client, None)))
        assert r.status_code == 400
        assert "no url" in r.json()["message"]

    def test_unreachable_url_is_502(self, client, session_manager):
        r = client.get(
            self._url(self._create(client, f"http://127.0.0.1:{free_port()}"))
        )
        assert r.status_code == 502
        assert "/schema" in r.json()["message"]

    def test_server_without_a_schema_is_null(self, client, session_manager):
        with serve_in_thread() as base_url:
            r = client.get(self._url(self._create(client, base_url)))
        assert r.status_code == 200, r.text
        assert r.json() == {"reset_schema": None}

    def test_returns_the_reset_schema(self, client, session_manager):
        with serve_in_thread(
            extra_routes={"/schema": {"reset": RESET_SCHEMA}}
        ) as base_url:
            r = client.get(self._url(self._create(client, base_url)))
        assert r.status_code == 200, r.text
        assert r.json() == {"reset_schema": RESET_SCHEMA}

    def test_missing_openenv_server_is_404(self, client):
        assert client.get(self._url("nope")).status_code == 404


class TestVersion:
    def test_reports_server_version(self, client, session_manager):
        with serve_in_thread() as base_url:
            r = client.post(
                "/api/projects/p1/openenv_servers",
                json={"name": "Live", "url": base_url},
            )
            openenv_server_id = r.json()["id"]
            r = client.get(
                f"/api/projects/p1/openenv_servers/{openenv_server_id}/version"
            )
            assert r.status_code == 200, r.text
            assert r.json() == {"openenv_version": f"{ENV_NAME}@{ENV_VERSION}"}

    def test_rereads_version_after_server_restart(self, client, session_manager):
        port = free_port()
        r = client.post(
            "/api/projects/p1/openenv_servers",
            json={"name": "Live", "url": f"http://127.0.0.1:{port}"},
        )
        openenv_server_id = r.json()["id"]
        url = f"/api/projects/p1/openenv_servers/{openenv_server_id}/version"
        with serve_in_thread(port=port, version="1.0.0"):
            assert client.get(url).json()["openenv_version"] == f"{ENV_NAME}@1.0.0"
        with serve_in_thread(port=port, version="2.0.0"):
            assert client.get(url).json()["openenv_version"] == f"{ENV_NAME}@2.0.0"

    def test_unreachable_url_is_502(self, client, session_manager):
        r = client.post(
            "/api/projects/p1/openenv_servers",
            json={"name": "Down", "url": f"http://127.0.0.1:{free_port()}"},
        )
        openenv_server_id = r.json()["id"]
        r = client.get(f"/api/projects/p1/openenv_servers/{openenv_server_id}/version")
        assert r.status_code == 502
        assert "/metadata" in r.json()["message"]

    def test_no_url_is_502(self, client, session_manager):
        r = client.post("/api/projects/p1/openenv_servers", json={"name": "Empty"})
        openenv_server_id = r.json()["id"]
        r = client.get(f"/api/projects/p1/openenv_servers/{openenv_server_id}/version")
        assert r.status_code == 502
        assert "no url" in r.json()["message"]

    def test_missing_openenv_server_is_404(self, client):
        r = client.get("/api/projects/p1/openenv_servers/nope/version")
        assert r.status_code == 404


class TestRunOpenEnvServer:
    @pytest.fixture
    def task(self, project):
        task = Task(name="T", instruction="i", parent=project)
        task.save_to_file()
        with patch("kiln_server.task_api.project_from_id", return_value=project):
            yield task

    @pytest.fixture
    def lookup(self, client, task):
        def _lookup(tool_ids: list[str]) -> dict:
            r = client.post(
                f"/api/projects/p1/tasks/{task.id}/run_openenv_server",
                json={"tool_ids": tool_ids},
            )
            assert r.status_code == 200, r.text
            return r.json()

        return _lookup

    @pytest.fixture
    def make_openenv_server(self, client):
        def _make(name: str) -> str:
            r = client.post(
                "/api/projects/p1/openenv_servers",
                json={"name": name, "named_reset_kwargs": ACME_OPTIONS},
            )
            assert r.status_code == 200, r.text
            return r.json()["id"]

        return _make

    def test_no_openenv_server(self, lookup):
        empty = {"openenv_server": None, "error": None}
        assert lookup([]) == empty
        assert lookup(["kiln_tool::add_numbers"]) == empty

    def test_one_openenv_server(self, lookup, make_openenv_server):
        acme = make_openenv_server("Acme")
        body = lookup(
            [build_openenv_tool_id(acme, "search"), build_openenv_tool_id(acme, "get")]
        )
        assert body["error"] is None
        assert body["openenv_server"]["id"] == acme
        assert body["openenv_server"]["named_reset_kwargs"] == ACME_OPTIONS

    def test_two_openenv_servers(self, lookup, make_openenv_server):
        acme, beta = make_openenv_server("Acme"), make_openenv_server("Beta")
        body = lookup(
            [
                build_openenv_tool_id(acme, "search"),
                build_openenv_tool_id(beta, "search"),
            ]
        )
        assert body == {
            "openenv_server": None,
            "error": "Your tools use more than one OpenEnv server (Acme, Beta). A run can only use one.",
        }

    def test_missing_openenv_server(self, lookup):
        body = lookup([build_openenv_tool_id("gone", "search")])
        assert body == {
            "openenv_server": None,
            "error": "OpenEnv server gone wasn't found.",
        }

    def test_unknown_task(self, client, task):
        r = client.post(
            "/api/projects/p1/tasks/nope/run_openenv_server", json={"tool_ids": []}
        )
        assert r.status_code == 404
