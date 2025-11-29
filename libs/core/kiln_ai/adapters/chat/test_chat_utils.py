import pytest

from kiln_ai.adapters.chat.chat_formatter import ToolCallMessage, ToolResponseMessage
from kiln_ai.adapters.chat.chat_utils import (
    build_tool_call_messages,
    extract_text_from_content,
)
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam


def assert_tool_call_message(
    msg: ToolCallMessage,
    expected_content: str | None,
    expected_tool_count: int,
    expected_tool_names: list[str] | None = None,
):
    assert isinstance(msg, ToolCallMessage)
    assert msg.role == "assistant"
    assert msg.content == expected_content
    assert len(msg.tool_calls) == expected_tool_count
    if expected_tool_names:
        for i, name in enumerate(expected_tool_names):
            assert msg.tool_calls[i]["function"]["name"] == name


def assert_tool_response_message(
    msg: ToolResponseMessage,
    expected_content: str,
    expected_tool_call_id: str,
):
    assert isinstance(msg, ToolResponseMessage)
    assert msg.role == "tool"
    assert msg.content == expected_content
    assert msg.tool_call_id == expected_tool_call_id


@pytest.mark.parametrize(
    "trace, expected_count",
    [
        (None, 0),  # no trace
        ([], 0),  # empty trace
        (
            [
                {"role": "system", "content": "You are a helpful assistant"},
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
            ],
            0,  # no tools
        ),
    ],
)
def test_build_tool_call_messages_returns_empty(
    trace: list[ChatCompletionMessageParam] | None, expected_count: int
):
    result = build_tool_call_messages(trace)
    assert len(result) == expected_count


def test_build_tool_call_messages_with_single_tool_call():
    trace: list[ChatCompletionMessageParam] = [
        {
            "role": "system",
            "content": "You are a calculator",
        },
        {
            "role": "user",
            "content": "What is 2+2?",
        },
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {
                        "name": "add",
                        "arguments": '{"a": 2, "b": 2}',
                    },
                }
            ],
        },
        {
            "role": "tool",
            "content": "4",
            "tool_call_id": "call_123",
        },
        {
            "role": "assistant",
            "content": "The answer is 4",
        },
    ]

    result = build_tool_call_messages(trace)

    assert len(result) == 2
    assert_tool_call_message(result[0], "", 1, ["add"])
    assert result[0].tool_calls[0]["id"] == "call_123"
    assert_tool_response_message(result[1], "4", "call_123")


def test_build_tool_call_messages_with_multiple_tool_calls():
    trace: list[ChatCompletionMessageParam] = [
        {
            "role": "system",
            "content": "You are a calculator",
        },
        {
            "role": "user",
            "content": "What's (18-6)/(3+3)?",
        },
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "subtract",
                        "arguments": '{"a": 18, "b": 6}',
                    },
                },
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {
                        "name": "add",
                        "arguments": '{"a": 3, "b": 3}',
                    },
                },
            ],
        },
        {
            "role": "tool",
            "content": "12",
            "tool_call_id": "call_1",
        },
        {
            "role": "tool",
            "content": "6",
            "tool_call_id": "call_2",
        },
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_3",
                    "type": "function",
                    "function": {
                        "name": "divide",
                        "arguments": '{"a": 12, "b": 6}',
                    },
                }
            ],
        },
        {
            "role": "tool",
            "content": "2.0",
            "tool_call_id": "call_3",
        },
        {
            "role": "assistant",
            "content": "The answer is 2.0",
        },
    ]

    result = build_tool_call_messages(trace)

    assert len(result) == 5
    assert_tool_call_message(result[0], "", 2, ["subtract", "add"])
    assert_tool_response_message(result[1], "12", "call_1")
    assert_tool_response_message(result[2], "6", "call_2")
    assert_tool_call_message(result[3], "", 1, ["divide"])
    assert_tool_response_message(result[4], "2.0", "call_3")


def test_build_tool_call_messages_with_none_content():
    trace: list[ChatCompletionMessageParam] = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_456",
                    "type": "function",
                    "function": {
                        "name": "test",
                        "arguments": "{}",
                    },
                }
            ],
        },
        {
            "role": "tool",
            "content": "result",
            "tool_call_id": "call_456",
        },
    ]

    result = build_tool_call_messages(trace)

    assert len(result) == 2
    assert_tool_call_message(result[0], None, 1, ["test"])
    assert_tool_response_message(result[1], "result", "call_456")


def test_build_tool_call_messages_raises_on_missing_tool_call_id():
    trace: list[ChatCompletionMessageParam] = [
        {
            "role": "tool",
            "content": "result",
        },
    ]

    with pytest.raises(ValueError, match="Tool call ID is required"):
        build_tool_call_messages(trace)


def test_build_tool_call_messages_raises_on_missing_content():
    trace: list[ChatCompletionMessageParam] = [
        {
            "role": "tool",
            "tool_call_id": "call_789",
        },
    ]

    with pytest.raises(ValueError, match="Content is required"):
        build_tool_call_messages(trace)


@pytest.mark.parametrize(
    "content, expected",
    [
        # string remains string
        ("Hello world", "Hello world"),
        (None, None),
        # Empty list becomes None
        ([], None),
        (
            [
                {"type": "text", "text": "The quick brown fox"},
                {
                    "type": "image",
                    "url": "should_be_ignored.jpg",
                },  # not text type, ignore
                {"type": "text", "text": " jumps over the lazy dog"},
            ],
            "The quick brown fox jumps over the lazy dog",
        ),
        (
            [
                {"type": "text"},  # no text value, ignored
                {"type": "text", "text": "Only this should appear"},
            ],
            "Only this should appear",
        ),
    ],
)
def test_extract_text_from_content(content, expected):
    assert extract_text_from_content(content) == expected
