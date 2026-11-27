import asyncio
import json
import logging
from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient

from kiln_mcp_server import skill_files
from kiln_mcp_server.api_tool import tool as api_tool
from kiln_mcp_server.conftest import (
    MCP_HEADERS,
    build_server,
    host_app,
    jsonrpc,
    sse_message,
)
from kiln_mcp_server.server import (
    MCP_PATH,
    SERVER_NAME,
    McpEndpoint,
    sweep_expired_tmp_files,
)
from kiln_mcp_server.texts import CALL_KILN_API_DESCRIPTION, SERVER_INSTRUCTIONS

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


def test_tools_list_has_exactly_the_two_tools(mcp_client):
    tools = result_of(mcp_client, "tools/list")["tools"]
    assert sorted(tool["name"] for tool in tools) == ["call_kiln_api", "kiln_skill"]


def test_call_kiln_api_schema(mcp_client):
    tools = result_of(mcp_client, "tools/list")["tools"]
    (tool,) = [tool for tool in tools if tool["name"] == "call_kiln_api"]
    assert "outputSchema" not in tool
    assert tool["description"] == CALL_KILN_API_DESCRIPTION
    query_value = [
        {"type": "string"},
        {"type": "integer"},
        {"type": "number"},
        {"type": "boolean"},
    ]
    assert tool["inputSchema"] == {
        "type": "object",
        "title": "call_kiln_apiArguments",
        "required": ["method", "url_path"],
        "properties": {
            "method": {
                "type": "string",
                "title": "Method",
                "enum": ["GET", "POST", "PATCH", "DELETE"],
                "description": api_tool.METHOD_DESCRIPTION,
            },
            "url_path": {
                "type": "string",
                "title": "Url Path",
                "description": api_tool.URL_PATH_DESCRIPTION,
            },
            "body": {
                "anyOf": [
                    {"type": "object", "additionalProperties": True},
                    {"type": "array", "items": {}},
                    {"type": "string"},
                    {"type": "null"},
                ],
                "default": None,
                "title": "Body",
                "description": api_tool.BODY_DESCRIPTION,
            },
            "query_params": {
                "anyOf": [
                    {
                        "type": "object",
                        "additionalProperties": {
                            "anyOf": [
                                *query_value,
                                {"type": "array", "items": {"anyOf": query_value}},
                                {"type": "null"},
                            ]
                        },
                    },
                    {"type": "null"},
                ],
                "default": None,
                "title": "Query Params",
                "description": api_tool.QUERY_PARAMS_DESCRIPTION,
            },
            "jq_filter": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "default": None,
                "title": "Jq Filter",
                "description": api_tool.JQ_FILTER_DESCRIPTION,
            },
            "body_limit": {
                "type": "integer",
                "default": 30000,
                "title": "Body Limit",
                "description": api_tool.BODY_LIMIT_DESCRIPTION,
            },
            "save_to_tmpfile": {
                "type": "boolean",
                "default": False,
                "title": "Save To Tmpfile",
                "description": api_tool.SAVE_TO_TMPFILE_DESCRIPTION,
            },
        },
    }


def test_call_kiln_api_reaches_the_api_app(mcp_client):
    result = result_of(
        mcp_client,
        "tools/call",
        {
            "name": "call_kiln_api",
            "arguments": {"method": "GET", "url_path": "/api/items/7"},
        },
    )
    assert result["isError"] is False
    assert json.loads(result["content"][0]["text"]) == {
        "status_code": 200,
        "body": {"id": "7", "tags": None, "limit": 0},
    }
    assert "structuredContent" not in result


def test_no_prompts_and_no_resources(mcp_client):
    assert result_of(mcp_client, "prompts/list")["prompts"] == []
    assert result_of(mcp_client, "resources/list")["resources"] == []


def test_the_skill_tool_serves_the_shipped_skill(mcp_client):
    result = result_of(
        mcp_client, "tools/call", {"name": "kiln_skill", "arguments": {}}
    )
    assert result["isError"] is False
    assert result["content"][0]["text"].startswith("# Kiln")


def test_a_ui_origin_reaches_the_skill_tool_description(api_app, tmp_path):
    server = build_server(api_app, tmp_path, ui_origin="http://localhost:5173")
    with TestClient(host_app(server), base_url="http://localhost:8757") as client:
        tools = result_of(client, "tools/list")["tools"]
    (skill_tool,) = [tool for tool in tools if tool["name"] == "kiln_skill"]
    description = skill_tool["description"]
    assert "http://localhost:5173, not http://localhost:8757" in description


def test_a_broken_skill_bundle_fails_the_build(monkeypatch, api_app, tmp_path):
    def missing_index():
        raise RuntimeError(skill_files.E_NO_SKILL_MD)

    monkeypatch.setattr(skill_files, "get_index", missing_index)
    with pytest.raises(RuntimeError, match=r"no SKILL\.md"):
        build_server(api_app, tmp_path)


def test_building_a_server_keeps_the_root_logging_setup(api_app, tmp_path):
    root = logging.getLogger()
    saved_handlers, saved_level = list(root.handlers), root.level
    # FastMCP's basicConfig only adds a handler to a root logger with none.
    for handler in saved_handlers:
        root.removeHandler(handler)
    root.setLevel(logging.ERROR)
    try:
        build_server(api_app, tmp_path)
        assert root.handlers == []
        assert root.level == logging.ERROR
    finally:
        for handler in saved_handlers:
            root.addHandler(handler)
        root.setLevel(saved_level)


def test_two_servers_in_one_process_both_run(api_app, tmp_path):
    servers = [
        build_server(api_app, tmp_path, version=version) for version in ("1", "2")
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


def test_wildcard_build_has_no_host_or_origin_check(api_app, tmp_path):
    server = build_server(api_app, tmp_path, host="0.0.0.0")
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


def test_run_removes_the_temp_files_of_earlier_runs(api_app, tmp_path):
    server = build_server(api_app, tmp_path)
    root = tmp_path / "kiln_mcp"
    root.mkdir(mode=0o700)
    (root / "kiln_api_old.json").write_text("{}")
    with TestClient(host_app(server), base_url="http://localhost:8757"):
        assert list(root.iterdir()) == []


async def test_the_sweep_purges_expired_files_every_interval():
    store = MagicMock()
    sweep = asyncio.create_task(sweep_expired_tmp_files(store, 0.01))
    await asyncio.sleep(0.1)
    sweep.cancel()
    with pytest.raises(asyncio.CancelledError):
        await sweep
    assert store.purge_expired.call_count >= 2
    store.purge_all.assert_not_called()
