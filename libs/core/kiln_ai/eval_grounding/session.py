"""The grounding agent's tools on one OpenEnv server, and the episodes they open.

The agent changes environments mid-run, so its tools call the session manager directly
with the session's current episode, rather than through `kiln_tool::openenv::` ids and the
episode ContextVar, which is bound to one episode per run.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import JsonValue

from kiln_ai.datamodel.openenv import (
    OpenEnvEpisode,
    OpenEnvReset,
    OpenEnvServer,
    OpenEnvTool,
)
from kiln_ai.datamodel.tool_id import build_kiln_unmanaged_tool_id
from kiln_ai.eval_grounding.models import LoggedCall
from kiln_ai.openenv.session_manager import (
    OpenEnvError,
    OpenEnvRejectedError,
    OpenEnvSessionManager,
    OpenEnvTransientError,
    tool_call_error_ends_session,
)
from kiln_ai.tools.base_tool import (
    KilnToolInterface,
    ToolCallContext,
    ToolCallError,
    ToolCallResult,
    UnmanagedKilnTool,
)
from kiln_ai.tools.openenv_tool import tool_call_result

START_EPISODE_TOOL = "start_episode"
"""The session tool that starts a fresh environment from reset arguments."""
READ_STATE_TOOL = "read_state"
"""The session tool that reads the current environment's state."""
_SESSION_TOOL_NAMES = (START_EPISODE_TOOL, READ_STATE_TOOL)

NO_EPISODE_MESSAGE = "Call start_episode first."
"""The tool error for an environment tool called before any environment started."""
CLOSED_EPISODE_MESSAGE = "The environment closed. Call start_episode again."
"""The tool error after the server ended the current environment's session."""
LIMIT_MESSAGE = (
    "You have used up your {limit}. Stop calling tools and return your result now."
)
"""The tool error for every call once a limit is passed; `{limit}` names the limit."""

DEFAULT_TIME_LIMIT_S = 900.0
"""How long the grounding agent may spend on one case, in seconds."""


@dataclass(frozen=True)
class GroundingLimits:
    """How many calls the grounding agent may make on one case."""

    max_tool_calls: int = 40
    """Server tool and read_state calls per case. A valid start_episode is counted by max_resets instead; one whose reset_kwargs is not an object counts here."""
    max_resets: int = 10
    """start_episode calls per case, rejected ones included."""
    calls_after_limit: int = 5
    """Calls refused with LIMIT_MESSAGE once a limit is passed, before the session gives up."""


DEFAULT_LIMITS = GroundingLimits()
"""The limits a case runs under unless the caller sets its own."""


class GroundingLimitReached(Exception):
    """The agent kept calling tools after a limit told it to stop."""


class GroundingSession:
    """One case's tools on an OpenEnv server: `start_episode`, `read_state`, and one per
    server tool, sharing the current episode, the limits and the call log.

    Owns at most one live episode at a time; `close()` releases it. `last_reset` is the
    reset of the last episode that started, the environment the agent worked in last."""

    def __init__(
        self,
        openenv_server: OpenEnvServer,
        session_manager: OpenEnvSessionManager,
        server_tools: Sequence[OpenEnvTool],
        limits: GroundingLimits = DEFAULT_LIMITS,
        transient_retry_delays_s: Sequence[float] = (1.0, 3.0),
    ) -> None:
        self._server = openenv_server
        self._session_manager = session_manager
        self._limits = limits
        self._retry_delays_s = tuple(transient_retry_delays_s)
        # The adapter runs one turn's tool calls concurrently; episodes and counters
        # change one call at a time.
        self._lock = asyncio.Lock()
        self._episode: OpenEnvEpisode | None = None
        self._episode_closed = False
        self._last_reset: OpenEnvReset | None = None
        self._tool_calls = 0
        self._resets = 0
        self._exhausted_limit: str | None = None
        self._refused_after_limit = 0
        self._call_log: list[LoggedCall] = []
        self._tools = self._build_tools(server_tools)

    def tools(self) -> list[KilnToolInterface]:
        """The agent's tools, to pass as `AdapterConfig.unmanaged_tools`."""
        return list(self._tools)

    @property
    def call_log(self) -> list[LoggedCall]:
        """Every tool call so far, refused and failed ones included, as a copy."""
        return list(self._call_log)

    @property
    def last_reset(self) -> OpenEnvReset | None:
        """The reset of the last episode that started; None before any start."""
        return self._last_reset

    @property
    def limit_reached(self) -> bool:
        """True once a call or reset limit has been passed."""
        return self._exhausted_limit is not None

    async def close(self) -> None:
        """Release the current episode, if any. Safe to call more than once."""
        async with self._lock:
            await self._release_current()

    def _build_tools(
        self, server_tools: Sequence[OpenEnvTool]
    ) -> list[KilnToolInterface]:
        tools: list[KilnToolInterface] = [
            _GroundingTool(
                START_EPISODE_TOOL,
                "Start a fresh environment from these reset arguments, throwing the "
                "current one away. Returns what the server reported about the new "
                "environment, and how many resets and tool calls are left.",
                {
                    "type": "object",
                    "properties": {
                        "reset_kwargs": {
                            "type": "object",
                            "description": "Keyword arguments for the server's reset, as its reset schema describes them. {} for the server's defaults.",
                        }
                    },
                    "required": ["reset_kwargs"],
                },
                lambda kwargs: self._start_episode(kwargs),
            ),
            _GroundingTool(
                READ_STATE_TOOL,
                "Read the current environment's state, as the server reports it.",
                {"type": "object", "properties": {}},
                lambda kwargs: self._read_state(kwargs),
            ),
        ]
        taken = set(_SESSION_TOOL_NAMES)
        for server_tool in server_tools:
            exposed_name = server_tool.name
            while exposed_name in taken:
                exposed_name = f"env_{exposed_name}"
            taken.add(exposed_name)
            tools.append(
                _GroundingTool(
                    exposed_name,
                    server_tool.description,
                    _object_schema(server_tool.input_schema),
                    self._server_tool_handler(exposed_name, server_tool.name),
                )
            )
        return tools

    def _server_tool_handler(
        self, exposed_name: str, server_name: str
    ) -> Callable[[dict[str, Any]], Awaitable[ToolCallResult]]:
        return lambda kwargs: self._call_server_tool(exposed_name, server_name, kwargs)

    async def _start_episode(self, kwargs: dict[str, Any]) -> ToolCallResult:
        reset_kwargs = kwargs.get("reset_kwargs", {})
        async with self._lock:
            if not isinstance(reset_kwargs, dict):
                self._check_limits(START_EPISODE_TOOL, kwargs, counts_as_reset=False)
                raise self._refusal(
                    START_EPISODE_TOOL, kwargs, "reset_kwargs must be a JSON object."
                )
            self._check_limits(START_EPISODE_TOOL, kwargs, counts_as_reset=True)
            await self._release_current()
            try:
                episode = await self._start_with_retries(reset_kwargs)
            except OpenEnvRejectedError as e:
                raise self._refusal(
                    START_EPISODE_TOOL,
                    kwargs,
                    f"The server rejected these reset arguments: {e.server_message or e}",
                )
            except OpenEnvError as e:
                self._log(START_EPISODE_TOOL, kwargs, str(e), is_error=True)
                raise
            self._episode = episode
            self._episode_closed = False
            self._last_reset = episode.reset
            output = json.dumps(
                {
                    "reset_metadata": episode.reset_metadata,
                    "resets_left": self._limits.max_resets - self._resets,
                    "tool_calls_left": self._limits.max_tool_calls - self._tool_calls,
                },
                ensure_ascii=False,
            )
            self._log(START_EPISODE_TOOL, kwargs, output, is_error=False)
            return ToolCallResult(output=output)

    async def _start_with_retries(
        self, reset_kwargs: dict[str, JsonValue]
    ) -> OpenEnvEpisode:
        """A server at capacity or a dropped connection is not the case's fault: retry
        with backoff, then raise so the caller fails the step instead of dropping."""
        for delay_s in self._retry_delays_s:
            try:
                return await self._session_manager.start_episode(
                    self._server, reset_kwargs
                )
            except OpenEnvTransientError:
                await asyncio.sleep(delay_s)
        return await self._session_manager.start_episode(self._server, reset_kwargs)

    async def _read_state(self, kwargs: dict[str, Any]) -> ToolCallResult:
        async with self._lock:
            episode = self._episode_for_call(READ_STATE_TOOL, kwargs)
            try:
                state = await self._session_manager.read_state(episode)
            except OpenEnvError as e:
                raise await self._episode_error(READ_STATE_TOOL, kwargs, e)
            output = json.dumps(state, ensure_ascii=False)
            self._log(READ_STATE_TOOL, kwargs, output, is_error=False)
            return ToolCallResult(output=output)

    async def _call_server_tool(
        self, exposed_name: str, server_name: str, kwargs: dict[str, Any]
    ) -> ToolCallResult:
        async with self._lock:
            episode = self._episode_for_call(exposed_name, kwargs)
            try:
                outcome = await self._session_manager.call_tool(
                    episode, server_name, kwargs
                )
            except OpenEnvError as e:
                raise await self._episode_error(exposed_name, kwargs, e)
            result = tool_call_result(outcome)
            self._log(exposed_name, kwargs, result.output, is_error=result.is_error)
            return result

    def _episode_for_call(self, tool: str, kwargs: dict[str, Any]) -> OpenEnvEpisode:
        self._check_limits(tool, kwargs, counts_as_reset=False)
        episode = self._episode
        if episode is None:
            raise self._refusal(
                tool,
                kwargs,
                CLOSED_EPISODE_MESSAGE if self._episode_closed else NO_EPISODE_MESSAGE,
            )
        return episode

    def _check_limits(
        self, tool: str, kwargs: dict[str, Any], *, counts_as_reset: bool
    ) -> None:
        if self._exhausted_limit is None:
            if counts_as_reset and self._resets >= self._limits.max_resets:
                self._exhausted_limit = f"{self._limits.max_resets} resets"
            elif not counts_as_reset and (
                self._tool_calls >= self._limits.max_tool_calls
            ):
                self._exhausted_limit = f"{self._limits.max_tool_calls} tool calls"
        if self._exhausted_limit is not None:
            self._refused_after_limit += 1
            if self._refused_after_limit > self._limits.calls_after_limit:
                message = f"The grounding agent kept calling tools after using up its {self._exhausted_limit}."
                self._log(tool, kwargs, message, is_error=True)
                raise GroundingLimitReached(message)
            raise self._refusal(
                tool, kwargs, LIMIT_MESSAGE.format(limit=self._exhausted_limit)
            )
        if counts_as_reset:
            self._resets += 1
        else:
            self._tool_calls += 1

    async def _episode_error(
        self, tool: str, kwargs: dict[str, Any], error: OpenEnvError
    ) -> BaseException:
        """The error to raise for a failed call in the current episode. A rejection goes
        back to the model; anything else ended the session."""
        if not tool_call_error_ends_session(error):
            return self._refusal(tool, kwargs, str(error))
        if isinstance(error, OpenEnvTransientError):
            # The session is gone, so retrying the call can't work, and a dropped
            # connection is not the case's fault.
            self._log(tool, kwargs, str(error), is_error=True)
            result: BaseException = error
        else:
            result = self._refusal(tool, kwargs, f"{error} {CLOSED_EPISODE_MESSAGE}")
        await self._release_current()
        self._episode_closed = True
        return result

    def _refusal(
        self, tool: str, kwargs: dict[str, Any], message: str
    ) -> ToolCallError:
        """Logs the refused call; the caller raises the error so the model reads it."""
        self._log(tool, kwargs, message, is_error=True)
        return ToolCallError(message)

    def _log(
        self, tool: str, kwargs: dict[str, Any], output: str, *, is_error: bool
    ) -> None:
        self._call_log.append(
            LoggedCall(
                tool=tool,
                args=kwargs,
                output=output,
                is_error=is_error,
                episode_id=self._episode.episode_id if self._episode else None,
            )
        )

    async def _release_current(self) -> None:
        episode, self._episode = self._episode, None
        if episode is not None:
            await self._session_manager.release(episode)


class _GroundingTool(UnmanagedKilnTool):
    def __init__(
        self,
        name: str,
        description: str,
        parameters_schema: dict[str, Any],
        handler: Callable[[dict[str, Any]], Awaitable[ToolCallResult]],
    ) -> None:
        super().__init__(
            build_kiln_unmanaged_tool_id(f"grounding_{name}"),
            name,
            description,
            parameters_schema,
        )
        self._handler = handler

    async def run(
        self, context: ToolCallContext | None = None, **kwargs: Any
    ) -> ToolCallResult:
        return await self._handler(kwargs)


def _object_schema(input_schema: dict[str, Any]) -> dict[str, Any]:
    """The server's input schema with the `type` and `properties` a tool definition needs,
    which servers often leave out for a tool with no arguments."""
    return {"type": "object", "properties": {}, **input_schema}
