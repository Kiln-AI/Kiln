"""The OpenEnv session behind one adapter run.

A run whose tools reach an environment (directly, through code tools, or through Kiln
task tools) runs against a live session on it: the session is reset before the model is
called and settled when the run ends, and its record is saved on the run. Every adapter
run goes through here, so the run API, the Python library and Kiln task tool sub-runs
behave the same. A run started inside an active episode (a sub-run, or an eval job,
which opens its own) uses that episode instead of opening another.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Literal

from pydantic import JsonValue

from kiln_ai.datamodel.openenv import OpenEnvEpisode, OpenEnvServer
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.run_config import as_kiln_agent_run_config
from kiln_ai.datamodel.task import RunConfigProperties, Task
from kiln_ai.openenv.session_manager import (
    OpenEnvCapacityError,
    OpenEnvError,
    OpenEnvRejectedError,
    OpenEnvSessionManager,
    shared_session_manager,
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
    "kwargs_without_openenv",
]


class OpenEnvRunError(Exception):
    """A run's environment session could not be set up, so the model was never
    called. `message` is written for the person who started the run."""

    def __init__(self, kind: OpenEnvRunErrorKind, message: str) -> None:
        super().__init__(message)
        self.kind: OpenEnvRunErrorKind = kind
        self.message = message


@dataclass
class OpenEnvRunHandle:
    context: EpisodeContext
    episode: OpenEnvEpisode | None = None
    """The settled record to save on the run. Set when the run ends without an error."""


@asynccontextmanager
async def openenv_for_run(
    task: Task,
    run_config_properties: RunConfigProperties,
    reset_kwargs: dict[str, JsonValue] | None,
    session_manager: OpenEnvSessionManager | None = None,
) -> AsyncIterator[OpenEnvRunHandle | None]:
    """Open a session on the one environment the run's tools reach, and make it the
    current episode for the body. Yields None when the run uses no environment,
    already runs inside an episode, or runs where sessions are off
    (`no_openenv_sessions`).

    Raises OpenEnvRunError before the body runs when the tools reach more than one
    environment, the environment is missing, unreachable or full, it rejects the reset,
    or `reset_kwargs` is given for a run that reaches no environment. An error in the
    body releases the session and propagates unchanged."""
    if get_episode() is not None or openenv_sessions_off():
        yield None
        return

    openenv_server = _run_openenv_server(task, run_config_properties)
    if openenv_server is None:
        if reset_kwargs is not None:
            raise OpenEnvRunError(
                "kwargs_without_openenv",
                "Reset arguments were sent, but this run's tools don't use an OpenEnv.",
            )
        yield None
        return

    # TODO: multi-turn conversations keep one session across turns; until that lands,
    # each turn of a multi-turn task opens and settles its own session.
    manager = session_manager or shared_session_manager()
    context = await _start_episode(manager, openenv_server, reset_kwargs or {})
    handle = OpenEnvRunHandle(context=context)
    token = set_episode(context)
    try:
        try:
            yield handle
        finally:
            reset_episode(token)
    except BaseException:
        await manager.release(context.episode)
        raise
    handle.episode = await _end_episode(manager, context)


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
            "Streaming runs can't use an OpenEnv. Use invoke() for a run whose tools "
            "reach an OpenEnv or that sets openenv_reset_kwargs."
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
        raise OpenEnvRunError("not_found", f"OpenEnv {openenv_server_id} wasn't found.")
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
            f"OpenEnv {openenv_server.name} is at capacity. Wait for a run to finish, "
            "or raise the server's session limit.",
        )
    logger.warning("Can't reach OpenEnv server %s: %s", openenv_server.id, error)
    return OpenEnvRunError(
        "unreachable",
        f"Can't reach OpenEnv {openenv_server.name} at {openenv_server.url}. "
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
