"""Tests for OpenAI types wrapper to ensure compatibility."""

from typing import get_args, get_origin

from openai.types.chat import (
    ChatCompletionAssistantMessageParam as OpenAIChatCompletionAssistantMessageParam,
)
from openai.types.chat import (
    ChatCompletionMessageParam as OpenAIChatCompletionMessageParam,
)

from kiln_ai.utils.open_ai_types import (
    ChatCompletionAssistantMessageParamWrapper,
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


def test_chat_completion_message_param_union_compatibility():
    """
    Test that our ChatCompletionMessageParam union contains the same types as OpenAI's,
    except with our wrapper instead of the original assistant message param.
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

    # Expected difference: OpenAI has ChatCompletionAssistantMessageParam,
    # Kiln has ChatCompletionAssistantMessageParamWrapper
    expected_openai_only = {"ChatCompletionAssistantMessageParam"}
    expected_kiln_only = {"ChatCompletionAssistantMessageParamWrapper"}

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
        "ChatCompletionToolMessageParam",
        "ChatCompletionFunctionMessageParam",
    }

    assert common_types == expected_common_types, (
        f"Common types mismatch. Expected: {expected_common_types}, Got: {common_types}"
    )


def test_wrapper_can_be_instantiated():
    """Test that our wrapper can be instantiated with the same data as the original."""
    # Create a sample message that should work with both types
    sample_message: ChatCompletionAssistantMessageParamWrapper = {
        "role": "assistant",
        "content": "Hello, world!",
    }

    # This should work without type errors (runtime test)
    assert sample_message["role"] == "assistant"
    assert sample_message.get("content") == "Hello, world!"

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
