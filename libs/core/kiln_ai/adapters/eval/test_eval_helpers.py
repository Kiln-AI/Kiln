"""Tests for KilnEvalHelpers -- pure-Python helper class for user scorers."""

from typing import Any, ClassVar

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

    def test_get_tool_results_openai_format(self, helpers: KilnEvalHelpers):
        """The shape Kiln actually stores: role "tool" messages."""
        results = helpers.get_tool_results(_OPENAI_FORMAT_TRACE)
        assert len(results) == 2
        assert results[0]["tool_call_id"] == "call_abc123"
        assert results[0]["content"] == "result1"
        assert results[1]["tool_call_id"] == "call_def456"

    def test_get_tool_results_legacy_shapes(self, helpers: KilnEvalHelpers):
        trace = [
            {"role": "tool_result", "content": "result1"},
            {"type": "tool_result", "content": "result2"},
            {"role": "assistant", "content": "not a result"},
        ]
        results = helpers.get_tool_results(trace)
        assert len(results) == 2
        assert results[0]["content"] == "result1"

    def test_get_tool_results_round_trip_from_task_run(self, helpers: KilnEvalHelpers):
        """End-to-end over the real data path: a TaskRun trace converted via
        EvalTaskInput (exactly what the eval runner hands scorers) must yield
        its tool results."""
        from kiln_ai.datamodel.eval import EvalTaskInput
        from kiln_ai.datamodel.task_output import (
            DataSource,
            DataSourceType,
            TaskOutput,
        )
        from kiln_ai.datamodel.task_run import TaskRun

        source = DataSource(
            type=DataSourceType.synthetic,
            properties={
                "model_name": "m",
                "model_provider": "p",
                "adapter_name": "a",
            },
        )
        task_run = TaskRun(
            input="Search for cats",
            input_source=source,
            output=TaskOutput(output="done", source=source),
            trace=_OPENAI_FORMAT_TRACE,
        )
        eti = EvalTaskInput.from_task_run(task_run)
        results = helpers.get_tool_results(eti.trace)
        assert [r["tool_call_id"] for r in results] == [
            "call_abc123",
            "call_def456",
        ]


class TestCountMessages:
    @pytest.mark.parametrize("trace", [None, []], ids=["none", "empty"])
    def test_empty(self, helpers: KilnEvalHelpers, trace):
        assert helpers.count_messages(trace, "assistant") == 0

    def test_counts_by_role(self, helpers: KilnEvalHelpers):
        assert helpers.count_messages(_OPENAI_FORMAT_TRACE, "user") == 1
        assert helpers.count_messages(_OPENAI_FORMAT_TRACE, "assistant") == 2
        assert helpers.count_messages(_OPENAI_FORMAT_TRACE, "tool") == 2
        assert helpers.count_messages(_OPENAI_FORMAT_TRACE, "system") == 0

    def test_messages_not_tool_calls(self, helpers: KilnEvalHelpers):
        """One assistant message carries two tool calls: message count stays
        1; tool-call counting is get_tool_calls' job."""
        trace = _OPENAI_FORMAT_TRACE[:2]
        assert helpers.count_messages(trace, "assistant") == 1
        assert len(helpers.get_tool_calls(trace)) == 2


class TestGetToolResultContent:
    def test_string_content(self, helpers: KilnEvalHelpers):
        assert (
            helpers.get_tool_result_content(_OPENAI_FORMAT_TRACE, "call_abc123")
            == "result1"
        )
        assert (
            helpers.get_tool_result_content(_OPENAI_FORMAT_TRACE, "call_def456")
            == "result2"
        )

    def test_no_match_returns_empty(self, helpers: KilnEvalHelpers):
        assert helpers.get_tool_result_content(_OPENAI_FORMAT_TRACE, "call_nope") == ""
        assert helpers.get_tool_result_content(None, "call_abc123") == ""
        assert helpers.get_tool_result_content([], "call_abc123") == ""

    def test_falsy_id_returns_empty(self, helpers: KilnEvalHelpers):
        """A None id (get_tool_calls emits it for malformed calls) must not
        pair with legacy entries lacking the key (None == None)."""
        trace = [{"role": "tool_result", "content": "legacy, no id"}]
        assert helpers.get_tool_result_content(trace, None) == ""
        assert helpers.get_tool_result_content(trace, "") == ""

    def test_block_list_content(self, helpers: KilnEvalHelpers):
        trace = [
            {
                "role": "tool",
                "tool_call_id": "c1",
                "content": [
                    {"type": "text", "text": "line one"},
                    {"type": "text", "text": "line two"},
                ],
            }
        ]
        assert helpers.get_tool_result_content(trace, "c1") == "line one\nline two"

    def test_malformed_blocks_never_raise(self, helpers: KilnEvalHelpers):
        trace = [
            {
                "role": "tool",
                "tool_call_id": "c1",
                "content": [
                    {"type": "text", "text": None},
                    {"type": "text"},
                    "bare string",
                    42,
                ],
            }
        ]
        assert helpers.get_tool_result_content(trace, "c1") == "\n\nbare string\n42"

    def test_duplicate_ids_first_wins(self, helpers: KilnEvalHelpers):
        trace = [
            {"role": "tool", "tool_call_id": "c1", "content": "first"},
            {"role": "tool", "tool_call_id": "c1", "content": "second"},
        ]
        assert helpers.get_tool_result_content(trace, "c1") == "first"

    def test_non_string_content_coerced(self, helpers: KilnEvalHelpers):
        trace = [
            {"role": "tool", "tool_call_id": "c1", "content": 3.14},
            {"role": "tool", "tool_call_id": "c2", "content": None},
        ]
        assert helpers.get_tool_result_content(trace, "c1") == "3.14"
        assert helpers.get_tool_result_content(trace, "c2") == ""


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


class TestGetAssistantEmittedText:
    _TRACE: ClassVar[list[dict[str, Any]]] = [
        {"role": "user", "content": "translate to japanese"},
        {
            "role": "assistant",
            "content": None,
            "reasoning_content": "thinking about kanji",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "dictionary_lookup",
                        "arguments": '{"word": "\\u7aaf"}',
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "TOOL_PAYLOAD"},
        {"role": "assistant", "content": "窯 (kama) means kiln."},
    ]

    @pytest.mark.parametrize("trace", [None, []], ids=["none", "empty"])
    def test_empty(self, helpers: KilnEvalHelpers, trace):
        assert helpers.get_assistant_emitted_text(trace) == ""

    def test_default_surface(self, helpers: KilnEvalHelpers):
        text = helpers.get_assistant_emitted_text(self._TRACE)
        assert "窯 (kama) means kiln." in text
        assert "thinking about kanji" in text
        # never tool results, tool names, or (by default) arguments
        assert "TOOL_PAYLOAD" not in text
        assert "dictionary_lookup" not in text
        assert "u7aaf" not in text

    def test_exclude_reasoning(self, helpers: KilnEvalHelpers):
        text = helpers.get_assistant_emitted_text(self._TRACE, include_reasoning=False)
        assert "thinking about kanji" not in text
        assert "窯 (kama) means kiln." in text

    def test_include_tool_call_arguments_not_names(self, helpers: KilnEvalHelpers):
        text = helpers.get_assistant_emitted_text(self._TRACE, include_tool_calls=True)
        assert '{"word": "\\u7aaf"}' in text
        assert "dictionary_lookup" not in text

    def test_refusal_and_blocks(self, helpers: KilnEvalHelpers):
        trace = [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "block text"},
                    {"type": "text", "text": None},
                    "bare block",
                ],
                "refusal": "I can't help with that.",
            }
        ]
        text = helpers.get_assistant_emitted_text(trace)
        assert "block text" in text
        assert "bare block" in text
        assert "I can't help with that." in text


# ---------------------------------------------------------------------------
# Health / usage metrics
# ---------------------------------------------------------------------------


class _UsageObject:
    """Stands in for MessageUsage: attribute-bearing, not a dict."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class TestGetUsageTotals:
    @pytest.mark.parametrize("trace", [None, []], ids=["none", "empty"])
    def test_empty(self, helpers: KilnEvalHelpers, trace):
        totals = helpers.get_usage_totals(trace)
        assert totals["total_tokens"] == 0.0
        assert totals["cost"] == 0.0

    def test_sums_dict_usage(self, helpers: KilnEvalHelpers):
        trace = [
            {
                "role": "assistant",
                "content": "a",
                "usage": {"input_tokens": 10, "output_tokens": 5, "cost": 0.01},
            },
            {
                "role": "assistant",
                "content": "b",
                "usage": {"input_tokens": 20, "output_tokens": 15, "cost": 0.02},
            },
            {"role": "user", "content": "ignored", "usage": {"input_tokens": 999}},
        ]
        totals = helpers.get_usage_totals(trace)
        assert totals["input_tokens"] == 30.0
        assert totals["output_tokens"] == 20.0
        assert totals["cost"] == pytest.approx(0.03)

    def test_sums_object_usage(self, helpers: KilnEvalHelpers):
        """Pickle-transport traces carry usage as objects, not dicts."""
        trace = [
            {
                "role": "assistant",
                "content": "a",
                "usage": _UsageObject(input_tokens=7, total_tokens=12, cost=0.5),
            }
        ]
        totals = helpers.get_usage_totals(trace)
        assert totals["input_tokens"] == 7.0
        assert totals["total_tokens"] == 12.0
        assert totals["cost"] == 0.5

    def test_absent_usage_sums_to_zero(self, helpers: KilnEvalHelpers):
        """Documented caveat: no usage data is indistinguishable from zero."""
        trace = [{"role": "assistant", "content": "a"}]
        assert helpers.get_usage_totals(trace)["total_tokens"] == 0.0

    def test_non_numeric_and_bool_values_ignored(self, helpers: KilnEvalHelpers):
        trace = [
            {
                "role": "assistant",
                "content": "a",
                "usage": {"input_tokens": "lots", "output_tokens": True, "cost": 1.0},
            }
        ]
        totals = helpers.get_usage_totals(trace)
        assert totals["input_tokens"] == 0.0
        assert totals["output_tokens"] == 0.0
        assert totals["cost"] == 1.0


class TestGetTotalLatencyMs:
    @pytest.mark.parametrize("trace", [None, []], ids=["none", "empty"])
    def test_empty(self, helpers: KilnEvalHelpers, trace):
        assert helpers.get_total_latency_ms(trace) == 0.0

    def test_sums_assistant_latency(self, helpers: KilnEvalHelpers):
        trace = [
            {"role": "assistant", "content": "a", "latency_ms": 120},
            {"role": "assistant", "content": "b", "latency_ms": 80.5},
            {"role": "assistant", "content": "c"},
            {"role": "tool", "tool_call_id": "x", "content": "r", "latency_ms": 999},
        ]
        assert helpers.get_total_latency_ms(trace) == pytest.approx(200.5)


class TestGetErrorToolResults:
    @pytest.mark.parametrize("trace", [None, []], ids=["none", "empty"])
    def test_empty(self, helpers: KilnEvalHelpers, trace):
        assert helpers.get_error_tool_results(trace) == []

    def test_flagged_errors_only(self, helpers: KilnEvalHelpers):
        trace = [
            {"role": "tool", "tool_call_id": "c1", "content": "ok"},
            {"role": "tool", "tool_call_id": "c2", "content": "", "is_error": True},
            {
                "role": "tool",
                "tool_call_id": "c3",
                "content": "boom",
                "error_message": "timeout",
            },
            {
                "role": "tool",
                "tool_call_id": "c4",
                "content": "fine",
                "is_error": False,
            },
        ]
        errors = helpers.get_error_tool_results(trace)
        assert [e["tool_call_id"] for e in errors] == ["c2", "c3"]


# ---------------------------------------------------------------------------
# Markdown helpers
# ---------------------------------------------------------------------------


class TestGetMarkdownLinks:
    @pytest.mark.parametrize("text", [None, ""], ids=["none", "empty"])
    def test_empty_input(self, helpers: KilnEvalHelpers, text):
        assert helpers.get_markdown_links(text) == []

    def test_simple_links(self, helpers: KilnEvalHelpers):
        text = "See [docs](https://docs.kiln.ai) and [home](https://kiln.ai)."
        assert helpers.get_markdown_links(text) == [
            ("docs", "https://docs.kiln.ai"),
            ("home", "https://kiln.ai"),
        ]

    def test_balanced_parens_in_target(self, helpers: KilnEvalHelpers):
        """Wikipedia-style URLs must not truncate at the inner paren."""
        text = "[kiln](https://en.wikipedia.org/wiki/Kiln_(disambiguation))"
        assert helpers.get_markdown_links(text) == [
            ("kiln", "https://en.wikipedia.org/wiki/Kiln_(disambiguation)")
        ]

    @pytest.mark.parametrize("quote", ['"', "'"], ids=["double", "single"])
    def test_title_stripped(self, helpers: KilnEvalHelpers, quote):
        text = f"[docs](https://docs.kiln.ai {quote}The Docs{quote})"
        assert helpers.get_markdown_links(text) == [("docs", "https://docs.kiln.ai")]

    def test_images_excluded(self, helpers: KilnEvalHelpers):
        text = "![logo](https://kiln.ai/logo.png) but [site](https://kiln.ai)"
        assert helpers.get_markdown_links(text) == [("site", "https://kiln.ai")]

    def test_code_spans_ignored(self, helpers: KilnEvalHelpers):
        text = "Use `arr[i](x)` to call it; real [link](https://kiln.ai)."
        assert helpers.get_markdown_links(text) == [("link", "https://kiln.ai")]

    def test_empty_target_is_reported(self, helpers: KilnEvalHelpers):
        """A broken link with no target is exactly what link checks look for."""
        assert helpers.get_markdown_links("[broken]()") == [("broken", "")]

    def test_nested_brackets_unsupported(self, helpers: KilnEvalHelpers):
        assert helpers.get_markdown_links("[a[b]](https://kiln.ai)") == []

    def test_adjacent_links(self, helpers: KilnEvalHelpers):
        assert helpers.get_markdown_links("[a](https://x.ai)[b](https://y.ai)") == [
            ("a", "https://x.ai"),
            ("b", "https://y.ai"),
        ]

    def test_unquoted_space_in_target_unsupported(self, helpers: KilnEvalHelpers):
        assert helpers.get_markdown_links("[t](not a link)") == []

    @pytest.mark.parametrize(
        "payload",
        ["`" * 100_000, "[a](" + " " * 100_000, "[a](" + "(" * 100_000],
        ids=["backtick-run", "space-run", "paren-run"],
    )
    def test_pathological_input_stays_linear(self, helpers: KilnEvalHelpers, payload):
        """These inputs took tens of seconds with backtracking-ambiguous
        regexes (quadratic); the linear rewrite must stay well under the
        sandbox timeout. Generous bound to avoid CI flake."""
        import time

        start = time.perf_counter()
        helpers.get_markdown_links(payload)
        assert time.perf_counter() - start < 2.0
