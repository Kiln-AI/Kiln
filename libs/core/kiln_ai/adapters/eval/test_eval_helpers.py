"""Tests for KilnEvalHelpers -- pure-Python helper class for user scorers."""

import pytest

from kiln_ai.adapters.eval.eval_helpers import KilnEvalHelpers


@pytest.fixture
def helpers() -> KilnEvalHelpers:
    return KilnEvalHelpers()


# ---------------------------------------------------------------------------
# Trace navigation
# ---------------------------------------------------------------------------

_OPENAI_FORMAT_TRACE = [
    {"role": "user", "content": "Search for cats"},
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_abc123",
                "type": "function",
                "function": {"name": "search", "arguments": '{"q": "cats"}'},
            },
            {
                "id": "call_def456",
                "type": "function",
                "function": {"name": "lookup", "arguments": '{"id": 1}'},
            },
        ],
    },
    {"role": "tool", "tool_call_id": "call_abc123", "content": "result1"},
    {"role": "tool", "tool_call_id": "call_def456", "content": "result2"},
    {"role": "assistant", "content": "Got it, here are the results."},
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
        calls = helpers.get_tool_calls(_OPENAI_FORMAT_TRACE)
        assert len(calls) == 2
        assert calls[0]["name"] == "search"
        assert calls[0]["arguments"] == {"q": "cats"}
        assert calls[0]["id"] == "call_abc123"
        assert calls[1]["name"] == "lookup"
        assert calls[1]["arguments"] == {"id": 1}
        assert calls[1]["id"] == "call_def456"

    def test_get_tool_calls_malformed(self, helpers: KilnEvalHelpers):
        trace = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_bad",
                        "function": {"name": "fn", "arguments": "not json"},
                    },
                    {"id": "call_missing"},
                    "not_a_dict",
                ],
            }
        ]
        calls = helpers.get_tool_calls(trace)
        assert len(calls) == 3
        assert calls[0]["name"] == "fn"
        assert calls[0]["arguments"] == {}
        assert calls[1]["name"] == ""
        assert calls[1]["arguments"] == {}
        assert calls[2]["name"] == ""
        assert calls[2]["id"] is None

    @pytest.mark.parametrize(
        "trace",
        [None, []],
        ids=["none", "empty"],
    )
    def test_get_assistant_messages_empty(self, helpers: KilnEvalHelpers, trace):
        assert helpers.get_assistant_messages(trace) == []

    def test_get_assistant_messages(self, helpers: KilnEvalHelpers):
        msgs = helpers.get_assistant_messages(_OPENAI_FORMAT_TRACE)
        assert len(msgs) == 1
        assert msgs[0] == "Got it, here are the results."

    def test_get_assistant_messages_omits_null_content(self, helpers: KilnEvalHelpers):
        trace = [
            {"role": "assistant", "content": None},
            {"role": "assistant", "content": "visible"},
        ]
        msgs = helpers.get_assistant_messages(trace)
        assert msgs == ["visible"]

    @pytest.mark.parametrize(
        "trace",
        [None, []],
        ids=["none", "empty"],
    )
    def test_get_tool_results_empty(self, helpers: KilnEvalHelpers, trace):
        assert helpers.get_tool_results(trace) == []

    def test_get_tool_results(self, helpers: KilnEvalHelpers):
        trace = [
            {"role": "tool_result", "content": "result1"},
            {"type": "tool_result", "content": "result2"},
            # OpenAI format — the shape Kiln actually stores
            {"role": "tool", "tool_call_id": "tc1", "content": "result3"},
        ]
        results = helpers.get_tool_results(trace)
        assert len(results) == 3
        assert results[0]["content"] == "result1"
        assert results[2]["tool_call_id"] == "tc1"

    def test_get_tool_results_openai_dialect(self, helpers: KilnEvalHelpers):
        """Stored Kiln traces use role "tool" (ChatCompletionToolMessageParamWrapper)."""
        results = helpers.get_tool_results(_OPENAI_FORMAT_TRACE)
        assert len(results) >= 1
        assert all(r.get("role") == "tool" for r in results)

    def test_get_tool_result_content(self, helpers: KilnEvalHelpers):
        trace = [
            {"role": "tool", "tool_call_id": "tc1", "content": "plain text"},
            {
                "role": "tool",
                "tool_call_id": "tc2",
                "content": [
                    {"type": "text", "text": "block a"},
                    {"type": "text", "text": "block b"},
                ],
            },
            {"role": "tool", "tool_call_id": "tc3", "content": None},
        ]
        assert helpers.get_tool_result_content(trace, "tc1") == "plain text"
        assert helpers.get_tool_result_content(trace, "tc2") == "block a\nblock b"
        assert helpers.get_tool_result_content(trace, "tc3") == ""
        assert helpers.get_tool_result_content(trace, "missing") == ""
        assert helpers.get_tool_result_content(None, "tc1") == ""

    def test_get_markdown_links(self, helpers: KilnEvalHelpers):
        text = "See [the task](/optimize/1/2) and [docs](https://docs.kiln.tech)."
        assert helpers.get_markdown_links(text) == [
            ("the task", "/optimize/1/2"),
            ("docs", "https://docs.kiln.tech"),
        ]
        assert helpers.get_markdown_links("") == []
        assert helpers.get_markdown_links(None) == []


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
