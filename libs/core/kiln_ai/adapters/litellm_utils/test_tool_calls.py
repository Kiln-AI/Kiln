import pytest
from litellm.types.utils import (
    ChatCompletionMessageCustomToolCall,
    ChatCompletionMessageToolCall,
    Function,
)

from kiln_ai.adapters.litellm_utils.tool_calls import (
    MISSING_TOOL_NAME_ERROR,
    function_tool_calls,
    response_function_tool_calls,
)


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


@pytest.mark.parametrize(
    "arguments, expected",
    [
        pytest.param(None, "{}", id="null"),
        pytest.param("", "{}", id="empty"),
        pytest.param("   ", "{}", id="spaces"),
        pytest.param("\n\t", "{}", id="newline_and_tab"),
        pytest.param("{}", "{}", id="empty_object"),
        pytest.param('{"a": 1}', '{"a": 1}', id="json"),
        pytest.param(' {"a": 1} ', ' {"a": 1} ', id="json_with_padding"),
        pytest.param("{", "{", id="invalid_json"),
    ],
)
def test_response_function_tool_calls_normalizes_null_and_blank_arguments(
    arguments, expected
):
    call = _function_call()
    call.function.arguments = arguments

    assert response_function_tool_calls([call]) == [call]
    assert call.function.arguments == expected


def test_response_function_tool_calls_keeps_empty_name():
    call = _function_call()
    call.function.name = ""

    assert response_function_tool_calls([call]) == [call]
    assert call.function.name == ""


def test_response_function_tool_calls_rejects_missing_name():
    nameless = _function_call()
    nameless.function.name = None

    with pytest.raises(ValueError) as exc_info:
        response_function_tool_calls([_function_call(), nameless])
    assert str(exc_info.value) == MISSING_TOOL_NAME_ERROR


def test_response_function_tool_calls_rejects_custom_tool_call():
    custom = ChatCompletionMessageCustomToolCall(
        id="call_2",
        type="custom",
        custom={"name": "grammar_tool", "input": "x"},
    )
    with pytest.raises(ValueError, match="custom tool call"):
        response_function_tool_calls([custom])
