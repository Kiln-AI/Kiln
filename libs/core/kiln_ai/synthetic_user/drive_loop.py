"""Single-case drive loop for the multi-turn synthetic-user runner.

`drive_case` alternates the target task adapter with the local
`SyntheticUserDriver`, producing a chain of `TaskRun`s on the target side.
The loop runs for a fixed `turns` count — no early termination, no
`<DONE>` / `<CANCEL>` sentinels — by design (see spec). The seed prompt is
the first user message, so `turns` assistant turns consume exactly
`turns - 1` synthetic-user replies; the SU is not called after the final
assistant turn.

Persistence is fully delegated to `target_invoker(...)`: the batch runner's
invoker writes each TaskRun to disk (with `parent_task_run_id` chaining),
while the eval-time invoker keeps the chain in memory. Either way the
returned runs carry `trace` and `cumulative_usage`. The SU side is
in-memory only and produces no TaskRuns.
"""

from dataclasses import dataclass
from typing import Protocol

from kiln_ai.datamodel.task_run import TaskRun
from kiln_ai.datamodel.usage import Usage
from kiln_ai.run_context import clear_episode_id, generate_episode_id, set_episode_id
from kiln_ai.synthetic_user.driver import SyntheticUserDriver
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam


class TargetInvoker(Protocol):
    """Callable that invokes the target task for one turn. The runner
    wraps `adapter_for_task(task, run_config).invoke` to satisfy this;
    tests pass in a fake. Keeps the drive loop target-agnostic — it just
    cares about the TaskRun that comes back, persisted or in-memory per
    the invoker.
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

    Fires once per assistant turn INCLUDING the last — consumers use it to
    track every persisted run and to emit per-turn progress, so skipping it
    on the final turn would strand the leaf. On that final turn there is no
    next user message (see `_drive_case_turns`) and `su_message` is `""`.
    """

    async def __call__(self, *, run: TaskRun, su_message: str) -> None: ...


def _reported(usage: Usage) -> Usage | None:
    """None when the accumulator holds nothing the provider actually reported.

    Field-level check rather than `== Usage()` so a Usage subclass instance
    can't defeat pydantic's class-sensitive equality. Distinguishing "no
    usage reported" from "zero tokens" is what lets a consumer tell an
    unmeasured drive from a free one.
    """
    if all(v is None for v in usage.model_dump().values()):
        return None
    return usage


@dataclass(frozen=True)
class DriveCaseResult:
    """Outcome of one drive_case run.

    `chain` is the list of TaskRuns the adapter produced (leaf last);
    whether they were persisted is the target_invoker's choice. There is
    no stop_reason field — every case ends after exactly `turns`
    iterations by design.

    `su_usage` sums the SU driver's per-turn usage (tokens, cost, latency)
    across the case. SU turns aren't persisted as TaskRuns, so this is the
    only place that spend surfaces: callers that discard it make the driver
    model's spend unrecoverable after the fact. None when no turn reported
    usage.
    """

    chain: list[TaskRun]
    su_usage: Usage | None

    @property
    def su_total_cost(self) -> float:
        """The SU's dollar cost alone, for callers that only need the scalar
        (e.g. the interactive runner's per-case UI event). 0.0 when the
        provider reported no cost — do NOT read that as a measured zero;
        check `su_usage is None` for that."""
        if self.su_usage is None or self.su_usage.cost is None:
            return 0.0
        return float(self.su_usage.cost)


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
        target_invoker: how to call the target task for one turn; returns
            the turn's TaskRun (persistence is the invoker's concern).
        su_driver: pre-built SU driver for this case. Caller is responsible
            for construction (so a malformed persona fails at the caller's
            layer, not here).
        turns: exact number of assistant turns to produce. The loop runs
            `range(turns)` and always completes all iterations — no early
            stop. `su_driver.respond` is called `turns - 1` times: the seed
            prompt supplies the first user message and the last assistant
            turn needs no follow-up.
        on_turn: optional async hook called once per assistant turn, after
            `su_driver.respond` where there is one. The runner plugs in here
            to emit TurnCompletedEvent. On the final turn `su_message` is
            `""` — no SU reply is generated.

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
    su_usage = Usage()

    # One episode ID for the whole case: every turn's adapter invoke (and any
    # tool call it makes) sees the same ID via the run-context contextvar,
    # while concurrently-driven cases each carry their own.
    set_episode_id(generate_episode_id())
    try:
        return await _drive_case_turns(
            user_msg=user_msg,
            prev_run=prev_run,
            prev_trace=prev_trace,
            chain=chain,
            su_usage=su_usage,
            target_invoker=target_invoker,
            su_driver=su_driver,
            turns=turns,
            on_turn=on_turn,
        )
    finally:
        clear_episode_id()


async def _drive_case_turns(
    *,
    user_msg: str,
    prev_run: TaskRun | None,
    prev_trace: list[ChatCompletionMessageParam] | None,
    chain: list[TaskRun],
    su_usage: Usage,
    target_invoker: TargetInvoker,
    su_driver: SyntheticUserDriver,
    turns: int,
    on_turn: TurnHook | None,
) -> DriveCaseResult:
    last_turn = turns - 1
    for turn_index in range(turns):
        new_run = await target_invoker(
            input=user_msg,
            prior_trace=prev_trace,
            parent_task_run=prev_run,
        )
        chain.append(new_run)

        # No SU call after the final assistant turn. The seed prompt is the
        # first user message, so `turns` assistant turns need only
        # `turns - 1` SU replies — a reply produced here would be assigned
        # to `user_msg` and thrown away as the loop exits. That discarded
        # call is not free:
        #   - it carries the largest context of the case (the whole
        #     conversation), and measures at 45.5% of ALL synthetic-user
        #     input tokens across a drive (KIL-778);
        #   - asked to reply to a conversation that has visibly finished,
        #     driver models routinely return an EMPTY assistant message,
        #     which the adapter rejects ("Model returned an assistant
        #     message, but no content or tool calls"). That exception
        #     propagates out of drive_case and destroys a conversation that
        #     had already completed successfully — no EvalRun is persisted.
        su_message = ""
        if turn_index < last_turn:
            # The SU driver does the role filtering / role swap / invariant
            # checks itself. We pass the new run's cumulative trace as-is.
            su_message, turn_usage = await su_driver.respond(new_run.trace or [])
            if turn_usage is not None:
                su_usage = su_usage + turn_usage

        # Still fires on the final turn (with an empty su_message): callers
        # track persisted runs and per-turn progress here, so the leaf must
        # not be skipped.
        if on_turn is not None:
            await on_turn(run=new_run, su_message=su_message)

        user_msg = su_message
        prev_run = new_run
        prev_trace = new_run.trace

    return DriveCaseResult(chain=chain, su_usage=_reported(su_usage))
