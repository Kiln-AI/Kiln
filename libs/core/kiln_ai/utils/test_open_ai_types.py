"""Tests for OpenAI types wrapper to ensure compatibility."""

from typing import get_args, get_origin

from openai.types.chat import (
    ChatCompletionAssistantMessageParam as OpenAIChatCompletionAssistantMessageParam,
)
from openai.types.chat import (
    ChatCompletionMessageParam as OpenAIChatCompletionMessageParam,
)
from openai.types.chat import (
    ChatCompletionToolMessageParam as OpenAIChatCompletionToolMessageParam,
)

from kiln_ai.utils.open_ai_types import (
    ChatCompletionAssistantMessageParamWrapper,
    ChatCompletionToolMessageParamWrapper,
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

    # Kiln task tool data is an added property. Confirm it's there and remove it from the comparison.
    assert "kiln_task_tool_data" in kiln_properties, (
        "Kiln should have kiln_task_tool_data"
    )
    kiln_properties.remove("kiln_task_tool_data")

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
        "kiln_task_tool_data": "project_123::tool_456::task_789::run_101",
    }

    assert (
        sample_with_kiln_data.get("kiln_task_tool_data")
        == "project_123::tool_456::task_789::run_101"
    )

    # Test with kiln_task_tool_data as None
    sample_with_none_kiln_data: ChatCompletionToolMessageParamWrapper = {
        "role": "tool",
        "content": "Tool response",
        "tool_call_id": "call_123",
        "kiln_task_tool_data": None,
    }

    assert sample_with_none_kiln_data.get("kiln_task_tool_data") is None
