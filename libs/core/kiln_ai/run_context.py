"""Agent run context management using contextvars.

The agent run ID propagates automatically through async call chains,
including asyncio.gather and sub-agent calls via KilnTaskTool.

This is a general-purpose ID for scoping work to a single agent run,
usable for logging, caching, metrics, or any run-scoped operations.
"""

import uuid
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Iterator

from kiln_ai.datamodel.openenv import OpenEnvEpisode, OpenEnvServer, OpenEnvTool
from kiln_ai.openenv.session_manager import OpenEnvSessionManager

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
    """The episode a run or eval job is generating against, plus what the tool registry
    needs to resolve the environment's tool ids: the environment, the session manager that
    holds the live session, and the tools the environment serves (by function name).
    """

    episode: "OpenEnvEpisode"
    openenv_server: "OpenEnvServer"
    session_manager: "OpenEnvSessionManager"
    tools: dict[str, "OpenEnvTool"] = field(default_factory=dict)


# Set while an episode's run generates (by the eval runner for a job, and by the adapter
# for a run whose tools reach an environment), and reset with the token in a `finally`.
# The reset is correctness, not hygiene: `AsyncJobRunner` reuses long-lived worker tasks,
# and consecutive jobs on one worker share a context. Request handlers and other tasks
# copy the *server's* context at creation, so they never observe another run's episode.
# Graders read the episode from the trace, not from here.
_episode: ContextVar["EpisodeContext | None"] = ContextVar("episode", default=None)


def get_episode() -> "EpisodeContext | None":
    """The episode the current task is running against, or None outside an environment."""
    return _episode.get()


def set_episode(
    ctx: "EpisodeContext | None",
) -> Token["EpisodeContext | None"]:
    """Make `ctx` the current episode; pass the returned token to `reset_episode`."""
    return _episode.set(ctx)


def reset_episode(token: Token["EpisodeContext | None"]) -> None:
    """Restore the episode that was current before the matching `set_episode`."""
    _episode.reset(token)


# Set while a run that must not open its own environment session generates (eval
# generation, which owns its episodes). Nested runs, such as a Kiln task tool's sub-run,
# inherit it, so none of them opens a session either.
_openenv_sessions_off: ContextVar[bool] = ContextVar(
    "openenv_sessions_off", default=False
)


def openenv_sessions_off() -> bool:
    """True when runs in the current context must not open environment sessions."""
    return _openenv_sessions_off.get()


@contextmanager
def no_openenv_sessions() -> Iterator[None]:
    """Stop runs in this block, and runs nested in them, opening environment sessions."""
    token = _openenv_sessions_off.set(True)
    try:
        yield
    finally:
        _openenv_sessions_off.reset(token)
