from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Literal, Optional

from kiln_ai.datamodel.datamodel_enums import ChatStrategy
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error

COT_FINAL_ANSWER_PROMPT = "Considering the above, return a final result."


@dataclass
class ChatMessage:
    role: Literal["system", "assistant", "user"]
    content: Optional[str]


@dataclass
class ChatTurn:
    """
    All data needed to send a chat turn to the model.
    """

    messages: List[ChatMessage]
    final_call: bool


class ChatFormatter(ABC):
    def __init__(
        self,
        system_message: str,
        user_input: str | Dict,
        thinking_instructions: str | None = None,
    ) -> None:
        self.system_message = system_message
        self.user_input = user_input
        self.thinking_instructions = thinking_instructions
        self._messages: List[ChatMessage] = []
        self._state = "start"
        self._intermediate_outputs: Dict[str, str] = {}

    @property
    def messages(self) -> List[ChatMessage]:
        return list(self._messages)

    def message_dicts(self) -> List[dict[str, str | None]]:
        return [{"role": m.role, "content": m.content} for m in self._messages]

    def intermediate_outputs(self) -> Dict[str, str]:
        """Get the intermediate outputs from the chat formatter."""
        return self._intermediate_outputs

    @abstractmethod
    def next_turn(self, previous_output: str | None = None) -> Optional[ChatTurn]:
        """Advance the conversation and return the next messages if any."""
        raise NotImplementedError


class SingleTurnFormatter(ChatFormatter):
    def next_turn(self, previous_output: str | None = None) -> Optional[ChatTurn]:
        if self._state == "start":
            msgs = [
                ChatMessage("system", self.system_message),
                ChatMessage("user", format_user_message(self.user_input)),
            ]
            self._state = "awaiting_final"
            self._messages.extend(msgs)
            return ChatTurn(messages=msgs, final_call=True)

        if self._state == "awaiting_final":
            if previous_output is None:
                raise ValueError("previous_output required for final step")
            self._messages.append(ChatMessage("assistant", previous_output))
            self._state = "done"
            return None

        return None


class TwoMessageCotLegacyFormatter(ChatFormatter):
    def __init__(
        self,
        system_message: str,
        user_input: str | Dict,
        thinking_instructions: str | None,
    ) -> None:
        super().__init__(system_message, user_input, thinking_instructions)
        if self.thinking_instructions is None:
            raise ValueError(
                "thinking_instructions are required when strategy is final_and_intermediate"
            )

    def next_turn(self, previous_output: str | None = None) -> Optional[ChatTurn]:
        if self._state == "start":
            msgs = [
                ChatMessage("system", self.system_message),
                ChatMessage("user", format_user_message(self.user_input)),
                ChatMessage("system", self.thinking_instructions),
            ]
            self._state = "awaiting_thinking"
            self._messages.extend(msgs)
            return ChatTurn(messages=msgs, final_call=False)

        if self._state == "awaiting_thinking":
            if previous_output is None:
                raise ValueError("previous_output required for thinking step")
            self._intermediate_outputs["chain_of_thought"] = previous_output
            self._state = "awaiting_final"
            cot_message = ChatMessage("user", COT_FINAL_ANSWER_PROMPT)
            self._messages.append(ChatMessage("assistant", previous_output))
            self._messages.append(cot_message)
            return ChatTurn(messages=[cot_message], final_call=True)

        if self._state == "awaiting_final":
            if previous_output is None:
                raise ValueError("previous_output required for final step")
            self._messages.append(ChatMessage("assistant", previous_output))
            self._state = "done"
            return None

        return None


class TwoMessageCotFormatter(ChatFormatter):
    def __init__(
        self,
        system_message: str,
        user_input: str | Dict,
        thinking_instructions: str | None,
    ) -> None:
        super().__init__(system_message, user_input, thinking_instructions)
        if self.thinking_instructions is None:
            raise ValueError(
                "thinking_instructions are required when strategy is final_and_intermediate"
            )

    def next_turn(self, previous_output: str | None = None) -> Optional[ChatTurn]:
        if self._state == "start":
            # User message combines the input and the thinking instructions
            formatted_user_message = format_user_message(self.user_input)
            user_message = f"The input is:\n<user_input>\n{formatted_user_message}\n</user_input>\n\n{self.thinking_instructions}"

            msgs = [
                ChatMessage("system", self.system_message),
                ChatMessage("user", user_message),
            ]
            self._state = "awaiting_thinking"
            self._messages.extend(msgs)
            return ChatTurn(messages=msgs, final_call=False)

        if self._state == "awaiting_thinking":
            if previous_output is None:
                raise ValueError("previous_output required for thinking step")
            self._intermediate_outputs["chain_of_thought"] = previous_output
            self._state = "awaiting_final"
            self._messages.append(ChatMessage("assistant", previous_output))
            cot_message = ChatMessage("user", COT_FINAL_ANSWER_PROMPT)
            self._messages.append(cot_message)
            return ChatTurn(messages=[cot_message], final_call=True)

        if self._state == "awaiting_final":
            if previous_output is None:
                raise ValueError("previous_output required for final step")
            self._messages.append(ChatMessage("assistant", previous_output))
            self._state = "done"
            return None

        return None


class SingleTurnR1ThinkingFormatter(ChatFormatter):
    def next_turn(self, previous_output: str | None = None) -> Optional[ChatTurn]:
        if self._state == "start":
            msgs = [
                ChatMessage("system", self.system_message),
                ChatMessage("user", format_user_message(self.user_input)),
            ]
            self._state = "awaiting_final"
            self._messages.extend(msgs)
            return ChatTurn(messages=msgs, final_call=True)

        if self._state == "awaiting_final":
            if previous_output is None:
                raise ValueError("previous_output required for final step")
            self._messages.append(ChatMessage("assistant", previous_output))
            self._state = "done"
            return None

        return None


def get_chat_formatter(
    strategy: ChatStrategy,
    system_message: str,
    user_input: str | Dict,
    thinking_instructions: str | None = None,
) -> ChatFormatter:
    match strategy:
        case ChatStrategy.single_turn:
            return SingleTurnFormatter(system_message, user_input)
        case ChatStrategy.two_message_cot_legacy:
            return TwoMessageCotLegacyFormatter(
                system_message, user_input, thinking_instructions
            )
        case ChatStrategy.two_message_cot:
            return TwoMessageCotFormatter(
                system_message, user_input, thinking_instructions
            )
        case ChatStrategy.single_turn_r1_thinking:
            return SingleTurnR1ThinkingFormatter(system_message, user_input)
        case _:
            raise_exhaustive_enum_error(strategy)


def format_user_message(input: Dict | str) -> str:
    """Build a user message from the input.

    Args:
        input (Union[Dict, str]): The input to format into a message.

    Returns:
        str: The formatted user message.
    """
    if isinstance(input, dict):
        return json.dumps(input, ensure_ascii=False)

    return input
