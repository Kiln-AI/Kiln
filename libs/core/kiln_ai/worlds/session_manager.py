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
    start_episode     open a `/ws` session and `reset(**reset_kwargs)`
    call_tool         `step(CallToolAction)`; each observation's reward is kept in memory
    end_episode       `state`, then close the session
    release           close the session

One session per episode; sessions are closed by `end_episode`, so the record on the
trace is the durable state.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx
from pydantic import JsonValue
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

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
this is deliberately generous; an environment enforces its own per-tool timeouts."""


class OpenEnvError(RuntimeError):
    """The environment answered a request with an error, or could not be reached."""


@dataclass(frozen=True)
class ToolCallOutcome:
    """What one `step(CallToolAction)` came back with."""

    result: Any
    error: str | None
    reward: float | None
    done: bool


class WorldSessionManager(Protocol):
    """The seam the eval runner and the tool proxies call. `OpenEnvSessionManager` is the
    implementation; tests substitute a fake."""

    async def world_version(
        self, world: World, reset_kwargs: dict[str, JsonValue]
    ) -> str:
        """Identity of the environment code an episode would run, without starting one.
        Folded into the trace fingerprint: change it and traces regenerate."""
        ...

    async def list_tools(self, world: World) -> list[OpenEnvTool]: ...

    async def start_episode(
        self, world: World, reset_kwargs: dict[str, JsonValue]
    ) -> WorldEpisode: ...

    async def call_tool(
        self, episode: WorldEpisode, tool_name: str, arguments: dict[str, Any]
    ) -> ToolCallOutcome: ...

    async def end_episode(self, episode: WorldEpisode) -> WorldEpisode: ...

    async def release(self, episode: WorldEpisode) -> None: ...

    async def shutdown(self) -> None: ...


@dataclass
class _EnvServer:
    world_id: str
    base_url: str
    env_name: str
    env_version: str | None
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
    rewards: list[float] = field(default_factory=list)
    done: bool = False


class OpenEnvSessionManager:
    """Drives sessions on running OpenEnv environments."""

    def __init__(self, step_timeout_s: float = STEP_TIMEOUT_S) -> None:
        self._step_timeout_s = step_timeout_s
        self._servers: dict[str, _EnvServer] = {}
        self._server_locks: dict[str, asyncio.Lock] = {}
        self._sessions: dict[str, _Session] = {}

    # ---- protocol ----

    async def world_version(
        self, world: World, reset_kwargs: dict[str, JsonValue]
    ) -> str:
        server = await self._server_for(world)
        return server.world_version

    async def list_tools(self, world: World) -> list[OpenEnvTool]:
        server = await self._server_for(world)
        if server.tools is not None:
            return server.tools
        async with self._connect(server) as ws:
            data = await self._request(
                ws, {"type": "step", "data": {"type": "list_tools"}}
            )
            await self._end_session(ws)
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
            )
            reward = data.get("reward")
            if isinstance(reward, (int, float)) and not isinstance(reward, bool):
                session.rewards.append(float(reward))
            done = bool(data.get("done", False))
            session.done = session.done or done
        observation = data.get("observation") or {}
        error = observation.get("error")
        if isinstance(error, dict):
            error = str(error.get("message") or error)
        elif error is not None:
            error = str(error)
        return ToolCallOutcome(
            result=observation.get("result"),
            error=error,
            reward=float(reward) if isinstance(reward, (int, float)) else None,
            done=done,
        )

    async def end_episode(self, episode: WorldEpisode) -> WorldEpisode:
        session = self._sessions.pop(episode.episode_id, None)
        if session is None:
            return episode
        state: dict[str, JsonValue] | None = None
        try:
            async with session.lock:
                data = await self._request(session.ws, {"type": "state"})
                state = {str(k): v for k, v in data.items()}
                await self._end_session(session.ws)
        finally:
            await self._close_quietly(session.ws)
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

    def server_for_world_id(self, world_id: str) -> _EnvServer | None:
        return self._servers.get(world_id)

    async def _server_for(self, world: World) -> _EnvServer:
        """What Kiln knows about the world's environment: its address, reported
        identity and content version. Cached per world; re-read when the world's URL
        changes."""
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
            if current is not None and current.base_url == base_url:
                return current
            server = await self._connect_remote(world, base_url)
            self._servers[world.id] = server
            return server

    async def _connect_remote(self, world: World, base_url: str) -> _EnvServer:
        assert world.id
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(f"{base_url}/metadata")
                response.raise_for_status()
                meta = response.json()
            except Exception as e:
                raise OpenEnvError(
                    f"World '{world.name}' points at {base_url}, which did "
                    f"not answer /metadata: {e}"
                ) from e
        name = str(meta.get("name") or world.name)
        version = meta.get("version")
        version = str(version) if version is not None else None
        return _EnvServer(
            world_id=world.id,
            base_url=base_url,
            env_name=name,
            env_version=version,
            world_version=_compose_world_version(name, version),
        )

    # ---- sessions ----

    async def _open(self, server: _EnvServer) -> ClientConnection:
        try:
            return await connect(server.ws_url, max_size=None, open_timeout=30)
        except (OSError, ConnectionClosed) as e:
            raise OpenEnvError(
                f"Could not open a session on {server.base_url}: {e}"
            ) from e

    def _connect(self, server: _EnvServer) -> "_SessionScope":
        return _SessionScope(self, server)

    async def _send(self, ws: ClientConnection, message: dict[str, Any]) -> None:
        await ws.send(json.dumps(message))

    async def _request(
        self, ws: ClientConnection, message: dict[str, Any]
    ) -> dict[str, Any]:
        """Send one message and return the response's `data`, raising on an error
        response."""
        try:
            await self._send(ws, message)
            raw = await asyncio.wait_for(ws.recv(), timeout=self._step_timeout_s)
        except ConnectionClosed as e:
            hint = ""
            if message.get("type") == "reset":
                hint = (
                    " An OpenEnv server accepts one session by default; if this "
                    "happens under concurrent eval jobs, raise its max_concurrent_envs."
                )
            raise OpenEnvError(f"The environment closed the session: {e}.{hint}") from e
        except asyncio.TimeoutError as e:
            raise OpenEnvError(
                f"The environment did not answer a '{message.get('type')}' message "
                f"within {self._step_timeout_s:.0f}s"
            ) from e
        try:
            response = json.loads(raw)
        except json.JSONDecodeError as e:
            raise OpenEnvError(f"The environment sent invalid JSON: {raw!r}") from e
        if not isinstance(response, dict):
            raise OpenEnvError(f"The environment sent an unexpected message: {raw!r}")
        data = response.get("data")
        if response.get("type") == "error":
            detail = data.get("message") if isinstance(data, dict) else data
            raise OpenEnvError(
                f"The environment rejected a '{message.get('type')}' message: {detail}"
            )
        return data if isinstance(data, dict) else {}

    async def _end_session(self, ws: ClientConnection) -> None:
        """Tell the environment the session is over and let it close the socket, so
        its handler sees a clean close rather than an abnormal disconnect. Every path
        that drops a session goes through here, including failures and shutdown; the
        socket is closed regardless."""
        try:
            await self._send(ws, {"type": "close"})
            await asyncio.wait_for(ws.wait_closed(), timeout=5)
        except (ConnectionClosed, asyncio.TimeoutError, OSError):
            pass
        finally:
            await self._close_quietly(ws)

    async def _close_quietly(self, ws: ClientConnection) -> None:
        try:
            await ws.close()
        except Exception:
            pass


class _SessionScope:
    def __init__(
        self, session_manager: OpenEnvSessionManager, server: _EnvServer
    ) -> None:
        self._session_manager = session_manager
        self._server = server
        self._ws: ClientConnection | None = None

    async def __aenter__(self) -> ClientConnection:
        self._ws = await self._session_manager._open(self._server)
        return self._ws

    async def __aexit__(self, *exc: object) -> None:
        if self._ws is not None:
            await self._session_manager._close_quietly(self._ws)


_shared: OpenEnvSessionManager | None = None


def shared_session_manager() -> OpenEnvSessionManager:
    """The process-wide session manager, so what Kiln knows about each environment is read
    once and reused across eval runs."""
    global _shared
    if _shared is None:
        _shared = OpenEnvSessionManager()
    return _shared


async def shutdown_shared_session_manager() -> None:
    global _shared
    if _shared is not None:
        await _shared.shutdown()
        _shared = None


# ---- helpers ----


def _compose_world_version(name: str, version: str | None) -> str:
    """The environment's identity as it reports it, readable on a trace: a run keyed by
    `helpdesk_toy@1.0.0` says what produced its state. Kiln trusts a version to be
    immutable, the way it trusts an input id; an environment that changes without
    bumping its version will have old traces reused against it."""
    return f"{name}@{version}" if version else name
