"""Unit tests for drive_case.

The TargetInvoker is replaced with a hand-written fake; the
SyntheticUserDriver is replaced with a `Mock(spec=)` whose `respond()`
is an AsyncMock returning canned strings. No real model calls.
"""

from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from kiln_ai.datamodel.task_run import TaskRun
from kiln_ai.synthetic_user.driver import SyntheticUserDriver

from app.desktop.studio_server.api_client.kiln_ai_server_client.models import (
    SyntheticUserCase,
)
from app.desktop.studio_server.synthetic_user.drive_loop import (
    DriveCaseResult,
    drive_case,
)

# ───────────────────────── helpers / fixtures ─────────────────────────


_SYSTEM_PROMPT = "You are a target agent."


def _case(seed: str = "hi there") -> SyntheticUserCase:
    return SyntheticUserCase(
        seed_prompt=seed,
        synthetic_user_info=(
            "<persona>frustrated customer</persona>"
            "<goal>get a refund outside policy</goal>"
            "<behavior_guidance>be polite then escalate</behavior_guidance>"
        ),
    )


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


def _su_driver_with_replies(replies: list[str]) -> Mock:
    """Mock(spec=SyntheticUserDriver) with respond() returning canned strings."""
    drv = Mock(spec=SyntheticUserDriver)
    drv.respond = AsyncMock(side_effect=replies)
    return drv


# ───────────────────────── happy path ─────────────────────────


@pytest.mark.asyncio
async def test_drive_case_runs_exactly_turns_iterations() -> None:
    """No early termination — loop always completes `turns` iterations."""
    invoker = _FakeInvoker(assistant_replies=["a1", "a2", "a3", "a4"])
    su = _su_driver_with_replies(["u2", "u3", "u4", "u5"])

    result = await drive_case(
        case=_case(),
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
        case=_case(seed="custom seed"),
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
        case=_case(seed="u1"),
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
        case=_case(seed="u1"),
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
        case=_case(),
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
        case=_case(),
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
            case=_case(),
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
            case=_case(seed=""),
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
            case=_case(),
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
            case=_case(),
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
        case=_case(seed="u1"),
        target_invoker=invoker,
        su_driver=su,
        turns=3,
    )

    assert [r.id for r in result.chain] == ["run-turn-1", "run-turn-2", "run-turn-3"]
    # Leaf's trace is the longest — covers all three round-trips.
    assert len(result.chain[-1].trace) > len(result.chain[0].trace)
