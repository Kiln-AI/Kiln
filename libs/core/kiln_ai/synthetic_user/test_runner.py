"""Unit tests for run_cases_batch.

`adapter_for_task` is monkeypatched to return a fake adapter whose
`.invoke` is an AsyncMock; `SyntheticUserDriver` is replaced with a
patched class returning a mocked instance whose `respond()` yields
canned strings. Tests collect the event stream into a list and inspect
ordering / per-case bookkeeping.
"""

import asyncio
import re
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from kiln_ai.datamodel.datamodel_enums import (
    ModelProviderName,
    StructuredOutputMode,
)
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties, ToolsRunConfig
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.task_run import TaskRun
from kiln_ai.synthetic_user import runner as runner_mod
from kiln_ai.synthetic_user.case import SyntheticUserCase
from kiln_ai.synthetic_user.driver import SyntheticUserDriver
from kiln_ai.synthetic_user.models import SyntheticUserDriverConfig
from kiln_ai.synthetic_user.parser import SyntheticUserInfoParseError
from kiln_ai.synthetic_user.runner import (
    BatchCompletedEvent,
    BatchEvent,
    BatchStartedEvent,
    CaseCompletedEvent,
    CaseFailedEvent,
    TurnCompletedEvent,
    run_cases_batch,
)

# ───────────────────────── helpers / fixtures ─────────────────────────


def _case(idx: int = 0) -> SyntheticUserCase:
    return SyntheticUserCase(
        seed_prompt=f"seed-{idx}",
        synthetic_user_info=(
            f"<persona>persona-{idx}</persona>"
            f"<goal>goal-{idx}</goal>"
            f"<behavior_guidance>guidance-{idx}</behavior_guidance>"
        ),
    )


def _su_driver_config() -> SyntheticUserDriverConfig:
    return SyntheticUserDriverConfig(
        model_name="claude_4_5_haiku",
        model_provider_name=ModelProviderName.openrouter,
    )


def _target_run_config() -> KilnAgentRunConfigProperties:
    return KilnAgentRunConfigProperties(
        model_name="gpt_5_5",
        model_provider_name=ModelProviderName.openrouter,
        prompt_id="simple_prompt_builder",
        structured_output_mode=StructuredOutputMode.default,
        tools_config=ToolsRunConfig(tools=[]),
    )


def _fake_run(run_id: str, cost: float = 0.0) -> Mock:
    """Stand-in for a persisted TaskRun. drive_case reads `.trace`; runner
    reads `.id` + `.cumulative_usage.cost`; `_tag_leaf` writes `.tags`
    and calls `.save_to_file()`.
    """
    run = Mock(spec=TaskRun)
    run.id = run_id
    run.trace = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u"},
        {"role": "assistant", "content": f"a-{run_id}"},
    ]
    run.cumulative_usage = Mock(cost=cost)
    run.tags = []
    run.save_to_file = Mock()
    return run


def _patch_adapter_for_task(
    monkeypatch: pytest.MonkeyPatch, invoke_side_effect: Any
) -> AsyncMock:
    """Make `adapter_for_task` return an adapter whose .invoke yields the
    given side_effect (list of TaskRuns or a callable).
    """
    adapter = Mock()
    adapter.invoke = AsyncMock(side_effect=invoke_side_effect)
    monkeypatch.setattr(
        runner_mod, "adapter_for_task", lambda task, run_config: adapter
    )
    return adapter.invoke


def _patch_su_driver(
    monkeypatch: pytest.MonkeyPatch, replies_per_case: dict[int, list[str]] | list[str]
) -> None:
    """Replace SyntheticUserDriver with a stub that returns canned strings.

    Pass a list to give every case the same reply schedule; pass a dict
    keyed by case_index for per-case schedules.
    """
    call_counter = {"i": 0}

    def _ctor(blob, config):
        idx = call_counter["i"]
        call_counter["i"] += 1
        replies = (
            replies_per_case[idx]
            if isinstance(replies_per_case, dict)
            else list(replies_per_case)
        )
        instance = Mock(spec=SyntheticUserDriver)
        # respond() returns (message, cost). Tests that don't care about
        # cost get 0.0 — the runner adds it to total_cost regardless.
        instance.respond = AsyncMock(side_effect=[(r, 0.0) for r in replies])
        return instance

    monkeypatch.setattr(runner_mod, "SyntheticUserDriver", _ctor)


def _patch_su_driver_factory(monkeypatch: pytest.MonkeyPatch, factory: Any) -> None:
    """For when tests need full control (e.g., raise on construction)."""
    monkeypatch.setattr(runner_mod, "SyntheticUserDriver", factory)


@pytest.fixture
def fake_task() -> Mock:
    return Mock(spec=Task)


async def _collect(gen) -> list[BatchEvent]:
    out: list[BatchEvent] = []
    async for ev in gen:
        out.append(ev)
    return out


# ───────────────────────── input validation ─────────────────────────


@pytest.mark.asyncio
async def test_empty_cases_raises(fake_task: Mock) -> None:
    with pytest.raises(ValueError, match="cases cannot be empty"):
        async for _ in run_cases_batch(
            cases=[],
            target_task=fake_task,
            target_run_config=_target_run_config(),
            su_driver_config=_su_driver_config(),
        ):
            pass


@pytest.mark.asyncio
async def test_invalid_turns_raises(fake_task: Mock) -> None:
    with pytest.raises(ValueError, match="turns must be >= 1"):
        async for _ in run_cases_batch(
            cases=[_case()],
            target_task=fake_task,
            target_run_config=_target_run_config(),
            su_driver_config=_su_driver_config(),
            turns=0,
        ):
            pass


@pytest.mark.asyncio
async def test_invalid_concurrency_raises(fake_task: Mock) -> None:
    with pytest.raises(ValueError, match="concurrency must be >= 1"):
        async for _ in run_cases_batch(
            cases=[_case()],
            target_task=fake_task,
            target_run_config=_target_run_config(),
            su_driver_config=_su_driver_config(),
            concurrency=0,
        ):
            pass


# ───────────────────────── happy path ─────────────────────────


@pytest.mark.asyncio
async def test_three_cases_produce_full_event_stream(
    fake_task: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases = [_case(0), _case(1), _case(2)]
    _patch_adapter_for_task(
        monkeypatch,
        [
            _fake_run("r0", cost=0.01),
            _fake_run("r1", cost=0.02),
            _fake_run("r2", cost=0.04),
        ],
    )
    _patch_su_driver(monkeypatch, replies_per_case=["u-next"])

    events = await _collect(
        run_cases_batch(
            cases=cases,
            target_task=fake_task,
            target_run_config=_target_run_config(),
            su_driver_config=_su_driver_config(),
            turns=1,
            concurrency=4,
            batch_tag="testbatch",
        )
    )

    assert isinstance(events[0], BatchStartedEvent)
    assert events[0].batch_tag == "testbatch"
    assert events[0].num_cases == 3

    assert isinstance(events[-1], BatchCompletedEvent)
    assert events[-1].successful == 3
    assert events[-1].failed == 0
    assert events[-1].batch_tag == "testbatch"
    assert events[-1].total_cost == pytest.approx(0.07)

    turn_events = [e for e in events if isinstance(e, TurnCompletedEvent)]
    case_done = [e for e in events if isinstance(e, CaseCompletedEvent)]
    assert len(turn_events) == 3
    assert len(case_done) == 3
    assert {e.case_index for e in case_done} == {0, 1, 2}
    for ev in case_done:
        assert ev.total_turns == 1


@pytest.mark.asyncio
async def test_total_cost_sums_target_and_su_driver_spend(
    fake_task: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CaseCompletedEvent.total_cost = leaf.cumulative_usage.cost + sum of
    SU driver's per-turn cost across the case. BatchCompletedEvent.total_cost
    sums those across successful cases. Locks in the honest-totals contract.
    """
    leaf_a = _fake_run("a-leaf", cost=0.10)
    leaf_b = _fake_run("b-leaf", cost=0.05)
    _patch_adapter_for_task(
        monkeypatch,
        [_fake_run("a-1"), leaf_a, _fake_run("b-1"), leaf_b],
    )

    # Each case's driver gets two replies at $0.01 each → $0.02 SU per case.
    def _ctor(blob, config):
        instance = Mock(spec=SyntheticUserDriver)
        instance.respond = AsyncMock(side_effect=[("u2", 0.01), ("u3", 0.01)])
        return instance

    monkeypatch.setattr(runner_mod, "SyntheticUserDriver", _ctor)

    events = await _collect(
        run_cases_batch(
            cases=[_case(0), _case(1)],
            target_task=fake_task,
            target_run_config=_target_run_config(),
            su_driver_config=_su_driver_config(),
            turns=2,
            concurrency=1,
        )
    )

    case_a, case_b = (e for e in events if isinstance(e, CaseCompletedEvent))
    assert case_a.total_cost == pytest.approx(0.10 + 0.02)
    assert case_b.total_cost == pytest.approx(0.05 + 0.02)

    batch = next(e for e in events if isinstance(e, BatchCompletedEvent))
    assert batch.total_cost == pytest.approx(0.12 + 0.07)


@pytest.mark.asyncio
async def test_turn_completed_event_carries_su_message_and_trace(
    fake_task: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_adapter_for_task(monkeypatch, [_fake_run("r0", cost=0.01)])
    _patch_su_driver(monkeypatch, replies_per_case=["the SU's reply"])

    events = await _collect(
        run_cases_batch(
            cases=[_case()],
            target_task=fake_task,
            target_run_config=_target_run_config(),
            su_driver_config=_su_driver_config(),
            turns=1,
        )
    )

    turn = next(e for e in events if isinstance(e, TurnCompletedEvent))
    assert turn.su_next_message == "the SU's reply"
    assert turn.cumulative_cost == pytest.approx(0.01)
    # Trace is whatever the fake run carried.
    assert any(m.get("role") == "assistant" for m in turn.trace)


@pytest.mark.asyncio
async def test_leaf_is_tagged_with_synthetic_user_case_and_batch_tag(
    fake_task: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    leaf = _fake_run("leaf")
    _patch_adapter_for_task(monkeypatch, [leaf])
    _patch_su_driver(monkeypatch, replies_per_case=["x"])

    await _collect(
        run_cases_batch(
            cases=[_case()],
            target_task=fake_task,
            target_run_config=_target_run_config(),
            su_driver_config=_su_driver_config(),
            turns=1,
            batch_tag="abc123",
        )
    )

    assert "synthetic_user_case" in leaf.tags
    assert "synthetic_user_batch:abc123" in leaf.tags
    leaf.save_to_file.assert_called_once()


@pytest.mark.asyncio
async def test_leaf_tagging_is_idempotent_on_pre_tagged_leaf(
    fake_task: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-tagging a leaf that already has the runner's tags + an unrelated
    user tag preserves the user tag and dedupes the runner's tags. The
    spec calls this out as the property that makes re-runs safe.
    """
    leaf = _fake_run("leaf")
    leaf.tags = [
        "synthetic_user_case",
        "synthetic_user_batch:abc123",
        "user_kept_this",
    ]
    _patch_adapter_for_task(monkeypatch, [leaf])
    _patch_su_driver(monkeypatch, replies_per_case=["x"])

    await _collect(
        run_cases_batch(
            cases=[_case()],
            target_task=fake_task,
            target_run_config=_target_run_config(),
            su_driver_config=_su_driver_config(),
            turns=1,
            batch_tag="abc123",
        )
    )

    assert leaf.tags.count("synthetic_user_case") == 1
    assert leaf.tags.count("synthetic_user_batch:abc123") == 1
    assert "user_kept_this" in leaf.tags
    assert leaf.tags == sorted(leaf.tags)


@pytest.mark.asyncio
async def test_auto_generates_batch_tag_when_not_provided(
    fake_task: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_adapter_for_task(monkeypatch, [_fake_run("r")])
    _patch_su_driver(monkeypatch, replies_per_case=["x"])

    events = await _collect(
        run_cases_batch(
            cases=[_case()],
            target_task=fake_task,
            target_run_config=_target_run_config(),
            su_driver_config=_su_driver_config(),
            turns=1,
        )
    )

    # Couple the assertion to the public contract — the auto-generated
    # tag must satisfy the batch_tag input regex `[A-Za-z0-9_-]{1,64}` so
    # it can be passed back as `batch_tag` on a subsequent run. Avoids
    # restating the implementation (uuid4().hex[:12]), which would lock
    # us in to a specific length/charset just because that's what we picked.
    started = next(e for e in events if isinstance(e, BatchStartedEvent))
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,64}", started.batch_tag) is not None


# ───────────────────────── per-case failure isolation ─────────────────────────


@pytest.mark.asyncio
async def test_malformed_blob_surfaces_as_case_failed(
    fake_task: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SyntheticUserDriver construction raises on a bad blob — that case
    fails alone; the others run normally.
    """
    call_counter = {"i": 0}

    def _ctor(blob, config):
        idx = call_counter["i"]
        call_counter["i"] += 1
        if idx == 1:
            raise SyntheticUserInfoParseError("bad blob")
        instance = Mock(spec=SyntheticUserDriver)
        instance.respond = AsyncMock(return_value=("ok", 0.0))
        return instance

    _patch_su_driver_factory(monkeypatch, _ctor)
    _patch_adapter_for_task(monkeypatch, [_fake_run("r0"), _fake_run("r2")])

    events = await _collect(
        run_cases_batch(
            cases=[_case(0), _case(1), _case(2)],
            target_task=fake_task,
            target_run_config=_target_run_config(),
            su_driver_config=_su_driver_config(),
            turns=1,
            concurrency=1,  # serialize so the SU driver factory is called in case order
        )
    )

    case_done = [e for e in events if isinstance(e, CaseCompletedEvent)]
    case_failed = [e for e in events if isinstance(e, CaseFailedEvent)]
    assert {e.case_index for e in case_done} == {0, 2}
    assert {e.case_index for e in case_failed} == {1}
    assert case_failed[0].error_code == "bad_synthetic_user_info"


@pytest.mark.asyncio
async def test_target_invoke_failure_surfaces_as_case_failed(
    fake_task: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If adapter.invoke raises, the case is marked failed — but other
    in-flight cases keep running.
    """
    _patch_adapter_for_task(monkeypatch, RuntimeError("kaboom"))
    _patch_su_driver(monkeypatch, replies_per_case=["x"])

    events = await _collect(
        run_cases_batch(
            cases=[_case()],
            target_task=fake_task,
            target_run_config=_target_run_config(),
            su_driver_config=_su_driver_config(),
            turns=1,
        )
    )

    failed = next(e for e in events if isinstance(e, CaseFailedEvent))
    assert failed.error_code == "unexpected_error"
    assert "RuntimeError" in failed.message
    assert "kaboom" in failed.message


@pytest.mark.asyncio
async def test_tag_leaf_failure_surfaces_as_case_failed(
    fake_task: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If save_to_file fails (e.g., disk full, validator rejects the tag),
    the case becomes case_failed instead of silently vanishing.
    """
    bad_leaf = _fake_run("bad-leaf")
    bad_leaf.save_to_file = Mock(side_effect=OSError("disk full"))
    _patch_adapter_for_task(monkeypatch, [bad_leaf])
    _patch_su_driver(monkeypatch, replies_per_case=["x"])

    events = await _collect(
        run_cases_batch(
            cases=[_case()],
            target_task=fake_task,
            target_run_config=_target_run_config(),
            su_driver_config=_su_driver_config(),
            turns=1,
        )
    )

    failed = next(e for e in events if isinstance(e, CaseFailedEvent))
    assert failed.error_code == "unexpected_error"
    assert "disk full" in failed.message


# ───────────────────────── concurrency ─────────────────────────


@pytest.mark.asyncio
async def test_concurrency_semaphore_caps_in_flight_cases(
    fake_task: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With concurrency=2 and 5 cases, max-in-flight should be exactly 2."""
    in_flight = 0
    max_seen = 0
    fan_out_event = asyncio.Event()
    lock = asyncio.Lock()

    async def slow_invoke(**_kwargs: Any) -> Mock:
        nonlocal in_flight, max_seen
        async with lock:
            in_flight += 1
            max_seen = max(max_seen, in_flight)
            if in_flight >= 2:
                fan_out_event.set()
        # Block until fan-out has been observed to actually happen.
        try:
            await asyncio.wait_for(fan_out_event.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            pass
        async with lock:
            in_flight -= 1
        return _fake_run("r")

    _patch_adapter_for_task(monkeypatch, slow_invoke)
    _patch_su_driver(monkeypatch, replies_per_case=["x"])

    await _collect(
        run_cases_batch(
            cases=[_case(i) for i in range(5)],
            target_task=fake_task,
            target_run_config=_target_run_config(),
            su_driver_config=_su_driver_config(),
            turns=1,
            concurrency=2,
        )
    )

    # Exactly 2 — not <=2 — so a regression that serialized everything
    # wouldn't pass vacuously.
    assert max_seen == 2


# ───────────────────────── input_source attribution ─────────────────────


@pytest.mark.asyncio
async def test_root_input_source_carries_decomposed_case_context(
    fake_task: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """First adapter.invoke call gets an input_source with the decomposed
    SU case context (persona/goal/behavior_guidance/seed_prompt) rather
    than the opaque blob. Lets dataset readers inspect attribution
    without re-parsing.
    """
    captured: list[dict[str, Any]] = []

    async def _capture(**kwargs: Any) -> Mock:
        captured.append(kwargs)
        return _fake_run(f"r-{len(captured)}")

    _patch_adapter_for_task(monkeypatch, _capture)
    _patch_su_driver(monkeypatch, replies_per_case=["x"])

    case = _case(0)
    await _collect(
        run_cases_batch(
            cases=[case],
            target_task=fake_task,
            target_run_config=_target_run_config(),
            su_driver_config=_su_driver_config(),
            turns=1,
            batch_tag="rb1",
        )
    )

    root_invoke = captured[0]
    props = root_invoke["input_source"].properties
    assert props["adapter_name"] == "kiln_synthetic_user_runner"
    assert props["model_name"] == "claude_4_5_haiku"
    assert props["model_provider"] == "openrouter"
    assert props["batch_tag"] == "rb1"
    assert props["turn_index"] == 1
    # Decomposed — no opaque blob persisted.
    assert "synthetic_user_info" not in props
    assert props["persona"] == "persona-0"
    assert props["goal"] == "goal-0"
    assert props["behavior_guidance"] == "guidance-0"
    assert props["seed_prompt"] == case.seed_prompt


@pytest.mark.asyncio
async def test_root_input_source_omits_behavior_guidance_when_absent(
    fake_task: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`behavior_guidance` is the only optional SU info field — when the
    blob omits the tag (or has empty content), the property must be
    absent rather than empty-stringed. The DataSource validator rejects
    empty strings, so the filter in `_build_input_source` would otherwise
    save us here, but we want the wire shape predictable either way.
    """
    captured: list[dict[str, Any]] = []

    async def _capture(**kwargs: Any) -> Mock:
        captured.append(kwargs)
        return _fake_run(f"r-{len(captured)}")

    _patch_adapter_for_task(monkeypatch, _capture)
    _patch_su_driver(monkeypatch, replies_per_case=["x"])

    case_no_guidance = SyntheticUserCase(
        seed_prompt="hello",
        synthetic_user_info="<persona>p</persona><goal>g</goal>",
    )
    await _collect(
        run_cases_batch(
            cases=[case_no_guidance],
            target_task=fake_task,
            target_run_config=_target_run_config(),
            su_driver_config=_su_driver_config(),
            turns=1,
        )
    )

    props = captured[0]["input_source"].properties
    assert props["persona"] == "p"
    assert props["goal"] == "g"
    assert "behavior_guidance" not in props


@pytest.mark.asyncio
async def test_non_root_input_source_is_slim(
    fake_task: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Second turn's input_source carries only batch_tag + turn_index;
    the case context lives on the root.
    """
    captured: list[dict[str, Any]] = []

    async def _capture(**kwargs: Any) -> Mock:
        captured.append(kwargs)
        return _fake_run(f"r-{len(captured)}")

    _patch_adapter_for_task(monkeypatch, _capture)
    _patch_su_driver(monkeypatch, replies_per_case=["u2", "u3"])

    await _collect(
        run_cases_batch(
            cases=[_case()],
            target_task=fake_task,
            target_run_config=_target_run_config(),
            su_driver_config=_su_driver_config(),
            turns=2,
            batch_tag="rb2",
        )
    )

    assert len(captured) == 2
    second_props = captured[1]["input_source"].properties
    assert "synthetic_user_info" not in second_props
    assert "seed_prompt" not in second_props
    assert second_props["batch_tag"] == "rb2"
    assert second_props["turn_index"] == 2


# ───────────────────────── consumer cancellation ─────────────────────────


@pytest.mark.asyncio
async def test_consumer_cancellation_cancels_in_flight_case_tasks(
    fake_task: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the consumer breaks off mid-stream, the closer cancels in-flight
    case tasks rather than letting them run to completion writing to a
    dead queue.
    """
    case_started = asyncio.Event()
    case_can_proceed = asyncio.Event()
    saw_cancel = {"cancelled": False}

    async def _slow_invoke(**_kwargs: Any) -> Mock:
        case_started.set()
        try:
            await case_can_proceed.wait()
        except asyncio.CancelledError:
            saw_cancel["cancelled"] = True
            raise
        return _fake_run("r")

    _patch_adapter_for_task(monkeypatch, _slow_invoke)
    _patch_su_driver(monkeypatch, replies_per_case=["x"])

    gen = run_cases_batch(
        cases=[_case()],
        target_task=fake_task,
        target_run_config=_target_run_config(),
        su_driver_config=_su_driver_config(),
        turns=1,
    )

    # Drain BatchStartedEvent, then break.
    started = await gen.__anext__()
    assert isinstance(started, BatchStartedEvent)

    # Wait until the case task is actually running.
    await asyncio.wait_for(case_started.wait(), timeout=1.0)

    # Close the generator — simulates consumer disconnect. This should
    # cancel the in-flight case task via the finally block.
    await gen.aclose()

    # Give the cancellation a beat to propagate.
    await asyncio.sleep(0)

    assert saw_cancel["cancelled"] is True
