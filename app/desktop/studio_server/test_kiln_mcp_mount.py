import asyncio
import json
import socket
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, TextContent
from starlette.requests import Request
from starlette.routing import Mount, Route

from app.desktop import desktop_server
from app.desktop.desktop_server import ThreadedServer, make_app, server_config
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
    assert sorted(tool["name"] for tool in tools) == ["call_kiln_api", "kiln_skill"]


def test_the_temp_folder_is_the_test_folder(app, kiln_mcp_tmp_root):
    kiln_mcp_tmp_root.mkdir(mode=0o700)
    (kiln_mcp_tmp_root / "kiln_api_old.json").write_text("{}")
    with TestClient(app, base_url="http://localhost:8757"):
        assert list(kiln_mcp_tmp_root.iterdir()) == []


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


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _text(result: CallToolResult) -> str:
    (content,) = result.content
    assert isinstance(content, TextContent)
    return content.text


async def _agent_session(url: str) -> dict[str, CallToolResult]:
    async with streamable_http_client(url) as (read, write, _):
        async with ClientSession(read, write) as client:
            await client.initialize()
            return {
                "skill": await client.call_tool("kiln_skill", {}),
                "ping": await client.call_tool(
                    "call_kiln_api", {"method": "GET", "url_path": "/ping"}
                ),
                "projects": await client.call_tool(
                    "call_kiln_api", {"method": "GET", "url_path": "/api/projects/"}
                ),
                "unknown": await client.call_tool(
                    "call_kiln_api", {"method": "GET", "url_path": "/api/nope"}
                ),
                "blocked": await client.call_tool(
                    "call_kiln_api", {"method": "GET", "url_path": "/api/jobs/events"}
                ),
            }


def test_end_to_end_on_the_running_app():
    port = _free_port()
    server = ThreadedServer(config=server_config(port, "127.0.0.1"))
    with server.run_in_thread():
        results = asyncio.run(_agent_session(f"http://127.0.0.1:{port}/mcp"))
        stop_started = time.monotonic()
    assert time.monotonic() - stop_started < 5

    assert results["skill"].isError is False
    assert _text(results["skill"]).startswith("# Kiln")
    assert json.loads(_text(results["ping"])) == {"status_code": 200, "body": "pong"}
    projects = json.loads(_text(results["projects"]))
    assert projects["status_code"] == 200
    assert isinstance(projects["body"], list)
    assert results["unknown"].isError is True
    assert _text(results["unknown"]).startswith(
        "No Kiln API endpoint matches GET /api/nope."
    )
    assert results["blocked"].isError is True
    assert _text(results["blocked"]).startswith(
        "The endpoint GET /api/jobs/events is not available to agents over MCP."
    )
