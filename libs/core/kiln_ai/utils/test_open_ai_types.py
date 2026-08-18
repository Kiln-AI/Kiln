"""Tests for OpenAI types wrapper to ensure compatibility."""

import json
from typing import get_args, get_origin

import pytest
from openai.types.chat import (
    ChatCompletionAssistantMessageParam as OpenAIChatCompletionAssistantMessageParam,
)
from openai.types.chat import (
    ChatCompletionMessageParam as OpenAIChatCompletionMessageParam,
)
from openai.types.chat import (
    ChatCompletionToolMessageParam as OpenAIChatCompletionToolMessageParam,
)

from kiln_ai.datamodel.task_output import TaskOutput
from kiln_ai.datamodel.task_run import TaskRun
from kiln_ai.datamodel.usage import MessageUsage
from kiln_ai.utils.open_ai_types import (
    KILN_ONLY_MESSAGE_FIELDS,
    ChatCompletionAssistantMessageParamWrapper,
    ChatCompletionToolMessageParamWrapper,
    sanitize_messages_for_provider,
    serialize_trace,
    trace_has_pending_client_tool_calls,
)
from kiln_ai.utils.open_ai_types import (
    ChatCompletionMessageParam as KilnChatCompletionMessageParam,
)


def test_assistant_message_param_properties_match():
    """
    Test that ChatCompletionAssistantMessageParamWrapper has all the same properties
    as OpenAI's ChatCompletionAssistantMessageParam, except for the known tool_calls type difference.

    This will catch any changes to the OpenAI types that we haven't updated our wrapper for.
    """
    # Get annotations for both types
    openai_annotations = OpenAIChatCompletionAssistantMessageParam.__annotations__
    kiln_annotations = ChatCompletionAssistantMessageParamWrapper.__annotations__

    # Check that both have the same property names
    openai_properties = set(openai_annotations.keys())
    kiln_properties = set(kiln_annotations.keys())

    # Reasoning content is an added property. Confirm it's there and remove it from the comparison.
    assert "reasoning_content" in kiln_properties, "Kiln should have reasoning_content"
    kiln_properties.remove("reasoning_content")

    # latency_ms is a Kiln-added property for LLM call timing. Confirm it's there and remove it.
    assert "latency_ms" in kiln_properties, "Kiln should have latency_ms"
    kiln_properties.remove("latency_ms")

    # usage is a Kiln-added property for per-LLM-call token usage and cost.
    assert "usage" in kiln_properties, "Kiln should have usage"
    kiln_properties.remove("usage")

    assert openai_properties == kiln_properties, (
        f"Property names don't match. "
        f"OpenAI has: {openai_properties}, "
        f"Kiln has: {kiln_properties}, "
        f"Missing from Kiln: {openai_properties - kiln_properties}, "
        f"Extra in Kiln: {kiln_properties - openai_properties}"
    )


def test_tool_message_param_properties_match():
    """
    Test that ChatCompletionToolMessageParamWrapper has all the same properties
    as OpenAI's ChatCompletionToolMessageParam, plus the kiln_task_tool_data property.

    This will catch any changes to the OpenAI types that we haven't updated our wrapper for.
    """
    # Get annotations for both types
    openai_annotations = OpenAIChatCompletionToolMessageParam.__annotations__
    kiln_annotations = ChatCompletionToolMessageParamWrapper.__annotations__

    # Check that both have the same property names
    openai_properties = set(openai_annotations.keys())
    kiln_properties = set(kiln_annotations.keys())

    kiln_extra_properties = {"kiln_task_tool_data", "is_error", "error_message"}
    for prop in kiln_extra_properties:
        assert prop in kiln_properties, f"Kiln should have {prop}"
        kiln_properties.remove(prop)

    assert openai_properties == kiln_properties, (
        f"Property names don't match. "
        f"OpenAI has: {openai_properties}, "
        f"Kiln has: {kiln_properties}, "
        f"Missing from Kiln: {openai_properties - kiln_properties}, "
        f"Extra in Kiln: {kiln_properties - openai_properties}"
    )


def test_chat_completion_message_param_union_compatibility():
    """
    Test that our ChatCompletionMessageParam union contains the same types as OpenAI's,
    except with our wrappers instead of the original assistant and tool message params.
    """
    # Get the union members for both types
    openai_union_args = get_args(OpenAIChatCompletionMessageParam)
    kiln_union_args = get_args(KilnChatCompletionMessageParam)

    # Both should be unions with the same number of members
    assert get_origin(OpenAIChatCompletionMessageParam) == get_origin(
        KilnChatCompletionMessageParam
    ), (
        f"Both should be Union types. OpenAI: {get_origin(OpenAIChatCompletionMessageParam)}, "
        f"Kiln: {get_origin(KilnChatCompletionMessageParam)}"
    )
    assert len(openai_union_args) == len(kiln_union_args), (
        f"Union member count mismatch. OpenAI has {len(openai_union_args)} members, "
        f"Kiln has {len(kiln_union_args)} members"
    )

    # Convert to sets of type names for easier comparison
    openai_type_names = {arg.__name__ for arg in openai_union_args}
    kiln_type_names = {arg.__name__ for arg in kiln_union_args}

    # Expected differences: OpenAI has ChatCompletionAssistantMessageParam and ChatCompletionToolMessageParam,
    # Kiln has ChatCompletionAssistantMessageParamWrapper and ChatCompletionToolMessageParamWrapper
    expected_openai_only = {
        "ChatCompletionAssistantMessageParam",
        "ChatCompletionToolMessageParam",
    }
    expected_kiln_only = {
        "ChatCompletionAssistantMessageParamWrapper",
        "ChatCompletionToolMessageParamWrapper",
    }

    openai_only = openai_type_names - kiln_type_names
    kiln_only = kiln_type_names - openai_type_names

    assert openai_only == expected_openai_only, (
        f"Unexpected types only in OpenAI union: {openai_only - expected_openai_only}"
    )
    assert kiln_only == expected_kiln_only, (
        f"Unexpected types only in Kiln union: {kiln_only - expected_kiln_only}"
    )

    # All other types should be identical
    common_types = openai_type_names & kiln_type_names
    expected_common_types = {
        "ChatCompletionDeveloperMessageParam",
        "ChatCompletionSystemMessageParam",
        "ChatCompletionUserMessageParam",
        "ChatCompletionFunctionMessageParam",
    }

    assert common_types == expected_common_types, (
        f"Common types mismatch. Expected: {expected_common_types}, Got: {common_types}"
    )


def test_assistant_message_wrapper_can_be_instantiated():
    """Test that our assistant message wrapper can be instantiated with the same data as the original."""
    # Test basic assistant message
    sample_assistant_message: ChatCompletionAssistantMessageParamWrapper = {
        "role": "assistant",
        "content": "Hello, world!",
    }

    # This should work without type errors (runtime test)
    assert sample_assistant_message["role"] == "assistant"
    assert sample_assistant_message.get("content") == "Hello, world!"

    # Test with tool calls using List instead of Iterable
    sample_with_tools: ChatCompletionAssistantMessageParamWrapper = {
        "role": "assistant",
        "content": "I'll help you with that.",
        "tool_calls": [
            {
                "id": "call_123",
                "type": "function",
                "function": {"name": "test_function", "arguments": '{"arg": "value"}'},
            }
        ],
    }

    assert len(sample_with_tools.get("tool_calls", [])) == 1
    tool_calls = sample_with_tools.get("tool_calls", [])
    if tool_calls:
        assert tool_calls[0]["id"] == "call_123"


def test_tool_message_wrapper_can_be_instantiated():
    """Test that our tool message wrapper can be instantiated with the same data as the original."""
    # Test basic tool message
    sample_tool_message: ChatCompletionToolMessageParamWrapper = {
        "role": "tool",
        "content": "Tool response",
        "tool_call_id": "call_123",
    }

    assert sample_tool_message["role"] == "tool"
    assert sample_tool_message.get("content") == "Tool response"
    assert sample_tool_message.get("tool_call_id") == "call_123"

    # Test with kiln_task_tool_data
    sample_with_kiln_data: ChatCompletionToolMessageParamWrapper = {
        "role": "tool",
        "content": "Tool response",
        "tool_call_id": "call_123",
        "kiln_task_tool_data": "project_123:::tool_456:::task_789:::run_101",
    }

    assert (
        sample_with_kiln_data.get("kiln_task_tool_data")
        == "project_123:::tool_456:::task_789:::run_101"
    )

    # Test with kiln_task_tool_data as None
    sample_with_none_kiln_data: ChatCompletionToolMessageParamWrapper = {
        "role": "tool",
        "content": "Tool response",
        "tool_call_id": "call_123",
        "kiln_task_tool_data": None,
    }

    assert sample_with_none_kiln_data.get("kiln_task_tool_data") is None


def test_kiln_only_message_fields_set():
    assert KILN_ONLY_MESSAGE_FIELDS == frozenset(
        {"latency_ms", "is_error", "error_message", "kiln_task_tool_data", "usage"}
    )


def test_sanitize_messages_strips_kiln_only_fields():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "hello",
            "latency_ms": 200,
            "usage": MessageUsage(input_tokens=10, output_tokens=5, cost=0.001),
        },
        {
            "role": "tool",
            "content": "{}",
            "tool_call_id": "c1",
            "is_error": True,
            "error_message": "boom",
            "kiln_task_tool_data": "p:::t:::ta:::r",
        },
    ]

    sanitized = sanitize_messages_for_provider(messages)

    assert sanitized == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "tool", "content": "{}", "tool_call_id": "c1"},
    ]


def test_sanitize_messages_strips_usage_from_assistant():
    messages = [
        {
            "role": "assistant",
            "content": "hi",
            "usage": MessageUsage(input_tokens=42, output_tokens=7, cost=0.005),
        }
    ]

    sanitized = sanitize_messages_for_provider(messages)

    assert sanitized == [{"role": "assistant", "content": "hi"}]
    assert "usage" not in sanitized[0]


def test_assistant_wrapper_accepts_usage_field():
    usage = MessageUsage(input_tokens=10, output_tokens=20, total_tokens=30, cost=0.01)
    message: ChatCompletionAssistantMessageParamWrapper = {
        "role": "assistant",
        "content": "ok",
        "latency_ms": 123,
        "usage": usage,
    }

    assert message["role"] == "assistant"
    assert message.get("latency_ms") == 123
    assert message.get("usage") is usage


def test_sanitize_messages_does_not_mutate_input():
    original = [
        {
            "role": "tool",
            "content": "{}",
            "tool_call_id": "c1",
            "is_error": True,
            "error_message": "boom",
        }
    ]
    snapshot = [dict(m) for m in original]

    sanitize_messages_for_provider(original)

    assert original == snapshot


def test_sanitize_messages_passes_non_dicts_through_unchanged():
    class Sentinel:
        pass

    sentinel = Sentinel()
    messages = [
        sentinel,
        {"role": "user", "content": "hi", "latency_ms": 5},
    ]

    sanitized = sanitize_messages_for_provider(messages)

    assert sanitized[0] is sentinel
    assert sanitized[1] == {"role": "user", "content": "hi"}


def test_sanitize_messages_preserves_other_extension_fields():
    messages = [
        {
            "role": "assistant",
            "content": "hi",
            "reasoning_content": "thinking...",
            "latency_ms": 50,
        }
    ]

    sanitized = sanitize_messages_for_provider(messages)

    assert sanitized == [
        {
            "role": "assistant",
            "content": "hi",
            "reasoning_content": "thinking...",
        }
    ]


def test_trace_has_pending_client_tool_calls_empty_trace():
    assert trace_has_pending_client_tool_calls(None) is False
    assert trace_has_pending_client_tool_calls([]) is False


def test_trace_has_pending_client_tool_calls_last_not_assistant():
    trace: list[KilnChatCompletionMessageParam] = [
        {"role": "assistant", "content": "x"},
        {"role": "user", "content": "y"},
    ]
    assert trace_has_pending_client_tool_calls(trace) is False


def test_trace_has_pending_client_tool_calls_only_task_response():
    trace: list[KilnChatCompletionMessageParam] = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "task_response", "arguments": "{}"},
                }
            ],
        },
    ]
    assert trace_has_pending_client_tool_calls(trace) is False


def test_trace_has_pending_client_tool_calls_external_only():
    trace: list[KilnChatCompletionMessageParam] = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "add", "arguments": "{}"},
                }
            ],
        },
    ]
    assert trace_has_pending_client_tool_calls(trace) is True


def test_trace_has_pending_client_tool_calls_mixed_task_response_and_external():
    trace: list[KilnChatCompletionMessageParam] = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "task_response", "arguments": "{}"},
                },
                {
                    "id": "c2",
                    "type": "function",
                    "function": {"name": "add", "arguments": "{}"},
                },
            ],
        },
    ]
    assert trace_has_pending_client_tool_calls(trace) is True


class TestSerializeTrace:
    """`serialize_trace` is what stands between a trace and `json.dumps`.

    A trace is not plain data once pydantic has validated it: the per-message
    `usage` key is a `MessageUsage` model, which the stdlib encoder refuses. These
    pin both halves of that - that the model shapes encode, and that the ordinary
    all-plain-data trace encodes to exactly the same bytes as before.
    """

    def test_serializes_a_message_usage_model_that_json_dumps_cannot(self):
        trace: list[KilnChatCompletionMessageParam] = [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "yo",
                "usage": MessageUsage(input_tokens=4, output_tokens=2, cost=0.01),
            },
        ]

        with pytest.raises(TypeError, match="MessageUsage is not JSON serializable"):
            json.dumps(trace, indent=2, ensure_ascii=False)

        assert json.loads(serialize_trace(trace))[1]["usage"] == {
            "input_tokens": 4,
            "output_tokens": 2,
            "total_tokens": None,
            "cost": 0.01,
            "cached_tokens": None,
        }

    def test_output_is_byte_identical_to_json_dumps_for_a_plain_data_trace(self):
        """The string reaches the UI and the OpenAPI surface, so existing data must
        render exactly as it did before, formatting included."""
        trace: list[KilnChatCompletionMessageParam] = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "héllo \U0001f600"},
            {
                "role": "assistant",
                "content": "resp",
                "latency_ms": 12,
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "f", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "content": "r", "is_error": False},
        ]

        assert serialize_trace(trace) == json.dumps(trace, indent=2, ensure_ascii=False)

    def test_shapes_the_wrappers_do_not_declare_survive_byte_identically(self):
        """The riskiest parity case, because nothing about it is declared.

        A key or a role the wrappers don't know about matches no union member, so
        pydantic drops to duck-typed inference and copies the message through
        verbatim. That fallback is what makes this function a safe swap for
        `json.dumps`, and it is version-sensitive: a pydantic upgrade that
        tightened union serialization would start silently dropping data. This is
        the test that would fail first.
        """
        trace: list[KilnChatCompletionMessageParam] = [
            {
                "role": "assistant",
                "content": "resp",
                # Keys LiteLLM and Anthropic put on messages that Kiln never declared.
                "provider_specific_fields": {"thinking_blocks": [{"n": 1}]},
                "cache_control": {"type": "ephemeral"},
            },
            {"role": "wizard", "content": "a role from a newer Kiln"},
        ]

        assert serialize_trace(trace) == json.dumps(trace, indent=2, ensure_ascii=False)

    def test_matches_what_the_task_run_writes_to_disk(self):
        """Same bytes the trace is persisted with - one shape for stored and
        displayed traces, whichever path produced them."""
        task_run = TaskRun(
            input="in",
            output=TaskOutput(output="out"),
            trace=[
                {"role": "user", "content": "hi"},
                {
                    "role": "assistant",
                    "content": "yo",
                    "usage": MessageUsage(input_tokens=4, cost=0.01),
                },
            ],
        )

        persisted = json.loads(task_run.model_dump_json())["trace"]

        assert json.loads(serialize_trace(task_run.trace)) == persisted

    def test_a_trace_loaded_back_off_disk_still_needs_this(self, tmp_path):
        """The bug is not confined to freshly built traces. Pydantic re-validates
        `usage` into a `MessageUsage` on load too, so a TaskRun read from disk hits
        the same `json.dumps` failure the in-memory one does."""
        path = tmp_path / "task_run.kiln"
        path.write_text(
            TaskRun(
                input="in",
                output=TaskOutput(output="out"),
                trace=[
                    {
                        "role": "assistant",
                        "content": "yo",
                        "usage": MessageUsage(input_tokens=4),
                    }
                ],
            ).model_dump_json(exclude={"path"}),
            encoding="utf-8",
        )

        loaded = TaskRun.load_from_file(path)

        assert loaded.trace is not None
        assert isinstance(loaded.trace[0]["usage"], MessageUsage)
        with pytest.raises(TypeError, match="MessageUsage is not JSON serializable"):
            json.dumps(loaded.trace, indent=2, ensure_ascii=False)
        assert (
            json.loads(serialize_trace(loaded.trace))[0]["usage"]["input_tokens"] == 4
        )

    def test_a_list_valued_content_survives_being_serialized(self):
        """Serializing must not damage the trace it was handed.

        Pydantic validates a list-valued `content` into a single-use
        `ValidatorIterator`, and reading it empties it. Without the materializing
        walk this serialized correctly once and as `content: []` forever after,
        and a `save_to_file` on the same object persisted the empty version.
        """
        task_run = TaskRun(
            input="in",
            output=TaskOutput(output="out"),
            trace=[
                {"role": "assistant", "content": [{"type": "text", "text": "KEEP"}]}
            ],
        )

        first = serialize_trace(task_run.trace)
        second = serialize_trace(task_run.trace)

        assert json.loads(first)[0]["content"] == [{"text": "KEEP", "type": "text"}]
        assert second == first
        # And the trace is still intact for whoever else holds it - the failure mode
        # here was a persisted `content: []`, not just a bad second read.
        #
        # This dump prints a `PydanticSerializationUnexpectedValue` warning, which is
        # expected, not a defect: a materialized list matches neither the `str` nor the
        # `generator` branch of the union the way the lazy iterator did. The bytes it
        # writes are what this asserts, and they are correct.
        assert json.loads(task_run.model_dump_json())["trace"][0]["content"] == [
            {"text": "KEEP", "type": "text"}
        ]

    def test_materializing_content_leaves_a_usage_model_alone(self):
        """The walk is scoped to `content` and must not be generalized.

        A pydantic model is iterable - it yields `(name, value)` pairs - so a walk
        over "any iterable value" would turn `usage` into a list of pairs. This is
        the test that catches that.
        """
        trace: list[KilnChatCompletionMessageParam] = [
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "hi"}],
                "usage": MessageUsage(input_tokens=4, cost=0.01),
            }
        ]

        serialized = json.loads(serialize_trace(trace))[0]

        assert serialized["content"] == [{"text": "hi", "type": "text"}]
        assert serialized["usage"]["input_tokens"] == 4
        assert serialized["usage"]["cost"] == 0.01
