import json
from typing import Any, Dict
from uuid import uuid4

from kiln_ai.adapters.fine_tune.dataset_format import DatasetFormat
from kiln_ai.datamodel import TaskRun
from kiln_ai.tools.base_tool import ToolCallDefinition
from kiln_ai.tools.tool_registry import tool_definitions_from_ids
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam


class TraceBasedDatasetFormatter:
    """Generate dataset for training from a task run trace"""

    def __init__(
        self,
        system_message: str,
    ):
        self.system_message = system_message

    async def build_training_chat_from_trace(
        self,
        task_run: TaskRun,
        data_format: DatasetFormat,
    ) -> Dict[str, Any]:
        # Check if trace is available
        trace = task_run.trace
        if not trace:
            raise ValueError("Trace is required")

        # Get the tool definitions from the task run config
        tool_definitions = await self._get_tool_definitions_from_config(task_run)

        # Generate training message based on data format
        match data_format:
            case DatasetFormat.OPENAI_CHAT_JSONL:
                return self.generate_openai_chat_message_response(
                    trace, tool_definitions
                )
            case DatasetFormat.OPENAI_CHAT_JSON_SCHEMA_JSONL:
                return self.generate_openai_json_schema_message(trace, tool_definitions)
            case DatasetFormat.OPENAI_CHAT_TOOLCALL_JSONL:
                return self.generate_openai_toolcall_message(trace, tool_definitions)
            case DatasetFormat.HUGGINGFACE_CHAT_TEMPLATE_JSONL:
                return self.generate_huggingface_chat_template(trace)
            case DatasetFormat.HUGGINGFACE_CHAT_TEMPLATE_TOOLCALL_JSONL:
                return self.generate_huggingface_chat_template_toolcall(trace)
            case DatasetFormat.VERTEX_GEMINI:
                return self.generate_vertex_gemini(trace)
            case _:
                raise ValueError(f"Unsupported data format: {data_format}")

    # Helpers

    async def _get_tool_definitions_from_config(
        self,
        task_run: TaskRun,
    ) -> list[ToolCallDefinition] | None:
        """Extract tool definitions from task run config"""
        if not task_run.output.source:
            return None

        run_config = task_run.output.source.run_config
        if not run_config:
            return None

        tools_config = run_config.tools_config
        if not tools_config or not tools_config.tools:
            return None

        task = task_run.parent_task()
        if task is None:
            return None

        tool_definitions = await tool_definitions_from_ids(tools_config.tools, task)
        return tool_definitions

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
        tools: list[ToolCallDefinition] | None = None,
    ) -> Dict[str, Any]:
        """Generate openai chat message list from trace"""
        messages = self.generate_openai_chat_message_list(trace)
        result: Dict[str, Any] = {"messages": messages}

        if tools:
            result["tools"] = tools

        return result

    def generate_openai_json_schema_message(
        self,
        trace: list[ChatCompletionMessageParam],
        tools: list[ToolCallDefinition] | None = None,
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
        return self.generate_openai_chat_message_response(trace, tools)

    def generate_openai_toolcall_message(
        self,
        trace: list[ChatCompletionMessageParam],
        tools: list[ToolCallDefinition] | None = None,
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

        result: Dict[str, Any] = {"messages": messages}

        if tools:
            result["tools"] = tools

        return result

    def generate_huggingface_chat_template(
        self,
        trace: list[ChatCompletionMessageParam],
    ) -> Dict[str, Any]:
        """Generate huggingface chat template message from trace"""

        # See https://huggingface.co/docs/transformers/en/chat_templating

        conversations = self.generate_openai_chat_message_list(trace)
        return {"conversations": conversations}

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
        # Get content of last message
        last_message_content = last_message.get("content", None)

        conversations.append(
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "task_response",
                            "id": str(uuid4()).replace("-", "")[:9],
                            "arguments": last_message_content,
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

        contents: list[Dict[str, Any]] = []
        # keep track of the function name by tool call id
        call_name_by_id: dict[str, str] = {}

        """        
        Store consecutive tool responses
        OpenAI format expects tool responses to be in separate tool role messages
        #Vertex expects all tool responses from a single assistant message to be in the same list.

        OpenAI:
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_m91m9tVSGZlOjlGX5ueUXMUX",
                            "function": {
                                "arguments": '{"a": 18, "b": 6}',
                                "name": "subtract",
                            },
                            "type": "function",
                        },
                        {
                            "id": "call_Yc2l2die7FDuMcjwZ46vjd9A",
                            "function": {
                                "arguments": '{"a": 3, "b": 3}',
                                "name": "add",
                            },
                            "type": "function",
                        },
                    ],
                },
                {
                    "role": "tool",
                    "content": "12",
                    "tool_call_id": "call_m91m9tVSGZlOjlGX5ueUXMUX",
                },
                {
                    "role": "tool",
                    "content": "6",
                    "tool_call_id": "call_Yc2l2die7FDuMcjwZ46vjd9A",
                },

        Vertex: 
                {
                    "role": "user",
                    "parts": [{"text": "What's the result of (18 - 6) / (3 + 3)"}],
                },
                {
                    "role": "model",
                    "parts": [
                        {
                            "functionCall": {
                                "name": "subtract",
                                "args": {"a": 18, "b": 6},
                            }
                        },
                        {
                            "functionCall": {
                                "name": "add",
                                "args": {"a": 3, "b": 3},
                            }
                        },
                    ],
                },
                {   # Here is the difference in formatting, all tool responses are in the same list.
                    "parts": [
                        {
                            "functionResponse": {
                                "name": "subtract",
                                "response": {"content": "12"},
                            }
                        },
                        {
                            "functionResponse": {
                                "name": "add",
                                "response": {"content": "6"},
                            }
                        },
                    ],
                },
        """
        tool_response_parts: list[dict[str, Any]] = []

        def flush_tool_responses() -> None:
            """Helper to flush buffered tool responses into contents"""
            nonlocal tool_response_parts
            if tool_response_parts:
                contents.append({"parts": tool_response_parts})
                tool_response_parts = []

        for message in trace[1:]:
            role = message["role"]
            current_function_name = None

            match role:
                case "system":
                    continue  # system messages are not included in the contents
                case "user":
                    # Flush any buffered tool responses before adding user message
                    flush_tool_responses()
                    contents.append(
                        {
                            "role": "user",
                            "parts": [{"text": message.get("content", None)}],
                        }
                    )
                case "assistant":
                    # Flush any buffered tool responses before adding assistant message
                    flush_tool_responses()

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
                            call_id = tool_call.get("id")
                            if isinstance(call_id, str) and current_function_name:
                                call_name_by_id[call_id] = current_function_name

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
                    # Get the matching function name
                    tool_call_id = message.get("tool_call_id")
                    # Look up function name by tool call id, default to current_function_name if not found
                    function_name = call_name_by_id.get(
                        tool_call_id or "", current_function_name
                    )
                    if not function_name:
                        raise ValueError(
                            f"Could not find function name for tool_call_id: {tool_call_id}. "
                            "Ensure tool messages have matching assistant tool calls in the trace."
                        )

                    # Buffer the function response part instead of immediately adding to contents
                    tool_response_parts.append(
                        {
                            "functionResponse": {
                                "name": function_name,
                                "response": {
                                    "content": content,  # hardcode the content using 'content' key, Vertex expects 'response' to be a dict
                                },
                            },
                        }
                    )

        # Flush any remaining buffered tool responses
        flush_tool_responses()

        return {
            "systemInstruction": {
                "role": "system",
                "parts": [
                    {
                        "text": self.system_message,
                    }
                ],
            },
            "contents": contents,
        }
