from kiln_ai.adapters.chat import ChatStrategy, get_chat_formatter
from kiln_ai.adapters.chat.chat_formatter import (
    COT_FINAL_ANSWER_PROMPT,
    format_user_message,
)


def test_chat_formatter_final_only():
    expected = [
        {"role": "system", "content": "system message"},
        {"role": "user", "content": "test input"},
        {"role": "assistant", "content": "test output"},
    ]

    formatter = get_chat_formatter(
        strategy=ChatStrategy.single_turn,
        system_message="system message",
        user_input="test input",
    )

    first = formatter.next_turn()
    assert [m.__dict__ for m in first.messages] == expected[:2]
    assert first.final_call
    assert formatter.intermediate_outputs() == {}

    assert formatter.next_turn("test output") is None
    assert formatter.message_dicts() == expected
    assert formatter.intermediate_outputs() == {}


def test_chat_formatter_final_and_intermediate():
    expected = [
        {"role": "system", "content": "system message"},
        {"role": "user", "content": "test input"},
        {"role": "system", "content": "thinking instructions"},
        {"role": "assistant", "content": "thinking output"},
        {"role": "user", "content": COT_FINAL_ANSWER_PROMPT},
        {"role": "assistant", "content": "test output"},
    ]

    formatter = get_chat_formatter(
        strategy=ChatStrategy.two_message_cot_legacy,
        system_message="system message",
        user_input="test input",
        thinking_instructions="thinking instructions",
    )

    first = formatter.next_turn()
    assert first is not None
    assert [m.__dict__ for m in first.messages] == expected[:3]
    assert not first.final_call
    assert formatter.intermediate_outputs() == {}

    second = formatter.next_turn("thinking output")
    assert second is not None
    assert [m.__dict__ for m in second.messages] == expected[4:5]
    assert second.final_call
    assert formatter.intermediate_outputs() == {"chain_of_thought": "thinking output"}

    assert formatter.next_turn("test output") is None
    assert formatter.message_dicts() == expected
    assert formatter.intermediate_outputs() == {"chain_of_thought": "thinking output"}


def test_chat_formatter_two_message_cot():
    user_message = "The input is:\n<user_input>\ntest input\n</user_input>\n\nthinking instructions"
    expected = [
        {"role": "system", "content": "system message"},
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": "thinking output"},
        {"role": "user", "content": COT_FINAL_ANSWER_PROMPT},
        {"role": "assistant", "content": "test output"},
    ]

    formatter = get_chat_formatter(
        strategy=ChatStrategy.two_message_cot,
        system_message="system message",
        user_input="test input",
        thinking_instructions="thinking instructions",
    )

    first = formatter.next_turn()
    assert first is not None
    assert [m.__dict__ for m in first.messages] == expected[:2]
    assert not first.final_call
    assert formatter.intermediate_outputs() == {}

    second = formatter.next_turn("thinking output")
    assert second is not None
    assert [m.__dict__ for m in second.messages] == expected[3:4]
    assert second.final_call
    assert formatter.intermediate_outputs() == {"chain_of_thought": "thinking output"}

    assert formatter.next_turn("test output") is None
    assert formatter.message_dicts() == expected
    assert formatter.intermediate_outputs() == {"chain_of_thought": "thinking output"}


def test_chat_formatter_r1_style():
    thinking_output = "<think>thinking</think> answer"
    expected = [
        {"role": "system", "content": "system message"},
        {"role": "user", "content": "test input"},
        {"role": "assistant", "content": thinking_output},
    ]

    formatter = get_chat_formatter(
        strategy=ChatStrategy.single_turn_r1_thinking,
        system_message="system message",
        user_input="test input",
    )

    first = formatter.next_turn()
    assert [m.__dict__ for m in first.messages] == expected[:2]
    assert first.final_call

    assert formatter.next_turn(thinking_output) is None
    assert formatter.message_dicts() == expected
    assert formatter.intermediate_outputs() == {}


def test_format_user_message():
    # String
    assert format_user_message("test input") == "test input"
    # JSON, preserving order
    assert (
        format_user_message({"test": "input", "a": "b"})
        == '{"test": "input", "a": "b"}'
    )


def test_simple_prompt_builder_structured_input_non_ascii():
    input = {"key": "你好👋"}
    user_msg = format_user_message(input)
    assert "你好👋" in user_msg
