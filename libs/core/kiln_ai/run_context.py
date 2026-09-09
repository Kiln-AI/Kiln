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
    from kiln_ai.datamodel.synthetic_world import (
        SyntheticInstance,
        SyntheticTool,
        SyntheticWorld,
    )

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
class SyntheticInstanceContext:
    """The synthetic instance an eval job is running against, plus what the registry
    needs to swap tools: the world and its bindings, resolved once per job.

    `state_unavailable` marks a reused trace whose instance copy has been evicted:
    tools are still swapped (nothing should generate), but graders that need the
    state must skip rather than read a path that no longer exists.
    """

    instance: "SyntheticInstance"
    world: "SyntheticWorld"
    bindings: dict[str, "SyntheticTool"] = field(default_factory=dict)
    state_unavailable: bool = False


# Set by the eval runner for the duration of one job (generation and grading), and
# reset with the token in a `finally`. The reset is correctness, not hygiene:
# `AsyncJobRunner` reuses long-lived worker tasks, and consecutive jobs on one worker
# share a context. Request handlers and other tasks copy the *server's* context at
# creation, so they never observe a job's value; that is why the registry override
# below can never leak into API, chat, or export code paths.
_synthetic_instance: ContextVar["SyntheticInstanceContext | None"] = ContextVar(
    "synthetic_instance", default=None
)


def get_synthetic_instance() -> "SyntheticInstanceContext | None":
    return _synthetic_instance.get()


def set_synthetic_instance(
    ctx: "SyntheticInstanceContext | None",
) -> Token["SyntheticInstanceContext | None"]:
    return _synthetic_instance.set(ctx)


def reset_synthetic_instance(token: Token["SyntheticInstanceContext | None"]) -> None:
    _synthetic_instance.reset(token)


def generate_synthetic_instance_id() -> str:
    return f"inst_{uuid.uuid4().hex[:16]}"
