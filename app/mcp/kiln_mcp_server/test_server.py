import logging

import pytest
from starlette.testclient import TestClient

from kiln_mcp_server import skill_files
from kiln_mcp_server.conftest import MCP_HEADERS, host_app, jsonrpc, sse_message
from kiln_mcp_server.server import (
    MCP_PATH,
    SERVER_NAME,
    McpEndpoint,
    build_kiln_mcp_server,
)
from kiln_mcp_server.texts import SERVER_INSTRUCTIONS

INITIALIZE_PARAMS = {
    "protocolVersion": "2025-06-18",
    "capabilities": {},
    "clientInfo": {"name": "test", "version": "1"},
}


def post(client: TestClient, method: str, params: dict | None = None, **kwargs):
    return client.post(
        MCP_PATH,
        json=jsonrpc(method, params),
        headers={**MCP_HEADERS, **kwargs.pop("headers", {})},
        **kwargs,
    )


def result_of(client: TestClient, method: str, params: dict | None = None) -> dict:
    response = post(client, method, params)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    return sse_message(response.text)["result"]


def test_server_info_and_instructions(mcp_client):
    result = result_of(mcp_client, "initialize", INITIALIZE_PARAMS)
    assert result["serverInfo"]["name"] == SERVER_NAME == "kiln"
    assert result["serverInfo"]["version"] == "9.9.9"
    assert result["instructions"] == SERVER_INSTRUCTIONS


def test_tools_list_has_the_skill_tool(mcp_client):
    tools = result_of(mcp_client, "tools/list")["tools"]
    assert [tool["name"] for tool in tools] == ["kiln_skill"]


def test_no_prompts_and_no_resources(mcp_client):
    assert result_of(mcp_client, "prompts/list")["prompts"] == []
    assert result_of(mcp_client, "resources/list")["resources"] == []


def test_the_skill_tool_serves_the_shipped_skill(mcp_client):
    result = result_of(
        mcp_client, "tools/call", {"name": "kiln_skill", "arguments": {}}
    )
    assert result["isError"] is False
    assert result["content"][0]["text"].startswith("# Kiln")


def test_a_broken_skill_bundle_fails_the_build(monkeypatch):
    def missing_index():
        raise RuntimeError(skill_files.E_NO_SKILL_MD)

    monkeypatch.setattr(skill_files, "get_index", missing_index)
    with pytest.raises(RuntimeError, match=r"no SKILL\.md"):
        build_kiln_mcp_server(app_version="1", host="127.0.0.1", port=8757)


def test_building_a_server_keeps_the_root_logging_setup():
    root = logging.getLogger()
    saved_handlers, saved_level = list(root.handlers), root.level
    # FastMCP's basicConfig only adds a handler to a root logger with none.
    for handler in saved_handlers:
        root.removeHandler(handler)
    root.setLevel(logging.ERROR)
    try:
        build_kiln_mcp_server(app_version="1", host="127.0.0.1", port=8757)
        assert root.handlers == []
        assert root.level == logging.ERROR
    finally:
        for handler in saved_handlers:
            root.addHandler(handler)
        root.setLevel(saved_level)


def test_two_servers_in_one_process_both_run():
    servers = [
        build_kiln_mcp_server(app_version=version, host="127.0.0.1", port=8757)
        for version in ("1", "2")
    ]
    with (
        TestClient(host_app(servers[0]), base_url="http://localhost:8757") as first,
        TestClient(host_app(servers[1]), base_url="http://localhost:8757") as second,
    ):
        assert (
            result_of(first, "initialize", INITIALIZE_PARAMS)["serverInfo"]["version"]
            == "1"
        )
        assert (
            result_of(second, "initialize", INITIALIZE_PARAMS)["serverInfo"]["version"]
            == "2"
        )


@pytest.mark.parametrize("method", ["GET", "DELETE", "PUT"])
def test_only_post_is_served(mcp_client, method):
    response = mcp_client.request(method, MCP_PATH, headers=MCP_HEADERS)
    assert response.status_code == 405
    assert response.headers["allow"] == "POST"


def test_loopback_build_refuses_other_hosts_and_origins(mcp_client):
    assert (
        post(mcp_client, "tools/list", headers={"Host": "evil.com"}).status_code == 421
    )
    assert (
        post(
            mcp_client, "tools/list", headers={"Origin": "http://evil.com"}
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "headers",
    [
        {"Host": "localhost"},
        {"Host": "localhost:9000"},
        {"Host": "127.0.0.1:8757"},
        {"Host": "[::1]:8757"},
        {"Origin": "http://localhost:5173"},
    ],
)
def test_loopback_build_accepts_loopback_names_on_any_port(mcp_client, headers):
    assert post(mcp_client, "tools/list", headers=headers).status_code == 200


def test_wildcard_build_has_no_host_or_origin_check():
    server = build_kiln_mcp_server(app_version="1", host="0.0.0.0", port=8757)
    with TestClient(host_app(server), base_url="http://localhost:8757") as client:
        assert (
            post(client, "tools/list", headers={"Host": "evil.com"}).status_code == 200
        )
        assert (
            post(
                client, "tools/list", headers={"Origin": "http://evil.com"}
            ).status_code
            == 200
        )


def test_the_endpoint_bypasses_the_git_sync_write_lock():
    assert McpEndpoint._git_sync_no_write_lock is True
