import json
from dataclasses import dataclass

from openai.types.chat import ChatCompletionMessageToolCallParam

from kiln_ai.datamodel import TaskRun
from kiln_ai.tools.tool_registry import tool_from_id
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam


class EvalUtils:
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

            message_details = EvalUtils.message_details_from_message(message)

            if message_details.role == "tool":
                origin_tool_call_name = EvalUtils.origin_tool_call_name_from_message(
                    message, trace
                )
                conversation_history += f"{message_details.role} - {origin_tool_call_name}: {message_details.content}"
            else:
                # TODO: reasoning content doesn't seem to be working as expected
                if message_details.reasoning_content:
                    conversation_history += f"{message_details.role} - reasoning: {message_details.reasoning_content}"
                if message_details.tool_calls:
                    conversation_history += f"{message_details.role} - requested tool calls: {message_details.tool_calls}"
                if message_details.content:
                    conversation_history += (
                        f"{message_details.role}: {message_details.content}"
                    )
        return conversation_history

    @staticmethod
    def message_details_from_message(
        message: ChatCompletionMessageParam,
    ) -> MessageDetails:
        return EvalUtils.MessageDetails(
            role=EvalUtils.role_from_message(message),
            reasoning_content=EvalUtils.reasoning_content_from_message(message),
            tool_calls=EvalUtils.formatted_tool_calls_from_message(message),
            content=EvalUtils.content_from_message(message),
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
        tool_calls = EvalUtils.tool_calls_from_message(message)
        if tool_calls is None:
            return None

        tool_calls_description = ""
        for tool_call in tool_calls:
            tool_call_function = tool_call["function"]
            tool_name = tool_call_function["name"]
            tool_call_arguments = tool_call_function["arguments"]
            tool_calls_description += (
                f"\n- Tool Name: {tool_name}\n- Arguments: {tool_call_arguments}"
            )
        return tool_calls_description

    @staticmethod
    def origin_tool_call_name_from_message(
        tool_message: ChatCompletionMessageParam,
        trace: list[ChatCompletionMessageParam],
    ) -> str | None:
        tool_call_id = tool_message.get("tool_call_id")
        if not tool_call_id:
            return None
        for message in trace:
            tool_calls = EvalUtils.tool_calls_from_message(message)
            if tool_calls:
                for tool_call in tool_calls:
                    if tool_call["id"] == tool_call_id:
                        return tool_call["function"]["name"]
        return None

    @staticmethod
    async def formatted_available_tools_from_task_run(task_run: TaskRun) -> str | None:
        if (
            not task_run.parent_task()
            or not task_run.output.source
            or not task_run.output.source.run_config
            or not task_run.output.source.run_config.tools_config
        ):
            return None

        available_tools = task_run.output.source.run_config.tools_config.tools
        if not available_tools:
            return ""

        available_tools_description = ""

        for tool in available_tools:
            tool_object = tool_from_id(tool, task_run.parent_task())
            try:
                tool_definition = await tool_object.toolcall_definition()
                tool_name = tool_definition["function"]["name"]
                tool_description = tool_definition["function"]["description"]
                available_tools_description += f"\n- Tool Name: {tool_name}\n- Tool Description: {tool_description}"
            except Exception:
                continue

        return available_tools_description
