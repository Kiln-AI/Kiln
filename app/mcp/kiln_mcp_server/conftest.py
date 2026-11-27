import asyncio
import json
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse, StreamingResponse
from kiln_server.utils.agent_checks import ALLOW_AGENT, DENY_AGENT, with_mcp_deny
from pydantic import BaseModel
from starlette.applications import Starlette
from starlette.routing import Mount, Route
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


class Item(BaseModel):
    name: str


def make_api_app() -> FastAPI:
    """A small API with the route shapes that `call_kiln_api` has to handle."""
    app = FastAPI()

    @app.get("/ping", openapi_extra=ALLOW_AGENT)
    def ping() -> str:
        return "pong"

    @app.get("/api/items/{item_id}", openapi_extra=ALLOW_AGENT)
    def get_item(
        item_id: str, tags: Annotated[list[str] | None, Query()] = None, limit: int = 0
    ) -> dict:
        return {"id": item_id, "tags": tags, "limit": limit}

    @app.patch("/api/items/{item_id}", openapi_extra=ALLOW_AGENT)
    def patch_item(item_id: str, item: Item) -> dict:
        return {"id": item_id, "name": item.name}

    @app.get("/api/things/special", openapi_extra=with_mcp_deny(ALLOW_AGENT))
    def special_thing() -> dict:
        return {"special": True}

    @app.get("/api/things/{thing_id}", openapi_extra=ALLOW_AGENT)
    def get_thing(thing_id: str) -> dict:
        return {"thing": thing_id}

    @app.post("/api/secrets", openapi_extra=with_mcp_deny(DENY_AGENT))
    def secrets() -> dict:
        return {"secret": "s3cret"}

    @app.get("/api/text", openapi_extra=ALLOW_AGENT)
    def text() -> PlainTextResponse:
        return PlainTextResponse("plain text")

    @app.post("/api/stream", openapi_extra=ALLOW_AGENT)
    def stream() -> StreamingResponse:
        async def events() -> AsyncIterator[str]:
            yield "data: 1\n\n"
            yield "data: 2\n\n"
            yield "data: complete\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.get("/api/slow", openapi_extra=ALLOW_AGENT)
    async def slow(seconds: float) -> dict:
        await asyncio.sleep(seconds)
        return {"slept": seconds}

    @app.get("/api/missing", openapi_extra=ALLOW_AGENT)
    def missing() -> dict:
        raise HTTPException(status_code=404, detail="Item not found")

    @app.get("/not_api", openapi_extra=ALLOW_AGENT)
    def not_api() -> str:
        return "web"

    app.router.routes.append(Mount("/static", app=PlainTextResponse("static")))
    return app


@pytest.fixture
def api_app() -> FastAPI:
    return make_api_app()


def build_server(
    api_app: FastAPI,
    tmp_path: Path,
    host: str = "127.0.0.1",
    version: str = "9.9.9",
    ui_origin: str | None = None,
) -> KilnMcpServer:
    """A server whose `call_kiln_api` reaches `api_app` in process."""
    return build_kiln_mcp_server(
        api_app=api_app,
        app_version=version,
        host=host,
        port=8757,
        tmp_root=tmp_path / "kiln_mcp",
        ui_origin=ui_origin,
        api_transport=httpx.ASGITransport(app=api_app),
    )


@pytest.fixture
def mcp_client(api_app, tmp_path) -> Iterator[TestClient]:
    """An HTTP client for a server built for the default loopback bind."""
    server = build_server(api_app, tmp_path)
    with TestClient(host_app(server), base_url="http://localhost:8757") as client:
        yield client


def write_tree(root: Path, files: dict[str, str]) -> Path:
    for key, text in files.items():
        path = root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    return root
