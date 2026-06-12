"""Tests for KilnEvalHelpers -- pure-Python helper class for user scorers."""

import pytest

from kiln_ai.adapters.eval.eval_helpers import KilnEvalHelpers


@pytest.fixture
def helpers() -> KilnEvalHelpers:
    return KilnEvalHelpers()


# ---------------------------------------------------------------------------
# Trace navigation
# ---------------------------------------------------------------------------

_SAMPLE_TRACE = [
    {"role": "assistant", "content": "Hello"},
    {"role": "tool_call", "name": "search", "arguments": {"q": "kiln"}},
    {"role": "tool_result", "content": "result1"},
    {"role": "assistant", "content": "Got it"},
    {"type": "tool_call", "name": "lookup", "arguments": {"id": 1}},
    {"type": "tool_result", "content": "result2"},
]


class TestTraceNavigation:
    @pytest.mark.parametrize(
        "trace",
        [None, []],
        ids=["none", "empty"],
    )
    def test_get_tool_calls_empty(self, helpers: KilnEvalHelpers, trace):
        assert helpers.get_tool_calls(trace) == []

    def test_get_tool_calls(self, helpers: KilnEvalHelpers):
        calls = helpers.get_tool_calls(_SAMPLE_TRACE)
        assert len(calls) == 2
        assert calls[0]["name"] == "search"
        assert calls[1]["name"] == "lookup"

    @pytest.mark.parametrize(
        "trace",
        [None, []],
        ids=["none", "empty"],
    )
    def test_get_assistant_messages_empty(self, helpers: KilnEvalHelpers, trace):
        assert helpers.get_assistant_messages(trace) == []

    def test_get_assistant_messages(self, helpers: KilnEvalHelpers):
        msgs = helpers.get_assistant_messages(_SAMPLE_TRACE)
        assert len(msgs) == 2
        assert msgs[0]["content"] == "Hello"

    @pytest.mark.parametrize(
        "trace",
        [None, []],
        ids=["none", "empty"],
    )
    def test_get_tool_results_empty(self, helpers: KilnEvalHelpers, trace):
        assert helpers.get_tool_results(trace) == []

    def test_get_tool_results(self, helpers: KilnEvalHelpers):
        results = helpers.get_tool_results(_SAMPLE_TRACE)
        assert len(results) == 2
        assert results[0]["content"] == "result1"


# ---------------------------------------------------------------------------
# Tool-call matching
# ---------------------------------------------------------------------------


class TestToolCallMatching:
    @pytest.fixture
    def calls(self) -> list[dict]:
        return [
            {"name": "search", "arguments": {"q": "kiln", "limit": 10}},
            {"tool_name": "lookup", "args": {"id": 42}},
        ]

    def test_has_tool_call_by_name(self, helpers: KilnEvalHelpers, calls: list[dict]):
        assert helpers.has_tool_call(calls, "search") is True

    def test_has_tool_call_by_tool_name_key(
        self, helpers: KilnEvalHelpers, calls: list[dict]
    ):
        assert helpers.has_tool_call(calls, "lookup") is True

    def test_has_tool_call_missing(self, helpers: KilnEvalHelpers, calls: list[dict]):
        assert helpers.has_tool_call(calls, "delete") is False

    def test_has_tool_call_with_expected_args_match(
        self, helpers: KilnEvalHelpers, calls: list[dict]
    ):
        assert helpers.has_tool_call(calls, "search", {"q": "kiln"}) is True

    def test_has_tool_call_with_expected_args_mismatch(
        self, helpers: KilnEvalHelpers, calls: list[dict]
    ):
        assert helpers.has_tool_call(calls, "search", {"q": "other"}) is False

    def test_has_tool_call_with_expected_args_partial(
        self, helpers: KilnEvalHelpers, calls: list[dict]
    ):
        assert helpers.has_tool_call(calls, "search", {"limit": 10}) is True

    def test_has_tool_call_with_args_key(
        self, helpers: KilnEvalHelpers, calls: list[dict]
    ):
        assert helpers.has_tool_call(calls, "lookup", {"id": 42}) is True

    def test_count_tool_calls_all(self, helpers: KilnEvalHelpers, calls: list[dict]):
        assert helpers.count_tool_calls(calls) == 2

    def test_count_tool_calls_by_name(
        self, helpers: KilnEvalHelpers, calls: list[dict]
    ):
        assert helpers.count_tool_calls(calls, "search") == 1

    def test_count_tool_calls_missing(
        self, helpers: KilnEvalHelpers, calls: list[dict]
    ):
        assert helpers.count_tool_calls(calls, "delete") == 0

    def test_count_tool_calls_empty(self, helpers: KilnEvalHelpers):
        assert helpers.count_tool_calls([]) == 0


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


class TestScoring:
    def test_pass_fail_true(self, helpers: KilnEvalHelpers):
        assert helpers.pass_fail(True) == 1.0

    def test_pass_fail_false(self, helpers: KilnEvalHelpers):
        assert helpers.pass_fail(False) == 0.0

    def test_five_star_valid(self, helpers: KilnEvalHelpers):
        assert helpers.five_star(3) == 3.0
        assert helpers.five_star(1) == 1.0
        assert helpers.five_star(5) == 5.0

    def test_five_star_float(self, helpers: KilnEvalHelpers):
        assert helpers.five_star(3.5) == 3.5

    def test_five_star_out_of_range_low(self, helpers: KilnEvalHelpers):
        with pytest.raises(ValueError, match="between 1 and 5"):
            helpers.five_star(0)

    def test_five_star_out_of_range_high(self, helpers: KilnEvalHelpers):
        with pytest.raises(ValueError, match="between 1 and 5"):
            helpers.five_star(6)

    def test_five_star_bool_rejected(self, helpers: KilnEvalHelpers):
        with pytest.raises(ValueError, match="must be a number"):
            helpers.five_star(True)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------


class TestAssertions:
    def test_assert_contains_true(self, helpers: KilnEvalHelpers):
        assert helpers.assert_contains("hello world", "world") is True

    def test_assert_contains_false(self, helpers: KilnEvalHelpers):
        assert helpers.assert_contains("hello world", "xyz") is False

    def test_assert_not_contains_true(self, helpers: KilnEvalHelpers):
        assert helpers.assert_not_contains("hello world", "xyz") is True

    def test_assert_not_contains_false(self, helpers: KilnEvalHelpers):
        assert helpers.assert_not_contains("hello world", "hello") is False

    def test_assert_matches_true(self, helpers: KilnEvalHelpers):
        assert helpers.assert_matches("hello 123 world", r"\d+") is True

    def test_assert_matches_false(self, helpers: KilnEvalHelpers):
        assert helpers.assert_matches("hello world", r"\d+") is False

    def test_assert_matches_invalid_regex(self, helpers: KilnEvalHelpers):
        # Invalid regex should not raise, just return False
        assert helpers.assert_matches("hello", r"[invalid") is False

    def test_assert_matches_full_pattern(self, helpers: KilnEvalHelpers):
        assert helpers.assert_matches("abc123def", r"^abc\d+def$") is True
