import pytest
from pydantic import ValidationError

from app.desktop.studio_server.ai_sdk_types import (
    ChatStreamRequestBody,
    UIMessage,
    UIMessagePart,
    extract_user_input_from_messages,
)


def test_extract_user_input_from_messages_last_user_message():
    messages = [
        UIMessage(
            id="1", role="assistant", parts=[UIMessagePart(type="text", text="Hi")]
        ),
        UIMessage(
            id="2",
            role="user",
            parts=[UIMessagePart(type="text", text="Hello world")],
        ),
    ]
    assert extract_user_input_from_messages(messages) == "Hello world"


def test_extract_user_input_from_messages_multiple_text_parts():
    messages = [
        UIMessage(
            id="1",
            role="user",
            parts=[
                UIMessagePart(type="text", text="Part one"),
                UIMessagePart(type="text", text="Part two"),
            ],
        ),
    ]
    assert extract_user_input_from_messages(messages) == "Part one Part two"


def test_extract_user_input_from_messages_empty():
    assert extract_user_input_from_messages([]) == ""


def test_extract_user_input_from_messages_no_user():
    messages = [
        UIMessage(
            id="1", role="assistant", parts=[UIMessagePart(type="text", text="Hi")]
        ),
    ]
    assert extract_user_input_from_messages(messages) == ""


def test_chat_stream_request_body_input():
    body = ChatStreamRequestBody(input="hello")
    assert body.input == "hello"
    assert body.messages is None


def test_chat_stream_request_body_messages():
    body = ChatStreamRequestBody(
        messages=[
            UIMessage(
                id="1", role="user", parts=[UIMessagePart(type="text", text="hi")]
            ),
        ]
    )
    assert body.messages is not None
    assert len(body.messages) == 1
    assert body.input is None


def test_chat_stream_request_body_neither():
    with pytest.raises(ValidationError):
        ChatStreamRequestBody()


def test_chat_stream_request_body_both():
    with pytest.raises(ValidationError):
        ChatStreamRequestBody(
            input="hello",
            messages=[
                UIMessage(
                    id="1", role="user", parts=[UIMessagePart(type="text", text="hi")]
                )
            ],
        )
