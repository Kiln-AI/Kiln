"""Tests for OpenAI types wrapper to ensure compatibility."""

import copy
import json
from collections import UserDict
from types import MappingProxyType
from typing import ClassVar, get_args, get_origin, get_type_hints

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

# Fields whose type deliberately differs from the OpenAI SDK type of the same name.
# `content` on every role, and `tool_calls` on the assistant - see the module docstring
# of kiln_ai.utils.open_ai_types for what each substitution buys.
WRAPPER_TYPE_EXEMPTIONS = {"content", "tool_calls"}


@pytest.mark.parametrize(
    "kiln_type, openai_type, kiln_only_fields",
    [
        (
            ChatCompletionDeveloperMessageParamWrapper,
            OpenAIChatCompletionDeveloperMessageParam,
            set(),
        ),
        (
            ChatCompletionSystemMessageParamWrapper,
            OpenAIChatCompletionSystemMessageParam,
            set(),
        ),
        (
            ChatCompletionUserMessageParamWrapper,
            OpenAIChatCompletionUserMessageParam,
            set(),
        ),
        (
            ChatCompletionAssistantMessageParamWrapper,
            OpenAIChatCompletionAssistantMessageParam,
            {"reasoning_content", "latency_ms", "usage"},
        ),
        (
            ChatCompletionToolMessageParamWrapper,
            OpenAIChatCompletionToolMessageParam,
            {"kiln_task_tool_data", "is_error", "error_message"},
        ),
    ],
)
def test_wrappers_match_the_openai_sdk_type_they_copy(
    kiln_type, openai_type, kiln_only_fields
):
    """The wrappers are hand-copied from the OpenAI SDK types, so they can drift from
    them: `openai` is pinned with no upper bound, and a stored trace is validated
    against whatever version is installed.

    Resolved types, not just property names. A comparison of names alone would pass
    while the SDK flipped a field from Required to optional or changed a Literal, and
    with `content` now materialized at validation such a drift shows up as a stored
    run that will not load, rather than as a degradation.
    """
    openai_hints = get_type_hints(openai_type, include_extras=True)
    kiln_hints = get_type_hints(kiln_type, include_extras=True)

    for field in kiln_only_fields:
        assert field in kiln_hints, f"{kiln_type.__name__} should have {field}"
        del kiln_hints[field]

    assert set(openai_hints) == set(kiln_hints), (
        f"Property names don't match between {kiln_type.__name__} and "
        f"{openai_type.__name__}. "
        f"Missing from Kiln: {set(openai_hints) - set(kiln_hints)}, "
        f"Extra in Kiln: {set(kiln_hints) - set(openai_hints)}"
    )

    for name, openai_annotation in openai_hints.items():
        if name in WRAPPER_TYPE_EXEMPTIONS:
            continue
        assert kiln_hints[name] == openai_annotation, (
            f"{kiln_type.__name__}.{name} is {kiln_hints[name]}, but "
            f"{openai_type.__name__}.{name} is now {openai_annotation}. Copy the "
            "change over, or add the field to WRAPPER_TYPE_EXEMPTIONS with a reason."
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

    def test_serializing_a_trace_twice_returns_the_same_json(self):
        """This is a public function taking a plain list, so it also gets traces that
        never went through a model. `dump_json` runs serializers, not validators, so
        the `Trace` alias does not reach here: without materializing first, the
        serializer drains a lazy content and the second call returns `content: []`.
        """
        trace = [
            {"role": "user", "content": (p for p in [{"type": "text", "text": "KEEP"}])}
        ]

        first = serialize_trace(trace)  # type: ignore[arg-type]
        second = serialize_trace(trace)  # type: ignore[arg-type]

        assert json.loads(first)[0]["content"] == [{"type": "text", "text": "KEEP"}]
        assert first == second


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

    def test_a_message_appended_to_the_trace_in_place_survives_both_saves(
        self, tmp_path
    ):
        """`validate_assignment` fires when the field is rebound, not when the list it
        holds is mutated, so an appended message reaches the serializer unvalidated.
        The first save used to write it and every save after it wrote `content: []`.
        """
        task_run = self._task_run(tmp_path, [{"role": "user", "content": "hello"}])

        assert task_run.trace is not None
        task_run.trace.append(
            {"role": "user", "content": (p for p in [{"type": "text", "text": "GEN"}])}
        )
        task_run.save_to_file()
        first = json.loads(task_run.path.read_text(encoding="utf-8"))["trace"]
        task_run.save_to_file()
        second = json.loads(task_run.path.read_text(encoding="utf-8"))["trace"]

        assert first == second
        assert second[1]["content"] == [{"type": "text", "text": "GEN"}]

    @pytest.mark.parametrize(
        "container",
        [tuple, lambda messages: (m for m in messages)],
        ids=["tuple", "generator"],
    )
    def test_a_lazy_trace_container_does_not_smuggle_a_lazy_content_past(
        self, tmp_path, container
    ):
        """Pydantic accepts a tuple or a generator for the `list[T]` trace field, so
        the container is a way in for exactly the content this guards against."""
        task_run = self._task_run(
            tmp_path,
            container(
                [
                    {
                        "role": "user",
                        "content": (p for p in [{"type": "text", "text": "GEN"}]),
                    }
                ]
            ),
        )

        assert task_run.trace is not None
        assert task_run.trace[0]["content"] == [{"type": "text", "text": "GEN"}]


class TestContentPartsAreStoredAsHandedOver:
    """A trace is a record of what happened. Every provider extends the OpenAI content
    part set, so validating a part against the SDK's closed union means a part we
    cannot parse is a part we destroy - either by refusing the save outright, after
    the model has been paid for, or by dropping a key we did not expect.

    `ContentPart` is a plain dict for that reason. These pin the shapes that made it
    necessary - all of them produced by Kiln itself, in `encode_file_litellm_format`
    or by the providers it talks to.
    """

    @pytest.mark.parametrize(
        "role, part",
        [
            # encode_file_litellm_format emits this for video on OpenRouter.
            (
                "user",
                {"type": "video_url", "video_url": {"url": "data:video/mp4;base64,AA"}},
            ),
            # ...and this for audio/ogg. The SDK's InputAudio.format is wav or mp3.
            (
                "user",
                {"type": "input_audio", "input_audio": {"data": "AA", "format": "ogg"}},
            ),
            # LiteLLM's explicit image type hint: an extra key inside a part the SDK
            # does declare, so this one used to be dropped rather than rejected.
            (
                "user",
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64,aGk=",
                        "format": "image/png",
                    },
                },
            ),
            # Anthropic prompt caching, same shape of loss.
            ("user", {"type": "text", "text": "hi", "cache_control": {"type": "e"}}),
            # The assistant's list content is narrower still in the SDK - text or a
            # refusal - so a reasoning block from a thinking model does not fit.
            ("assistant", {"type": "thinking", "thinking": "step one"}),
            ("tool", {"type": "text", "text": "ok", "annotations": []}),
        ],
        ids=[
            "video_url",
            "input_audio_ogg",
            "image_url_format_hint",
            "text_cache_control",
            "assistant_thinking_block",
            "tool_extra_key",
        ],
    )
    def test_a_part_the_openai_union_does_not_admit_round_trips_whole(
        self, tmp_path, role, part
    ):
        message = {"role": role, "content": [part]}
        if role == "tool":
            message["tool_call_id"] = "c1"

        task_run = TaskRun(
            path=tmp_path / "task_run.kiln",
            input="in",
            output=TaskOutput(output="out"),
            trace=[message],
        )
        task_run.save_to_file()
        reloaded = TaskRun.load_from_file(task_run.path)

        assert reloaded.trace is not None
        assert reloaded.trace[0]["content"] == [part]

    def test_a_stored_run_holding_an_unknown_part_still_loads(self, tmp_path):
        """The worst outcome of a closed part set is not the failed save, it is the
        file already on disk: `load_from_file` raising makes one run poison the whole
        task's run list, which is read with `error_on_first=True`.
        """
        path = tmp_path / "task_run.kiln"
        task_run = TaskRun(
            path=path,
            input="in",
            output=TaskOutput(output="out"),
            trace=[
                {
                    "role": "user",
                    "content": [{"type": "something_new", "payload": {"a": 1}}],
                }
            ],
        )
        task_run.save_to_file()

        assert TaskRun.load_from_file(path).trace == task_run.trace


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

    def test_the_callers_message_is_normalized_in_place(self):
        """Draining a generator is destructive whether or not the message is copied,
        so copying would leave the caller holding a spent one. Writing the list back
        is what makes a second pass over the same trace return the same thing.
        """
        message = {
            "role": "user",
            "content": (p for p in [{"type": "text", "text": "G"}]),
        }
        trace = [message]

        first = materialize_lazy_content(trace)
        second = materialize_lazy_content(trace)

        assert (
            first
            == second
            == [{"role": "user", "content": [{"type": "text", "text": "G"}]}]
        )
        assert message["content"] == [{"type": "text", "text": "G"}]

    def test_a_read_only_mapping_message_is_copied_instead(self):
        """A MappingProxyType cannot be written to. Copying it still beats letting the
        union drain the generator."""
        message = MappingProxyType(
            {"role": "user", "content": (p for p in [{"type": "text", "text": "G"}])}
        )

        assert materialize_lazy_content([message]) == [
            {"role": "user", "content": [{"type": "text", "text": "G"}]}
        ]

    def test_a_none_content_passes_through(self):
        trace = [{"role": "assistant", "content": None, "tool_calls": []}]

        assert materialize_lazy_content(trace) == trace

    @pytest.mark.parametrize("value", [None, "not a list", 42, b"bytes"])
    def test_a_value_that_is_not_a_trace_passes_through_for_pydantic_to_reject(
        self, value
    ):
        """Bad input is pydantic's to complain about, with its own error message."""
        assert materialize_lazy_content(value) is value

    @pytest.mark.parametrize(
        "container",
        [
            lambda messages: tuple(messages),
            lambda messages: (m for m in messages),
            lambda messages: map(lambda m: m, messages),
        ],
        ids=["tuple", "generator", "map"],
    )
    def test_a_lazy_container_is_walked_too(self, container):
        """Pydantic lax mode accepts a tuple or a generator for a `list[T]` field, so
        a guard that only looked inside a real `list` would let those carry their lazy
        content straight past it.
        """
        messages = [
            {"role": "user", "content": (p for p in [{"type": "text", "text": "GEN"}])}
        ]

        assert materialize_lazy_content(container(messages)) == [
            {"role": "user", "content": [{"type": "text", "text": "GEN"}]}
        ]

    @pytest.mark.parametrize(
        "content",
        [
            MappingProxyType({"type": "text", "text": "hi"}),
            UserDict({"type": "text", "text": "hi"}),
            MessageUsage(input_tokens=4),
            bytearray(b"hi"),
            memoryview(b"hi"),
        ],
        ids=["mappingproxy", "userdict", "pydantic_model", "bytearray", "memoryview"],
    )
    def test_an_iterable_that_does_not_iterate_to_its_own_content_is_left_alone(
        self, content
    ):
        """Every one of these is `Iterable`, and iterating it yields something that is
        not its value: keys, `(name, value)` pairs, ints. Draining one would replace
        the caller's value with a mangled one, and the union error that followed would
        report the mangled value rather than what was passed in.
        """
        result = materialize_lazy_content([{"role": "user", "content": content}])

        assert result[0]["content"] is content

    def test_a_non_dict_message_passes_through(self):
        """Traces transiently hold LiteLLM Message objects, not only dicts."""
        message = MessageUsage(input_tokens=1)

        assert materialize_lazy_content([message]) == [message]
