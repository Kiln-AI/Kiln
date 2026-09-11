"""Agent run context management using contextvars.

The agent run ID propagates automatically through async call chains,
including asyncio.gather and sub-agent calls via KilnTaskTool.

This is a general-purpose ID for scoping work to a single agent run,
usable for logging, caching, metrics, or any run-scoped operations.
"""

import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kiln_ai.datamodel.world import (
        Episode,
        OpenEnvTool,
        World,
    )
    from kiln_ai.worlds.session_manager import WorldSessionManager

_agent_run_id: ContextVar[str | None] = ContextVar("agent_run_id", default=None)


def get_agent_run_id() -> str | None:
    return _agent_run_id.get()


def set_agent_run_id(run_id: str) -> None:
    _agent_run_id.set(run_id)


def clear_agent_run_id() -> None:
    _agent_run_id.set(None)


def generate_agent_run_id() -> str:
    return f"run_{uuid.uuid4().hex[:16]}"


@dataclass(frozen=True)
class EpisodeContext:
    """The episode an eval job is running against, plus what the registry
    needs to swap tools: the world, the session manager that holds the live session, and the
    tools the environment serves (by function name), resolved once per job.
    """

    episode: "Episode"
    world: "World"
    session_manager: "WorldSessionManager"
    tools: dict[str, "OpenEnvTool"] = field(default_factory=dict)


# Set by the eval runner for the duration of one job (generation and grading), and
# reset with the token in a `finally`. The reset is correctness, not hygiene:
# `AsyncJobRunner` reuses long-lived worker tasks, and consecutive jobs on one worker
# share a context. Request handlers and other tasks copy the *server's* context at
# creation, so they never observe a job's value; that is why the registry override
# below can never leak into API, chat, or export code paths.
_episode: ContextVar["EpisodeContext | None"] = ContextVar("episode", default=None)


def get_episode() -> "EpisodeContext | None":
    return _episode.get()


def set_episode(
    ctx: "EpisodeContext | None",
) -> Token["EpisodeContext | None"]:
    return _episode.set(ctx)


def reset_episode(token: Token["EpisodeContext | None"]) -> None:
    _episode.reset(token)


def generate_episode_id() -> str:
    return f"ep_{uuid.uuid4().hex[:16]}"
