import json
from typing import Any, Dict
from uuid import uuid4

from kiln_ai.adapters.fine_tune.dataset_format import DatasetFormat
from kiln_ai.datamodel import TaskRun
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam


class TraceBasedDatasetFormatter:
    """Generate dataset for training from a task run trace"""

    def __init__(
        self,
        system_message: str,
    ):
        self.system_message = system_message

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

    def _validate_json_dictionary(self, s: str, property_name: str) -> dict[str, Any]:
        """Validate if a string is valid JSON dictionary, raises ValueError if not"""
        try:
            json_data = json.loads(s)
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            raise ValueError(f"Invalid JSON: {e}")

        if not isinstance(json_data, dict):
            raise ValueError(
                f"{property_name} must be a dictionary object, got {type(json_data)}"
            )

        return json_data

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
                case "system":
                    # Use the supplied system message
                    chat_message = {
                        "role": "system",
                        "content": self.system_message,
                    }
                case "user":
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
            _ = self._validate_json_dictionary(content or "", "last message content")
        except ValueError as e:
            raise ValueError(
                f"Last message is not a JSON Dictionary (structured data), and this format expects structured_data: {e}"
            ) from e

        # The response is valid structured output. Put this into OpenAI format.
        return self.generate_openai_chat_message_response(trace)

    def generate_openai_toolcall_message(
        self,
        trace: list[ChatCompletionMessageParam],
    ) -> Dict[str, Any]:
        """Generate toolcall message from trace"""

        # Get last message
        last_message = trace[-1]
        # Remove last message from trace
        new_trace = trace[:-1]
        # Generate messages from trace without last message
        messages = self.generate_openai_chat_message_list(new_trace)
        # Get content of last message
        last_message_content = last_message.get("content", None)

        messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "task_response",
                            "arguments": last_message_content,  # pass a string directly
                        },
                    }
                ],
            },
        )

        return {"messages": messages}

    def generate_huggingface_chat_template(
        self,
        trace: list[ChatCompletionMessageParam],
    ) -> Dict[str, Any]:
        """Generate huggingface chat template message from trace"""
        messages = self.generate_openai_chat_message_list(trace)
        return {"conversations": messages}

    def generate_huggingface_chat_template_toolcall(
        self,
        trace: list[ChatCompletionMessageParam],
    ) -> Dict[str, Any]:
        """Generate huggingface chat template toolcall message from trace"""

        # Get last message
        last_message = trace[-1]
        # Remove last message from trace
        new_trace = trace[:-1]
        # Generate messages from trace without last message
        conversations = self.generate_openai_chat_message_list(new_trace)

        conversations.append(
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "task_response",
                            "id": str(uuid4()).replace("-", "")[:9],
                            "arguments": last_message,
                        },
                    }
                ],
            },
        )

        return {"conversations": conversations}

    def generate_vertex_gemini(
        self,
        trace: list[ChatCompletionMessageParam],
    ) -> Dict[str, Any]:
        """Generate vertex gemini message from trace"""
        # See https://cloud.google.com/vertex-ai/generative-ai/docs/models/tune-function-calling

        # Get the first system message
        system_msg = next((m for m in trace if m.get("role") == "system"), None)
        if not system_msg:
            raise ValueError("System message not found in trace")
        system_instruction = system_msg.get("content", "")

        contents: list[Dict[str, Any]] = []
        for message in trace[1:]:
            role = message["role"]
            current_function_name = None

            match role:
                case "system" | "user":
                    contents.append(
                        {
                            "role": role,
                            "parts": [{"text": message.get("content", None)}],
                        }
                    )
                case "assistant":
                    parts: list[dict[str, Any]] = []

                    if tool_calls := message.get("tool_calls"):
                        # every tool call is a single "part"
                        for tool_call in tool_calls:
                            arguments_str = tool_call["function"]["arguments"]
                            # arguments needs to be a JSON dictionary
                            arguments = self._validate_json_dictionary(
                                arguments_str, "tool call arguments"
                            )
                            current_function_name = tool_call["function"]["name"]
                            parts.append(
                                {
                                    "functionCall": {
                                        "name": current_function_name,
                                        "args": arguments,  # arguments are "args" in Vertex
                                    }
                                }
                            )
                    else:
                        # don't include text if there is a tool call
                        parts.append({"text": message.get("content", None)})

                    contents.append(
                        {
                            "role": "model",  # Vertex uses "model" for assistant role
                            "parts": parts,
                        }
                    )
                case "tool":
                    # tool role is "user" with "functionResponse" in Vertex
                    # response needs to be a dict
                    content = message.get("content", None)
                    if not isinstance(content, str):
                        raise ValueError(
                            f"Tool message content must be a string, got {type(content)}"
                        )
                    contents.append(
                        {
                            "role": "user",
                            "parts": [
                                {
                                    "functionResponse": {
                                        "name": current_function_name,
                                        "response": {
                                            "content": content,  # hardcode the content using 'content' key, Vertex expects 'response' to be a dict
                                        },
                                    },
                                }
                            ],
                        }
                    )

        return {
            "systemInstruction": {
                "role": "system",
                "parts": [
                    {
                        "text": system_instruction,
                    }
                ],
            },
            "contents": contents,
        }
