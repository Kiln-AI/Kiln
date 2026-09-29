import pytest
from litellm.types.utils import (
    ChatCompletionMessageCustomToolCall,
    ChatCompletionMessageToolCall,
    Function,
)

from kiln_ai.adapters.litellm_utils.tool_calls import function_tool_calls


def _function_call() -> ChatCompletionMessageToolCall:
    return ChatCompletionMessageToolCall(
        id="call_1",
        type="function",
        function=Function(name="add", arguments="{}"),
    )


def test_function_tool_calls_none_and_empty():
    assert function_tool_calls(None) == []
    assert function_tool_calls([]) == []


def test_function_tool_calls_returns_function_calls():
    call = _function_call()
    assert function_tool_calls([call]) == [call]


def test_function_tool_calls_rejects_custom_tool_call():
    custom = ChatCompletionMessageCustomToolCall(
        id="call_2",
        type="custom",
        custom={"name": "grammar_tool", "input": "x"},
    )
    with pytest.raises(ValueError, match="custom tool call"):
        function_tool_calls([_function_call(), custom])
