"""Builds the Kiln MCP server: a stateless Streamable HTTP endpoint that the
desktop app mounts at `MCP_PATH`."""

import asyncio
import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager, suppress
from pathlib import Path

import httpx
from fastapi import FastAPI
from kiln_ai.utils.config import local_api_base_url
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import StreamableHTTPASGIApp
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from kiln_mcp_server import skill_files
from kiln_mcp_server.addresses import transport_security_for
from kiln_mcp_server.api_tool.policy import ConnectionPolicy
from kiln_mcp_server.api_tool.route_index import RouteIndex
from kiln_mcp_server.api_tool.tmp_files import TmpFileStore
from kiln_mcp_server.api_tool.tool import ApiToolDeps, register_call_kiln_api
from kiln_mcp_server.skill_tool import register_skill_tool
from kiln_mcp_server.texts import SERVER_INSTRUCTIONS

MCP_PATH = "/mcp"
SERVER_NAME = "kiln"
TMP_SWEEP_INTERVAL_SECONDS = 3600.0


class McpEndpoint:
    """The ASGI endpoint of the `/mcp` route.

    Only POST is served. A stateless server has no server-to-client stream, and
    the SDK would otherwise hold a `GET` open as an empty event stream forever.
    """

    # Read by GitSyncMiddleware: the MCP request itself is not wrapped in a
    # write lock. The REST calls a tool makes pass through the middleware.
    _git_sync_no_write_lock = True

    def __init__(self, inner: ASGIApp) -> None:
        self._inner = inner

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] != "POST":
            response = Response(status_code=405, headers={"Allow": "POST"})
            await response(scope, receive, send)
            return
        await self._inner(scope, receive, send)


class KilnMcpServer:
    def __init__(self, mcp: FastMCP, tmp_files: TmpFileStore) -> None:
        self._mcp = mcp
        self._tmp_files = tmp_files
        self.asgi_app = McpEndpoint(StreamableHTTPASGIApp(mcp.session_manager))

    @asynccontextmanager
    async def run(self) -> AsyncIterator[None]:
        """Serve requests while the context is open. Enter once per server,
        in the app's lifespan.

        Temp files of earlier runs are removed on entry, and expired ones every
        hour while the server runs.
        """
        await asyncio.to_thread(self._tmp_files.purge_all)
        sweep = asyncio.create_task(
            sweep_expired_tmp_files(self._tmp_files, TMP_SWEEP_INTERVAL_SECONDS)
        )
        try:
            async with self._mcp.session_manager.run():
                yield
        finally:
            sweep.cancel()
            with suppress(asyncio.CancelledError):
                await sweep


async def sweep_expired_tmp_files(tmp_files: TmpFileStore, interval: float) -> None:
    while True:
        await asyncio.sleep(interval)
        await asyncio.to_thread(tmp_files.purge_expired)


@contextmanager
def _preserve_root_logging() -> Iterator[None]:
    """Undo the `logging.basicConfig` call that FastMCP makes on construction,
    so the host app keeps its own logging setup."""
    root = logging.getLogger()
    handlers = list(root.handlers)
    level = root.level
    try:
        yield
    finally:
        for handler in list(root.handlers):
            if handler not in handlers:
                root.removeHandler(handler)
        root.setLevel(level)


def build_kiln_mcp_server(
    *,
    api_app: FastAPI,
    app_version: str,
    host: str,
    port: int,
    tmp_root: Path,
    api_transport: httpx.AsyncBaseTransport | None = None,
) -> KilnMcpServer:
    """Build a new server for `api_app`, bound to `host` and `port`.

    `call_kiln_api` reaches the routes that `api_app` has at this moment, over
    loopback HTTP, or through `api_transport` when one is given. Files that it
    saves go in `tmp_root`.

    Raises RuntimeError when the skill files are missing from the package, so a
    broken bundle fails at start rather than at an agent's first call.
    """
    with _preserve_root_logging():
        mcp = FastMCP(
            name=SERVER_NAME,
            instructions=SERVER_INSTRUCTIONS,
            stateless_http=True,
            json_response=False,
            log_level="WARNING",
            transport_security=transport_security_for(host),
        )
    # FastMCP has no public argument for the version it reports in serverInfo.
    mcp._mcp_server.version = app_version

    tmp_files = TmpFileStore(tmp_root)
    api_deps = ApiToolDeps(
        api_base_url=local_api_base_url(host, port),
        route_index=RouteIndex.from_app(api_app),
        policy=ConnectionPolicy(),
        tmp_files=tmp_files,
        transport=api_transport,
    )

    register_skill_tool(mcp, bound_host=host, bound_port=port)
    register_call_kiln_api(mcp, api_deps)
    skill_files.get_index()

    # Creates mcp.session_manager; the Starlette app it returns is not used.
    mcp.streamable_http_app()
    return KilnMcpServer(mcp, tmp_files)
