import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.routing import Mount, Route

from app.desktop import desktop_server
from app.desktop.desktop_server import make_app, server_config
from app.desktop.git_sync.middleware import GitSyncMiddleware
from app.desktop.studio_server._version import __version__
from app.desktop.studio_server.kiln_mcp_mount import connect_kiln_mcp_server

MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


def mcp_post(client: TestClient, method: str, params: dict | None = None, **kwargs):
    return client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
        headers={**MCP_HEADERS, **kwargs.pop("headers", {})},
        **kwargs,
    )


def mcp_result(response) -> dict:
    assert response.status_code == 200
    data_line = next(
        line for line in response.text.splitlines() if line.startswith("data:")
    )
    return json.loads(data_line[len("data:") :])["result"]


@pytest.fixture
def app() -> FastAPI:
    return make_app()


def test_mcp_route_is_last_before_the_web_host(app):
    *_, mcp_route, web_host = app.routes
    assert isinstance(mcp_route, Route)
    assert mcp_route.path == "/mcp"
    assert mcp_route.endpoint is app.state.kiln_mcp_server.asgi_app
    assert isinstance(web_host, Mount)
    assert web_host.path == ""


def test_mcp_is_not_in_the_openapi_document(app):
    assert not any(path.startswith("/mcp") for path in app.openapi()["paths"])


def test_initialize_and_tools_list(app):
    with TestClient(app, base_url="http://localhost:8757") as client:
        initialize = mcp_result(
            mcp_post(
                client,
                "initialize",
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            )
        )
        tools = mcp_result(mcp_post(client, "tools/list"))["tools"]
    assert initialize["serverInfo"] == {"name": "kiln", "version": __version__}
    assert [tool["name"] for tool in tools] == ["kiln_skill"]


def test_get_is_not_allowed(app):
    with TestClient(app, base_url="http://localhost:8757") as client:
        response = client.get("/mcp")
    assert response.status_code == 405
    assert response.headers["allow"] == "POST"


def test_the_default_test_client_host_is_refused(app):
    with TestClient(app) as client:
        assert mcp_post(client, "tools/list").status_code == 421


def test_git_sync_middleware_sees_the_no_write_lock_marker(app):
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/mcp",
            "root_path": "",
            "query_string": b"",
            "headers": [],
            "app": app,
        }
    )
    endpoint = GitSyncMiddleware(app=MagicMock())._resolve_endpoint(request)
    assert endpoint is app.state.kiln_mcp_server.asgi_app
    assert getattr(endpoint, "_git_sync_no_write_lock", False) is True


def test_server_config_passes_host_and_port_and_bounds_shutdown():
    with patch.object(desktop_server, "make_app", return_value=FastAPI()) as factory:
        config = server_config(9000, "127.0.0.1")
    factory.assert_called_once_with(tk_root=None, host="127.0.0.1", port=9000)
    assert config.timeout_graceful_shutdown == 2


def test_a_wildcard_bind_has_no_host_check():
    app = make_app(host="0.0.0.0", port=9000)
    with TestClient(app, base_url="http://localhost:9000") as client:
        response = mcp_post(client, "tools/list", headers={"Host": "evil.com"})
    assert response.status_code == 200


def test_bare_make_app_uses_the_configured_host_and_port(monkeypatch):
    monkeypatch.setenv("KILN_LOCAL_API_HOST", "0.0.0.0")
    monkeypatch.setenv("KILN_LOCAL_API_PORT", "9100")
    with patch.object(desktop_server, "connect_kiln_mcp_server") as connect:
        app = make_app()
    connect.assert_called_once_with(app, host="0.0.0.0", port=9100)


def test_explicit_host_and_port_win_over_the_config():
    with patch.object(desktop_server, "connect_kiln_mcp_server") as connect:
        app = make_app(host="192.168.1.5", port=9200)
    connect.assert_called_once_with(app, host="192.168.1.5", port=9200)


def test_connect_reads_no_config():
    app = FastAPI()
    with patch(
        "kiln_ai.utils.config.Config.shared", side_effect=AssertionError("read config")
    ):
        connect_kiln_mcp_server(app, host="127.0.0.1", port=8757)
    assert app.state.kiln_mcp_server.asgi_app is app.routes[-1].endpoint
