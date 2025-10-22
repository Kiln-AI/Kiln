import json
from typing import Any, Dict

from kiln_ai.adapters.fine_tune.dataset_format import DatasetFormat
from kiln_ai.datamodel import TaskRun
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam


class TraceBasedDatasetFormatter:
    """Generate dataset for training from a task run trace"""

    def build_training_chat_from_trace(
        self,
        task_run: TaskRun,
        data_format: DatasetFormat,
    ) -> Dict[str, Any]:
        # Check if trace is available
        trace = task_run.trace
        if not trace:
            raise ValueError("Trace is required")

        # Generate training message based on data format
        match data_format:
            case DatasetFormat.OPENAI_CHAT_JSONL:
                return self.generate_openai_chat_message_response(trace)
            case DatasetFormat.OPENAI_CHAT_JSON_SCHEMA_JSONL:
                return self.generate_openai_json_schema_message(trace)
            case DatasetFormat.OPENAI_CHAT_TOOLCALL_JSONL:
                return self.generate_openai_toolcall_message(trace)
            case DatasetFormat.HUGGINGFACE_CHAT_TEMPLATE_JSONL:
                return self.generate_huggingface_chat_template(trace)
            case DatasetFormat.HUGGINGFACE_CHAT_TEMPLATE_TOOLCALL_JSONL:
                return self.generate_huggingface_chat_template_toolcall(trace)
            case DatasetFormat.VERTEX_GEMINI:
                return self.generate_vertex_gemini(trace)
            case _:
                raise ValueError(f"Unsupported data format: {data_format}")

    # Helpers

    def generate_openai_chat_message_list(
        self,
        trace: list[ChatCompletionMessageParam],
    ) -> list[dict[str, Any]]:
        """Generate OpenAI chat message list from trace"""
        messages = []

        # Reference to https://platform.openai.com/docs/api-reference/fine-tuning/chat-input

        for message in trace:
            role = message["role"]
            chat_message = {}

            match role:
                case "system" | "user":
                    chat_message = {
                        "role": role,
                        "content": message.get("content", None),
                    }
                case "assistant":
                    chat_message = {
                        "role": role,
                        "content": message.get("content", None),
                    }
                    # Add tool_calls if available
                    if message.get("tool_calls", None):
                        chat_message["tool_calls"] = message.get("tool_calls", None)
                case "tool":
                    chat_message = {
                        "role": role,
                        "content": message.get("content", None),
                        "tool_call_id": message.get("tool_call_id", None),
                    }
                case _:
                    # Skip unsupported traces types
                    continue

            messages.append(chat_message)

        return messages

    # Individual generators

    def generate_openai_chat_message_response(
        self,
        trace: list[ChatCompletionMessageParam],
    ) -> Dict[str, Any]:
        """Generate openai chat message list from trace"""
        messages = self.generate_openai_chat_message_list(trace)
        return {"messages": messages}

    def generate_openai_json_schema_message(
        self,
        trace: list[ChatCompletionMessageParam],
    ) -> Dict[str, Any]:
        """
        Generate json schema message from trace.
        This mode checks if the answer (last assistant message) is a valid JSON structured output
        """

        last_message = trace[-1]
        content = last_message.get("content", "")
        if not isinstance(content, str):
            raise ValueError(
                "assistant message content must be a string for JSON validation"
            )

        try:
            json_data = json.loads(content or "")
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Last message is not JSON (structured), and this format expects structured data: {e}"
            )

        if not isinstance(json_data, dict):
            raise ValueError(
                "Last message is not a JSON Dictionary (structured data), and this format expects structured_data."
            )

        # The response is valid structured output. Put this into OpenAI format.
        return self.generate_openai_chat_message_response(trace)

    def generate_openai_toolcall_message(
        self,
        trace: list[ChatCompletionMessageParam],
    ) -> Dict[str, Any]:
        """Generate toolcall message from trace"""
        return {}

    def generate_huggingface_chat_template(
        self,
        trace: list[ChatCompletionMessageParam],
    ) -> Dict[str, Any]:
        """Generate huggingface chat template message from trace"""
        return {}

    def generate_huggingface_chat_template_toolcall(
        self,
        trace: list[ChatCompletionMessageParam],
    ) -> Dict[str, Any]:
        """Generate huggingface chat template toolcall message from trace"""
        return {}

    def generate_vertex_gemini(
        self,
        trace: list[ChatCompletionMessageParam],
    ) -> Dict[str, Any]:
        """Generate vertex gemini message from trace"""
        return {}
