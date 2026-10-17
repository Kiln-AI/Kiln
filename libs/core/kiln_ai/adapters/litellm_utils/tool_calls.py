from typing import Sequence

from litellm.types.utils import (
    ChatCompletionMessageCustomToolCall,
    ChatCompletionMessageToolCall,
)

MISSING_TOOL_NAME_ERROR = (
    "The model requested a tool call, without providing a function name (required)."
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
    """Take the function tool calls from a model response, ready for the trace.

    Null arguments become "{}" (no arguments) on the calls themselves, so the
    response message that holds them can be stored in a trace and sent back to
    providers that parse arguments as JSON. Raises ValueError for a custom tool
    call, or for a call with no function name, which a trace can't store.
    """
    calls = function_tool_calls(tool_calls)
    for call in calls:
        if call.function.name is None:
            raise ValueError(MISSING_TOOL_NAME_ERROR)
        if call.function.arguments is None:
            call.function.arguments = "{}"
    return calls
