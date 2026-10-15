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


def response_function_tool_calls(
    tool_calls: Sequence[
        ChatCompletionMessageToolCall | ChatCompletionMessageCustomToolCall
    ]
    | None,
) -> list[ChatCompletionMessageToolCall]:
    """The function tool calls of a model response, normalized in place so the
    message can be re-sent to the provider and saved in a trace.

    `None` arguments become an empty string, as LiteLLM itself does, so the call is
    answered as unparseable arguments. A call without a function name raises: it
    can't be answered or saved.
    """
    result = function_tool_calls(tool_calls)
    for tool_call in result:
        if tool_call.function.name is None:
            raise ValueError(
                "The model requested a tool call, without providing a function name (required)."
            )
        if tool_call.function.arguments is None:
            tool_call.function.arguments = ""
    return result
