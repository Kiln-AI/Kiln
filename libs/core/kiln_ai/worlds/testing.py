"""A tiny OpenEnv environment server for tests, with no Kiln imports.

Speaks the subset of OpenEnv's HTTP and WebSocket protocol that Kiln's session manager uses:
`/health`, `/metadata`, and `/ws` sessions carrying `reset`, `step` (with the MCP
`list_tools` and `call_tool` actions), `state` and `close`. Each session is one
`CounterEnv`: `reset(**kwargs)` starts an episode, `append_note` adds a
note and pays a reward, `read_notes` lists them, `explode` fails, and `state` reports
the notes.

`serve_in_thread` runs it in-process on a free localhost port. Built on `websockets`,
a dependency of `kiln_ai` itself, so importing this module needs nothing extra.
"""

from __future__ import annotations

import json
import socket
import threading
from contextlib import contextmanager
from http import HTTPStatus
from typing import Any, Callable, Iterator

from websockets.exceptions import ConnectionClosed
from websockets.http11 import Request, Response
from websockets.sync.server import ServerConnection, serve

ENV_NAME = "kiln_counter_env"
ENV_VERSION = "1.0.0"

TOOLS: list[dict[str, Any]] = [
    {
        "name": "append_note",
        "description": "Append a note to the episode's notebook.",
        "input_schema": {
            "type": "object",
            "properties": {"note": {"type": "string"}},
            "required": ["note"],
        },
    },
    {
        "name": "read_notes",
        "description": "Read every note in the notebook.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "explode",
        "description": "Always fails.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


class CounterEnv:
    def __init__(self) -> None:
        self.episode_id: str | None = None
        self.step_count = 0
        self.notes: list[str] = []
        self.fixture_id = "default"
        self.frozen_time: str | None = None
        self.extra: dict[str, Any] = {}

    def reset(self, **kwargs: Any) -> dict[str, Any]:
        self.episode_id = kwargs.pop("episode_id", None)
        self.fixture_id = str(kwargs.pop("fixture_id", "default"))
        self.frozen_time = kwargs.pop("frozen_time", None)
        self.extra = dict(kwargs)
        self.notes = []
        self.step_count = 0
        return {
            "observation": {
                "message": f"ready:{self.fixture_id}",
                "metadata": {
                    "fixture_id": self.fixture_id,
                    "frozen_time": self.frozen_time,
                },
            },
            "reward": None,
            "done": False,
            "metadata": {
                "fixture_id": self.fixture_id,
                "frozen_time": self.frozen_time,
            },
        }

    def step(self, action: dict[str, Any]) -> dict[str, Any]:
        kind = action.get("type")
        if kind == "list_tools":
            return {"observation": {"tools": TOOLS}, "reward": None, "done": False}
        if kind != "call_tool":
            raise ValueError(f"Unknown action type: {kind!r}")
        self.step_count += 1
        name = action.get("tool_name")
        args = action.get("arguments") or {}
        if name == "append_note":
            self.notes.append(str(args.get("note", "")))
            return {
                "observation": {
                    "tool_name": name,
                    "result": f"noted:{len(self.notes)}",
                    "error": None,
                },
                "reward": 1.0,
                "done": False,
            }
        if name == "read_notes":
            return {
                "observation": {
                    "tool_name": name,
                    "result": list(self.notes),
                    "error": None,
                },
                "reward": 0.0,
                "done": False,
            }
        if name == "explode":
            return {
                "observation": {
                    "tool_name": name,
                    "result": None,
                    "error": {"error_type": "execution_error", "message": "boom"},
                },
                "reward": -1.0,
                "done": True,
            }
        return {
            "observation": {
                "tool_name": name,
                "result": None,
                "error": {
                    "error_type": "tool_not_found",
                    "message": f"no tool {name!r}",
                },
            },
            "reward": None,
            "done": False,
        }

    @property
    def state(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "episode_id": self.episode_id,
            "step_count": self.step_count,
            "notes": list(self.notes),
            "fixture_id": self.fixture_id,
        }
        return result


def _handle_session(websocket: ServerConnection) -> None:
    env = CounterEnv()
    try:
        for raw in websocket:
            message = json.loads(raw)
            kind = message.get("type")
            try:
                if kind == "reset":
                    response = {
                        "type": "observation",
                        "data": env.reset(**(message.get("data") or {})),
                    }
                elif kind == "step":
                    response = {
                        "type": "observation",
                        "data": env.step(message.get("data") or {}),
                    }
                elif kind == "state":
                    response = {"type": "state", "data": env.state}
                elif kind == "close":
                    break
                else:
                    response = {
                        "type": "error",
                        "data": {
                            "message": f"Unknown message type: {kind}",
                            "code": "unknown_type",
                        },
                    }
            except Exception as e:
                response = {
                    "type": "error",
                    "data": {"message": str(e), "code": "error"},
                }
            websocket.send(json.dumps(response))
    except ConnectionClosed:
        pass
    finally:
        websocket.close()


def _http_routes(
    version: str,
) -> Callable[[ServerConnection, Request], Response | None]:
    """Answer the plain HTTP endpoints; `/ws` falls through to the WebSocket handshake."""
    bodies = {
        "/health": {"status": "healthy"},
        "/metadata": {"name": ENV_NAME, "version": version, "description": "test env"},
    }

    def process_request(
        connection: ServerConnection, request: Request
    ) -> Response | None:
        if request.path == "/ws":
            return None
        body = bodies.get(request.path)
        if body is None:
            return connection.respond(HTTPStatus.NOT_FOUND, "not found\n")
        response = connection.respond(HTTPStatus.OK, json.dumps(body))
        response.headers["Content-Type"] = "application/json"
        return response

    return process_request


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@contextmanager
def serve_in_thread(
    port: int | None = None, version: str = ENV_VERSION
) -> Iterator[str]:
    """Run the test environment on localhost in a background thread; yields its base URL."""
    port = port or free_port()
    server = serve(
        _handle_session,
        "127.0.0.1",
        port,
        process_request=_http_routes(version),
        max_size=None,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=10)
