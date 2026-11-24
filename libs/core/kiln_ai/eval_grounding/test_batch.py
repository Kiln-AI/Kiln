"""ground_cases, with ground_case stubbed so the tests control when and how each case ends."""

import asyncio
import json
from typing import Any
from unittest.mock import patch

import litellm
import pytest

from kiln_ai.adapters.errors import KilnRunError
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.openenv import OpenEnvReset
from kiln_ai.eval_grounding.batch import (
    CaseGrounded,
    GroundingCaseError,
    GroundingFinished,
    ground_cases,
)
from kiln_ai.eval_grounding.conftest import model_reply
from kiln_ai.eval_grounding.models import (
    DropReason,
    EvalContext,
    GroundedReference,
    GroundingCase,
    GroundingOutcome,
)
from kiln_ai.eval_grounding.test_agent import MISBEHAVIOURS, result, start
from kiln_ai.utils.usage import Usage

EVAL_CONTEXT = EvalContext(specification="spec", target_task_prompt="prompt")


def case(index: int) -> GroundingCase:
    return GroundingCase(
        scenario=f"scenario {index}",
        seed_prompt="hi",
        synthetic_user_info="<persona>p</persona><goal>g</goal>",
    )


def grounded(tokens: int) -> GroundingOutcome:
    return GroundingOutcome(
        status="grounded",
        openenv_reset=OpenEnvReset(openenv_server_id="srv", reset_kwargs={}),
        seed_prompt="hi",
        synthetic_user_info="<persona>p</persona><goal>g</goal>",
        reference=GroundedReference(
            starting_point="s",
            facts=[],
            expected_outcome="",
        ),
        usage=Usage(input_tokens=tokens, output_tokens=1, total_tokens=tokens + 1),
    )


def dropped() -> GroundingOutcome:
    return GroundingOutcome.dropped(
        DropReason.no_fit, "Nothing fits.", call_log=[], usage=None
    )


@pytest.fixture
def batch(openenv_server, session_manager):
    def run(cases: list[GroundingCase], retry_delay_s: float = 0, **overrides: Any):
        return ground_cases(
            cases,
            eval_context=EVAL_CONTEXT,
            openenv_server=openenv_server,
            session_manager=session_manager,
            model_name="gpt-4",
            model_provider=ModelProviderName.openai,
            target_tools=[],
            retry_delay_s=retry_delay_s,
            **overrides,
        )

    return run


async def test_yields_each_case_then_the_totals(batch, session_manager):
    outcomes = {
        "scenario 0": grounded(10),
        "scenario 1": dropped(),
        "scenario 2": grounded(5),
    }
    seen_kwargs: list[dict[str, Any]] = []

    async def fake_ground_case(grounding_case: GroundingCase, **kwargs: Any):
        seen_kwargs.append(kwargs)
        return outcomes[grounding_case.scenario]

    with (
        patch("kiln_ai.eval_grounding.batch.ground_case", side_effect=fake_ground_case),
        patch.object(
            session_manager, "list_tools", wraps=session_manager.list_tools
        ) as list_tools,
    ):
        events = [event async for event in batch([case(0), case(1), case(2)])]

    finished = events[-1]
    assert isinstance(finished, GroundingFinished)
    assert (finished.grounded, finished.dropped) == (2, 1)
    assert finished.usage is not None and finished.usage.input_tokens == 15
    assert finished.usage_complete
    progress = events[:-1]
    assert all(isinstance(event, CaseGrounded) for event in progress)
    assert {event.case_index: event.outcome for event in progress} == {  # type: ignore[union-attr]
        0: outcomes["scenario 0"],
        1: outcomes["scenario 1"],
        2: outcomes["scenario 2"],
    }
    assert list_tools.call_count == 1
    assert [t.name for t in seen_kwargs[0]["server_tools"]] == [
        "append_note",
        "read_notes",
        "explode",
        "sleep",
    ]
    assert all(
        kw["server_tools"] is seen_kwargs[0]["server_tools"] for kw in seen_kwargs
    )
    assert seen_kwargs[0]["answer_style"] == "structured_output"
    assert seen_kwargs[0]["model_name"] == "gpt-4"


async def test_runs_at_most_concurrency_cases_at_once(batch):
    running = 0
    most = 0

    async def fake_ground_case(grounding_case: GroundingCase, **kwargs: Any):
        nonlocal running, most
        running += 1
        most = max(most, running)
        await asyncio.sleep(0.02)
        running -= 1
        return dropped()

    with patch(
        "kiln_ai.eval_grounding.batch.ground_case", side_effect=fake_ground_case
    ):
        events = [e async for e in batch([case(i) for i in range(6)], concurrency=2)]

    assert most == 2
    assert len(events) == 7


async def test_an_error_waits_for_the_rest_to_release_then_is_raised(batch):
    released: list[int] = []

    async def fake_ground_case(grounding_case: GroundingCase, **kwargs: Any):
        index = int(grounding_case.scenario.split()[-1])
        if index == 0:
            await asyncio.sleep(0.02)
            raise RuntimeError("the environment went away")
        try:
            await asyncio.sleep(10)
        finally:
            # Releasing an episode takes a round trip, longer for some cases.
            await asyncio.sleep(0.05 * index)
            released.append(index)
        return dropped()

    with patch(
        "kiln_ai.eval_grounding.batch.ground_case", side_effect=fake_ground_case
    ):
        with pytest.raises(GroundingCaseError) as raised:
            async for _ in batch([case(i) for i in range(4)], concurrency=4):
                pass
        assert sorted(released) == [1, 2, 3]

    assert raised.value.case_index == 0
    assert isinstance(raised.value.error, RuntimeError)
    assert raised.value.__cause__ is raised.value.error
    assert str(raised.value) == "Case 0: the environment went away"


async def test_an_error_releases_real_episodes(
    batch, scripted_model, server_is_free, session_manager
):
    """Two cases on the one-session server: the first starts an episode, then the
    second fails, which cancels the first while it holds the episode. The episode is
    free once the error is raised."""
    stalled = asyncio.Event()

    async def stall():
        stalled.set()
        await asyncio.sleep(10)
        raise AssertionError("not reached")

    async def fail():
        await stalled.wait()
        raise RuntimeError("provider down")

    scripted_model.script(
        model_reply(None, ("start_episode", {"reset_kwargs": {}})), fail, stall
    )
    with pytest.raises(GroundingCaseError):
        async for _ in batch([case(0), case(1)], concurrency=2):
            pass
    await server_is_free()


async def test_incomplete_usage_is_reported(batch):
    incomplete = dropped().model_copy(update={"usage_complete": False})

    async def fake_ground_case(grounding_case: GroundingCase, **kwargs: Any):
        return incomplete if grounding_case.scenario == "scenario 1" else dropped()

    with patch(
        "kiln_ai.eval_grounding.batch.ground_case", side_effect=fake_ground_case
    ):
        events = [e async for e in batch([case(0), case(1)])]
    assert isinstance(events[-1], GroundingFinished)
    assert not events[-1].usage_complete


async def test_closing_early_cancels_the_rest(batch):
    cancelled: list[int] = []

    async def fake_ground_case(grounding_case: GroundingCase, **kwargs: Any):
        index = int(grounding_case.scenario.split()[-1])
        if index == 0:
            return dropped()
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.append(index)
        return dropped()

    with patch(
        "kiln_ai.eval_grounding.batch.ground_case", side_effect=fake_ground_case
    ):
        events = batch([case(i) for i in range(3)], concurrency=3)
        first = await anext(events)
        await events.aclose()

    assert isinstance(first, CaseGrounded) and first.case_index == 0
    assert sorted(cancelled) == [1, 2]


async def test_concurrency_must_be_positive(batch):
    with pytest.raises(ValueError, match="at least 1"):
        await anext(batch([case(0)], concurrency=0))


def provider_error(error: Exception) -> KilnRunError:
    """`error` as Kiln's adapter raises it."""
    return KilnRunError("failed", partial_trace=None, original=error)


def timeout() -> KilnRunError:
    return provider_error(litellm.Timeout("timed out", "gpt-4", "openai"))


class TestRetries:
    async def test_a_transient_error_retries_the_case(self, batch):
        attempts: dict[str, int] = {}

        async def fake_ground_case(grounding_case: GroundingCase, **kwargs: Any):
            attempts[grounding_case.scenario] = (
                attempts.get(grounding_case.scenario, 0) + 1
            )
            if grounding_case.scenario == "scenario 0" and attempts["scenario 0"] < 3:
                raise timeout()
            return grounded(10)

        with patch(
            "kiln_ai.eval_grounding.batch.ground_case", side_effect=fake_ground_case
        ):
            events = [e async for e in batch([case(0), case(1)])]

        assert attempts == {"scenario 0": 3, "scenario 1": 1}
        finished = events[-1]
        assert isinstance(finished, GroundingFinished)
        assert (finished.grounded, finished.dropped) == (2, 0)
        assert not finished.usage_complete
        outcomes = {
            e.case_index: e.outcome for e in events if isinstance(e, CaseGrounded)
        }
        assert not outcomes[0].usage_complete
        assert outcomes[1].usage_complete

    async def test_a_transient_error_that_persists_fails_the_batch(self, batch):
        attempts = 0

        async def fake_ground_case(grounding_case: GroundingCase, **kwargs: Any):
            nonlocal attempts
            attempts += 1
            raise timeout()

        with patch(
            "kiln_ai.eval_grounding.batch.ground_case", side_effect=fake_ground_case
        ):
            with pytest.raises(GroundingCaseError) as raised:
                async for _ in batch([case(0)], max_retries=2):
                    pass

        assert attempts == 3
        assert raised.value.case_index == 0
        assert isinstance(raised.value.error, KilnRunError)
        assert isinstance(raised.value.error.original, litellm.Timeout)

    @pytest.mark.parametrize(
        "error",
        [
            provider_error(litellm.AuthenticationError("bad key", "openai", "gpt-4")),
            RuntimeError("the environment went away"),
        ],
    )
    async def test_other_errors_fail_the_batch_at_once(self, batch, error):
        attempts = 0

        async def fake_ground_case(grounding_case: GroundingCase, **kwargs: Any):
            nonlocal attempts
            attempts += 1
            raise error

        with patch(
            "kiln_ai.eval_grounding.batch.ground_case", side_effect=fake_ground_case
        ):
            with pytest.raises(GroundingCaseError) as raised:
                async for _ in batch([case(0)]):
                    pass

        assert attempts == 1
        assert raised.value.error is error

    async def test_a_retry_starts_over_in_a_fresh_episode(
        self, batch, scripted_model, server_is_free
    ):
        """On the one-session server, the retry's reset only succeeds once the failed
        attempt has released its episode."""

        async def fail():
            raise litellm.Timeout("timed out", "gpt-4", "openai")

        scripted_model.script(
            model_reply(None, start("a")),
            fail,
            model_reply(None, start("b")),
            model_reply(json.dumps(result(), ensure_ascii=False)),
        )
        events = [e async for e in batch([case(0)])]

        grounded_case = events[0]
        assert isinstance(grounded_case, CaseGrounded)
        assert grounded_case.outcome.status == "grounded"
        assert grounded_case.outcome.openenv_reset is not None
        assert grounded_case.outcome.openenv_reset.reset_kwargs == {"fixture_id": "b"}
        assert [c.tool for c in grounded_case.outcome.call_log] == ["start_episode"]
        assert not grounded_case.outcome.usage_complete
        await server_is_free()


@pytest.mark.parametrize("misbehaviour", list(MISBEHAVIOURS))
async def test_a_misbehaving_model_drops_only_its_case(
    batch, scripted_model, server_is_free, few_tool_rounds, misbehaviour
):
    reason, _detail, replies = MISBEHAVIOURS[misbehaviour]
    scripted_model.script(
        model_reply(None, start()),
        *replies,
        model_reply(None, start()),
        model_reply(json.dumps(result(), ensure_ascii=False)),
    )
    events = [e async for e in batch([case(0), case(1)], concurrency=1)]

    outcomes = {e.case_index: e.outcome for e in events if isinstance(e, CaseGrounded)}
    assert outcomes[0].drop_reason == reason
    assert outcomes[1].status == "grounded"
    finished = events[-1]
    assert isinstance(finished, GroundingFinished)
    assert (finished.grounded, finished.dropped) == (1, 1)
    await server_is_free()
