"""Tests for kiln_ai.datamodel.usage.

Covers the MessageUsage / Usage split, the re-exports for backwards
compatibility, and ``MessageUsage.from_trace``.

Field-level Usage tests (validation, simple ``__add__``, etc.) live in
``test_example_models.py`` — they predate this module move and don't need
to be duplicated here.
"""

import pytest

from kiln_ai.datamodel import MessageUsage as MessageUsageFromDatamodel
from kiln_ai.datamodel import Usage as UsageFromDatamodel
from kiln_ai.datamodel.task_run import MessageUsage as MessageUsageFromTaskRun
from kiln_ai.datamodel.task_run import Usage as UsageFromTaskRun
from kiln_ai.datamodel.usage import MessageUsage, Usage
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


def test_message_usage_re_exported_from_task_run():
    """`MessageUsage` mirrors the `Usage` re-export pattern."""
    assert MessageUsageFromTaskRun is MessageUsage


def test_message_usage_re_exported_from_datamodel_init():
    assert MessageUsageFromDatamodel is MessageUsage


def test_usage_is_message_usage_subclass():
    assert issubclass(Usage, MessageUsage)
    assert isinstance(Usage(), MessageUsage)


def test_message_usage_has_no_latency_field():
    """The base class intentionally does not carry total_llm_latency_ms."""
    assert "total_llm_latency_ms" not in MessageUsage.model_fields
    assert "total_llm_latency_ms" in Usage.model_fields


def test_message_usage_add_returns_message_usage_without_latency():
    a = MessageUsage(input_tokens=10, output_tokens=5, total_tokens=15, cost=0.01)
    b = MessageUsage(input_tokens=3, output_tokens=2, total_tokens=5, cost=0.005)

    result = a + b

    # Returns the base class — no latency field, no Usage-narrowing.
    assert type(result) is MessageUsage
    assert result.input_tokens == 13
    assert result.output_tokens == 7
    assert result.total_tokens == 20
    assert result.cost == pytest.approx(0.015)


def test_message_usage_add_handles_none_fields():
    a = MessageUsage(input_tokens=10, output_tokens=None, cost=None)
    b = MessageUsage(input_tokens=None, output_tokens=4, cost=0.5)

    result = a + b

    assert result.input_tokens == 10
    assert result.output_tokens == 4
    assert result.cost == 0.5


def test_message_usage_add_rejects_non_message_usage():
    with pytest.raises(TypeError, match="Cannot add MessageUsage with"):
        MessageUsage() + 5  # type: ignore[operator]


def test_usage_plus_usage_sums_latency():
    a = Usage(input_tokens=1, total_llm_latency_ms=200)
    b = Usage(input_tokens=2, total_llm_latency_ms=300)

    result = a + b

    assert isinstance(result, Usage)
    assert result.input_tokens == 3
    assert result.total_llm_latency_ms == 500


def test_usage_plus_message_usage_carries_latency_through():
    """Right-hand side has no latency to contribute, so the accumulator's
    latency passes through unchanged."""
    accumulator = Usage(input_tokens=10, total_llm_latency_ms=400)
    increment = MessageUsage(input_tokens=2)

    result = accumulator + increment

    assert isinstance(result, Usage)
    assert result.input_tokens == 12
    assert result.total_llm_latency_ms == 400


def test_message_usage_plus_usage_returns_message_usage_without_latency():
    """Left-hand side is the base class — `MessageUsage.__add__` must drop
    any latency the right-hand `Usage` carries. Documents that the only
    place latency is preserved is when `self` is a `Usage`. Guards against
    a future regression where `MessageUsage.__add__` is changed to delegate
    to a more permissive code path."""
    base = MessageUsage(input_tokens=1)
    sub = Usage(input_tokens=2, total_llm_latency_ms=999)
    result = base + sub
    assert type(result) is MessageUsage
    assert not isinstance(result, Usage)
    assert result.input_tokens == 3
    assert not hasattr(result, "total_llm_latency_ms")


def test_usage_plus_message_usage_with_none_latency_left_side():
    accumulator = Usage(input_tokens=0, total_llm_latency_ms=None)
    increment = MessageUsage(input_tokens=5)

    result = accumulator + increment

    assert isinstance(result, Usage)
    assert result.total_llm_latency_ms is None
    assert result.input_tokens == 5


def test_usage_add_rejects_non_message_usage():
    with pytest.raises(TypeError, match="Cannot add Usage with"):
        Usage() + "not_usage"  # type: ignore[operator]


def test_message_usage_from_trace_returns_message_usage():
    trace: list[ChatCompletionMessageParam] = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "yo",
            "usage": MessageUsage(input_tokens=4, output_tokens=2, cost=0.01),
        },
    ]
    result = MessageUsage.from_trace(trace)

    # Always MessageUsage — never a Usage (the trace doesn't carry latency).
    assert type(result) is MessageUsage
    assert result.input_tokens == 4


def test_from_trace_none_returns_empty_message_usage():
    result = MessageUsage.from_trace(None)
    assert type(result) is MessageUsage
    assert result == MessageUsage()


def test_from_trace_empty_list_returns_empty_message_usage():
    result = MessageUsage.from_trace([])
    assert type(result) is MessageUsage
    assert result == MessageUsage()


def test_from_trace_skips_non_assistant_messages():
    trace: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        {"role": "tool", "content": "{}", "tool_call_id": "c1"},
    ]
    assert MessageUsage.from_trace(trace) == MessageUsage()


def test_from_trace_single_assistant_with_usage():
    usage = MessageUsage(input_tokens=10, output_tokens=5, total_tokens=15, cost=0.01)
    trace: list[ChatCompletionMessageParam] = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "yo", "usage": usage},
    ]

    result = MessageUsage.from_trace(trace)

    assert result.input_tokens == 10
    assert result.output_tokens == 5
    assert result.total_tokens == 15
    assert result.cost == 0.01


def test_from_trace_multiple_assistants_sums_usage():
    u1 = MessageUsage(input_tokens=10, output_tokens=5, total_tokens=15, cost=0.01)
    u2 = MessageUsage(input_tokens=3, output_tokens=2, total_tokens=5, cost=0.005)
    trace: list[ChatCompletionMessageParam] = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "first", "usage": u1},
        {"role": "user", "content": "more"},
        {"role": "assistant", "content": "second", "usage": u2},
    ]

    result = MessageUsage.from_trace(trace)

    assert result.input_tokens == 13
    assert result.output_tokens == 7
    assert result.total_tokens == 20
    assert result.cost == 0.015


def test_from_trace_skips_assistants_without_usage():
    u1 = MessageUsage(input_tokens=10, output_tokens=5, total_tokens=15, cost=0.01)
    trace: list[ChatCompletionMessageParam] = [
        {"role": "assistant", "content": "no usage here"},
        {"role": "assistant", "content": "with usage", "usage": u1},
    ]

    result = MessageUsage.from_trace(trace)

    assert result.input_tokens == 10
    assert result.cost == 0.01


def test_from_trace_handles_assistant_with_usage_set_to_none():
    u1 = MessageUsage(input_tokens=10, output_tokens=5, total_tokens=15, cost=0.01)
    trace: list[ChatCompletionMessageParam] = [
        {"role": "assistant", "content": "explicit none", "usage": None},
        {"role": "assistant", "content": "real", "usage": u1},
    ]

    result = MessageUsage.from_trace(trace)

    assert result.input_tokens == 10
    assert result.cost == 0.01


def test_from_trace_accepts_usage_as_dict():
    """After a JSON round-trip, per-message `usage` may arrive as a plain
    dict rather than a MessageUsage instance. from_trace must handle both."""
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

    result = MessageUsage.from_trace(trace)

    assert result.input_tokens == 7
    assert result.output_tokens == 3
    assert result.total_tokens == 10
    assert result.cost == 0.002


def test_from_trace_partial_none_fields_in_usage():
    u1 = MessageUsage(input_tokens=10, output_tokens=None, total_tokens=None, cost=None)
    u2 = MessageUsage(
        input_tokens=None, output_tokens=None, total_tokens=None, cost=0.5
    )
    trace: list[ChatCompletionMessageParam] = [
        {"role": "assistant", "content": "a", "usage": u1},
        {"role": "assistant", "content": "b", "usage": u2},
    ]

    result = MessageUsage.from_trace(trace)

    assert result.input_tokens == 10
    assert result.output_tokens is None
    assert result.total_tokens is None
    assert result.cost == 0.5


def test_from_trace_returns_message_usage_instance_never_none():
    """from_trace always returns a MessageUsage — callers detect 'unknown'
    by looking at the optional field on TaskRun (cumulative_usage), not at
    the return value of this function."""
    assert isinstance(MessageUsage.from_trace(None), MessageUsage)
    assert isinstance(MessageUsage.from_trace([]), MessageUsage)
    assert isinstance(
        MessageUsage.from_trace([{"role": "user", "content": "x"}]),
        MessageUsage,
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
            "usage": MessageUsage(input_tokens=4),
        },
    ]

    result = MessageUsage.from_trace(trace)  # type: ignore[arg-type]

    assert result.input_tokens == 4


def test_from_trace_accepts_usage_with_legacy_latency_key():
    """Old per-message ``usage`` payloads may include a leftover
    ``total_llm_latency_ms`` key. Pydantic's default ``extra='ignore'`` (on
    BaseModel) silently drops it during model_validate."""
    trace: list[ChatCompletionMessageParam] = [
        {
            "role": "assistant",
            "content": "legacy",
            "usage": {
                "input_tokens": 3,
                "cost": 0.01,
                "total_llm_latency_ms": 400,  # not on MessageUsage
            },
        },
    ]

    result = MessageUsage.from_trace(trace)

    assert type(result) is MessageUsage
    assert result.input_tokens == 3
    assert result.cost == 0.01
