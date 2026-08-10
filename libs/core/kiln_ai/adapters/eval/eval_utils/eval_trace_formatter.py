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
        """Convert a trace of chat completion messages to a formatted conversation history string.

        One message can carry several things at once — an assistant commonly
        replies with visible text AND requests tool calls in the same message.
        Each is rendered as its own block, in the order the model produced them
        (the text, then the calls it announced). Rendering only one of them
        hides real behavior from everything that reads this transcript.

        Reasoning content is deliberately not rendered: it is model-internal,
        not part of the observable behavior a transcript is read to judge.
        MessageDetails still parses it for callers that want it.
        """
        blocks: list[str] = []
        for message in trace:
            message_details = EvalTraceFormatter.message_details_from_message(message)
            role = message_details.role

            if role == "tool" and message_details.content:
                origin_tool_call_name = (
                    EvalTraceFormatter.origin_tool_call_name_from_message(
                        message, trace
                    )
                )

                # A tool result we can't trace back to its call is scaffolding
                # without an author, so it is left out entirely.
                if origin_tool_call_name:
                    blocks.append(
                        EvalTraceFormatter.format_message(
                            role,
                            f"{role}_tool_message",
                            message_details.content,
                        )
                    )

            else:
                if message_details.content:
                    blocks.append(
                        EvalTraceFormatter.format_message(
                            role,
                            f"{role}_message",
                            message_details.content,
                        )
                    )

                if message_details.tool_calls:
                    blocks.append(
                        EvalTraceFormatter.format_message(
                            f"{role} requested tool calls",
                            f"{role}_requested_tool_calls",
                            message_details.tool_calls,
                        )
                    )

        return "\n\n".join(blocks)

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

        # Parallel tool calls each get their own line pair. Without the
        # separator the last argument of one call runs straight into the name
        # of the next, which reads as a single mangled call.
        tool_call_descriptions: list[str] = []
        for tool_call in tool_calls:
            tool_call_function = tool_call["function"]
            tool_name = tool_call_function["name"]
            tool_call_arguments = tool_call_function["arguments"]
            tool_call_descriptions.append(
                f"- Tool Name: {tool_name}\n- Arguments: {tool_call_arguments}"
            )
        return "\n".join(tool_call_descriptions)

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
