"""The grounding agent's tools on one OpenEnv server, and the episodes they open.

The agent changes environments mid-run, so its tools call the session manager directly
with the session's current episode, rather than through `kiln_tool::openenv::` ids and the
episode ContextVar, which is bound to one episode per run.
"""

from __future__ import annotations

import asyncio
import json
import logging
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

logger = logging.getLogger(__name__)

START_EPISODE_TOOL = "start_episode"
"""The session tool that starts a fresh environment from reset arguments."""
FINAL_STATE_TIMEOUT_S = 30.0
"""How long `end_episode()` waits for the final state. It is only for checking the
rehearsal, so a slow read gives up on it instead of holding the case."""
READ_STATE_TOOL = "read_state"
"""The session tool that reads the current environment's state."""
SUBMIT_RESULT_TOOL = "submit_result"
"""The tool the agent may return its result through (`agent.py`). Reserved here so a
server tool of the same name is renamed rather than shadowed."""
_RESERVED_TOOL_NAMES = (START_EPISODE_TOOL, READ_STATE_TOOL, SUBMIT_RESULT_TOOL)

NO_EPISODE_MESSAGE = "Call start_episode first."
"""The tool error for an environment tool called before any environment started."""
CLOSED_EPISODE_MESSAGE = "The environment closed. Call start_episode again."
"""The tool error after the server ended the current environment's session."""
LIMIT_MESSAGE = (
    "You have used up your {limit}. Stop calling tools and return your result now."
)
"""The tool error for every call once a limit is passed; `{limit}` names the limit."""
TOOLS_CLOSED_MESSAGE = (
    "Your work in the environment is over. Don't call any more tools: return your "
    "result now."
)
"""The tool error for every call after `close_tools()`."""

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

    Owns at most one live episode at a time; `close()` releases it, and `end_episode()`
    ends it with its final state. `last_reset` is the reset of the last episode that
    started, the environment the agent worked in last; `reset_of()` gives any episode's."""

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
        self._tools_closed = False
        self._refused_after_limit = 0
        self._stop_error: BaseException | None = None
        self._stopped = asyncio.Event()
        self._call_log: list[LoggedCall] = []
        self._ended_episode: OpenEnvEpisode | None = None
        self._episode_resets: dict[str, OpenEnvReset] = {}
        self._server_names: dict[str, str] = {}
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
    def ended_episode(self) -> OpenEnvEpisode | None:
        """The last episode, when `end_episode()` ended it and read its final state.
        None when it was released instead, or when reading its state failed or timed
        out."""
        return self._ended_episode

    def reset_of(self, episode_id: str) -> OpenEnvReset | None:
        """The reset an episode of this session started from; None for an unknown id."""
        return self._episode_resets.get(episode_id)

    def rehearsal_calls(self) -> list[LoggedCall]:
        """The calls the agent made in the ended episode, in order, as the agent under
        test would make them: without `start_episode` and `read_state`, which it doesn't
        have, and with each server tool under its server name. Empty when no episode
        was ended with its state."""
        if self._ended_episode is None:
            return []
        episode_id = self._ended_episode.episode_id
        return [
            call.model_copy(
                update={"tool": self._server_names.get(call.tool, call.tool)}
            )
            for call in self._call_log
            if call.episode_id == episode_id
            and call.tool not in (START_EPISODE_TOOL, READ_STATE_TOOL)
        ]

    @property
    def limit_reached(self) -> bool:
        """True once a call or reset limit has been passed."""
        return self._exhausted_limit is not None

    @property
    def stop_error(self) -> BaseException | None:
        """The first error a tool raised instead of returning to the model: the hard stop
        after a limit (`GroundingLimitReached`), or an environment failure that is not
        the case's fault. None while the agent may carry on."""
        return self._stop_error

    async def wait_until_stopped(self) -> None:
        """Returns once a tool has raised `stop_error`. Kiln's adapter shows such an
        error to the model as a failed call and keeps running, so the caller races its
        run against this to end it."""
        await self._stopped.wait()

    async def close_tools(self, *, keep_episode: bool = False) -> None:
        """Release the current episode and refuse every later call, so a follow-up that
        asks only for the agent's result can't change the environment it describes.
        `last_reset` keeps the reset the agent worked in. Refusals count toward the
        hard stop as they do after a limit. With `keep_episode` the episode stays live,
        for a later `end_episode()` or `close()`."""
        async with self._lock:
            self._tools_closed = True
            if not keep_episode:
                await self._release_current()

    async def end_episode(self, timeout_s: float | None = None) -> None:
        """End the current episode with its final state, kept as `ended_episode`. Does
        nothing when no episode is live. A read that fails or takes longer than
        `timeout_s` (default `FINAL_STATE_TIMEOUT_S`) leaves `ended_episode` None; the
        episode is closed either way."""
        async with self._lock:
            await self._end_current(
                FINAL_STATE_TIMEOUT_S if timeout_s is None else timeout_s
            )

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
                self._watched(self._start_episode),
            ),
            _GroundingTool(
                READ_STATE_TOOL,
                "Read the current environment's state, as the server reports it.",
                {"type": "object", "properties": {}},
                self._watched(self._read_state),
            ),
        ]
        taken = set(_RESERVED_TOOL_NAMES)
        for server_tool in server_tools:
            exposed_name = server_tool.name
            while exposed_name in taken:
                exposed_name = f"env_{exposed_name}"
            taken.add(exposed_name)
            self._server_names[exposed_name] = server_tool.name
            tools.append(
                _GroundingTool(
                    exposed_name,
                    server_tool.description,
                    _object_schema(server_tool.input_schema),
                    self._watched(
                        self._server_tool_handler(exposed_name, server_tool.name)
                    ),
                )
            )
        return tools

    def _server_tool_handler(
        self, exposed_name: str, server_name: str
    ) -> Callable[[dict[str, Any]], Awaitable[ToolCallResult]]:
        return lambda kwargs: self._call_server_tool(exposed_name, server_name, kwargs)

    def _watched(
        self, handler: Callable[[dict[str, Any]], Awaitable[ToolCallResult]]
    ) -> Callable[[dict[str, Any]], Awaitable[ToolCallResult]]:
        """`handler`, recording as `stop_error` the first exception it raises that isn't
        meant for the model."""

        async def run(kwargs: dict[str, Any]) -> ToolCallResult:
            try:
                return await handler(kwargs)
            except ToolCallError:
                raise
            except Exception as e:
                if self._stop_error is None:
                    self._stop_error = e
                    self._stopped.set()
                raise

        return run

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
            self._episode_resets[episode.episode_id] = episode.reset
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
        if self._tools_closed or self._exhausted_limit is not None:
            self._refused_after_limit += 1
            if self._refused_after_limit > self._limits.calls_after_limit:
                message = (
                    "The grounding agent kept calling tools after it was asked only "
                    "for its result."
                    if self._tools_closed
                    else "The grounding agent kept calling tools after using up its "
                    f"{self._exhausted_limit}."
                )
                self._log(tool, kwargs, message, is_error=True)
                raise GroundingLimitReached(message)
            raise self._refusal(
                tool,
                kwargs,
                TOOLS_CLOSED_MESSAGE
                if self._tools_closed
                else LIMIT_MESSAGE.format(limit=self._exhausted_limit),
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

    async def _end_current(self, timeout_s: float) -> None:
        episode, self._episode = self._episode, None
        if episode is None:
            return
        try:
            # asyncio.wait_for, not asyncio.timeout: libs/core supports Python 3.10.
            # The manager drops the session before its first await and closes it in a
            # finally, so a timeout leaks no session.
            self._ended_episode = await asyncio.wait_for(
                self._session_manager.end_episode(episode), timeout=timeout_s
            )
        except (OpenEnvError, asyncio.TimeoutError):
            # The end state is only for checking the rehearsal; the case itself
            # doesn't need it.
            logger.warning(
                "Couldn't read the final state of grounding episode %s",
                episode.episode_id,
                exc_info=True,
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
