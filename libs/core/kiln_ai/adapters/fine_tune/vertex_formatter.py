import json
from typing import Any, Dict

from kiln_ai.adapters.chat.chat_formatter import (
    ChatMessage,
    ToolCallMessage,
    ToolResponseMessage,
)
from kiln_ai.tools.base_tool import ToolCallDefinition

VERTEX_GEMINI_ROLE_MAP = {
    "system": "system",
    "user": "user",
    "assistant": "model",
}


def generate_vertex_gemini(
    training_chat: list[ChatMessage],
    tools: list[ToolCallDefinition] | None = None,
) -> Dict[str, Any]:
    """Generate Vertex Gemini format (flash and pro)"""
    # See https://cloud.google.com/vertex-ai/generative-ai/docs/models/tune-function-calling

    if not training_chat:
        raise ValueError("Training chat cannot be empty")

    # System message get's it's own entry in top level UI
    system_instruction = training_chat[0].content

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

    for message in training_chat[1:]:
        role = message.role
        current_function_name = None

        match role:
            case "system":
                continue  # system messages are not included in the contents
            case "user":
                # Flush any buffered tool responses before adding user message
                flush_tool_responses()
                contents.append(
                    {
                        "role": VERTEX_GEMINI_ROLE_MAP[role],
                        "parts": [{"text": message.content}],
                    }
                )
            case "assistant":
                # Flush any buffered tool responses before adding assistant message
                flush_tool_responses()

                parts: list[dict[str, Any]] = []

                if isinstance(message, ToolCallMessage):
                    tool_calls = message.tool_calls
                    # every tool call is a single "part"
                    for tool_call in tool_calls:
                        arguments_str = tool_call["function"]["arguments"]
                        # arguments needs to be a JSON dictionary
                        arguments = validate_json_dictionary(
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
                    parts.append({"text": message.content})

                contents.append(
                    {
                        "role": VERTEX_GEMINI_ROLE_MAP[
                            role
                        ],  # Vertex uses "model" for assistant role
                        "parts": parts,
                    }
                )
            case "tool" if isinstance(message, ToolResponseMessage):
                # tool role is "user" with "functionResponse" in Vertex
                # response needs to be a dict
                content = message.content
                if not isinstance(content, str):
                    raise ValueError(
                        f"Tool message content must be a string, got {type(content)}"
                    )
                # Get the matching function name
                tool_call_id = message.tool_call_id
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

    result = {
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

    # Add tools if available
    if tools:
        result["tools"] = [
            {
                "functionDeclarations": [
                    vertex_function_declaration(tool) for tool in tools
                ],
            }
        ]

    return result


def convert_schema_to_vertex_types(schema: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively convert JSON Schema types from lowercase (OpenAI) to uppercase (Vertex).

    """
    supported_vertex_types = {
        "string": "STRING",
        "integer": "INTEGER",
        "boolean": "BOOLEAN",
        "number": "NUMBER",
        "array": "ARRAY",
        "object": "OBJECT",
    }

    result = {}
    for key, value in schema.items():
        if key == "type" and isinstance(value, str):
            vertex_type = supported_vertex_types.get(value.lower())
            if not vertex_type:
                raise ValueError(
                    f"Unsupported type '{value}' in schema. Supported types: {list(supported_vertex_types.keys())}"
                )
            result[key] = vertex_type
        elif isinstance(value, dict):
            result[key] = convert_schema_to_vertex_types(value)
        elif isinstance(value, list):
            result[key] = [
                convert_schema_to_vertex_types(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value
    return result


def vertex_function_declaration(tool: ToolCallDefinition) -> dict[str, Any]:
    """
    Convert OpenAI tool call definition to Vertex function declaration.
    See https://cloud.google.com/vertex-ai/generative-ai/docs/models/tune-function-calling
    """
    function = tool["function"]
    parameters = function["parameters"]

    return {
        "name": function["name"],
        "description": function["description"],
        "parameters": convert_schema_to_vertex_types(parameters),
    }


def validate_json_dictionary(s: str, property_name: str) -> dict[str, Any]:
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
