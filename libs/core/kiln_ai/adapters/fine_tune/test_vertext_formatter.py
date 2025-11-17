from unittest.mock import AsyncMock, Mock

from kiln_ai.adapters.fine_tune.dataset_format import DatasetFormat
from kiln_ai.adapters.fine_tune.trace_based_dataset_formatter import (
    TraceBasedDatasetFormatter,
)
from kiln_ai.datamodel import TaskRun
from kiln_ai.datamodel.run_config import RunConfigProperties, ToolsRunConfig
from kiln_ai.datamodel.tool_id import KilnBuiltInToolId
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam


def create_mock_task_run(
    trace: list[ChatCompletionMessageParam], tool_ids: list[str] | None = None
) -> Mock:
    """Helper to create a mock TaskRun with proper structure"""
    task = Mock(spec=TaskRun)
    task.trace = trace
    output_mock = Mock()

    if tool_ids:
        run_config = RunConfigProperties(
            model_name="gpt-4",
            model_provider_name="openai",
            prompt_id="simple_prompt_builder",
            structured_output_mode="default",
            tools_config=ToolsRunConfig(tools=tool_ids),
        )
        output_mock.source = Mock()
        output_mock.source.run_config = run_config

        parent_task_mock = AsyncMock()
        task.parent_task = Mock(return_value=parent_task_mock)
    else:
        output_mock.source = None

    task.output = output_mock
    return task


def trace_without_tools(jsonOutput: bool = False) -> list[ChatCompletionMessageParam]:
    """Simple trace: system, user, assistant"""
    return [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is 2+2?"},
        {
            "role": "assistant",
            "content": '{"answer": 4}' if jsonOutput else "The answer is 4.",
        },
    ]


def trace_with_tools(jsonOutput: bool = False) -> list[ChatCompletionMessageParam]:
    """Real trace with math tools from GPT 4o Zero Shot"""
    return [
        {
            "content": "You are a calculator",
            "role": "system",
        },
        {"content": "What's the result of (18 - 6) / (3 + 3)", "role": "user"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [  # calling 2 tools at the same turn
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
                    "function": {"arguments": '{"a": 3, "b": 3}', "name": "add"},
                    "type": "function",
                },
            ],
        },
        {
            "content": "12",
            "role": "tool",
            "tool_call_id": "call_m91m9tVSGZlOjlGX5ueUXMUX",
        },
        {
            "content": "6",
            "role": "tool",
            "tool_call_id": "call_Yc2l2die7FDuMcjwZ46vjd9A",
        },
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_MZPbRcNAN6l2tjCs7gZfj3sl",
                    "function": {"arguments": '{"a":12,"b":6}', "name": "divide"},
                    "type": "function",
                }
            ],
        },
        {
            "content": "2.0",
            "role": "tool",
            "tool_call_id": "call_MZPbRcNAN6l2tjCs7gZfj3sl",
        },
        {
            "role": "assistant",
            "content": '{"answer": 2.0}'
            if jsonOutput
            else "The result of \\((18 - 6) / (3 + 3)\\) is \\(2.0\\).",
        },
    ]


class TestVertexFormatter:
    async def test_VERTEX_GEMINI_without_tools(self):
        """Test generate vertex gemini message without tools"""
        formatter = TraceBasedDatasetFormatter(system_message="Test System Message")
        task = create_mock_task_run(trace_without_tools())

        result = await formatter.build_training_chat_from_trace(
            task, DatasetFormat.VERTEX_GEMINI
        )
        assert result == {
            "systemInstruction": {
                "role": "system",
                "parts": [{"text": "Test System Message"}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": "What is 2+2?"}],
                },
                {
                    "role": "model",
                    "parts": [{"text": "The answer is 4."}],
                },
            ],
        }

    async def test_VERTEX_GEMINI_with_tools(self):
        """Test generate vertex gemini message with multiple tool calls"""
        formatter = TraceBasedDatasetFormatter(system_message="Test System Message")
        tool_ids = [
            KilnBuiltInToolId.ADD_NUMBERS.value,
            KilnBuiltInToolId.SUBTRACT_NUMBERS.value,
            KilnBuiltInToolId.MULTIPLY_NUMBERS.value,
            KilnBuiltInToolId.DIVIDE_NUMBERS.value,
        ]
        task = create_mock_task_run(trace_with_tools(), tool_ids=tool_ids)

        result = await formatter.build_training_chat_from_trace(
            task, DatasetFormat.VERTEX_GEMINI
        )

        assert result == {
            "systemInstruction": {
                "role": "system",
                "parts": [{"text": "Test System Message"}],
            },
            "contents": [
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
                {
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
                {
                    "role": "model",
                    "parts": [
                        {
                            "functionCall": {
                                "name": "divide",
                                "args": {"a": 12, "b": 6},
                            }
                        }
                    ],
                },
                {
                    "parts": [
                        {
                            "functionResponse": {
                                "name": "divide",
                                "response": {"content": "2.0"},
                            }
                        }
                    ],
                },
                {
                    "role": "model",
                    "parts": [
                        {"text": "The result of \\((18 - 6) / (3 + 3)\\) is \\(2.0\\)."}
                    ],
                },
            ],
            "tools": [
                {
                    "functionDeclarations": [
                        {
                            "name": "add",
                            "description": "Add two numbers together and return the result",
                            "parameters": {
                                "type": "OBJECT",
                                "properties": {
                                    "a": {
                                        "type": "NUMBER",
                                        "description": "The first number to add",
                                    },
                                    "b": {
                                        "type": "NUMBER",
                                        "description": "The second number to add",
                                    },
                                },
                                "required": ["a", "b"],
                            },
                        },
                        {
                            "name": "subtract",
                            "description": "Subtract the second number from the first number and return the result",
                            "parameters": {
                                "type": "OBJECT",
                                "properties": {
                                    "a": {
                                        "type": "NUMBER",
                                        "description": "The first number (minuend)",
                                    },
                                    "b": {
                                        "type": "NUMBER",
                                        "description": "The second number to subtract (subtrahend)",
                                    },
                                },
                                "required": ["a", "b"],
                            },
                        },
                        {
                            "name": "multiply",
                            "description": "Multiply two numbers together and return the result",
                            "parameters": {
                                "type": "OBJECT",
                                "properties": {
                                    "a": {
                                        "type": "NUMBER",
                                        "description": "The first number to multiply",
                                    },
                                    "b": {
                                        "type": "NUMBER",
                                        "description": "The second number to multiply",
                                    },
                                },
                                "required": ["a", "b"],
                            },
                        },
                        {
                            "name": "divide",
                            "description": "Divide the first number by the second number and return the result",
                            "parameters": {
                                "type": "OBJECT",
                                "properties": {
                                    "a": {
                                        "type": "NUMBER",
                                        "description": "The dividend (number to be divided)",
                                    },
                                    "b": {
                                        "type": "NUMBER",
                                        "description": "The divisor (number to divide by)",
                                    },
                                },
                                "required": ["a", "b"],
                            },
                        },
                    ],
                }
            ],
        }

    async def test_VERTEX_GEMINI_with_tool_declarations(self):
        """Test generate vertex gemini message with tool declarations"""
        formatter = TraceBasedDatasetFormatter(system_message="Test System Message")
        tool_ids = [
            KilnBuiltInToolId.ADD_NUMBERS.value,
            KilnBuiltInToolId.SUBTRACT_NUMBERS.value,
        ]
        task = create_mock_task_run(trace_with_tools(), tool_ids=tool_ids)

        result = await formatter.build_training_chat_from_trace(
            task, DatasetFormat.VERTEX_GEMINI
        )

        assert "tools" in result
        assert len(result["tools"]) == 1
        assert "functionDeclarations" in result["tools"][0]
        declarations = result["tools"][0]["functionDeclarations"]
        assert len(declarations) == 2

        add_tool = declarations[0]
        assert add_tool["name"] == "add"
        assert add_tool["parameters"]["type"] == "OBJECT"
        assert add_tool["parameters"]["properties"]["a"]["type"] == "NUMBER"
        assert add_tool["parameters"]["properties"]["b"]["type"] == "NUMBER"

        subtract_tool = declarations[1]
        assert subtract_tool["name"] == "subtract"
        assert subtract_tool["parameters"]["type"] == "OBJECT"

    def test_convert_schema_to_vertex_types(self):
        """Test schema conversion from OpenAI (lowercase) to Vertex (uppercase) types"""
        formatter = TraceBasedDatasetFormatter(system_message="Test")

        openai_schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Person name"},
                "age": {"type": "integer", "description": "Person age"},
                "score": {"type": "number"},
                "active": {"type": "boolean"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "metadata": {
                    "type": "object",
                    "properties": {"key": {"type": "string"}},
                },
            },
        }

        vertex_schema = formatter._convert_schema_to_vertex_types(openai_schema)

        assert vertex_schema["type"] == "OBJECT"
        assert vertex_schema["properties"]["name"]["type"] == "STRING"
        assert vertex_schema["properties"]["age"]["type"] == "INTEGER"
        assert vertex_schema["properties"]["score"]["type"] == "NUMBER"
        assert vertex_schema["properties"]["active"]["type"] == "BOOLEAN"
        assert vertex_schema["properties"]["tags"]["type"] == "ARRAY"
        assert vertex_schema["properties"]["tags"]["items"]["type"] == "STRING"
        assert vertex_schema["properties"]["metadata"]["type"] == "OBJECT"
        assert (
            vertex_schema["properties"]["metadata"]["properties"]["key"]["type"]
            == "STRING"
        )

    def test_convert_schema_preserves_non_type_fields(self):
        """Test that schema conversion preserves all non-type fields"""
        formatter = TraceBasedDatasetFormatter(system_message="Test")

        openai_schema = {
            "type": "object",
            "properties": {
                "product": {
                    "type": "string",
                    "description": "Product name",
                    "enum": ["Pixel 8 Pro 128GB", "Pixel 8 Pro 256GB"],
                }
            },
            "required": ["product"],
        }

        vertex_schema = formatter._convert_schema_to_vertex_types(openai_schema)

        expected_schema = {
            "type": "OBJECT",
            "properties": {
                "product": {
                    "type": "STRING",
                    "description": "Product name",
                    "enum": ["Pixel 8 Pro 128GB", "Pixel 8 Pro 256GB"],
                }
            },
            "required": ["product"],
        }

        assert vertex_schema == expected_schema
