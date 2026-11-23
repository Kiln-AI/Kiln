"""The OpenEnv session behind one adapter run.

A run whose tools reach an environment (directly, through code tools, or through Kiln
task tools) runs against a live session on it: the session is reset before the model is
called and settled when the run ends, and its record is saved on the run. Every adapter
run goes through here, so the run API, the Python library and Kiln task tool sub-runs
behave the same. A run started inside an active episode (a sub-run, or an eval job,
which opens its own) uses that episode instead of opening another.

A multi-turn conversation keeps one session for all its turns: the first turn opens it,
and between turns it is held under the latest turn (`ConversationSessions`). Only the
latest turn can be continued, and a conversation whose session is gone can't be
continued at all, because the environment's state would no longer match the history.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Iterator, Literal

from pydantic import JsonValue

from kiln_ai.adapters.retry_classification import unwrap_kiln_run_error
from kiln_ai.datamodel.datamodel_enums import TurnMode
from kiln_ai.datamodel.openenv import OpenEnvEpisode, OpenEnvServer
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.run_config import as_kiln_agent_run_config
from kiln_ai.datamodel.task import RunConfigProperties, Task
from kiln_ai.datamodel.task_run import TaskRun
from kiln_ai.openenv.conversations import ConversationSessions, HeldSession
from kiln_ai.openenv.session_manager import (
    OpenEnvCapacityError,
    OpenEnvError,
    OpenEnvRejectedError,
    OpenEnvSessionManager,
    shared_conversation_sessions,
    shared_session_manager,
    tool_call_error_ends_session,
)
from kiln_ai.run_context import (
    EpisodeContext,
    get_episode,
    openenv_sessions_off,
    reset_episode,
    set_episode,
)
from kiln_ai.tools.openenv_reach import OpenEnvReachError, single_openenv_server_id

logger = logging.getLogger(__name__)

OpenEnvRunErrorKind = Literal[
    "reach",
    "not_found",
    "unreachable",
    "at_capacity",
    "reset_rejected",
    "session_ended",
    "fork_refused",
    "not_started_with_openenv",
    "openenv_changed",
    "kwargs_without_openenv",
]


class OpenEnvRunError(Exception):
    """A run's environment session could not be set up, so the model was never
    called. `message` is written for the person who started the run."""

    def __init__(self, kind: OpenEnvRunErrorKind, message: str) -> None:
        super().__init__(message)
        self.kind: OpenEnvRunErrorKind = kind
        self.message = message


def openenv_run_error_code(error: OpenEnvRunError) -> str:
    """The error code an API sends with the refusal, so a client can show the message
    as written instead of as an unexpected failure."""
    return f"openenv_{error.kind}"


@dataclass
class OpenEnvRunHandle:
    context: EpisodeContext
    episode: OpenEnvEpisode | None = None
    """The settled record to save on the run. Set when the run ends without an error."""
    run_id: str | None = None
    """Set by the caller to the id of the run the body produced. A multi-turn
    conversation's session is held under it for the next turn."""


@asynccontextmanager
async def openenv_for_run(
    task: Task,
    run_config_properties: RunConfigProperties,
    reset_kwargs: dict[str, JsonValue] | None,
    parent_run: TaskRun | None = None,
    session_manager: OpenEnvSessionManager | None = None,
    conversations: ConversationSessions | None = None,
) -> AsyncIterator[OpenEnvRunHandle | None]:
    """Open a session on the one environment the run's tools reach, and make it the
    current episode for the body. Yields None when the run uses no environment,
    already runs inside an episode, or runs where sessions are off
    (`no_openenv_sessions`).

    For a multi-turn task, a turn with `parent_run` continues the session held under
    that turn and ignores `reset_kwargs`, and every turn holds the session under its own
    `handle.run_id` afterwards.

    Raises OpenEnvRunError before the body runs when the tools reach more than one
    environment, the environment is missing, unreachable or full, it rejects the reset,
    `reset_kwargs` is given for a run that reaches no environment, or a later turn can't
    continue the conversation's session. An error in the body propagates unchanged."""
    if get_episode() is not None or openenv_sessions_off():
        yield None
        return

    openenv_server = _run_openenv_server(task, run_config_properties)
    is_multiturn = task.turn_mode == TurnMode.multiturn
    if is_multiturn and parent_run is not None:
        held_sessions = conversations or shared_conversation_sessions()
        _refuse_openenv_change(held_sessions.peek(str(parent_run.id)), openenv_server)

    if openenv_server is None:
        if is_multiturn and parent_run is not None:
            _refuse_dropping_openenv(parent_run, conversations)
        if reset_kwargs is not None:
            raise OpenEnvRunError(
                "kwargs_without_openenv",
                "Reset arguments were sent, but this run's tools don't use an OpenEnv server.",
            )
        yield None
        return

    manager = session_manager or shared_session_manager()
    if not is_multiturn:
        async with _single_turn_session(
            manager, openenv_server, reset_kwargs
        ) as handle:
            yield handle
        return

    held_sessions = conversations or shared_conversation_sessions()
    if parent_run is None:
        context = await _start_episode(manager, openenv_server, reset_kwargs or {})
        held = HeldSession(context=context, loop=asyncio.get_running_loop())
    else:
        held = _continue_conversation(held_sessions, parent_run)
    async with _conversation_turn(held_sessions, held, parent_run) as handle:
        yield handle


@asynccontextmanager
async def _single_turn_session(
    manager: OpenEnvSessionManager,
    openenv_server: OpenEnvServer,
    reset_kwargs: dict[str, JsonValue] | None,
) -> AsyncIterator[OpenEnvRunHandle]:
    context = await _start_episode(manager, openenv_server, reset_kwargs or {})
    handle = OpenEnvRunHandle(context=context)
    try:
        with _current_episode(context):
            yield handle
    except BaseException:
        await manager.release(context.episode)
        raise
    handle.episode = await _end_episode(manager, context)


def _refuse_openenv_change(
    held: HeldSession | None, openenv_server: OpenEnvServer | None
) -> None:
    """The conversation's environment is fixed by its first turn: a later turn whose
    tools reach another environment, or none, is refused and the session kept."""
    if held is None or (
        openenv_server is not None
        and openenv_server.id == held.context.openenv_server.id
    ):
        return
    instead = f"use {openenv_server.name}" if openenv_server else "run without it"
    raise OpenEnvRunError(
        "openenv_changed",
        f"This conversation uses OpenEnv server {held.context.openenv_server.name}. Start a new "
        f"conversation to {instead}.",
    )


def _refuse_dropping_openenv(
    parent_run: TaskRun, conversations: ConversationSessions | None
) -> None:
    """A conversation that used an OpenEnv server can't continue without one, even
    once its session is gone or from an earlier turn, where nothing is held under
    the parent to compare against."""
    held_sessions = conversations or shared_conversation_sessions()
    if parent_run.openenv_episode is None and not held_sessions.holds_turn(
        str(parent_run.id)
    ):
        return
    raise OpenEnvRunError(
        "openenv_changed",
        "This conversation uses an OpenEnv server. Start a new conversation to run "
        "without it.",
    )


def _continue_conversation(
    held_sessions: ConversationSessions, parent_run: TaskRun
) -> HeldSession:
    parent_id = str(parent_run.id)
    held = held_sessions.take(parent_id)
    if held is None:
        if held_sessions.holds_turn(parent_id):
            raise OpenEnvRunError("fork_refused", _FORK_REFUSED_MESSAGE)
        if parent_run.openenv_episode is not None:
            raise OpenEnvRunError(
                "session_ended",
                session_ended_message(held_sessions.end_reason(parent_id)),
            )
        raise OpenEnvRunError(
            "not_started_with_openenv",
            "This conversation started without an OpenEnv server. Start a new conversation "
            "to use one.",
        )
    return held


_FORK_REFUSED_MESSAGE = (
    "This conversation uses an OpenEnv server, so it can only continue from the "
    "latest turn."
)

ConversationSessionState = Literal["none", "open", "ended"]


@dataclass(frozen=True)
class ConversationSessionStatus:
    state: ConversationSessionState
    """"none" when the conversation doesn't use an OpenEnv server, "open" when its
    session can take another message, "ended" when it can't."""
    message: str | None = None
    """Why the conversation can't continue, for the person. Set when "ended"."""


def conversation_session_status(
    task: Task, run: TaskRun, conversations: ConversationSessions | None = None
) -> ConversationSessionStatus:
    """Whether a message sent after `run` could use the conversation's OpenEnv session,
    so a client can say so before the person types one. A send can still be refused if
    the session ends in between."""
    if task.turn_mode != TurnMode.multiturn:
        return ConversationSessionStatus("none")
    held_sessions = conversations or shared_conversation_sessions()
    run_id = str(run.id)
    if held_sessions.peek(run_id) is not None:
        return ConversationSessionStatus("open")
    if held_sessions.holds_turn(run_id):
        return ConversationSessionStatus("ended", _FORK_REFUSED_MESSAGE)
    if run.openenv_episode is None:
        return ConversationSessionStatus("none")
    return ConversationSessionStatus(
        "ended", session_ended_message(held_sessions.end_reason(run_id))
    )


def session_ended_message(reason: str | None) -> str:
    """What the person sees when a conversation's session is gone. `reason` follows
    "ended"; without one the message doesn't say why."""
    ended = f"ended {reason}." if reason else "ended."
    return (
        f"The OpenEnv session for this conversation {ended} Start a new "
        "conversation to keep using this OpenEnv server."
    )


@asynccontextmanager
async def _conversation_turn(
    held_sessions: ConversationSessions,
    held: HeldSession,
    parent_run: TaskRun | None,
) -> AsyncIterator[OpenEnvRunHandle]:
    """Run one turn in the conversation's session. Afterwards the session is held under
    the new turn; after a failed turn it goes back under the parent, so the same turn
    can be retried, unless the failure ended the session, this was the first turn, the
    turn was cancelled (possibly mid-message, so the session can't be trusted), or the
    turn called one of the environment's tools. A tool call may have changed the
    environment, and the parent's history doesn't show it, so a retry would run against
    a state its history doesn't explain. A model failure, even one a retry layer treats
    as run-ending (a rate limit), leaves the environment's session usable, so it doesn't
    count as ending it."""
    context = held.context
    manager = context.session_manager
    handle = OpenEnvRunHandle(context=context)
    tool_calls_before = manager.tool_calls(context.episode)
    try:
        with _current_episode(context):
            yield handle
    except BaseException as e:
        lost_cause = manager.lost_cause(context.episode)
        if parent_run is None or not isinstance(e, Exception):
            await manager.release(context.episode)
        elif lost_cause is not None or _ended_openenv_session(e):
            held_sessions.record_end(
                str(parent_run.id),
                f"when {lost_cause}" if lost_cause else "when its last message failed",
            )
            await manager.release(context.episode)
        elif manager.tool_calls(context.episode) > tool_calls_before:
            held_sessions.record_end(
                str(parent_run.id),
                "when a message failed after calling the OpenEnv server's tools",
            )
            await manager.release(context.episode)
        else:
            held_sessions.put(str(parent_run.id), held)
        raise

    lost_cause = manager.lost_cause(context.episode)
    if lost_cause is not None:
        # A tool call ended the session during the turn. The model's answer is kept,
        # but the conversation can't continue.
        handle.episode = context.episode
        await _end_conversation(held_sessions, handle, f"when {lost_cause}")
        return
    try:
        state = await manager.read_state(context.episode)
    except OpenEnvError as e:
        logger.warning(
            "Couldn't read the state of OpenEnv server %s episode %s after a turn: %s",
            context.openenv_server.id,
            context.episode.episode_id,
            e,
        )
        handle.episode = context.episode
        if _ended_openenv_session(e):
            lost_cause = manager.lost_cause(context.episode)
            await _end_conversation(
                held_sessions,
                handle,
                f"when {lost_cause}"
                if lost_cause
                else "when reading the OpenEnv server's state failed",
            )
            return
    else:
        handle.episode = context.episode.model_copy(update={"final_state": state})

    if handle.run_id is None:
        await manager.release(context.episode)
        return
    held_sessions.put(handle.run_id, held)


async def _end_conversation(
    held_sessions: ConversationSessions, handle: OpenEnvRunHandle, reason: str
) -> None:
    """Close the session after a turn that produced a run, and remember why."""
    if handle.run_id is not None:
        held_sessions.record_end(handle.run_id, reason)
    await handle.context.session_manager.release(handle.context.episode)


@contextmanager
def _current_episode(context: EpisodeContext) -> Iterator[None]:
    token = set_episode(context)
    try:
        yield
    finally:
        reset_episode(token)


def _ended_openenv_session(error: BaseException) -> bool:
    """True when the error came from the environment and closed its session, so the
    session can't be used again."""
    cause = unwrap_kiln_run_error(error)
    return isinstance(cause, OpenEnvError) and tool_call_error_ends_session(cause)


def reject_openenv_for_streaming(
    task: Task,
    run_config_properties: RunConfigProperties,
    reset_kwargs: dict[str, JsonValue] | None,
) -> None:
    """Raise ValueError when a streaming run would need its own environment session,
    which streaming doesn't open: its tools reach one or more environments, or it sets
    `reset_kwargs`. A stream inside an active episode, or where sessions are off, is
    allowed. Reads the tool ids of any code tools and Kiln task tools it lists from disk."""
    if get_episode() is not None or openenv_sessions_off():
        return
    try:
        reached = _run_openenv_server_id(task, run_config_properties)
    except OpenEnvRunError as e:
        raise ValueError(e.message) from e
    if reset_kwargs is not None or reached is not None:
        raise ValueError(
            "Streaming runs can't use an OpenEnv server. Use invoke() for a run whose "
            "tools reach an OpenEnv server or that sets openenv_reset_kwargs."
        )


def _run_openenv_server_id(
    task: Task, run_config_properties: RunConfigProperties
) -> tuple[Project, str] | None:
    """The project and the id of the one environment the run's tools reach."""
    if run_config_properties.type != "kiln_agent":
        return None
    tools_config = as_kiln_agent_run_config(run_config_properties).tools_config
    tool_ids = list(tools_config.tools) if tools_config and tools_config.tools else []
    project = task.parent_project() if tool_ids else None
    if project is None:
        return None
    try:
        openenv_server_id = single_openenv_server_id(project, tool_ids)
    except OpenEnvReachError as e:
        raise OpenEnvRunError("reach", e.message) from e
    if openenv_server_id is None:
        return None
    return project, openenv_server_id


def _run_openenv_server(
    task: Task, run_config_properties: RunConfigProperties
) -> OpenEnvServer | None:
    reached = _run_openenv_server_id(task, run_config_properties)
    if reached is None:
        return None
    project, openenv_server_id = reached
    openenv_server = OpenEnvServer.from_id_and_parent_path(
        openenv_server_id, project.path
    )
    if openenv_server is None:
        raise OpenEnvRunError(
            "not_found", f"OpenEnv server {openenv_server_id} wasn't found."
        )
    return openenv_server


async def _start_episode(
    manager: OpenEnvSessionManager,
    openenv_server: OpenEnvServer,
    reset_kwargs: dict[str, JsonValue],
) -> EpisodeContext:
    try:
        await manager.refresh(openenv_server)
        tools = {tool.name: tool for tool in await manager.list_tools(openenv_server)}
    except OpenEnvError as e:
        raise _session_error(openenv_server, e) from e
    try:
        episode = await manager.start_episode(openenv_server, reset_kwargs)
    except OpenEnvRejectedError as e:
        raise OpenEnvRunError(
            "reset_rejected",
            f"{openenv_server.name} rejected the reset arguments: {e.server_message or e}",
        ) from e
    except OpenEnvError as e:
        raise _session_error(openenv_server, e) from e
    return EpisodeContext(
        episode=episode,
        openenv_server=openenv_server,
        session_manager=manager,
        tools=tools,
    )


def _session_error(
    openenv_server: OpenEnvServer, error: OpenEnvError
) -> OpenEnvRunError:
    """A failure to read the environment or open a session on it. A full server is
    reported as such; every other failure means it couldn't be reached."""
    if isinstance(error, OpenEnvCapacityError):
        return OpenEnvRunError(
            "at_capacity",
            f"OpenEnv server {openenv_server.name} is at capacity. Wait for a run to finish, "
            "or raise the server's session limit.",
        )
    logger.warning("Can't reach OpenEnv server %s: %s", openenv_server.id, error)
    return OpenEnvRunError(
        "unreachable",
        f"Can't reach OpenEnv server {openenv_server.name} at {openenv_server.url}. "
        "Check the server is running.",
    )


async def _end_episode(
    manager: OpenEnvSessionManager, context: EpisodeContext
) -> OpenEnvEpisode:
    """The episode with its final state. The run has already finished, so a state that
    can't be read is logged and the episode is kept without it, rather than failing
    a run whose output exists."""
    try:
        return await manager.end_episode(context.episode)
    except OpenEnvError as e:
        logger.warning(
            "Couldn't read the final state of OpenEnv server %s episode %s: %s",
            context.openenv_server.id,
            context.episode.episode_id,
            e,
        )
        return context.episode
