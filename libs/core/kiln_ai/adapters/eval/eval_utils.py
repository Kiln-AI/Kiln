from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam


class EvalUtils:
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
                tool_name = tool_call["function"]["name"]
                if tool_name not in tool_names:
                    tool_names.append(tool_name)

        return tool_names
