import json

from kiln_ai.datamodel.eval import EvalConfig, EvalDataType
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam


class EvalUtils:
    @staticmethod
    def additional_eval_data(
        eval_config: EvalConfig, trace: list[ChatCompletionMessageParam] | None
    ) -> tuple[str | None, list[str] | None]:
        """
        Get additional eval data besides just output (final answer) from a trace of chat completion messages. Returns a tuple of (full_trace, tool_call_list).
        """
        if not trace:
            return None, None

        parent_eval = eval_config.parent_eval()
        if not parent_eval:
            return None, None

        match parent_eval.evaluation_data_type:
            case EvalDataType.tool_call_list:
                tool_call_list = EvalUtils.called_tool_names_from_trace(trace)
                return None, tool_call_list
            case EvalDataType.full_trace:
                full_trace = json.dumps(trace, ensure_ascii=False)
                return full_trace, None
            case _:
                return None, None

    @staticmethod
    def called_tool_names_from_trace(
        trace: list[ChatCompletionMessageParam],
    ) -> list[str]:
        """Extract all tool names from a trace of chat completion messages."""
        tool_names = []

        # Filter for assistant messages with tool calls
        messages = [
            message
            for message in trace
            if message.get("role") == "assistant" and "tool_calls" in message
        ]

        # Extract tool names from the tool call functions
        for message in messages:
            tool_calls = message.get("tool_calls", [])
            for tool_call in tool_calls:
                tool_call_function = tool_call.get("function", {})
                tool_name = tool_call_function["name"]
                if tool_name and tool_name not in tool_names:
                    tool_names.append(tool_name)

        return tool_names
