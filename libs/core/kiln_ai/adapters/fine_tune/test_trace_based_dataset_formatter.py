from typing import Any
from unittest.mock import Mock

import pytest

from kiln_ai.adapters.fine_tune.dataset_format import DatasetFormat
from kiln_ai.adapters.fine_tune.trace_based_dataset_formatter import (
    TraceBasedDatasetFormatter,
)
from kiln_ai.datamodel import TaskRun
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam


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


def correct_openai_chat_messages(jsonOutput: bool = False) -> list[dict[str, Any]]:
    return [
        {
            "role": "system",
            "content": "Test System Message",
        },  # system message should come from the formatter not trace
        {"role": "user", "content": "What's the result of (18 - 6) / (3 + 3)"},
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
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_MZPbRcNAN6l2tjCs7gZfj3sl",
                    "function": {
                        "arguments": '{"a":12,"b":6}',
                        "name": "divide",
                    },
                    "type": "function",
                }
            ],
        },
        {
            "role": "tool",
            "content": "2.0",
            "tool_call_id": "call_MZPbRcNAN6l2tjCs7gZfj3sl",
        },
        {
            "role": "assistant",
            "content": '{"answer": 2.0}'
            if jsonOutput
            else "The result of \\((18 - 6) / (3 + 3)\\) is \\(2.0\\).",
        },
    ]


class TestTraceBasedDatasetFormatter:
    """Tests for TraceBasedDatasetFormatter"""

    def test_init(self):
        """Test initialization"""
        formatter = TraceBasedDatasetFormatter(system_message="Test system message")
        assert formatter.system_message == "Test system message"

    def test_missing_trace(self):
        """Test error when trace is missing"""
        formatter = TraceBasedDatasetFormatter(system_message="Test")
        task_run = Mock(spec=TaskRun)
        task_run.trace = None

        with pytest.raises(ValueError, match="Trace is required"):
            formatter.build_training_chat_from_trace(
                task_run, DatasetFormat.OPENAI_CHAT_JSONL
            )

    def test_unsupported_format(self):
        """Test error with unsupported format"""
        formatter = TraceBasedDatasetFormatter(system_message="Test")

        task = Mock(spec=TaskRun)
        task.trace = trace_without_tools()

        with pytest.raises(ValueError, match="Unsupported data format"):
            formatter.build_training_chat_from_trace(
                task,
                "invalid",  # type: ignore
            )

    # OPENAI_CHAT_JSONL

    def test_OPENAI_CHAT_JSONL_without_tools(self):
        """Test generate openai chat message response"""
        formatter = TraceBasedDatasetFormatter(system_message="Test System Message")
        task = Mock(spec=TaskRun)
        task.trace = trace_without_tools()

        result = formatter.build_training_chat_from_trace(
            task, DatasetFormat.OPENAI_CHAT_JSONL
        )
        assert result == {
            "messages": [
                {
                    "role": "system",
                    "content": "Test System Message",
                },  # system message should come from the formatter not trace
                {"role": "user", "content": "What is 2+2?"},
                {"role": "assistant", "content": "The answer is 4."},
            ]
        }

    def test_OPENAI_CHAT_JSONL_with_tools(self):
        """Test generate openai chat message response with tools"""
        formatter = TraceBasedDatasetFormatter(system_message="Test System Message")
        task = Mock(spec=TaskRun)
        task.trace = trace_with_tools()

        result = formatter.build_training_chat_from_trace(
            task, DatasetFormat.OPENAI_CHAT_JSONL
        )
        assert result == {
            "messages": correct_openai_chat_messages(),
        }

    # OPENAI_CHAT_JSON_SCHEMA_JSONL

    def test_OPENAI_CHAT_JSON_SCHEMA_JSONL_without_tools(self):
        """
        Test generate openai chat message response with json schema
        This mode checks if the answer (last assistant message) is a valid JSON structured output,
        then construct the dataset by going through generate_openai_chat_message_list
        """
        formatter = TraceBasedDatasetFormatter(system_message="Test System Message")
        task = Mock(spec=TaskRun)
        task.trace = trace_without_tools()

        # Should throw error if the output is not a json
        with pytest.raises(
            ValueError,
            match="Last message is not a JSON Dictionary \\(structured data\\), and this format expects structured_data",
        ):
            formatter.build_training_chat_from_trace(
                task, DatasetFormat.OPENAI_CHAT_JSON_SCHEMA_JSONL
            )

        # Should construct the dataset by going through generate_openai_chat_message_list
        task.trace = trace_without_tools(jsonOutput=True)
        result = formatter.build_training_chat_from_trace(
            task, DatasetFormat.OPENAI_CHAT_JSON_SCHEMA_JSONL
        )
        assert result == {
            "messages": [
                {"role": "system", "content": "Test System Message"},
                {"role": "user", "content": "What is 2+2?"},
                {"role": "assistant", "content": '{"answer": 4}'},
            ]
        }

    # OPENAI_CHAT_TOOLCALL_JSONL

    def test_OPENAI_CHAT_TOOLCALL_JSONL_without_tools(self):
        """Test generate openai chat message response with tool call"""
        formatter = TraceBasedDatasetFormatter(system_message="Test System Message")
        task = Mock(spec=TaskRun)
        task.trace = trace_without_tools()

        result = formatter.build_training_chat_from_trace(
            task, DatasetFormat.OPENAI_CHAT_TOOLCALL_JSONL
        )
        assert result == {
            "messages": [
                {"role": "system", "content": "Test System Message"},
                {"role": "user", "content": "What is 2+2?"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "task_response",
                                "arguments": "The answer is 4.",
                            },
                        }
                    ],
                },
            ]
        }

    def test_OPENAI_CHAT_TOOLCALL_JSONL_with_tools(self):
        """Test generate openai chat message response with tool call with tools"""
        formatter = TraceBasedDatasetFormatter(system_message="Test System Message")
        task = Mock(spec=TaskRun)
        task.trace = trace_with_tools(jsonOutput=True)

        result = formatter.build_training_chat_from_trace(
            task, DatasetFormat.OPENAI_CHAT_TOOLCALL_JSONL
        )
        assert result == {
            "messages": [
                {
                    "role": "system",
                    "content": "Test System Message",
                },  # system message should come from the formatter not trace
                {"role": "user", "content": "What's the result of (18 - 6) / (3 + 3)"},
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
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_MZPbRcNAN6l2tjCs7gZfj3sl",
                            "function": {
                                "arguments": '{"a":12,"b":6}',
                                "name": "divide",
                            },
                            "type": "function",
                        }
                    ],
                },
                {
                    "role": "tool",
                    "content": "2.0",
                    "tool_call_id": "call_MZPbRcNAN6l2tjCs7gZfj3sl",
                },
                {
                    # last message is replaced by a toolcall response
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "task_response",
                                "arguments": '{"answer": 2.0}',
                            },
                        }
                    ],
                },
            ]
        }

    # HUGGINGFACE_CHAT_TEMPLATE_JSONL

    def test_HUGGINGFACE_CHAT_TEMPLATE_JSONL_without_tools(self):
        """Test generate openai chat message response"""
        formatter = TraceBasedDatasetFormatter(system_message="Test System Message")
        task = Mock(spec=TaskRun)
        task.trace = trace_without_tools()

        result = formatter.build_training_chat_from_trace(
            task, DatasetFormat.HUGGINGFACE_CHAT_TEMPLATE_JSONL
        )
        assert result == {
            "conversations": [
                {
                    "role": "system",
                    "content": "Test System Message",
                },  # system message should come from the formatter not trace
                {"role": "user", "content": "What is 2+2?"},
                {"role": "assistant", "content": "The answer is 4."},
            ]
        }

    def test_HUGGINGFACE_CHAT_TEMPLATE_JSONL_with_tools(self):
        """Test generate openai chat message response with tools"""
        formatter = TraceBasedDatasetFormatter(system_message="Test System Message")
        task = Mock(spec=TaskRun)
        task.trace = trace_with_tools()

        result = formatter.build_training_chat_from_trace(
            task, DatasetFormat.HUGGINGFACE_CHAT_TEMPLATE_JSONL
        )
        assert result == {
            "conversations": correct_openai_chat_messages(),
        }

    # HUGGINGFACE_CHAT_TEMPLATE_TOOLCALL_JSONL

    def test_HUGGINGFACE_CHAT_TEMPLATE_TOOLCALL_JSONL_without_tools(self):
        """
        Test generate huggingface chat template message response with tool call
        This format is similar to OPENAI_CHAT_TOOLCALL_JSONL, but with a 9 char UUID
        """
        formatter = TraceBasedDatasetFormatter(system_message="Test System Message")
        task = Mock(spec=TaskRun)
        task.trace = trace_without_tools()

        result = formatter.build_training_chat_from_trace(
            task, DatasetFormat.HUGGINGFACE_CHAT_TEMPLATE_TOOLCALL_JSONL
        )

        assert len(result["conversations"]) == 3
        assert result["conversations"][0] == {
            "role": "system",
            "content": "Test System Message",
        }
        assert result["conversations"][1] == {"role": "user", "content": "What is 2+2?"}

        assistant_msg = result["conversations"][2]
        assert assistant_msg["role"] == "assistant"
        assert len(assistant_msg["tool_calls"]) == 1

        tool_call = assistant_msg["tool_calls"][0]
        assert tool_call["type"] == "function"
        assert tool_call["function"]["name"] == "task_response"
        assert tool_call["function"]["arguments"] == "The answer is 4."
        assert len(tool_call["function"]["id"]) == 9  # UUID is truncated to 9 chars
        assert tool_call["function"]["id"].isalnum()  # Check ID is alphanumeric
