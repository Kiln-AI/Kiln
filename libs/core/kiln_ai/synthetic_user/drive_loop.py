"""Single-case drive loop for the multi-turn synthetic-user runner.

`drive_case` alternates the target task adapter with the local
`SyntheticUserDriver`, producing a chain of `TaskRun`s on the target side.
The loop runs for a fixed `turns` count — no early termination, no
`<DONE>` / `<CANCEL>` sentinels — by design (see spec).

Persistence is fully delegated to `target_invoker(...)`: the batch runner's
invoker writes each TaskRun to disk (with `parent_task_run_id` chaining),
while the eval-time invoker keeps the chain in memory. Either way the
returned runs carry `trace` and `cumulative_usage`. The SU side is
in-memory only and produces no TaskRuns.
"""

from dataclasses import dataclass
from typing import Protocol

from kiln_ai.datamodel.task_run import TaskRun
from kiln_ai.synthetic_user.driver import SyntheticUserDriver
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam


class TargetInvoker(Protocol):
    """Callable that invokes the target task for one turn. The runner
    wraps `adapter_for_task(task, run_config).invoke` to satisfy this;
    tests pass in a fake. Keeps the drive loop target-agnostic — it just
    cares about the persisted TaskRun that comes back.
    """

    async def __call__(
        self,
        *,
        input: str,
        prior_trace: list[ChatCompletionMessageParam] | None,
        parent_task_run: TaskRun | None,
    ) -> TaskRun: ...


class TurnHook(Protocol):
    """Optional callback invoked once per turn after the SU has replied.

    The runner uses this to translate per-turn outcomes into BatchEvents
    without coupling drive_case to the event shape. The hook fires after
    both the assistant turn is persisted AND the SU's next message is
    produced, so callers have all per-turn signal in one place.
    """

    async def __call__(self, *, run: TaskRun, su_message: str) -> None: ...


@dataclass(frozen=True)
class DriveCaseResult:
    """Outcome of one drive_case run.

    `chain` is the list of persisted TaskRuns the adapter produced (leaf
    last). There is no stop_reason field — every case ends after exactly
    `turns` iterations by design.

    `su_total_cost` sums the SU driver's per-turn LLM cost across the
    case. SU turns aren't persisted as TaskRuns, so this is the only
    place that spend surfaces — the runner adds it to the target's
    `cumulative_usage.cost` to produce an honest total.
    """

    chain: list[TaskRun]
    su_total_cost: float


async def drive_case(
    *,
    seed_prompt: str,
    target_invoker: TargetInvoker,
    su_driver: SyntheticUserDriver,
    turns: int,
    on_turn: TurnHook | None = None,
) -> DriveCaseResult:
    """Drive one synthetic-user case for `turns` turns.

    Args:
        seed_prompt: the opening user-side message sent into the target task.
        target_invoker: how to call the target task; produces a persisted TaskRun.
        su_driver: pre-built SU driver for this case. Caller is responsible
            for construction (so a malformed persona fails at the caller's
            layer, not here).
        turns: exact number of assistant turns to produce. The loop runs
            `range(turns)` and always completes all iterations — no early
            stop.
        on_turn: optional async hook called once per turn after `su_driver.respond`
            returns. The runner plugs in here to emit TurnCompletedEvent.

    Returns:
        DriveCaseResult with the chain of TaskRuns produced (leaf last).
    """
    if turns < 1:
        raise ValueError(f"turns must be >= 1, got {turns}")
    # Assert-loud on missing seed. An empty string would silently flow
    # into the target adapter and surface as a confusing model-side error
    # rather than a clean "the case is malformed" signal.
    if not seed_prompt:
        raise ValueError("seed_prompt must be a non-empty string")

    user_msg: str = seed_prompt
    prev_run: TaskRun | None = None
    prev_trace: list[ChatCompletionMessageParam] | None = None
    chain: list[TaskRun] = []
    su_total_cost: float = 0.0

    for _ in range(turns):
        new_run = await target_invoker(
            input=user_msg,
            prior_trace=prev_trace,
            parent_task_run=prev_run,
        )
        chain.append(new_run)

        # The SU driver does the role filtering / role swap / invariant
        # checks itself. We pass the new run's cumulative trace as-is.
        su_message, su_cost = await su_driver.respond(new_run.trace or [])
        su_total_cost += su_cost

        if on_turn is not None:
            await on_turn(run=new_run, su_message=su_message)

        user_msg = su_message
        prev_run = new_run
        prev_trace = new_run.trace

    return DriveCaseResult(chain=chain, su_total_cost=su_total_cost)
