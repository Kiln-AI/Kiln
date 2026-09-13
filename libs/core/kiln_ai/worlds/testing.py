"""A tiny OpenEnv environment server for tests, with no Kiln imports.

Speaks the subset of OpenEnv's HTTP and WebSocket protocol that Kiln's session manager uses:
`/health`, `/metadata`, and `/ws` sessions carrying `reset`, `step` (with the MCP
`list_tools` and `call_tool` actions), `state` and `close`. Each session is one
`CounterEnv`: `reset(**kwargs)` starts an episode, `append_note` adds a
note and pays a reward, `read_notes` lists them, `explode` fails, and `state` reports
the notes.

`ControlledCounterEnv` is the same env with the parts a Seahaven-shaped world has and
this one does not: coded errors, and unlisted control tools that report what the episode
changed. `create_app` and `serve_in_thread` take an `env_factory` so a test picks one;
the default is the plain `CounterEnv`, the "environment that knows nothing of control
tools" baseline.

`serve_in_thread` runs it in-process on a free localhost port.
"""

from __future__ import annotations

import hashlib
import json
import socket
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

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
    TOOLS: list[dict[str, Any]] = TOOLS

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
            return {"observation": {"tools": self.TOOLS}, "reward": None, "done": False}
        if kind != "call_tool":
            raise ValueError(f"Unknown action type: {kind!r}")
        name = action.get("tool_name")
        args = action.get("arguments") or {}
        control = self.control_call(name, args)
        if control is not None:
            # A control call is the client's own probe, not a decision the episode
            # made: it must not move step_count.
            return control
        self.step_count += 1
        return self.tool_call(name, args)

    def control_call(self, name: Any, args: dict[str, Any]) -> dict[str, Any] | None:
        """This env serves no control tools; `ControlledCounterEnv` does."""
        return None

    def tool_call(self, name: Any, args: dict[str, Any]) -> dict[str, Any]:
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
                    "error": {"type": "execution_error", "message": "boom"},
                },
                "reward": -1.0,
                "done": True,
            }
        return {
            "observation": {
                "tool_name": name,
                "result": None,
                "error": {"type": "tool_not_found", "message": f"no tool {name!r}"},
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


CONTROLLED_TOOLS: list[dict[str, Any]] = [
    *TOOLS,
    {
        "name": "fail_coded",
        "description": "Always fails with a coded product error.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "fail_internal",
        "description": "Always fails with a coded world failure.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


class ControlledCounterEnv(CounterEnv):
    """A `CounterEnv` that also speaks coded errors and serves control tools.

    The control tools are not in `TOOLS` and never will be: a client reaches them only
    because it asks for them by name, which is the whole point of the control path."""

    TOOLS: list[dict[str, Any]] = CONTROLLED_TOOLS

    def reset(self, **kwargs: Any) -> dict[str, Any]:
        data = super().reset(**kwargs)
        # `tools` appears only here, `fixture_id` in both: a client that merges the two
        # sees the fill and the conflict at once.
        data["observation"]["result"] = {
            "fixture_id": f"result:{self.fixture_id}",
            "now": self.frozen_time,
            "tools": len(self.TOOLS),
        }
        return data

    def control_call(self, name: Any, args: dict[str, Any]) -> dict[str, Any] | None:
        if name == "controller_changes":
            return self._observation(name, result=self.changes, error=self.diff_error)
        if name == "controller_digest":
            return self._observation(name, result=self.digest)
        return None

    def tool_call(self, name: Any, args: dict[str, Any]) -> dict[str, Any]:
        if name == "fail_coded":
            return self._observation(
                name,
                error={
                    "code": "invalid_input",
                    "message": "bad note",
                    "details": {"field": "note"},
                },
            )
        if name == "fail_internal":
            return self._observation(
                name,
                error={"code": "internal", "message": "tripped", "details": None},
            )
        return super().tool_call(name, args)

    @property
    def changes(self) -> list[dict[str, Any]]:
        return [
            {
                "table": "notes",
                "op": "insert",
                "key": {"n": i},
                "before": None,
                "after": {"n": i, "note": note},
            }
            for i, note in enumerate(self.notes)
        ]

    @property
    def diff_error(self) -> dict[str, Any] | None:
        """A poisoned note makes the diff fail, so a client can be shown a control tool
        that is served and broken rather than absent."""
        if "poison" in self.notes:
            return {"code": "db_error", "message": "diff failed", "details": None}
        return None

    @property
    def digest(self) -> str:
        return hashlib.sha256("\n".join(self.notes).encode()).hexdigest()

    @staticmethod
    def _observation(
        name: Any, result: Any = None, error: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return {
            "observation": {
                "tool_name": name,
                "result": None if error is not None else result,
                "error": error,
            },
            "reward": None,
            "done": False,
        }


def create_app(
    version: str = ENV_VERSION,
    env_factory: Callable[[], CounterEnv] = CounterEnv,
) -> FastAPI:
    app = FastAPI()

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "healthy"}

    @app.get("/metadata")
    async def metadata() -> dict[str, Any]:
        return {"name": ENV_NAME, "version": version, "description": "test env"}

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        await websocket.accept()
        env = env_factory()
        try:
            while True:
                raw = await websocket.receive_text()
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
                await websocket.send_text(json.dumps(response))
        except WebSocketDisconnect:
            pass
        finally:
            try:
                await websocket.close()
            except Exception:
                pass

    return app


app = create_app()


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@contextmanager
def serve_in_thread(
    port: int | None = None,
    version: str = ENV_VERSION,
    env_factory: Callable[[], CounterEnv] = CounterEnv,
) -> Iterator[str]:
    """Run the test environment on localhost in a background thread; yields its base URL."""
    import uvicorn

    port = port or free_port()
    config = uvicorn.Config(
        create_app(version, env_factory),
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline:
            server.should_exit = True
            raise RuntimeError("test OpenEnv server did not start")
        time.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
