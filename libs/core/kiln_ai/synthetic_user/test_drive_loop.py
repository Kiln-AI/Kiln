"""Unit tests for drive_case.

The TargetInvoker is replaced with a hand-written fake; the
SyntheticUserDriver is replaced with a `Mock(spec=)` whose `respond()`
is an AsyncMock returning canned strings. No real model calls.
"""

from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from kiln_ai.datamodel.task_run import TaskRun
from kiln_ai.synthetic_user.drive_loop import DriveCaseResult, drive_case
from kiln_ai.synthetic_user.driver import SyntheticUserDriver

# ───────────────────────── helpers / fixtures ─────────────────────────


_SYSTEM_PROMPT = "You are a target agent."


def _fake_run(trace: list[dict], run_id: str | None = None) -> Mock:
    """Minimal stand-in for a persisted TaskRun — drive_case only reads
    `.trace`; we add `.id` so tests can identify the chain order.
    """
    run = Mock(spec=TaskRun)
    run.trace = trace
    run.id = run_id or f"run-{len(trace)}"
    return run


class _FakeInvoker:
    """Records each call's (input, prior_trace, parent_task_run) and
    returns successive canned TaskRun mocks. Each call appends one
    user + one assistant turn to the prior trace to mimic how
    `adapter.invoke` builds cumulative traces.
    """

    def __init__(self, assistant_replies: list[str]):
        self._replies = list(assistant_replies)
        self.calls: list[dict[str, Any]] = []

    async def __call__(
        self,
        *,
        input: str,
        prior_trace: list[dict] | None,
        parent_task_run: TaskRun | None,
    ) -> TaskRun:
        self.calls.append(
            {
                "input": input,
                "prior_trace": prior_trace,
                "parent_task_run": parent_task_run,
            }
        )
        if not self._replies:
            raise AssertionError("FakeInvoker called more times than replies provided")
        assistant_reply = self._replies.pop(0)
        if prior_trace is None:
            new_trace = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": input},
                {"role": "assistant", "content": assistant_reply},
            ]
        else:
            new_trace = [
                *prior_trace,
                {"role": "user", "content": input},
                {"role": "assistant", "content": assistant_reply},
            ]
        return _fake_run(new_trace, run_id=f"run-turn-{len(self.calls)}")


def _su_driver_with_replies(replies: list[str], cost_per_reply: float = 0.0) -> Mock:
    """Mock(spec=SyntheticUserDriver) with respond() returning canned
    (message, cost) tuples. `cost_per_reply` lets cost-aware tests inject
    a non-zero per-call cost; defaults to 0.0 for the legacy tests.
    """
    drv = Mock(spec=SyntheticUserDriver)
    drv.respond = AsyncMock(side_effect=[(r, cost_per_reply) for r in replies])
    return drv


# ───────────────────────── happy path ─────────────────────────


@pytest.mark.asyncio
async def test_drive_case_runs_exactly_turns_iterations() -> None:
    """No early termination — loop always completes `turns` iterations."""
    invoker = _FakeInvoker(assistant_replies=["a1", "a2", "a3", "a4"])
    su = _su_driver_with_replies(["u2", "u3", "u4", "u5"])

    result = await drive_case(
        seed_prompt="hi there",
        target_invoker=invoker,
        su_driver=su,
        turns=4,
    )

    assert isinstance(result, DriveCaseResult)
    assert len(result.chain) == 4
    assert len(invoker.calls) == 4
    assert su.respond.await_count == 4


@pytest.mark.asyncio
async def test_drive_case_seeds_first_turn_with_case_seed_prompt() -> None:
    invoker = _FakeInvoker(assistant_replies=["a1"])
    su = _su_driver_with_replies(["next user msg"])

    await drive_case(
        seed_prompt="custom seed",
        target_invoker=invoker,
        su_driver=su,
        turns=1,
    )

    first = invoker.calls[0]
    assert first["input"] == "custom seed"
    assert first["prior_trace"] is None
    assert first["parent_task_run"] is None


@pytest.mark.asyncio
async def test_drive_case_threads_prior_trace_and_parent_run() -> None:
    invoker = _FakeInvoker(assistant_replies=["r1", "r2", "r3"])
    su = _su_driver_with_replies(["u2", "u3", "u4"])

    result = await drive_case(
        seed_prompt="u1",
        target_invoker=invoker,
        su_driver=su,
        turns=3,
    )

    # Turn 2's invoke should receive turn 1's trace + TaskRun.
    second = invoker.calls[1]
    assert second["input"] == "u2"
    assert second["prior_trace"] is result.chain[0].trace
    assert second["parent_task_run"] is result.chain[0]

    # Turn 3's invoke should receive turn 2's trace + TaskRun.
    third = invoker.calls[2]
    assert third["input"] == "u3"
    assert third["prior_trace"] is result.chain[1].trace
    assert third["parent_task_run"] is result.chain[1]


@pytest.mark.asyncio
async def test_drive_case_passes_full_trace_to_su_driver() -> None:
    """The SU driver's `respond` receives the full cumulative trace —
    the driver itself filters to visible_message_roles.
    """
    invoker = _FakeInvoker(assistant_replies=["a1", "a2"])
    su = _su_driver_with_replies(["u2", "u3"])

    result = await drive_case(
        seed_prompt="u1",
        target_invoker=invoker,
        su_driver=su,
        turns=2,
    )

    # First respond() got turn-1's trace ([sys, u1, a1]).
    first_call_args = su.respond.await_args_list[0].args
    assert first_call_args[0] == result.chain[0].trace
    # Second respond() got turn-2's trace.
    second_call_args = su.respond.await_args_list[1].args
    assert second_call_args[0] == result.chain[1].trace


# ───────────────────────── on_turn hook ─────────────────────────


@pytest.mark.asyncio
async def test_drive_case_on_turn_hook_fires_once_per_turn() -> None:
    invoker = _FakeInvoker(assistant_replies=["a1", "a2", "a3"])
    su = _su_driver_with_replies(["u2", "u3", "u4"])

    captured: list[tuple[TaskRun, str]] = []

    async def _hook(*, run: TaskRun, su_message: str) -> None:
        captured.append((run, su_message))

    result = await drive_case(
        seed_prompt="hi there",
        target_invoker=invoker,
        su_driver=su,
        turns=3,
        on_turn=_hook,
    )

    assert len(captured) == 3
    for i, (run, msg) in enumerate(captured):
        assert run is result.chain[i]
        # SU's replies are u2, u3, u4 per the fake.
        assert msg == ["u2", "u3", "u4"][i]


@pytest.mark.asyncio
async def test_drive_case_works_without_on_turn_hook() -> None:
    """on_turn is optional — the loop runs normally if it's None."""
    invoker = _FakeInvoker(assistant_replies=["a1"])
    su = _su_driver_with_replies(["u2"])

    result = await drive_case(
        seed_prompt="hi there",
        target_invoker=invoker,
        su_driver=su,
        turns=1,
        on_turn=None,
    )

    assert len(result.chain) == 1


# ───────────────────────── invariants ─────────────────────────


@pytest.mark.parametrize("bad_turns", [0, -1, -100])
@pytest.mark.asyncio
async def test_drive_case_rejects_invalid_turns(bad_turns: int) -> None:
    """Parameterized so a regression that mistyped `if turns == 0` instead of
    `if turns < 1` would be caught by the negative cases.
    """
    invoker = _FakeInvoker(assistant_replies=[])
    su = _su_driver_with_replies([])

    with pytest.raises(ValueError, match="turns must be >= 1"):
        await drive_case(
            seed_prompt="hi there",
            target_invoker=invoker,
            su_driver=su,
            turns=bad_turns,
        )


@pytest.mark.asyncio
async def test_drive_case_rejects_empty_seed_prompt() -> None:
    """An empty seed would silently flow into the target adapter and
    surface as a confusing model-side error; assert-loud at the boundary
    so this fails as the unambiguous "malformed case" it is.
    """
    invoker = _FakeInvoker(assistant_replies=[])
    su = _su_driver_with_replies([])

    with pytest.raises(ValueError, match="seed_prompt"):
        await drive_case(
            seed_prompt="",
            target_invoker=invoker,
            su_driver=su,
            turns=1,
        )


@pytest.mark.asyncio
async def test_drive_case_propagates_target_invoker_errors() -> None:
    """If the target_invoker raises, the loop doesn't swallow — the
    runner is responsible for per-case isolation, not drive_case.
    """
    bad_invoker = AsyncMock(side_effect=RuntimeError("target blew up"))
    su = _su_driver_with_replies([])

    with pytest.raises(RuntimeError, match="target blew up"):
        await drive_case(
            seed_prompt="hi there",
            target_invoker=bad_invoker,
            su_driver=su,
            turns=3,
        )


@pytest.mark.asyncio
async def test_drive_case_propagates_su_driver_errors() -> None:
    """If su_driver.respond raises, the loop doesn't swallow either."""
    invoker = _FakeInvoker(assistant_replies=["a1"])
    su = Mock(spec=SyntheticUserDriver)
    su.respond = AsyncMock(side_effect=ValueError("bad conversation"))

    with pytest.raises(ValueError, match="bad conversation"):
        await drive_case(
            seed_prompt="hi there",
            target_invoker=invoker,
            su_driver=su,
            turns=3,
        )


# ───────────────────────── chain order ─────────────────────────


@pytest.mark.asyncio
async def test_drive_case_returns_chain_in_order_leaf_last() -> None:
    invoker = _FakeInvoker(assistant_replies=["a1", "a2", "a3"])
    su = _su_driver_with_replies(["u2", "u3", "u4"])

    result = await drive_case(
        seed_prompt="u1",
        target_invoker=invoker,
        su_driver=su,
        turns=3,
    )

    assert [r.id for r in result.chain] == ["run-turn-1", "run-turn-2", "run-turn-3"]
    # Leaf's trace is the longest — covers all three round-trips.
    assert len(result.chain[-1].trace) > len(result.chain[0].trace)


# ───────────────────────── episode id scoping ─────────────────────────


@pytest.mark.asyncio
async def test_drive_case_sets_one_episode_id_for_all_turns() -> None:
    from kiln_ai.run_context import get_episode_id

    seen: list[str | None] = []

    class _RecordingInvoker(_FakeInvoker):
        async def __call__(self, **kwargs):  # type: ignore[override]
            seen.append(get_episode_id())
            return await super().__call__(**kwargs)

    invoker = _RecordingInvoker(["a1", "a2", "a3"])
    await drive_case(
        seed_prompt="seed",
        target_invoker=invoker,
        su_driver=_su_driver_with_replies(["u2", "u3", "done"]),
        turns=3,
    )
    assert len(seen) == 3
    assert seen[0] is not None
    assert len(set(seen)) == 1, "all turns of one case share one episode id"
    assert get_episode_id() is None, "cleared after the case"


@pytest.mark.asyncio
async def test_drive_case_episode_ids_differ_across_cases() -> None:
    from kiln_ai.run_context import get_episode_id

    ids: list[str | None] = []

    class _RecordingInvoker(_FakeInvoker):
        async def __call__(self, **kwargs):  # type: ignore[override]
            ids.append(get_episode_id())
            return await super().__call__(**kwargs)

    for _ in range(2):
        await drive_case(
            seed_prompt="seed",
            target_invoker=_RecordingInvoker(["a1"]),
            su_driver=_su_driver_with_replies(["done"]),
            turns=1,
        )
    assert len(ids) == 2 and ids[0] != ids[1]
