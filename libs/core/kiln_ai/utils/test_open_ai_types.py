"""Tests for OpenAI types wrapper to ensure compatibility."""

import copy
import json
from typing import ClassVar, get_args, get_origin

import pytest
from openai.types.chat import (
    ChatCompletionAssistantMessageParam as OpenAIChatCompletionAssistantMessageParam,
)
from openai.types.chat import (
    ChatCompletionDeveloperMessageParam as OpenAIChatCompletionDeveloperMessageParam,
)
from openai.types.chat import (
    ChatCompletionMessageParam as OpenAIChatCompletionMessageParam,
)
from openai.types.chat import (
    ChatCompletionSystemMessageParam as OpenAIChatCompletionSystemMessageParam,
)
from openai.types.chat import (
    ChatCompletionToolMessageParam as OpenAIChatCompletionToolMessageParam,
)
from openai.types.chat import (
    ChatCompletionUserMessageParam as OpenAIChatCompletionUserMessageParam,
)

from kiln_ai.adapters.errors import ErrorWithTrace
from kiln_ai.datamodel.task_output import TaskOutput
from kiln_ai.datamodel.task_run import TaskRun
from kiln_ai.utils.open_ai_types import (
    KILN_ONLY_MESSAGE_FIELDS,
    ChatCompletionAssistantMessageParamWrapper,
    ChatCompletionDeveloperMessageParamWrapper,
    ChatCompletionSystemMessageParamWrapper,
    ChatCompletionToolMessageParamWrapper,
    ChatCompletionUserMessageParamWrapper,
    materialize_lazy_content,
    sanitize_messages_for_provider,
    serialize_trace,
    trace_has_pending_client_tool_calls,
)
from kiln_ai.utils.open_ai_types import (
    ChatCompletionMessageParam as KilnChatCompletionMessageParam,
)
from kiln_ai.utils.usage import MessageUsage


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


@pytest.mark.parametrize(
    "kiln_type, openai_type",
    [
        (
            ChatCompletionDeveloperMessageParamWrapper,
            OpenAIChatCompletionDeveloperMessageParam,
        ),
        (
            ChatCompletionSystemMessageParamWrapper,
            OpenAIChatCompletionSystemMessageParam,
        ),
        (
            ChatCompletionUserMessageParamWrapper,
            OpenAIChatCompletionUserMessageParam,
        ),
    ],
)
def test_content_only_wrappers_properties_match(kiln_type, openai_type):
    """These three wrappers add nothing - they exist only to swap Iterable[T] for
    List[T] on content. Any property the OpenAI type grows must be copied over.
    """
    assert set(openai_type.__annotations__.keys()) == set(
        kiln_type.__annotations__.keys()
    ), (
        f"Property names don't match between {kiln_type.__name__} and "
        f"{openai_type.__name__}."
    )


def test_no_union_member_declares_an_iterable_content():
    """The whole point of the wrappers. An Iterable[T] content validates into a
    single-use ValidatorIterator, which serializes to `[]` once read - see
    TestListValuedContentRoundTrip.
    """
    for member in get_args(KilnChatCompletionMessageParam):
        content_type = member.__annotations__.get("content")
        assert content_type is not None
        assert "Iterable" not in str(content_type), (
            f"{member.__name__}.content is declared as {content_type}. Use List[T], "
            "not Iterable[T] - pydantic cannot round-trip an Iterable[T]."
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

    # Expected differences: every role whose content can be a list of parts is a Kiln
    # wrapper, because the OpenAI type declares that content as Iterable[T] and pydantic
    # cannot round-trip an Iterable[T]. Only the function role, whose content is a plain
    # string, is used directly.
    expected_openai_only = {
        "ChatCompletionDeveloperMessageParam",
        "ChatCompletionSystemMessageParam",
        "ChatCompletionUserMessageParam",
        "ChatCompletionAssistantMessageParam",
        "ChatCompletionToolMessageParam",
    }
    expected_kiln_only = {
        "ChatCompletionDeveloperMessageParamWrapper",
        "ChatCompletionSystemMessageParamWrapper",
        "ChatCompletionUserMessageParamWrapper",
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
        """Serializing must not damage the trace it was handed, and must be
        repeatable - the second read has to say what the first one said.
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
        assert json.loads(task_run.model_dump_json())["trace"][0]["content"] == [
            {"text": "KEEP", "type": "text"}
        ]

    def test_a_list_valued_content_and_a_usage_model_coexist(self):
        """A list-valued `content` and a `MessageUsage` are both non-plain values on
        the same message, and they serialize differently: content is a list of parts,
        usage is a model dumped to an object. Neither may be mistaken for the other.
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


class TestListValuedContentRoundTrip:
    """A message's `content` can be a list of parts instead of a string - that is
    how a multimodal message (text plus an image, audio or a file) is expressed.

    Every role that allows it declared that content as `Iterable[T]`, which pydantic
    validates into a single-use `ValidatorIterator`. Serializing reads it, a read
    empties it, and `save_to_file` then wrote `content: []` to disk with no error and
    no warning. These pin that a list-valued content survives the model layer whole:
    to disk, back off disk, and through a copy.
    """

    LIST_CONTENT_MESSAGES: ClassVar[list[KilnChatCompletionMessageParam]] = [
        {"role": "developer", "content": [{"type": "text", "text": "DEV"}]},
        {"role": "system", "content": [{"type": "text", "text": "SYS"}]},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "USER"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,aGk="},
                },
            ],
        },
        {"role": "assistant", "content": [{"type": "text", "text": "ASST"}]},
        {
            "role": "tool",
            "tool_call_id": "c1",
            "content": [{"type": "text", "text": "TOOL"}],
        },
    ]

    def _task_run(self, tmp_path, messages):
        return TaskRun(
            path=tmp_path / "task_run.kiln",
            input="in",
            output=TaskOutput(output="out"),
            trace=list(messages),
        )

    def test_validation_produces_a_list_not_a_lazy_iterator(self, tmp_path):
        """The root cause, pinned directly. Everything below follows from this."""
        task_run = self._task_run(tmp_path, self.LIST_CONTENT_MESSAGES)

        assert task_run.trace is not None
        for message in task_run.trace:
            assert isinstance(message["content"], list), (
                f"{message['role']} content is a {type(message['content']).__name__}"
            )

    def test_every_role_survives_save_and_load(self, tmp_path):
        task_run = self._task_run(tmp_path, self.LIST_CONTENT_MESSAGES)

        task_run.save_to_file()
        loaded = TaskRun.load_from_file(task_run.path)

        assert loaded.trace is not None
        assert len(loaded.trace) == len(self.LIST_CONTENT_MESSAGES)
        for loaded_message, original in zip(loaded.trace, self.LIST_CONTENT_MESSAGES):
            assert loaded_message["content"] == original["content"], (
                f"{original['role']} content did not survive the round trip"
            )

    def test_the_image_part_of_a_multimodal_message_survives(self, tmp_path):
        """The case this protects in practice: an image part is not recoverable from
        anywhere else once it is dropped."""
        task_run = self._task_run(
            tmp_path, [m for m in self.LIST_CONTENT_MESSAGES if m["role"] == "user"]
        )

        task_run.save_to_file()
        loaded = TaskRun.load_from_file(task_run.path)

        assert loaded.trace is not None
        assert loaded.trace[0]["content"][1] == {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,aGk="},
        }

    def test_a_second_save_of_the_same_object_writes_the_same_content(self, tmp_path):
        """The original bug lost the content on the *second* write for some roles, so
        one save proving correct was never enough."""
        task_run = self._task_run(tmp_path, self.LIST_CONTENT_MESSAGES)

        task_run.save_to_file()
        first = task_run.path.read_text(encoding="utf-8")
        task_run.save_to_file()
        second = task_run.path.read_text(encoding="utf-8")

        assert json.loads(first)["trace"] == json.loads(second)["trace"]
        assert json.loads(second)["trace"][0]["content"] == [
            {"type": "text", "text": "DEV"}
        ]

    def test_a_loaded_run_can_be_saved_again_without_loss(self, tmp_path):
        """Load and re-save is what a repair or a tag edit does to a stored run."""
        task_run = self._task_run(tmp_path, self.LIST_CONTENT_MESSAGES)
        task_run.save_to_file()

        loaded = TaskRun.load_from_file(task_run.path).mutable_copy()
        loaded.save_to_file()
        reloaded = TaskRun.load_from_file(task_run.path)

        assert reloaded.trace is not None
        for message, original in zip(reloaded.trace, self.LIST_CONTENT_MESSAGES):
            assert message["content"] == original["content"]

    def test_mutable_copy_does_not_raise(self, tmp_path):
        """`mutable_copy` deep-copies, and a `ValidatorIterator` cannot be pickled -
        so a list-valued content used to raise `TypeError` here.
        """
        task_run = self._task_run(tmp_path, self.LIST_CONTENT_MESSAGES)

        copied = task_run.mutable_copy()

        assert copied.trace is not None
        assert copied.trace[2]["content"] == self.LIST_CONTENT_MESSAGES[2]["content"]

    def test_a_generator_content_is_materialized_at_validation(self, tmp_path):
        """A library caller can pass any iterable, not only a list. Validation must
        drain it there and then, while the values are still readable."""
        task_run = self._task_run(
            tmp_path,
            [
                {
                    "role": "user",
                    "content": (p for p in [{"type": "text", "text": "GEN"}]),
                }
            ],
        )

        task_run.save_to_file()
        loaded = TaskRun.load_from_file(task_run.path)

        assert loaded.trace is not None
        assert loaded.trace[0]["content"] == [{"type": "text", "text": "GEN"}]

    def test_a_string_content_is_left_a_string(self, tmp_path):
        """The common case, and the one every stored trace holds today."""
        task_run = self._task_run(
            tmp_path,
            [
                {"role": "user", "content": "plain"},
                {"role": "assistant", "content": "also plain"},
            ],
        )

        task_run.save_to_file()
        loaded = TaskRun.load_from_file(task_run.path)

        assert loaded.trace is not None
        assert loaded.trace[0]["content"] == "plain"
        assert loaded.trace[1]["content"] == "also plain"

    def test_the_trace_the_caller_handed_over_is_not_consumed(self, tmp_path):
        """Validation must not empty the caller's own list as a side effect."""
        caller_messages = copy.deepcopy(self.LIST_CONTENT_MESSAGES)

        self._task_run(tmp_path, caller_messages).save_to_file()

        assert caller_messages == self.LIST_CONTENT_MESSAGES


class TestMaterializeLazyContent:
    """The guardrail in front of union validation. A caller can pass any iterable as
    `content`; pydantic's smart union drains it on the members that do not match the
    role, so the matching member sees an empty iterator. This drains it first instead.
    """

    def test_a_generator_becomes_a_list(self):
        trace = [
            {"role": "user", "content": (p for p in [{"type": "text", "text": "GEN"}])}
        ]

        assert materialize_lazy_content(trace) == [
            {"role": "user", "content": [{"type": "text", "text": "GEN"}]}
        ]

    def test_a_list_is_left_alone(self):
        trace = [{"role": "user", "content": [{"type": "text", "text": "LIST"}]}]

        assert materialize_lazy_content(trace) == trace

    def test_a_string_is_not_split_into_characters(self):
        """A string is iterable too. Treating it as one would be the worst outcome
        here - `"hi"` would become `["h", "i"]`.
        """
        assert materialize_lazy_content([{"role": "user", "content": "hi"}]) == [
            {"role": "user", "content": "hi"}
        ]

    def test_a_usage_model_is_left_alone(self):
        """The walk is scoped to `content` and must not be generalized. A pydantic
        model is iterable - it yields `(name, value)` pairs - so a walk over "any
        iterable value" would turn `usage` into a list of pairs.
        """
        usage = MessageUsage(input_tokens=4, cost=0.01)
        trace = [{"role": "assistant", "content": "hi", "usage": usage}]

        assert materialize_lazy_content(trace)[0]["usage"] is usage

    def test_the_callers_message_is_not_mutated(self):
        message = {
            "role": "user",
            "content": (p for p in [{"type": "text", "text": "G"}]),
        }
        trace = [message]

        result = materialize_lazy_content(trace)

        assert result[0] is not message
        assert trace[0] is message

    def test_a_none_content_passes_through(self):
        trace = [{"role": "assistant", "content": None, "tool_calls": []}]

        assert materialize_lazy_content(trace) == trace

    @pytest.mark.parametrize("value", [None, "not a list", 42, {"role": "user"}])
    def test_a_non_list_passes_through_for_pydantic_to_reject(self, value):
        """Bad input is pydantic's to complain about, with its own error message."""
        assert materialize_lazy_content(value) is value

    def test_a_non_dict_message_passes_through(self):
        """Traces transiently hold LiteLLM Message objects, not only dicts."""
        message = MessageUsage(input_tokens=1)

        assert materialize_lazy_content([message]) == [message]


def test_error_with_trace_materializes_lazy_content():
    """`ErrorWithTrace` carries the partial trace of a failed run back to the client.
    A failed run's trace is the only record of what happened, so it needs the same
    guard `TaskRun.trace` has.
    """
    error = ErrorWithTrace(
        message="boom",
        error_type="RuntimeError",
        trace=[
            {"role": "user", "content": (p for p in [{"type": "text", "text": "GEN"}])}
        ],
    )

    assert error.trace is not None
    assert error.trace[0]["content"] == [{"type": "text", "text": "GEN"}]
