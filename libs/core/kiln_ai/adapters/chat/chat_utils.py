from typing import Union

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
                        content=content if isinstance(content, str) else None,
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
