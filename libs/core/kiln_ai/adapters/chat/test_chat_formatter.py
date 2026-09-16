from kiln_ai.adapters.chat import ChatStrategy, get_chat_formatter
from kiln_ai.adapters.chat.chat_formatter import (
    COT_FINAL_ANSWER_PROMPT,
    MultiturnFormatter,
    SingleTurnR1ThinkingFormatter,
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


def test_multiturn_formatter_initial_messages():
    prior_trace = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    formatter = MultiturnFormatter(prior_trace=prior_trace, user_input="new input")
    assert formatter.initial_messages() == prior_trace


def test_multiturn_formatter_next_turn():
    prior_trace = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    formatter = MultiturnFormatter(prior_trace=prior_trace, user_input="follow-up")

    first = formatter.next_turn()
    assert first is not None
    assert len(first.messages) == 1
    assert first.messages[0].role == "user"
    assert first.messages[0].content == "follow-up"
    assert first.final_call

    assert formatter.next_turn("assistant response") is None


def test_multiturn_formatter_preserves_tool_call_messages():
    prior_trace = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "4"},
        {
            "role": "assistant",
            "content": "",
            "reasoning_content": "Let me multiply 4 by 7.\n",
            "tool_calls": [
                {
                    "id": "call_abc123",
                    "function": {"arguments": '{"a": 4, "b": 7}', "name": "multiply"},
                    "type": "function",
                }
            ],
        },
        {
            "content": "28",
            "role": "tool",
            "tool_call_id": "call_abc123",
            "kiln_task_tool_data": None,
        },
        {
            "role": "assistant",
            "content": "4 multiplied by 7 is 28.",
            "reasoning_content": "Done.\n",
        },
    ]
    formatter = MultiturnFormatter(prior_trace=prior_trace, user_input="now double it")
    initial = formatter.initial_messages()
    assert initial == prior_trace
    assert initial[2]["tool_calls"][0]["id"] == "call_abc123"
    assert initial[2]["tool_calls"][0]["function"]["name"] == "multiply"
    assert initial[3]["role"] == "tool"
    assert initial[3]["tool_call_id"] == "call_abc123"

    first = formatter.next_turn()
    assert first is not None
    assert len(first.messages) == 1
    assert first.messages[0].role == "user"
    assert first.messages[0].content == "now double it"
    assert first.final_call


def test_multiturn_formatter_single_tool_result():
    """Tool result dict with tool_call_id should produce a ToolResponseMessage."""
    prior_trace = [
        {"role": "assistant", "content": None, "tool_calls": [{"id": "call_1"}]},
    ]
    formatter = MultiturnFormatter(
        prior_trace=prior_trace,
        user_input={"tool_call_id": "call_1", "content": "42"},
    )

    first = formatter.next_turn()
    assert first is not None
    assert len(first.messages) == 1
    msg = first.messages[0]
    assert msg.role == "tool"
    assert msg.content == "42"
    assert msg.tool_call_id == "call_1"
    assert first.final_call


def test_multiturn_formatter_multiple_tool_results():
    """List of tool result dicts should produce multiple ToolResponseMessages."""
    prior_trace = [
        {"role": "assistant", "content": None, "tool_calls": []},
    ]
    tool_results = [
        {"tool_call_id": "call_1", "content": "15"},
        {"tool_call_id": "call_2", "content": "36"},
    ]
    formatter = MultiturnFormatter(prior_trace=prior_trace, user_input=tool_results)

    first = formatter.next_turn()
    assert first is not None
    assert len(first.messages) == 2
    assert first.messages[0].role == "tool"
    assert first.messages[0].tool_call_id == "call_1"
    assert first.messages[0].content == "15"
    assert first.messages[1].role == "tool"
    assert first.messages[1].tool_call_id == "call_2"
    assert first.messages[1].content == "36"
    assert first.final_call


def test_multiturn_formatter_user_input_not_confused_with_tool_result():
    """A regular dict input (no tool_call_id) is treated as a user message."""
    prior_trace = [{"role": "system", "content": "sys"}]
    formatter = MultiturnFormatter(
        prior_trace=prior_trace,
        user_input={"question": "what is 2+2?"},
    )
    first = formatter.next_turn()
    assert first is not None
    assert len(first.messages) == 1
    assert first.messages[0].role == "user"


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


# ── SingleTurnR1ThinkingFormatter: forward_thinking_instructions ──────


def test_r1_thinking_forward_true():
    """forward_thinking_instructions=True wraps plain input in <user_input> tags."""
    f = SingleTurnR1ThinkingFormatter(
        system_message="sys",
        user_input="hello",
        thinking_instructions="Think carefully.",
        forward_thinking_instructions=True,
    )
    turn = f.next_turn()
    assert turn is not None
    user_msg = turn.messages[1].content
    assert "<user_input>" in user_msg
    assert "hello" in user_msg
    assert "Think carefully." in user_msg


def test_r1_thinking_forward_false_default():
    """Default forward_thinking_instructions=False drops thinking_instructions."""
    f = SingleTurnR1ThinkingFormatter(
        system_message="sys",
        user_input="hello",
        thinking_instructions="Think carefully.",
        forward_thinking_instructions=False,
    )
    import warnings

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        turn = f.next_turn()
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
        assert "forward_thinking_instructions" in str(w[0].message)
    assert turn is not None
    user_msg = turn.messages[1].content
    assert user_msg == "hello"
    assert "Think carefully." not in user_msg


def test_r1_thinking_forward_conversation_history():
    """When formatted contains <conversation_history>, no <user_input> wrapper is added."""
    input_with_history = (
        "<conversation_history>prior chat</conversation_history>\nWhat now?"
    )
    f = SingleTurnR1ThinkingFormatter(
        system_message="sys",
        user_input=input_with_history,
        thinking_instructions="Evaluate quality.",
        forward_thinking_instructions=True,
    )
    turn = f.next_turn()
    assert turn is not None
    user_msg = turn.messages[1].content
    assert "<user_input>" not in user_msg
    assert "<conversation_history>" in user_msg
    assert "Evaluate quality." in user_msg


def test_r1_thinking_forward_no_instructions():
    """When thinking_instructions is None, user_input is used as-is regardless of flag."""
    f = SingleTurnR1ThinkingFormatter(
        system_message="sys",
        user_input="plain",
        thinking_instructions=None,
        forward_thinking_instructions=True,
    )
    turn = f.next_turn()
    assert turn is not None
    user_msg = turn.messages[1].content
    assert user_msg == "plain"


def test_r1_thinking_deprecation_warning():
    """Deprecation warning fires when thinking_instructions present but forward=False."""
    import warnings

    f = SingleTurnR1ThinkingFormatter(
        system_message="sys",
        user_input="input",
        thinking_instructions="instructions",
        forward_thinking_instructions=False,
    )
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        f.next_turn()
        assert any(issubclass(x.category, DeprecationWarning) for x in w)


def test_get_chat_formatter_r1_passes_thinking_instructions():
    """get_chat_formatter passes forward_thinking_instructions to R1 formatter."""
    from kiln_ai.adapters.chat import ChatStrategy

    formatter = get_chat_formatter(
        strategy=ChatStrategy.single_turn_r1_thinking,
        system_message="sys",
        user_input="test",
        thinking_instructions="Think.",
        forward_thinking_instructions=True,
    )
    assert isinstance(formatter, SingleTurnR1ThinkingFormatter)
    assert formatter.forward_thinking_instructions is True
    turn = formatter.next_turn()
    assert turn is not None
    assert "Think." in turn.messages[1].content
