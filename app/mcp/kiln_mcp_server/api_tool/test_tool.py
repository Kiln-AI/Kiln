import json

import httpx
import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import CallToolResult, TextContent

from kiln_mcp_server.api_tool.policy import ConnectionPolicy
from kiln_mcp_server.api_tool.route_index import RouteIndex
from kiln_mcp_server.api_tool.tmp_files import TmpFileStore
from kiln_mcp_server.api_tool.tool import (
    CALL_KILN_API_TOOL_NAME,
    ApiToolDeps,
    register_call_kiln_api,
)


@pytest.fixture
def mcp(api_app, tmp_path) -> FastMCP:
    mcp = FastMCP(name="kiln")
    register_call_kiln_api(
        mcp,
        ApiToolDeps(
            api_base_url="http://kiln.test",
            route_index=RouteIndex.from_app(api_app),
            policy=ConnectionPolicy(),
            tmp_files=TmpFileStore(tmp_path / "kiln_mcp"),
            transport=httpx.ASGITransport(app=api_app),
            progress_interval=0.02,
        ),
    )
    return mcp


async def call(mcp: FastMCP, arguments: dict, **kwargs) -> CallToolResult:
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        return await client.call_tool(CALL_KILN_API_TOOL_NAME, arguments, **kwargs)


def body_of(result: CallToolResult):
    assert result.isError is False
    (content,) = result.content
    assert isinstance(content, TextContent)
    return json.loads(content.text)["body"]


async def test_lenient_arguments_are_accepted(mcp):
    result = await call(
        mcp,
        {
            "method": "get",
            "url_path": "/api/items/1",
            "query_params": {"tags": [1, True], "limit": 3},
            "body_limit": "50000",
            "unknown_argument": "ignored",
        },
    )
    assert body_of(result) == {"id": "1", "tags": ["1", "true"], "limit": 3}


async def test_a_wrong_argument_type_is_an_error(mcp):
    result = await call(mcp, {"method": "GET", "url_path": "/ping", "body_limit": "x"})
    assert result.isError is True


async def test_progress_reaches_a_client_that_asks_for_it(mcp):
    messages: list[str | None] = []

    async def on_progress(progress: float, total: float | None, message: str | None):
        messages.append(message)

    result = await call(
        mcp,
        {"method": "GET", "url_path": "/api/slow", "query_params": {"seconds": 0.2}},
        progress_callback=on_progress,
    )
    assert body_of(result) == {"slept": 0.2}
    assert messages
    assert messages[0] == "GET /api/slow: still running, 0 s"
