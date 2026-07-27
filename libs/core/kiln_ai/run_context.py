"""Agent run context management using contextvars.

The agent run ID propagates automatically through async call chains,
including asyncio.gather and sub-agent calls via KilnTaskTool.

This is a general-purpose ID for scoping work to a single agent run,
usable for logging, caching, metrics, or any run-scoped operations.
"""

import uuid
from contextvars import ContextVar

_agent_run_id: ContextVar[str | None] = ContextVar("agent_run_id", default=None)

# Unlike the agent run ID (fresh per adapter invoke, i.e. per turn), the episode
# ID spans one whole multi-turn conversation. It is set by drivers that own the
# full turn loop (e.g. the synthetic-user drive loop) and lets run-scoped
# consumers (tools, caches) key state to the conversation rather than the turn.
_episode_id: ContextVar[str | None] = ContextVar("episode_id", default=None)


def get_agent_run_id() -> str | None:
    return _agent_run_id.get()


def get_episode_id() -> str | None:
    return _episode_id.get()


def set_episode_id(episode_id: str) -> None:
    _episode_id.set(episode_id)


def clear_episode_id() -> None:
    _episode_id.set(None)


def generate_episode_id() -> str:
    return f"ep_{uuid.uuid4().hex[:16]}"


# The eval input ID spans one eval case (all turns driven for one EvalInput).
# Set by the eval runner around the drive; lets run-scoped consumers key
# behavior/state to the specific eval input being driven.
_eval_input_id: ContextVar[str | None] = ContextVar("eval_input_id", default=None)


def get_eval_input_id() -> str | None:
    return _eval_input_id.get()


def set_eval_input_id(input_id: str) -> None:
    _eval_input_id.set(input_id)


def clear_eval_input_id() -> None:
    _eval_input_id.set(None)


def set_agent_run_id(run_id: str) -> None:
    _agent_run_id.set(run_id)


def clear_agent_run_id() -> None:
    _agent_run_id.set(None)


def generate_agent_run_id() -> str:
    return f"run_{uuid.uuid4().hex[:16]}"
