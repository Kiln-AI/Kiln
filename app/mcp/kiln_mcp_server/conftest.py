import json
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from kiln_mcp_server.server import MCP_PATH, KilnMcpServer, build_kiln_mcp_server

MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


def jsonrpc(method: str, params: dict | None = None, request_id: int = 1) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params or {},
    }


def sse_message(body: str) -> dict:
    """The JSON-RPC message of a one-message SSE response body."""
    for line in body.splitlines():
        if line.startswith("data:"):
            return json.loads(line[len("data:") :])
    raise AssertionError(f"no data line in response: {body!r}")


def host_app(server: KilnMcpServer) -> Starlette:
    """A minimal app that mounts `server` the way the desktop app does."""

    @asynccontextmanager
    async def lifespan(_app: Starlette):
        async with server.run():
            yield

    return Starlette(
        routes=[Route(MCP_PATH, endpoint=server.asgi_app)], lifespan=lifespan
    )


@pytest.fixture
def mcp_client() -> Iterator[TestClient]:
    """An HTTP client for a server built for the default loopback bind."""
    server = build_kiln_mcp_server(app_version="9.9.9", host="127.0.0.1", port=8757)
    with TestClient(host_app(server), base_url="http://localhost:8757") as client:
        yield client


def write_tree(root: Path, files: dict[str, str]) -> Path:
    for key, text in files.items():
        path = root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    return root
