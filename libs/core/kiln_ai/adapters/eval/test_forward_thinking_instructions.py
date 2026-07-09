"""Tests for forward_thinking_instructions plumbing.

Verifies that AdapterConfig.forward_thinking_instructions propagates
through build_chat_formatter and get_chat_formatter into the
SingleTurnR1ThinkingFormatter.
"""

import warnings

from kiln_ai.adapters.chat.chat_formatter import (
    ChatStrategy,
    SingleTurnR1ThinkingFormatter,
    get_chat_formatter,
)
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig


class TestAdapterConfigForwardThinking:
    def test_forward_thinking_default_false(self):
        cfg = AdapterConfig()
        assert cfg.forward_thinking_instructions is False

    def test_forward_thinking_set_true(self):
        cfg = AdapterConfig(forward_thinking_instructions=True)
        assert cfg.forward_thinking_instructions is True


class TestGetChatFormatterForRunForwardThinking:
    def test_reasoning_model_forwards_thinking_when_true(self):
        thinking = "Think step by step about correctness."
        formatter = get_chat_formatter(
            strategy=ChatStrategy.single_turn_r1_thinking,
            system_message="You are a judge.",
            user_input="Hello world",
            thinking_instructions=thinking,
            forward_thinking_instructions=True,
        )
        assert isinstance(formatter, SingleTurnR1ThinkingFormatter)
        assert formatter.forward_thinking_instructions is True

        turn = formatter.next_turn(previous_output=None)
        assert turn is not None
        user_msg = turn.messages[-1]
        assert thinking in user_msg.content

    def test_reasoning_model_does_not_forward_when_false(self):
        thinking = "Think step by step about correctness."
        formatter = get_chat_formatter(
            strategy=ChatStrategy.single_turn_r1_thinking,
            system_message="You are a judge.",
            user_input="Hello world",
            thinking_instructions=thinking,
            forward_thinking_instructions=False,
        )
        assert isinstance(formatter, SingleTurnR1ThinkingFormatter)
        assert formatter.forward_thinking_instructions is False

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            turn = formatter.next_turn(previous_output=None)
        assert turn is not None
        user_msg = turn.messages[-1]
        assert thinking not in user_msg.content
        assert any(issubclass(x.category, DeprecationWarning) for x in w)
