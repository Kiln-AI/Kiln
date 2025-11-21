from typing import Any, Union

from kiln_ai.adapters.chat.chat_formatter import (
    ToolCallMessage,
    ToolResponseMessage,
)
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam


def build_tool_call_messages(
    trace: list[ChatCompletionMessageParam] | None,
) -> list[Union[ToolCallMessage, ToolResponseMessage]]:
    """
    Extract tool call and tool response messages from a trace. It's based off the OpenAI schema.

    Args:
        trace: The trace of the task run in OpenAI format

    Returns:
        List of ToolCallMessage and ToolResponseMessage objects extracted from the trace
    """
    if trace is None:
        return []

    tool_messages: list[Union[ToolCallMessage, ToolResponseMessage]] = []

    for message in trace:
        role = message.get("role")

        if role == "assistant" and "tool_calls" in message:
            tool_calls = message.get("tool_calls")
            if tool_calls:
                content = message.get("content")
                tool_messages.append(
                    ToolCallMessage(
                        role="assistant",
                        tool_calls=tool_calls,
                        content=extract_text_from_content(content),
                    )
                )
        elif role == "tool":
            content = message.get("content")
            tool_call_id = message.get("tool_call_id")

            if tool_call_id is None:
                raise ValueError("Tool call ID is required for tool response messages")
            if content is None:
                raise ValueError("Content is required for tool response messages")

            if not isinstance(content, str):
                content = str(content)

            tool_messages.append(
                ToolResponseMessage(
                    role="tool",
                    content=content,
                    tool_call_id=tool_call_id,
                )
            )

    return tool_messages


def extract_text_from_content(
    content: Any,
) -> str | None:
    """
    Extract text content from OpenAI message content.
    """
    if content is None:
        return None

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts = []
        for part in content:
            if (
                isinstance(part, dict)
                and part.get("type") == "text"
                and isinstance(part.get("text"), str)
            ):
                text_parts.append(part["text"])

        if text_parts:
            return "".join(text_parts)

    return None
