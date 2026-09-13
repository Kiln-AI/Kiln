"""The wire Kiln talks to: an OpenEnv-shaped FastAPI app over one world.

The message shapes are OpenEnv's, but the `openenv` package is not a dependency — it brings
several hundred megabytes of transitive dependencies for a protocol that is four message
types. Kiln's own test server already speaks this subset; this is the same shape with a real
world behind it.

One session is one episode. `reset` builds an instance, `step` calls tools on it, `state`
reports, `close` destroys it, and a dropped socket or an idle timeout destroys it too — an
instance is a temp directory, and nothing may leak one.

Errors never end the session. A malformed `step` gets an `invalid_action` frame and the loop
keeps reading; Kiln's session manager happens to raise on the first error frame, but a
debugging client should be able to send a bad message and carry on.
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .errors import ToolError, UnknownTool, WorldBug
from .instances import Instance
from .world import World

logger = logging.getLogger(__name__)


class _Session:
    __slots__ = ("episode_id", "instance", "step_count")

    def __init__(self) -> None:
        self.instance: Instance | None = None
        self.episode_id: str | None = None
        self.step_count = 0


def app(
    world: World,
    *,
    include_control_tools: bool = False,
    max_concurrent_envs: int = 500,
    session_timeout: float | None = 3600.0,
) -> FastAPI:
    api = FastAPI()
    # Capacity is per app, not per process: a test (or a fault run) may serve several
    # worlds from one interpreter, and one world's sessions must not fill another's budget.
    capacity = asyncio.Lock()
    active = 0

    @api.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "healthy"}

    @api.get("/metadata")
    async def metadata() -> dict[str, Any]:
        # Read at request time: a world that suffixes its version (a seeded fault, say)
        # must be visible on the very next request.
        return {
            "name": world.name,
            "version": world.version,
            "description": _description(world),
        }

    @api.websocket("/ws")
    async def session_socket(websocket: WebSocket) -> None:
        nonlocal active
        await websocket.accept()
        async with capacity:
            if active >= max_concurrent_envs:
                await _send(
                    websocket,
                    _error(
                        f"this world serves at most {max_concurrent_envs} sessions at "
                        "once; raise max_concurrent_envs",
                        "capacity_reached",
                    ),
                )
                await _close_quietly(websocket)
                return
            active += 1

        session = _Session()
        try:
            await _run_session(
                websocket, world, session, include_control_tools, session_timeout
            )
        except (WebSocketDisconnect, asyncio.TimeoutError):
            pass
        finally:
            async with capacity:
                active -= 1
            if session.instance is not None:
                await asyncio.to_thread(session.instance.destroy)
            await _close_quietly(websocket)

    return api


async def _run_session(
    websocket: WebSocket,
    world: World,
    session: _Session,
    include_control_tools: bool,
    session_timeout: float | None,
) -> None:
    while True:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=session_timeout)
        try:
            message = json.loads(raw)
        except json.JSONDecodeError as e:
            await _send(websocket, _error(f"invalid JSON: {e}", "invalid_json"))
            continue
        if not isinstance(message, dict):
            await _send(
                websocket, _error("a message must be a JSON object", "invalid_json")
            )
            continue

        kind = message.get("type")
        if kind == "reset":
            await _reset(websocket, world, session, message)
        elif kind == "step":
            await _step(websocket, world, session, message, include_control_tools)
        elif kind == "state":
            await _send(websocket, {"type": "state", "data": _state(world, session)})
        elif kind == "close":
            return
        else:
            await _send(
                websocket, _error(f"unknown message type: {kind!r}", "unknown_type")
            )


async def _reset(
    websocket: WebSocket, world: World, session: _Session, message: dict[str, Any]
) -> None:
    data = dict(message.get("data") or {})
    episode_id = data.pop("episode_id", None) or uuid.uuid4().hex
    seed = data.pop("seed", None)
    fixture = data.pop("fixture", None)
    now = data.pop("now", None)

    if session.instance is not None:
        previous, session.instance = session.instance, None
        await asyncio.to_thread(previous.destroy)
    # Cleared up front: if the new instance fails to build, `state` must not go on reporting
    # the episode that was just destroyed.
    session.episode_id = None
    session.step_count = 0
    try:
        session.instance = await asyncio.to_thread(
            lambda: world.instance(fixture, seed=seed, now=now, **data)
        )
    except Exception as e:
        # Every refusal is the operator's: an unknown reset argument, a missing fixture, a
        # startup hook that raised. The session stays open so the next reset can succeed.
        if not isinstance(e, WorldBug):
            logger.exception("reset failed")
        await _send(websocket, _error(str(e), "reset_failed"))
        return

    session.episode_id = episode_id
    session.step_count = 0
    facts = _facts(session.instance)
    await _send(
        websocket,
        {
            "type": "observation",
            "data": {
                "observation": {
                    "tool_name": "",
                    "result": facts,
                    "error": None,
                    "metadata": facts,
                },
                "reward": None,
                "done": False,
                "metadata": facts,
            },
        },
    )


async def _step(
    websocket: WebSocket,
    world: World,
    session: _Session,
    message: dict[str, Any],
    include_control_tools: bool,
) -> None:
    action = message.get("data")
    if not isinstance(action, dict):
        await _send(
            websocket, _error("step 'data' must be an object", "invalid_action")
        )
        return
    action_type = action.get("type")
    if action_type not in ("list_tools", "call_tool"):
        await _send(
            websocket,
            _error(
                f"step 'data.type' must be 'list_tools' or 'call_tool', got "
                f"{action_type!r}",
                "invalid_action",
            ),
        )
        return

    if action_type == "list_tools":
        # Answered without an instance: Kiln lists a world's tools on a fresh session,
        # before any episode exists.
        listings = [t.listing() for t in world.tools.values() if not t.control]
        await _send(
            websocket,
            {
                "type": "observation",
                "data": {
                    "observation": {"tools": listings},
                    "reward": None,
                    "done": False,
                },
            },
        )
        return

    name = action.get("tool_name")
    if not isinstance(name, str):
        await _send(
            websocket,
            _error("step 'data.tool_name' must be a string", "invalid_action"),
        )
        return
    arguments = action.get("arguments")
    if arguments is not None and not isinstance(arguments, dict):
        await _send(
            websocket,
            _error("step 'data.arguments' must be an object", "invalid_action"),
        )
        return
    if session.instance is None:
        await _send(
            websocket,
            _error("no episode on this session; send a reset first", "no_episode"),
        )
        return

    instance = session.instance
    tool = world.tools.get(name)
    is_control = tool is not None and tool.control
    error: ToolError | None = None
    result: Any = None
    if is_control and not include_control_tools:
        error = UnknownTool(name)
    else:
        try:
            result = await asyncio.to_thread(
                lambda: instance.call(name, **(arguments or {}))
            )
        except ToolError as e:
            error = e
        except WorldBug as e:
            logger.exception("world bug in tool %r", name)
            await _send(websocket, _error(str(e), "world_bug"))
            return
        except Exception:
            logger.exception("unhandled error in tool %r", name)
            error = ToolError("internal", "internal error")

    if not is_control:
        session.step_count += 1
    await _send(
        websocket,
        {
            "type": "observation",
            "data": {
                "observation": {
                    "tool_name": name,
                    "result": None if error is not None else result,
                    "error": None if error is None else error.to_dict(),
                },
                "reward": None,
                "done": False,
            },
        },
    )


def _state(world: World, session: _Session) -> dict[str, Any]:
    instance = session.instance
    return {
        "episode_id": session.episode_id,
        "step_count": session.step_count,
        "fixture": instance.fixture if instance is not None else None,
        "now": instance.clock.iso() if instance is not None else None,
        "world": world.name,
    }


def _facts(instance: Instance) -> dict[str, Any]:
    return {
        "fixture": instance.fixture,
        "now": instance.clock.iso(),
        "tools": len(instance.tools()),
    }


def _error(message: str, code: str) -> dict[str, Any]:
    return {"type": "error", "data": {"message": message, "code": code}}


async def _send(websocket: WebSocket, payload: dict[str, Any]) -> None:
    # ensure_ascii=False: a world's own text (issue titles, comments, error
    # messages) travels as itself rather than as \uXXXX escapes.
    await websocket.send_text(json.dumps(payload, ensure_ascii=False))


async def _close_quietly(websocket: WebSocket) -> None:
    try:
        await websocket.close()
    except Exception:
        pass


def _description(world: World) -> str:
    readme = world.fixtures_dir.parent / "README.md"
    try:
        text = readme.read_text(encoding="utf-8")
    except OSError:
        return ""
    for block in text.split("\n\n"):
        stripped = block.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return ""


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@contextmanager
def serve_in_thread(
    world: World, *, port: int | None = None, include_control_tools: bool = True
) -> Iterator[str]:
    """Run this world on localhost in a background thread; yields its base URL."""
    import uvicorn

    port = port or free_port()
    config = uvicorn.Config(
        app(world, include_control_tools=include_control_tools),
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
            raise RuntimeError(f"world server for '{world.name}' did not start")
        time.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
