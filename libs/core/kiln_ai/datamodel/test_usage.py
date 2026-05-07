"""Tests for kiln_ai.datamodel.usage.

Covers the Usage class itself (re-exported from task_run.py for backwards
compatibility) and the new Usage.from_trace static method.

Field-level Usage tests (validation, __add__, etc.) live in
test_example_models.py — they predate this module move and don't need to be
duplicated here.
"""

from kiln_ai.datamodel import Usage as UsageFromDatamodel
from kiln_ai.datamodel.task_run import Usage as UsageFromTaskRun
from kiln_ai.datamodel.usage import Usage
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam


def test_usage_re_exported_from_task_run():
    """`from kiln_ai.datamodel.task_run import Usage` returns the same class
    as `from kiln_ai.datamodel.usage import Usage`. Existing import sites
    must keep working after the file move."""
    assert UsageFromTaskRun is Usage


def test_usage_re_exported_from_datamodel_init():
    """`from kiln_ai.datamodel import Usage` continues to resolve to the
    moved class via the existing __init__.py re-export chain."""
    assert UsageFromDatamodel is Usage


def test_from_trace_none_returns_empty_usage():
    result = Usage.from_trace(None)
    assert isinstance(result, Usage)
    assert result == Usage()


def test_from_trace_empty_list_returns_empty_usage():
    result = Usage.from_trace([])
    assert isinstance(result, Usage)
    assert result == Usage()


def test_from_trace_skips_non_assistant_messages():
    trace: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        {"role": "tool", "content": "{}", "tool_call_id": "c1"},
    ]
    assert Usage.from_trace(trace) == Usage()


def test_from_trace_single_assistant_with_usage():
    usage = Usage(input_tokens=10, output_tokens=5, total_tokens=15, cost=0.01)
    trace: list[ChatCompletionMessageParam] = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "yo", "usage": usage},
    ]

    result = Usage.from_trace(trace)

    assert result.input_tokens == 10
    assert result.output_tokens == 5
    assert result.total_tokens == 15
    assert result.cost == 0.01


def test_from_trace_multiple_assistants_sums_usage():
    u1 = Usage(input_tokens=10, output_tokens=5, total_tokens=15, cost=0.01)
    u2 = Usage(input_tokens=3, output_tokens=2, total_tokens=5, cost=0.005)
    trace: list[ChatCompletionMessageParam] = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "first", "usage": u1},
        {"role": "user", "content": "more"},
        {"role": "assistant", "content": "second", "usage": u2},
    ]

    result = Usage.from_trace(trace)

    assert result.input_tokens == 13
    assert result.output_tokens == 7
    assert result.total_tokens == 20
    assert result.cost == 0.015


def test_from_trace_skips_assistants_without_usage():
    u1 = Usage(input_tokens=10, output_tokens=5, total_tokens=15, cost=0.01)
    trace: list[ChatCompletionMessageParam] = [
        {"role": "assistant", "content": "no usage here"},
        {"role": "assistant", "content": "with usage", "usage": u1},
    ]

    result = Usage.from_trace(trace)

    assert result.input_tokens == 10
    assert result.cost == 0.01


def test_from_trace_handles_assistant_with_usage_set_to_none():
    u1 = Usage(input_tokens=10, output_tokens=5, total_tokens=15, cost=0.01)
    trace: list[ChatCompletionMessageParam] = [
        {"role": "assistant", "content": "explicit none", "usage": None},
        {"role": "assistant", "content": "real", "usage": u1},
    ]

    result = Usage.from_trace(trace)

    assert result.input_tokens == 10
    assert result.cost == 0.01


def test_from_trace_accepts_usage_as_dict():
    """After a JSON round-trip, per-message `usage` may arrive as a plain
    dict rather than a Usage instance. from_trace must handle both."""
    trace: list[ChatCompletionMessageParam] = [
        {
            "role": "assistant",
            "content": "from json",
            "usage": {
                "input_tokens": 7,
                "output_tokens": 3,
                "total_tokens": 10,
                "cost": 0.002,
            },
        },
    ]

    result = Usage.from_trace(trace)

    assert result.input_tokens == 7
    assert result.output_tokens == 3
    assert result.total_tokens == 10
    assert result.cost == 0.002


def test_from_trace_partial_none_fields_in_usage():
    u1 = Usage(input_tokens=10, output_tokens=None, total_tokens=None, cost=None)
    u2 = Usage(input_tokens=None, output_tokens=None, total_tokens=None, cost=0.5)
    trace: list[ChatCompletionMessageParam] = [
        {"role": "assistant", "content": "a", "usage": u1},
        {"role": "assistant", "content": "b", "usage": u2},
    ]

    result = Usage.from_trace(trace)

    assert result.input_tokens == 10
    assert result.output_tokens is None
    assert result.total_tokens is None
    assert result.cost == 0.5


def test_from_trace_returns_usage_instance_never_none():
    """from_trace always returns a Usage — callers detect 'unknown' by
    looking at the optional field on TaskRun (cumulative_usage), not at
    the return value of this function."""
    assert isinstance(Usage.from_trace(None), Usage)
    assert isinstance(Usage.from_trace([]), Usage)
    assert isinstance(
        Usage.from_trace([{"role": "user", "content": "x"}]),
        Usage,
    )


def test_from_trace_ignores_non_dict_entries():
    """Traces can mix TypedDict messages with LiteLLM Message pydantic
    objects (the `else` branch in all_messages_to_trace). from_trace
    must skip the latter without crashing."""

    class FakeLiteLLMMessage:
        role = "assistant"

    trace = [
        FakeLiteLLMMessage(),
        {
            "role": "assistant",
            "content": "real",
            "usage": Usage(input_tokens=4),
        },
    ]

    result = Usage.from_trace(trace)  # type: ignore[arg-type]

    assert result.input_tokens == 4
