import copy
import json

import pytest
from litellm.types.utils import ChatCompletionMessageToolCall, Function
from litellm.types.utils import Message as LiteLLMMessage

from kiln_ai.adapters.errors import STUCK_LOOP_ERROR_PREFIX
from kiln_ai.adapters.model_adapters.tool_loop_guards import (
    STUCK_NUDGE_THRESHOLD,
    STUCK_STOP_THRESHOLD,
    IncrementalMessageCopier,
    RepeatedToolCallDetector,
)
from kiln_ai.utils.open_ai_types import (
    KILN_ONLY_MESSAGE_FIELDS,
    sanitize_messages_for_provider,
)


def _tool_call(call_id="call_1", name="add", arguments=None):
    return ChatCompletionMessageToolCall(
        id=call_id,
        type="function",
        function=Function(name=name, arguments=json.dumps(arguments or {"a": 1})),
    )


def _tool_message(call_id="call_1", content="ok", is_error=None):
    message = {"role": "tool", "tool_call_id": call_id, "content": content}
    if is_error is not None:
        message["is_error"] = is_error
    return message


class TestRepeatedToolCallDetector:
    def test_first_round_never_nudges(self):
        detector = RepeatedToolCallDetector()
        assert detector.record_round([_tool_call()], [_tool_message()]) is None

    def test_nudge_at_exactly_the_nudge_threshold(self):
        detector = RepeatedToolCallDetector()
        nudges = [
            detector.record_round([_tool_call()], [_tool_message()]) for _ in range(4)
        ]
        assert nudges[0] is None
        assert nudges[1] is None
        assert nudges[2] is not None
        # Only one nudge per streak.
        assert nudges[3] is None
        assert nudges[2]["role"] == "user"
        content = nudges[2]["content"]
        assert "add" in content
        assert str(STUCK_NUDGE_THRESHOLD) in content
        assert "Change your approach or provide your final answer." in content

    def test_streak_resets_on_changed_arguments(self):
        detector = RepeatedToolCallDetector()
        for i in range(10):
            args = {"a": i}
            assert (
                detector.record_round([_tool_call(arguments=args)], [_tool_message()])
                is None
            )

    def test_streak_resets_on_changed_result(self):
        detector = RepeatedToolCallDetector()
        for i in range(10):
            assert (
                detector.record_round(
                    [_tool_call()], [_tool_message(content=f"result-{i}")]
                )
                is None
            )

    def test_streak_resets_partway_through(self):
        detector = RepeatedToolCallDetector()
        detector.record_round([_tool_call()], [_tool_message()])
        detector.record_round([_tool_call()], [_tool_message()])
        # Different args break the streak, so the count starts over.
        assert (
            detector.record_round([_tool_call(arguments={"a": 99})], [_tool_message()])
            is None
        )
        assert detector.record_round([_tool_call()], [_tool_message()]) is None
        assert detector.record_round([_tool_call()], [_tool_message()]) is None
        assert detector.record_round([_tool_call()], [_tool_message()]) is not None

    def test_argument_key_order_does_not_break_the_streak(self):
        detector = RepeatedToolCallDetector()
        ordered = ChatCompletionMessageToolCall(
            id="call_1",
            type="function",
            function=Function(name="add", arguments='{"a": 1, "b": 2}'),
        )
        reordered = ChatCompletionMessageToolCall(
            id="call_1",
            type="function",
            function=Function(name="add", arguments='{"b": 2, "a": 1}'),
        )
        assert detector.record_round([ordered], [_tool_message()]) is None
        assert detector.record_round([reordered], [_tool_message()]) is None
        assert detector.record_round([ordered], [_tool_message()]) is not None

    def test_unparseable_arguments_compare_by_raw_string(self):
        detector = RepeatedToolCallDetector()
        bad = ChatCompletionMessageToolCall(
            id="call_1",
            type="function",
            function=Function(name="add", arguments="not json"),
        )
        assert detector.record_round([bad], [_tool_message()]) is None
        assert detector.record_round([bad], [_tool_message()]) is None
        assert detector.record_round([bad], [_tool_message()]) is not None

    def test_varying_error_text_is_still_the_same_stall(self):
        """A failing call whose error text changes every time still counts as repeated."""
        detector = RepeatedToolCallDetector()
        nudges = [
            detector.record_round(
                [_tool_call()],
                [
                    _tool_message(
                        content=f"request {i} failed at 12:0{i}", is_error=True
                    )
                ],
            )
            for i in range(STUCK_NUDGE_THRESHOLD)
        ]
        assert nudges[:-1] == [None] * (STUCK_NUDGE_THRESHOLD - 1)
        assert nudges[-1] is not None

    def test_varying_error_text_stops_at_the_stop_threshold(self):
        detector = RepeatedToolCallDetector()
        with pytest.raises(RuntimeError) as exc_info:
            for i in range(STUCK_STOP_THRESHOLD + 5):
                detector.record_round(
                    [_tool_call()],
                    [_tool_message(content=f"error id {i}", is_error=True)],
                )
        assert str(exc_info.value).startswith(STUCK_LOOP_ERROR_PREFIX)
        assert f"{STUCK_STOP_THRESHOLD} times in a row" in str(exc_info.value)

    def test_success_after_errors_resets_the_streak(self):
        """A call that starts working is progress, even with the same arguments."""
        detector = RepeatedToolCallDetector()
        for _ in range(STUCK_STOP_THRESHOLD - 1):
            detector.record_round([_tool_call()], [_tool_message(is_error=True)])
        # The success has a different fingerprint than the errors, so the count restarts
        # and the run is never stopped.
        assert detector.record_round([_tool_call()], [_tool_message()]) is None
        assert detector.record_round([_tool_call()], [_tool_message()]) is None
        assert detector.record_round([_tool_call()], [_tool_message()]) is not None

    def test_identical_successful_results_never_stop(self):
        detector = RepeatedToolCallDetector()
        nudge_count = 0
        for _ in range(STUCK_STOP_THRESHOLD * 10):
            if detector.record_round([_tool_call()], [_tool_message()]):
                nudge_count += 1
        assert nudge_count == 1

    def test_identical_error_results_stop_at_the_stop_threshold(self):
        detector = RepeatedToolCallDetector()
        nudges = []
        with pytest.raises(RuntimeError) as exc_info:
            for _ in range(STUCK_STOP_THRESHOLD + 5):
                nudges.append(
                    detector.record_round(
                        [_tool_call()], [_tool_message(is_error=True)]
                    )
                )
        assert str(exc_info.value).startswith(STUCK_LOOP_ERROR_PREFIX)
        # Stopped on the fifth identical round, after exactly one nudge on the third.
        assert len(nudges) == STUCK_STOP_THRESHOLD - 1
        assert len([n for n in nudges if n]) == 1

    def test_mixed_error_and_success_round_never_stops(self):
        detector = RepeatedToolCallDetector()
        rounds = STUCK_STOP_THRESHOLD * 3
        nudges = []
        for _ in range(rounds):
            nudges.append(
                detector.record_round(
                    [_tool_call("call_1"), _tool_call("call_2", name="divide")],
                    [
                        _tool_message("call_1", is_error=True),
                        _tool_message("call_2", content="fine"),
                    ],
                )
            )
        # Every round was recorded (no raise), and the streak was nudged exactly once.
        assert len(nudges) == rounds
        assert len([n for n in nudges if n]) == 1

    def test_task_response_is_excluded(self):
        detector = RepeatedToolCallDetector()
        # A result keyed to the task_response call, so the exclusion is the name check
        # and not the "no matching result" skip.
        for _ in range(STUCK_STOP_THRESHOLD * 3):
            assert (
                detector.record_round(
                    [_tool_call(name="task_response")],
                    [_tool_message(content='{"answer": 42}')],
                )
                is None
            )

    def test_task_response_alongside_a_real_call_is_ignored(self):
        detector = RepeatedToolCallDetector()
        calls = [_tool_call("call_1"), _tool_call("call_2", name="task_response")]
        # Both calls have results; only the real one may shape the fingerprint.
        messages = [
            _tool_message("call_1"),
            _tool_message("call_2", content='{"answer": 42}'),
        ]
        nudge = None
        for _ in range(STUCK_NUDGE_THRESHOLD):
            nudge = detector.record_round(calls, messages)
        assert nudge is not None
        assert "task_response" not in nudge["content"]
        assert nudge["content"].startswith("You have called add ")

    def test_nudge_is_marked_as_injected_by_kiln(self):
        """The marker lets the trace tell a Kiln nudge apart from real user input."""
        detector = RepeatedToolCallDetector()
        nudge = None
        for _ in range(STUCK_NUDGE_THRESHOLD):
            nudge = detector.record_round([_tool_call()], [_tool_message()])
        assert nudge is not None
        assert nudge["kiln_injected"] is True
        assert "kiln_injected" in KILN_ONLY_MESSAGE_FIELDS
        # Stripped before the provider call, kept on the message we hold.
        assert sanitize_messages_for_provider([nudge]) == [
            {"role": "user", "content": nudge["content"]}
        ]

    def test_parallel_calls_in_any_order_are_the_same_round(self):
        detector = RepeatedToolCallDetector()
        calls_a = [_tool_call("call_1", "add"), _tool_call("call_2", "divide")]
        calls_b = [_tool_call("call_2", "divide"), _tool_call("call_1", "add")]
        messages = [_tool_message("call_1"), _tool_message("call_2")]
        assert detector.record_round(calls_a, messages) is None
        assert detector.record_round(calls_b, messages) is None
        assert detector.record_round(calls_a, messages) is not None

    def test_call_without_a_matching_result_is_skipped(self):
        detector = RepeatedToolCallDetector()
        for _ in range(STUCK_STOP_THRESHOLD * 3):
            assert detector.record_round([_tool_call()], []) is None

    def test_distinct_calls_in_volume_never_trigger(self):
        detector = RepeatedToolCallDetector()
        for i in range(50):
            assert (
                detector.record_round(
                    [_tool_call(f"call_{i}", arguments={"a": i})],
                    [_tool_message(f"call_{i}", content=f"result-{i}")],
                )
                is None
            )


class TestIncrementalMessageCopier:
    def test_snapshot_matches_a_full_deepcopy(self):
        copier = IncrementalMessageCopier()
        messages = [{"role": "user", "content": "hi"}]
        for i in range(5):
            messages.append(LiteLLMMessage(role="assistant", content=f"assistant-{i}"))
            messages.append({"role": "tool", "tool_call_id": f"c{i}", "content": "ok"})
            snapshot = copier.snapshot(messages)
            assert snapshot == copy.deepcopy(messages)

    def test_snapshot_never_returns_the_original_objects(self):
        copier = IncrementalMessageCopier()
        messages = [{"role": "user", "content": "hi"}]
        snapshot = copier.snapshot(messages)
        assert snapshot is not messages
        assert all(a is not b for a, b in zip(snapshot, messages))

    def test_existing_copies_are_reused(self):
        copier = IncrementalMessageCopier()
        messages = [{"role": "user", "content": "hi"}]
        first = list(copier.snapshot(messages))
        messages.append({"role": "user", "content": "again"})
        second = copier.snapshot(messages)
        assert second[0] is first[0]
        assert len(second) == 2

    def test_mutating_a_copy_does_not_affect_the_canonical_history(self):
        copier = IncrementalMessageCopier()
        messages = [{"role": "user", "content": "hi"}]
        snapshot = copier.snapshot(messages)
        snapshot[0]["content"] = "tampered"
        assert messages[0]["content"] == "hi"

    def test_mutating_a_snapshot_does_not_leak_into_the_next_round(self):
        """Anything litellm could mutate is re-copied, so each round starts pristine."""
        copier = IncrementalMessageCopier()
        assistant = LiteLLMMessage(role="assistant", content="original")
        messages: list = [
            {"role": "user", "content": "hi", "tool_calls": [{"id": "c1"}]},
            assistant,
        ]

        first = copier.snapshot(messages)
        first[0]["tool_calls"].append({"id": "injected"})
        first[1].content = "mutated"

        second = copier.snapshot(messages)
        assert second[0]["tool_calls"] == [{"id": "c1"}]
        assert second[1].content == "original"
        # The caller's own objects were never touched either.
        assert messages[0]["tool_calls"] == [{"id": "c1"}]
        assert assistant.content == "original"

    def test_flat_dict_messages_are_reused_between_rounds(self):
        """Flat dicts are shared, which is what keeps the common case O(new).

        Safe because they hold no nested state, and sanitize rebuilds every dict, so
        the provider never receives one of the copier's objects.
        """
        copier = IncrementalMessageCopier()
        messages = [{"role": "tool", "tool_call_id": "c1", "content": "a big result"}]

        first = copier.snapshot(messages)
        second = copier.snapshot(messages)

        assert second[0] is first[0]
        assert sanitize_messages_for_provider(second)[0] is not second[0]

    def test_rewritten_history_is_copied_from_scratch(self):
        copier = IncrementalMessageCopier()
        messages = [{"role": "user", "content": "hi"}]
        copier.snapshot(messages)
        # Replace the message objects rather than appending to them.
        messages[:] = [{"role": "user", "content": "replaced"}]
        snapshot = copier.snapshot(messages)
        assert snapshot == [{"role": "user", "content": "replaced"}]

    def test_shortened_history_is_copied_from_scratch(self):
        copier = IncrementalMessageCopier()
        messages = [{"role": "user", "content": "a"}, {"role": "user", "content": "b"}]
        copier.snapshot(messages)
        messages.pop()
        assert copier.snapshot(messages) == [{"role": "user", "content": "a"}]
