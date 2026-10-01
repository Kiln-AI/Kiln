"""World sessions: the OpenEnv sessions Kiln opens, resets, drives and settles for
one episode each.

OpenEnv (https://github.com/huggingface/OpenEnv) splits an environment in two. The
`Environment` is what an env does: `reset`, `step`, `state`, `close`. A *provider* is
how you obtain a running one. Today Kiln does not start or stop environments: a world
names the URL of one that is already running (`World.env_url`). The session manager
here is the session layer plus the bookkeeping only Kiln needs: keying the trace by the
environment's content, recording what graders will read, and closing sessions. It is
also the place that will own launching local worlds when Kiln does that, the way
`MCPSessionManager` spawns local MCP servers and connects to remote ones behind one
interface.

An env author writes OpenEnv code and no Kiln code. Every Kiln-side value derives from
what OpenEnv already exposes:

    world_version   the environment's reported name and version
    refresh         re-read `/metadata`, so a new version on the same URL is seen
    start_episode   open a `/ws` session and `reset(**reset_kwargs)`
    call_tool       `step(CallToolAction)`
    end_episode     `state`, then close the session
    release         close the session

One session per episode; sessions are closed by `end_episode`, so the record on the
trace is the durable state.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol

import httpx
from pydantic import JsonValue
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, WebSocketException

from kiln_ai.datamodel.world import (
    OpenEnvTool,
    World,
    WorldEpisode,
    WorldReset,
)
from kiln_ai.run_context import generate_episode_id

logger = logging.getLogger(__name__)

STEP_TIMEOUT_S = 600.0
"""How long one reset, step or state call may take. Tool calls block the LLM loop, so
this is deliberately generous; an environment enforces its own per-tool timeouts.
A call that stalls the environment's event loop never reaches this ceiling: the
keepalive below closes the session once a ping goes PING_TIMEOUT_S unanswered, so a
stalled loop surfaces as a closed session after roughly two minutes, not a step timeout
at ten."""

PING_INTERVAL_S = 20.0
"""How often the websockets keepalive pings the environment. Stated rather than left to
the library's default so a default that moves cannot silently change what a run
measured."""

PING_TIMEOUT_S = 120.0
"""How long an unanswered ping may go before the keepalive closes the session. A world
server doing synchronous work stalls its event loop and cannot answer a ping: the
library's 20s timeout would drop every session on the box at once, so this matches the
120s a world framework's own client allows for it. Stated for the same reason as the
interval above."""

CONNECT_TIMEOUT_S = 30.0
"""How long reading `/metadata` or opening a session may take before the environment
is treated as unreachable."""

CLOSE_TIMEOUT_S = 5.0
"""How long to wait for the environment to close a session after Kiln asks it to."""

MAX_MESSAGE_BYTES = 64 * 1024 * 1024
"""The largest message Kiln accepts from an environment. Generous, because a `state`
can be large, but finite: a runaway environment closes the session with an error
instead of exhausting memory or writing an enormous trace."""

_ERROR_PREVIEW_CHARS = 500

_CAPACITY_HINT = (
    " The environment holds max_concurrent_envs sessions at once (OpenEnv's default "
    "is 1) and Kiln runs up to 25 eval jobs at once: start the server with "
    "max_concurrent_envs of at least 25, then re-run the eval to run the jobs that "
    "failed."
)


class OpenEnvError(RuntimeError):
    """The environment answered a request with an error, or could not be reached."""


class OpenEnvTransientError(OpenEnvError):
    """A failure that may not recur on a fresh session: the connection dropped or
    timed out, or the environment was at its session capacity. The eval runner
    retries these."""


class OpenEnvRejectedError(OpenEnvError):
    """The environment answered a message with an error. The session is still in
    step, so it stays usable."""


def read_observation_error(error: Any) -> tuple[str | None, str | None, Any]:
    """An observation's `error` as `(message, code, details)`.

    Kiln never rejects a shape here. OpenEnv declares `{error_type, message}` and
    forbids extra keys, so `error_type` is read first; a `code` is read after it, for
    an environment that reports one instead. `details` is whatever a dict carried,
    which a conformant environment has nowhere to put. An error that is not a dict,
    or one with no message, degrades to its own text rather than failing the call."""
    if error is None:
        return None, None, None
    if not isinstance(error, dict):
        return str(error), None, None
    code = error.get("error_type") or error.get("code")
    return (
        str(error.get("message") or error),
        str(code) if code else None,
        error.get("details"),
    )


@dataclass(frozen=True)
class ToolCallOutcome:
    """What one `step(CallToolAction)` came back with.

    An environment that reports an error as a dict has whatever structure it carries
    read out alongside the human-readable message. `error_code` is OpenEnv's own
    `error_type` -- one of `execution_error`, `invalid_args`, `transport_error`,
    `tool_not_found`, `timeout` -- and falls back to a `code` for an environment that
    predates that shape or does not use it. `error_details` is whatever a `details`
    carried, which a conformant environment does not send: `ToolError` forbids extra
    keys, so a world with a code and details of its own puts them somewhere this field
    does not reach. Neither is a shape Kiln insists on; an error that is not a dict at
    all leaves both None."""

    result: Any
    error: str | None
    reward: float | None
    done: bool
    error_code: str | None = None
    error_details: Any = None


class WorldSessionManager(Protocol):
    """The seam the eval runner and the tool proxies call. `OpenEnvSessionManager` is the
    implementation; tests substitute a fake."""

    async def world_version(self, world: World) -> str:
        """Identity of the environment code an episode would run, without starting one.
        One per environment, whatever an episode is reset with. Folded into the trace
        fingerprint: change it and traces regenerate."""
        ...

    async def refresh(self, world: World) -> None:
        """Re-read the environment's identity, so an environment restarted at a new
        version on the same URL is seen as new. Its tools are re-listed when the
        version changed."""
        ...

    async def list_tools(self, world: World, fresh: bool = False) -> list[OpenEnvTool]:
        """The tools the world's environment serves. Cached per environment version;
        `fresh` re-reads the environment's metadata and tools."""
        ...

    async def start_episode(
        self, world: World, reset_kwargs: dict[str, JsonValue]
    ) -> WorldEpisode:
        """Open a session on the world's environment and reset it with `reset_kwargs`.
        The session stays live until `end_episode` or `release`."""
        ...

    async def call_tool(
        self, episode: WorldEpisode, tool_name: str, arguments: dict[str, Any]
    ) -> ToolCallOutcome:
        """Call one of the environment's tools inside a live episode."""
        ...

    async def end_episode(self, episode: WorldEpisode) -> WorldEpisode:
        """Read the environment's final state and close the session. Returns the
        episode with `final_state` set: the durable record graders read."""
        ...

    async def release(self, episode: WorldEpisode) -> None:
        """Close an episode's session without reading its state, e.g. after a
        failed generation."""
        ...

    async def shutdown(self) -> None:
        """Close every live session and forget every environment."""
        ...


@dataclass
class _EnvServer:
    world_id: str
    base_url: str
    world_version: str
    tools: list[OpenEnvTool] | None = None

    @property
    def ws_url(self) -> str:
        scheme, rest = self.base_url.split("://", 1)
        return f"{'wss' if scheme == 'https' else 'ws'}://{rest}/ws"


@dataclass
class _Session:
    episode_id: str
    ws: ClientConnection
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class OpenEnvSessionManager:
    """Drives sessions on running OpenEnv environments.

    What Kiln knows about each environment (its version and tools) is cached per world
    and re-read when the world's URL changes or `refresh` is called."""

    def __init__(self, step_timeout_s: float = STEP_TIMEOUT_S) -> None:
        self._step_timeout_s = step_timeout_s
        self._servers: dict[str, _EnvServer] = {}
        self._server_locks: dict[str, asyncio.Lock] = {}
        self._sessions: dict[str, _Session] = {}

    # ---- protocol ----

    async def world_version(self, world: World) -> str:
        server = await self._server_for(world)
        return server.world_version

    async def refresh(self, world: World) -> None:
        await self._server_for(world, refresh=True)

    async def list_tools(self, world: World, fresh: bool = False) -> list[OpenEnvTool]:
        server = await self._server_for(world, refresh=fresh)
        if server.tools is not None and not fresh:
            return server.tools
        async with self._connect(server) as ws:
            data = await self._request(
                ws, {"type": "step", "data": {"type": "list_tools"}}, "observation"
            )
        observation = data.get("observation") or {}
        raw_tools = observation.get("tools") or []
        tools = [
            OpenEnvTool(
                name=str(t.get("name")),
                description=str(t.get("description") or ""),
                input_schema=dict(t.get("input_schema") or t.get("inputSchema") or {}),
            )
            for t in raw_tools
            if isinstance(t, dict) and t.get("name")
        ]
        server.tools = tools
        return tools

    async def start_episode(
        self, world: World, reset_kwargs: dict[str, JsonValue]
    ) -> WorldEpisode:
        if world.id is None:
            raise ValueError("World must be saved before starting an episode")
        server = await self._server_for(world)
        episode_id = generate_episode_id()
        ws = await self._open(server)
        try:
            data = await self._request(
                ws,
                {"type": "reset", "data": {**reset_kwargs, "episode_id": episode_id}},
                "observation",
            )
        except BaseException:
            await self._end_session(ws)
            raise
        self._sessions[episode_id] = _Session(episode_id=episode_id, ws=ws)

        reset_metadata: dict[str, JsonValue] = {}
        reported = data.get("metadata")
        if not isinstance(reported, dict):
            reported = (data.get("observation") or {}).get("metadata")
        if isinstance(reported, dict):
            reset_metadata.update({str(k): v for k, v in reported.items()})
        return WorldEpisode(
            reset=WorldReset(world_id=world.id, reset_kwargs=reset_kwargs),
            episode_id=episode_id,
            world_version=server.world_version,
            reset_metadata=reset_metadata,
        )

    async def call_tool(
        self, episode: WorldEpisode, tool_name: str, arguments: dict[str, Any]
    ) -> ToolCallOutcome:
        session = self._sessions.get(episode.episode_id)
        if session is None:
            raise RuntimeError(
                f"Episode {episode.episode_id} has no live session; tools "
                "can only be called during generation"
            )
        async with session.lock:
            try:
                data = await self._request(
                    session.ws,
                    {
                        "type": "step",
                        "data": {
                            "type": "call_tool",
                            "tool_name": tool_name,
                            "arguments": arguments,
                        },
                    },
                    "observation",
                )
            except OpenEnvRejectedError:
                raise
            except BaseException:
                # A late answer to this call would be read as the answer to the next
                # one: OpenEnv responses carry no request id. The session is dropped
                # so nothing reads from it again.
                self._sessions.pop(episode.episode_id, None)
                await self._close_quietly(session.ws)
                raise
        reward = data.get("reward")
        observation = data.get("observation") or {}
        error, error_code, error_details = read_observation_error(
            observation.get("error")
        )
        return ToolCallOutcome(
            result=observation.get("result"),
            error=error,
            reward=float(reward)
            if isinstance(reward, (int, float)) and not isinstance(reward, bool)
            else None,
            done=bool(data.get("done", False)),
            error_code=error_code,
            error_details=error_details,
        )

    async def end_episode(self, episode: WorldEpisode) -> WorldEpisode:
        session = self._sessions.pop(episode.episode_id, None)
        if session is None:
            return episode
        try:
            async with session.lock:
                data = await self._request(session.ws, {"type": "state"}, "state")
        finally:
            await self._end_session(session.ws)
        state: dict[str, JsonValue] = {str(k): v for k, v in data.items()}
        return episode.model_copy(update={"final_state": state})

    async def release(self, episode: WorldEpisode) -> None:
        session = self._sessions.pop(episode.episode_id, None)
        if session is not None:
            await self._end_session(session.ws)

    async def shutdown(self) -> None:
        sessions = list(self._sessions.values())
        self._sessions.clear()
        self._servers.clear()
        await asyncio.gather(*(self._end_session(s.ws) for s in sessions))

    # ---- servers ----

    async def _server_for(self, world: World, refresh: bool = False) -> _EnvServer:
        """What Kiln knows about the world's environment: its address, reported
        identity and content version. Cached per world; re-read when the world's URL
        changes or on `refresh`. A refresh that finds the same version keeps the
        cached tools; a new version re-lists them."""
        if world.id is None:
            raise ValueError("World must be saved before its environment can be used")
        if not world.env_url:
            raise OpenEnvError(
                f"World '{world.name}' has no env_url. Kiln does not start "
                "environments: run the OpenEnv server yourself and point the world at "
                "it (e.g. http://127.0.0.1:8000)."
            )
        base_url = world.env_url.rstrip("/")
        lock = self._server_locks.setdefault(world.id, asyncio.Lock())
        async with lock:
            current = self._servers.get(world.id)
            if current is not None and current.base_url != base_url:
                current = None
            if current is not None and not refresh:
                return current
            server = await self._connect_remote(world, base_url)
            if current is not None and current.world_version == server.world_version:
                server.tools = current.tools
            self._servers[world.id] = server
            return server

    async def _connect_remote(self, world: World, base_url: str) -> _EnvServer:
        assert world.id
        async with httpx.AsyncClient(timeout=CONNECT_TIMEOUT_S) as client:
            try:
                response = await client.get(f"{base_url}/metadata")
                response.raise_for_status()
                meta = response.json()
            except Exception as e:
                raise OpenEnvError(
                    f"World '{world.name}' points at {base_url}, which did "
                    f"not answer /metadata: {e}"
                ) from e
        if not isinstance(meta, dict):
            raise OpenEnvError(
                f"World '{world.name}' points at {base_url}, whose /metadata is not "
                f"a JSON object: {_preview(meta)}"
            )
        name = str(meta.get("name") or world.name)
        version = meta.get("version")
        return _EnvServer(
            world_id=world.id,
            base_url=base_url,
            world_version=_compose_world_version(
                name, str(version) if version is not None else None
            ),
        )

    # ---- sessions ----

    async def _open(self, server: _EnvServer) -> ClientConnection:
        try:
            return await connect(
                server.ws_url,
                max_size=MAX_MESSAGE_BYTES,
                open_timeout=CONNECT_TIMEOUT_S,
                ping_interval=PING_INTERVAL_S,
                ping_timeout=PING_TIMEOUT_S,
            )
        except (OSError, ConnectionClosed, asyncio.TimeoutError) as e:
            raise OpenEnvTransientError(
                f"Could not open a session on {server.base_url}: {e}"
            ) from e
        except WebSocketException as e:
            raise OpenEnvError(
                f"{server.base_url} refused a session; is it an OpenEnv server? {e}"
            ) from e

    @asynccontextmanager
    async def _connect(self, server: _EnvServer) -> AsyncIterator[ClientConnection]:
        """A short-lived session for one request, ended however the request went."""
        ws = await self._open(server)
        try:
            yield ws
        finally:
            await self._end_session(ws)

    async def _send(self, ws: ClientConnection, message: dict[str, Any]) -> None:
        await ws.send(json.dumps(message, ensure_ascii=False))

    async def _request(
        self, ws: ClientConnection, message: dict[str, Any], expected_type: str
    ) -> dict[str, Any]:
        """Send one message and return the response's `data`. An error response
        raises `OpenEnvRejectedError`; a dropped or silent connection raises
        `OpenEnvTransientError`; any other reply, including one of the wrong type,
        raises `OpenEnvError`."""
        kind = message.get("type")
        try:
            await self._send(ws, message)
            raw = await asyncio.wait_for(ws.recv(), timeout=self._step_timeout_s)
        except ConnectionClosed as e:
            hint = _CAPACITY_HINT if kind == "reset" else ""
            raise OpenEnvTransientError(
                f"The environment closed the session: {e}.{hint}"
            ) from e
        except asyncio.TimeoutError as e:
            raise OpenEnvTransientError(
                f"The environment did not answer a '{kind}' message "
                f"within {self._step_timeout_s:g}s"
            ) from e
        try:
            response = json.loads(raw)
        except json.JSONDecodeError as e:
            raise OpenEnvError(
                f"The environment sent invalid JSON: {_preview(raw)}"
            ) from e
        if not isinstance(response, dict):
            raise OpenEnvError(
                f"The environment sent an unexpected message: {_preview(raw)}"
            )
        data = response.get("data")
        response_type = response.get("type")
        if response_type == "error":
            detail = data.get("message") if isinstance(data, dict) else data
            code = data.get("code") if isinstance(data, dict) else None
            rejection = (
                f"The environment rejected a '{kind}' message: {_preview(detail)}"
            )
            if str(code).lower() == "capacity_reached":
                raise OpenEnvTransientError(rejection + _CAPACITY_HINT)
            raise OpenEnvRejectedError(rejection)
        if response_type != expected_type:
            raise OpenEnvError(
                f"The environment answered a '{kind}' message with a "
                f"'{response_type}' message, not '{expected_type}'"
            )
        return data if isinstance(data, dict) else {}

    async def _end_session(self, ws: ClientConnection) -> None:
        """Tell the environment the session is over and wait for it to close the
        socket. OpenEnv frees the session's slot before it closes the socket, so
        waiting guarantees the slot is free before the next reset; on a server that
        holds one session, a bare close could leave the next reset over capacity.
        Every path that drops a session goes through here, including failures and
        shutdown; the socket is closed regardless."""
        try:
            await self._send(ws, {"type": "close"})
            await asyncio.wait_for(ws.wait_closed(), timeout=CLOSE_TIMEOUT_S)
        except (ConnectionClosed, asyncio.TimeoutError, OSError):
            pass
        finally:
            await self._close_quietly(ws)

    async def _close_quietly(self, ws: ClientConnection) -> None:
        try:
            await ws.close()
        except Exception:
            pass


_shared: OpenEnvSessionManager | None = None


def shared_session_manager() -> OpenEnvSessionManager:
    """The process-wide session manager, so what Kiln knows about each environment is read
    once and reused across eval runs."""
    global _shared
    if _shared is None:
        _shared = OpenEnvSessionManager()
    return _shared


async def shutdown_shared_session_manager() -> None:
    """Close the process-wide session manager's sessions; the next call to
    `shared_session_manager` starts a fresh one."""
    global _shared
    if _shared is not None:
        await _shared.shutdown()
        _shared = None


# ---- helpers ----


def _compose_world_version(name: str, version: str | None) -> str:
    """The environment's identity as it reports it, readable on a trace: a run keyed by
    `helpdesk_toy@1.0.0` says what produced its state.

    Kiln trusts a version to be immutable, the way it trusts an input id: an
    environment that changes without bumping its version has old traces reused against
    it. OpenEnv's default `get_metadata()` reports the class name and version `1.0.0`
    for every environment, so an environment used as a world should override
    `get_metadata()` and bump its version whenever its behaviour changes. One that
    reports no version is keyed by its name alone and never regenerates."""
    return f"{name}@{version}" if version else name


def _preview(value: Any) -> str:
    text = value if isinstance(value, str) else repr(value)
    if len(text) <= _ERROR_PREVIEW_CHARS:
        return text
    return f"{text[:_ERROR_PREVIEW_CHARS]}... ({len(text)} chars)"
