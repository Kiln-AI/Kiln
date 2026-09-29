from typing import Sequence

from litellm.types.utils import (
    ChatCompletionMessageCustomToolCall,
    ChatCompletionMessageToolCall,
)


def function_tool_calls(
    tool_calls: Sequence[
        ChatCompletionMessageToolCall | ChatCompletionMessageCustomToolCall
    ]
    | None,
) -> list[ChatCompletionMessageToolCall]:
    """Narrow a message's tool calls to function tool calls.

    LiteLLM types a tool call as either a function call or an OpenAI custom
    tool call. Kiln only registers function tools, so a custom tool call is a
    model or provider error.
    """
    result: list[ChatCompletionMessageToolCall] = []
    for tool_call in tool_calls or []:
        if isinstance(tool_call, ChatCompletionMessageCustomToolCall):
            raise ValueError(
                "The model requested a custom tool call. Only function tool calls are supported."
            )
        result.append(tool_call)
    return result
