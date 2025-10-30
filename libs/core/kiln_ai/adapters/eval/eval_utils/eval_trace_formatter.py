import json
import logging
from dataclasses import dataclass

from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam
from openai.types.chat import ChatCompletionMessageToolCallParam

logger = logging.getLogger(__name__)


class EvalTraceFormatter:
    @dataclass
    class MessageDetails:
        role: str
        reasoning_content: str | None
        tool_calls: str | None
        content: str | None

    @staticmethod
    def trace_to_formatted_conversation_history(
        trace: list[ChatCompletionMessageParam],
    ) -> str:
        """Convert a trace of chat completion messages to a formatted conversation history string."""
        conversation_history = ""
        for index, message in enumerate(trace):
            if index > 0:
                conversation_history += "\n\n"

            message_details = EvalTraceFormatter.message_details_from_message(message)

            if message_details.role == "tool" and message_details.content:
                origin_tool_call_name = (
                    EvalTraceFormatter.origin_tool_call_name_from_message(
                        message, trace
                    )
                )
                if origin_tool_call_name:
                    conversation_history += EvalTraceFormatter.format_message(
                        message_details.role,
                        origin_tool_call_name,
                        message_details.content,
                    )
            else:
                if message_details.reasoning_content:
                    role_label = f"{message_details.role} reasoning"
                    tag = f"{message_details.role}_reasoning_message"
                    conversation_history += EvalTraceFormatter.format_message(
                        role_label, tag, message_details.reasoning_content
                    )
                if message_details.tool_calls:
                    role_label = f"{message_details.role} requested tool calls"
                    tag = f"{message_details.role}_requested_tool_calls"
                    conversation_history += EvalTraceFormatter.format_message(
                        role_label, tag, message_details.tool_calls
                    )
                if message_details.content:
                    tag = f"{message_details.role}_message"
                    conversation_history += EvalTraceFormatter.format_message(
                        message_details.role, tag, message_details.content
                    )
        return conversation_history

    @staticmethod
    def format_message(role_label: str, tag: str, content: str) -> str:
        return f"{role_label}:\n<{tag}>\n{content}\n</{tag}>"

    @staticmethod
    def message_details_from_message(
        message: ChatCompletionMessageParam,
    ) -> MessageDetails:
        return EvalTraceFormatter.MessageDetails(
            role=EvalTraceFormatter.role_from_message(message),
            reasoning_content=EvalTraceFormatter.reasoning_content_from_message(
                message
            ),
            tool_calls=EvalTraceFormatter.formatted_tool_calls_from_message(message),
            content=EvalTraceFormatter.content_from_message(message),
        )

    @staticmethod
    def role_from_message(message: ChatCompletionMessageParam) -> str:
        return message["role"]

    @staticmethod
    def content_from_message(message: ChatCompletionMessageParam) -> str | None:
        """Get the content of a message."""
        if (
            "content" not in message
            or message["content"] is None
            or not isinstance(message["content"], str)
        ):
            return None

        # For Kiln task tools, extract just the output field from the JSON response
        if message["role"] == "tool":
            try:
                parsed = json.loads(message["content"])
                if parsed and isinstance(parsed, dict) and "output" in parsed:
                    return parsed["output"]
            except Exception:
                # Content is not JSON, we will return as-is
                pass

        return message["content"]

    @staticmethod
    def reasoning_content_from_message(
        message: ChatCompletionMessageParam,
    ) -> str | None:
        if (
            "reasoning_content" not in message
            or message["reasoning_content"] is None
            or not isinstance(message["reasoning_content"], str)
        ):
            return None

        return message["reasoning_content"]

    @staticmethod
    def tool_calls_from_message(
        message: ChatCompletionMessageParam,
    ) -> list[ChatCompletionMessageToolCallParam] | None:
        tool_calls = message.get("tool_calls")
        return tool_calls if tool_calls else None

    @staticmethod
    def formatted_tool_calls_from_message(
        message: ChatCompletionMessageParam,
    ) -> str | None:
        tool_calls = EvalTraceFormatter.tool_calls_from_message(message)
        if tool_calls is None:
            return None

        tool_calls_description = ""
        for tool_call in tool_calls:
            tool_call_function = tool_call["function"]
            tool_name = tool_call_function["name"]
            tool_call_arguments = tool_call_function["arguments"]
            tool_calls_description += (
                f"- Tool Name: {tool_name}\n- Arguments: {tool_call_arguments}"
            )
        return tool_calls_description

    @staticmethod
    def origin_tool_call_name_from_message(
        message: ChatCompletionMessageParam,
        trace: list[ChatCompletionMessageParam],
    ) -> str | None:
        tool_call_id = message.get("tool_call_id")
        if not tool_call_id:
            return None
        for msg in trace:
            tool_calls = EvalTraceFormatter.tool_calls_from_message(msg)
            if tool_calls:
                for tool_call in tool_calls:
                    if tool_call["id"] == tool_call_id:
                        return tool_call["function"]["name"]
        logger.error(
            f"Origin tool call name not found for tool_call_id: {tool_call_id}"
        )
        return None
