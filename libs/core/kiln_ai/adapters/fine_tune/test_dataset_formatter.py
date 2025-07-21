import json
import logging
import re
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from kiln_ai.adapters.chat.chat_formatter import COT_FINAL_ANSWER_PROMPT, ChatMessage
from kiln_ai.adapters.fine_tune.dataset_formatter import (
    VERTEX_GEMINI_ROLE_MAP,
    DatasetFormat,
    DatasetFormatter,
    build_training_chat,
    generate_chat_message_response,
    generate_chat_message_toolcall,
    generate_huggingface_chat_template,
    generate_huggingface_chat_template_toolcall,
    generate_vertex_gemini,
    serialize_r1_style_message,
)
from kiln_ai.datamodel import (
    DatasetSplit,
    DataSource,
    DataSourceType,
    Task,
    TaskOutput,
    TaskRun,
)
from kiln_ai.datamodel.datamodel_enums import ChatStrategy

logger = logging.getLogger(__name__)


@pytest.fixture
def mock_task():
    task = Mock(spec=Task, thinking_instruction=None)
    task_runs = [
        Mock(
            spec=TaskRun,
            **{
                "id": f"run{i}",
                "input": '{"test": "input 你好"}',
                "repaired_output": None,
                "intermediate_outputs": {},
                "thinking_training_data": Mock(return_value=None),
                "input_source": Mock(
                    spec=DataSource,
                    **{
                        "type": DataSourceType.human,
                        "properties": {"created_by": "test"},
                    },
                ),
                "output": Mock(
                    spec=TaskOutput,
                    **{
                        "output": '{"test":   "output 你好"}',
                        "source": Mock(
                            spec=DataSource,
                            **{
                                "type": DataSourceType.synthetic,
                                "properties": {
                                    "model_name": "test",
                                    "model_provider": "test",
                                    "adapter_name": "test",
                                },
                            },
                        ),
                    },
                ),
            },
        )
        for i in range(1, 4)
    ]

    # Set up parent_task reference for each TaskRun
    for run in task_runs:
        run.parent_task = Mock(return_value=task)

    task.runs.return_value = task_runs
    return task


@pytest.fixture
def mock_intermediate_outputs(mock_task):
    for run in mock_task.runs():
        run.intermediate_outputs = {"reasoning": "thinking output"}
        run.thinking_training_data.return_value = "thinking output"
    mock_task.thinking_instruction = "thinking instructions"
    return mock_task


@pytest.fixture
def mock_dataset(mock_task):
    dataset = Mock(spec=DatasetSplit)
    dataset.name = "test_dataset"
    dataset.parent_task.return_value = mock_task
    dataset.split_contents = {"train": ["run1", "run2"], "test": ["run3"]}
    return dataset


@pytest.fixture
def mock_training_chat_short():
    return [
        ChatMessage(role="system", content="system message"),
        ChatMessage(
            role="user",
            content="test input",
        ),
        ChatMessage(role="assistant", content="test output"),
    ]


@pytest.fixture
def mock_training_chat_two_step_plaintext():
    return [
        ChatMessage(role="system", content="system message"),
        ChatMessage(
            role="user",
            content="The input is:\n<user_input>\ntest input\n</user_input>\n\nthinking instructions",
        ),
        ChatMessage(role="assistant", content="thinking output"),
        ChatMessage(role="user", content="thinking final answer prompt"),
        ChatMessage(role="assistant", content="test output"),
    ]


@pytest.fixture
def mock_training_chat_two_step_json():
    return [
        ChatMessage(role="system", content="system message"),
        ChatMessage(
            role="user",
            content="The input is:\n<user_input>\ntest input\n</user_input>\n\nthinking instructions",
        ),
        ChatMessage(role="assistant", content="thinking output"),
        ChatMessage(role="user", content="thinking final answer prompt"),
        ChatMessage(role="assistant", content='{"a":"你好"}'),
    ]


def test_generate_chat_message_response(mock_training_chat_two_step_plaintext):
    result = generate_chat_message_response(mock_training_chat_two_step_plaintext)

    assert result == {
        "messages": [
            {"role": "system", "content": "system message"},
            {
                "role": "user",
                "content": "The input is:\n<user_input>\ntest input\n</user_input>\n\nthinking instructions",
            },
            {"role": "assistant", "content": "thinking output"},
            {"role": "user", "content": "thinking final answer prompt"},
            {"role": "assistant", "content": "test output"},
        ]
    }


def test_generate_chat_message_response_json(mock_training_chat_two_step_json):
    result = generate_chat_message_response(mock_training_chat_two_step_json)

    assert result == {
        "messages": [
            {"role": "system", "content": "system message"},
            {
                "role": "user",
                "content": "The input is:\n<user_input>\ntest input\n</user_input>\n\nthinking instructions",
            },
            {"role": "assistant", "content": "thinking output"},
            {"role": "user", "content": "thinking final answer prompt"},
            {"role": "assistant", "content": '{"a":"你好"}'},
        ]
    }


def test_generate_chat_message_toolcall(mock_training_chat_two_step_json):
    result = generate_chat_message_toolcall(mock_training_chat_two_step_json)

    assert result == {
        "messages": [
            {"role": "system", "content": "system message"},
            {
                "role": "user",
                "content": "The input is:\n<user_input>\ntest input\n</user_input>\n\nthinking instructions",
            },
            {"role": "assistant", "content": "thinking output"},
            {"role": "user", "content": "thinking final answer prompt"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "task_response",
                            "arguments": '{"a": "你好"}',
                        },
                    }
                ],
            },
        ]
    }


def test_generate_chat_message_toolcall_invalid_json(mock_training_chat_two_step_json):
    mock_training_chat_two_step_json[-1].content = "invalid json"
    with pytest.raises(ValueError, match="^Last message is not JSON"):
        generate_chat_message_toolcall(mock_training_chat_two_step_json)


def test_dataset_formatter_dump_invalid_format(mock_dataset):
    formatter = DatasetFormatter(mock_dataset, "system message")

    with pytest.raises(ValueError, match="Unsupported format"):
        formatter.dump_to_file("train", "invalid_format", ChatStrategy.single_turn)


def test_dataset_formatter_dump_invalid_split(mock_dataset):
    formatter = DatasetFormatter(mock_dataset, "system message")

    with pytest.raises(ValueError, match="Split invalid_split not found in dataset"):
        formatter.dump_to_file(
            "invalid_split",
            DatasetFormat.OPENAI_CHAT_JSONL,
            ChatStrategy.single_turn,
        )


def test_dataset_formatter_dump_to_file(mock_dataset, tmp_path):
    formatter = DatasetFormatter(mock_dataset, "system message")
    output_path = tmp_path / "output.jsonl"

    result_path = formatter.dump_to_file(
        "train",
        DatasetFormat.OPENAI_CHAT_JSONL,
        path=output_path,
        data_strategy=ChatStrategy.single_turn,
    )

    assert result_path == output_path
    assert output_path.exists()

    # Verify file contents
    with open(output_path) as f:
        lines = f.readlines()
        assert len(lines) == 2  # Should have 2 entries for train split
        for line in lines:
            data = json.loads(line)
            assert "messages" in data
            assert len(data["messages"]) == 3
            assert data["messages"][0]["content"] == "system message"
            assert data["messages"][1]["content"] == '{"test": "input 你好"}'
            # Raw chat doesn't fix json issues, like extra spaces
            assert data["messages"][2]["content"] == '{"test":   "output 你好"}'


def test_dataset_formatter_dump_to_temp_file(mock_dataset):
    formatter = DatasetFormatter(mock_dataset, "system message 你好")

    result_path = formatter.dump_to_file(
        "train",
        DatasetFormat.OPENAI_CHAT_JSONL,
        data_strategy=ChatStrategy.single_turn,
    )

    assert result_path.exists()
    assert result_path.parent == Path(tempfile.gettempdir())
    # Test our nice naming
    assert result_path.name.startswith(
        "test_dataset -- split-train -- format-openai_chat_jsonl -- no-cot.jsonl"
    )
    assert result_path.name.endswith(".jsonl")
    # Verify file contents
    with open(result_path) as f:
        lines = f.readlines()
        assert len(lines) == 2
        # check non-ascii characters are not escaped
        assert "你好" in lines[0]
        assert "你好" in lines[1]

        # confirm didn't use COT for final_only
        assert "thinking output" not in lines[0]
        assert "thinking instructions" not in lines[0]


def test_dataset_formatter_dump_to_file_tool_format(mock_dataset, tmp_path):
    formatter = DatasetFormatter(mock_dataset, "system message")
    output_path = tmp_path / "output.jsonl"

    result_path = formatter.dump_to_file(
        "train",
        DatasetFormat.OPENAI_CHAT_TOOLCALL_JSONL,
        path=output_path,
        data_strategy=ChatStrategy.single_turn,
    )

    assert result_path == output_path
    assert output_path.exists()

    # Verify file contents
    with open(output_path) as f:
        lines = f.readlines()
        assert len(lines) == 2  # Should have 2 entries for train split
        for line in lines:
            data = json.loads(line)
            assert "messages" in data
            assert len(data["messages"]) == 3
            # Check system and user messages
            assert data["messages"][0]["content"] == "system message"
            assert data["messages"][1]["content"] == '{"test": "input 你好"}'
            # Check tool call format
            assistant_msg = data["messages"][2]
            assert assistant_msg["content"] is None
            assert "tool_calls" in assistant_msg
            assert len(assistant_msg["tool_calls"]) == 1
            tool_call = assistant_msg["tool_calls"][0]
            assert tool_call["type"] == "function"
            assert tool_call["function"]["name"] == "task_response"
            assert tool_call["function"]["arguments"] == '{"test": "output 你好"}'


def test_dataset_formatter_dump_with_intermediate_data(
    mock_dataset, mock_intermediate_outputs
):
    formatter = DatasetFormatter(
        mock_dataset,
        "system message 你好",
        thinking_instructions="thinking instructions",
    )

    result_path = formatter.dump_to_file(
        "train",
        DatasetFormat.OPENAI_CHAT_JSONL,
        data_strategy=ChatStrategy.two_message_cot_legacy,
    )

    assert result_path.exists()
    assert result_path.parent == Path(tempfile.gettempdir())
    # Test our nice naming, with cot
    assert (
        result_path.name
        == "test_dataset -- split-train -- format-openai_chat_jsonl -- cot.jsonl"
    )
    # Verify file contents
    with open(result_path) as f:
        lines = f.readlines()
        assert len(lines) == 2
        for line in lines:
            assert "thinking output" in line
            assert "thinking instructions" in line


def test_dataset_formatter_dump_with_intermediate_data_r1_style(
    mock_dataset, mock_intermediate_outputs
):
    formatter = DatasetFormatter(
        mock_dataset,
        "system message 你好",
        thinking_instructions=None,
    )

    result_path = formatter.dump_to_file(
        "train",
        DatasetFormat.OPENAI_CHAT_JSONL,
        data_strategy=ChatStrategy.single_turn_r1_thinking,
    )

    assert result_path.exists()
    assert result_path.parent == Path(tempfile.gettempdir())
    # Test our nice naming, with cot
    assert (
        result_path.name
        == "test_dataset -- split-train -- format-openai_chat_jsonl -- cot.jsonl"
    )
    # Verify file contents
    with open(result_path) as f:
        lines = f.readlines()
        assert len(lines) == 2
        for line in lines:
            assert "<think>" in line
            assert "</think>" in line


def test_dataset_formatter_dump_with_intermediate_data_custom_instructions(
    mock_dataset, mock_intermediate_outputs
):
    formatter = DatasetFormatter(
        mock_dataset, "custom system message 你好", "custom thinking instructions"
    )

    result_path = formatter.dump_to_file(
        "train",
        DatasetFormat.OPENAI_CHAT_JSONL,
        data_strategy=ChatStrategy.two_message_cot_legacy,
    )

    assert result_path.exists()
    assert result_path.parent == Path(tempfile.gettempdir())
    # Test our nice naming, with cot
    assert (
        result_path.name
        == "test_dataset -- split-train -- format-openai_chat_jsonl -- cot.jsonl"
    )
    # Verify file contents
    with open(result_path) as f:
        lines = f.readlines()
        assert len(lines) == 2
        for line in lines:
            assert "custom system message 你好" in line
            assert "custom thinking instructions" in line
            assert "thinking output" in line


def test_generate_huggingface_chat_template(mock_training_chat_two_step_plaintext):
    result = generate_huggingface_chat_template(mock_training_chat_two_step_plaintext)

    assert result == {
        "conversations": [
            {"role": "system", "content": "system message"},
            {
                "role": "user",
                "content": "The input is:\n<user_input>\ntest input\n</user_input>\n\nthinking instructions",
            },
            {"role": "assistant", "content": "thinking output"},
            {"role": "user", "content": "thinking final answer prompt"},
            {"role": "assistant", "content": "test output"},
        ]
    }


def test_generate_vertex_template(mock_training_chat_short):
    result = generate_vertex_gemini(mock_training_chat_short)

    assert result == {
        "systemInstruction": {
            "role": "system",
            "parts": [
                {
                    "text": "system message",
                }
            ],
        },
        "contents": [
            {"role": "user", "parts": [{"text": "test input"}]},
            {"role": "model", "parts": [{"text": "test output"}]},
        ],
    }


def test_generate_vertex_template_thinking(mock_training_chat_two_step_plaintext):
    result = generate_vertex_gemini(mock_training_chat_two_step_plaintext)

    assert result == {
        "systemInstruction": {
            "role": "system",
            "parts": [
                {
                    "text": "system message",
                }
            ],
        },
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": "The input is:\n<user_input>\ntest input\n</user_input>\n\nthinking instructions",
                    }
                ],
            },
            {"role": "model", "parts": [{"text": "thinking output"}]},
            {"role": "user", "parts": [{"text": "thinking final answer prompt"}]},
            {"role": "model", "parts": [{"text": "test output"}]},
        ],
    }


def test_generate_huggingface_chat_template_toolcall():
    messages = [
        ChatMessage("system", "system message"),
        ChatMessage("user", "test input"),
        ChatMessage("assistant", '{"key":"value"}'),
    ]

    result = generate_huggingface_chat_template_toolcall(messages)

    assert result["conversations"][0] == {"role": "system", "content": "system message"}
    assert result["conversations"][1] == {"role": "user", "content": "test input"}
    assistant_msg = result["conversations"][2]
    assert assistant_msg["role"] == "assistant"
    assert len(assistant_msg["tool_calls"]) == 1
    tool_call = assistant_msg["tool_calls"][0]
    assert tool_call["type"] == "function"
    assert tool_call["function"]["name"] == "task_response"
    assert len(tool_call["function"]["id"]) == 9  # UUID is truncated to 9 chars
    assert tool_call["function"]["id"].isalnum()  # Check ID is alphanumeric
    assert tool_call["function"]["arguments"] == {"key": "value"}


def test_generate_huggingface_chat_template_toolcall_thinking(
    mock_training_chat_two_step_json,
):
    result = generate_huggingface_chat_template_toolcall(
        mock_training_chat_two_step_json
    )

    assert result["conversations"][0] == {"role": "system", "content": "system message"}
    assert result["conversations"][1] == {
        "role": "user",
        "content": "The input is:\n<user_input>\ntest input\n</user_input>\n\nthinking instructions",
    }
    assert result["conversations"][2] == {
        "role": "assistant",
        "content": "thinking output",
    }
    assert result["conversations"][3] == {
        "role": "user",
        "content": "thinking final answer prompt",
    }

    assistant_msg = result["conversations"][4]
    assert assistant_msg["role"] == "assistant"
    assert len(assistant_msg["tool_calls"]) == 1
    tool_call = assistant_msg["tool_calls"][0]
    assert tool_call["type"] == "function"
    assert tool_call["function"]["name"] == "task_response"
    assert len(tool_call["function"]["id"]) == 9  # UUID is truncated to 9 chars
    assert tool_call["function"]["id"].isalnum()  # Check ID is alphanumeric
    assert tool_call["function"]["arguments"] == {"a": "你好"}


def test_generate_huggingface_chat_template_toolcall_invalid_json(
    mock_training_chat_two_step_json,
):
    mock_training_chat_two_step_json[-1].content = "invalid json"

    with pytest.raises(ValueError, match="^Last message is not JSON"):
        generate_huggingface_chat_template_toolcall(mock_training_chat_two_step_json)


def test_build_training_chat(mock_task):
    # Non repaired should use original output
    mock_task_run = mock_task.runs()[0]
    messages = build_training_chat(
        mock_task_run,
        "system message",
        data_strategy=ChatStrategy.single_turn,
    )

    assert len(messages) == 3
    system_msg = messages[0]
    assert system_msg.role == "system"
    assert system_msg.content == "system message"

    user_msg = messages[1]
    assert user_msg.role == "user"
    assert user_msg.content == '{"test": "input 你好"}'

    final_msg = messages[2]
    assert final_msg.role == "assistant"
    assert final_msg.content == '{"test":   "output 你好"}'


def test_build_training_data_with_COT(mock_task):
    # Setup with needed fields for thinking
    mock_task_run = mock_task.runs()[0]
    assert mock_task_run.parent_task() == mock_task
    mock_task_run.intermediate_outputs = {"chain_of_thought": "cot output"}
    mock_task_run.thinking_training_data.return_value = "cot output"

    messages = build_training_chat(
        mock_task_run,
        "system message",
        data_strategy=ChatStrategy.two_message_cot,
        thinking_instructions="thinking instructions",
    )

    assert len(messages) == 5
    system_msg = messages[0]
    assert system_msg.role == "system"
    assert system_msg.content == "system message"

    user_msg = messages[1]
    assert user_msg.role == "user"
    assert (
        user_msg.content
        == 'The input is:\n<user_input>\n{"test": "input 你好"}\n</user_input>\n\nthinking instructions'
    )

    assistant_msg = messages[2]
    assert assistant_msg.role == "assistant"
    assert assistant_msg.content == "cot output"

    final_answer_prompt_msg = messages[3]
    assert final_answer_prompt_msg.role == "user"
    assert final_answer_prompt_msg.content == COT_FINAL_ANSWER_PROMPT

    final_msg = messages[4]
    assert final_msg.role == "assistant"
    assert final_msg.content == '{"test":   "output 你好"}'


def test_build_training_data_with_COT_legacy(mock_task):
    # Setup with needed fields for thinking
    mock_task_run = mock_task.runs()[0]
    assert mock_task_run.parent_task() == mock_task
    mock_task_run.intermediate_outputs = {"chain_of_thought": "cot output"}
    mock_task_run.thinking_training_data.return_value = "cot output"

    messages = build_training_chat(
        mock_task_run,
        "system message",
        data_strategy=ChatStrategy.two_message_cot_legacy,
        thinking_instructions="thinking instructions",
    )

    assert len(messages) == 6
    system_msg = messages[0]
    assert system_msg.role == "system"
    assert system_msg.content == "system message"

    user_msg = messages[1]
    assert user_msg.role == "user"
    assert user_msg.content == '{"test": "input 你好"}'

    cot_msg = messages[2]
    assert cot_msg.role == "system"
    assert cot_msg.content == "thinking instructions"

    assistant_msg = messages[3]
    assert assistant_msg.role == "assistant"
    assert assistant_msg.content == "cot output"

    final_answer_prompt_msg = messages[4]
    assert final_answer_prompt_msg.role == "user"
    assert final_answer_prompt_msg.content == COT_FINAL_ANSWER_PROMPT

    final_msg = messages[5]
    assert final_msg.role == "assistant"
    assert final_msg.content == '{"test":   "output 你好"}'


def test_build_training_data_with_COT_r1_style(mock_task):
    # Setup with needed fields for thinking
    mock_task_run = mock_task.runs()[0]
    assert mock_task_run.parent_task() == mock_task
    mock_task_run.intermediate_outputs = {"chain_of_thought": "cot output"}
    mock_task_run.thinking_training_data.return_value = "cot output"

    messages = build_training_chat(
        mock_task_run,
        "system message",
        data_strategy=ChatStrategy.single_turn_r1_thinking,
        thinking_instructions=None,
    )

    assert len(messages) == 3
    system_msg = messages[0]
    assert system_msg.role == "system"
    assert system_msg.content == "system message"

    user_msg = messages[1]
    assert user_msg.role == "user"
    assert user_msg.content == '{"test": "input 你好"}'

    final_msg = messages[2]
    assert final_msg.role == "assistant"
    assert (
        final_msg.content
        == '<think>\ncot output\n</think>\n\n{"test":   "output 你好"}'
    )


def test_build_training_data_with_thinking(mock_task):
    # Setup with needed fields for thinking
    mock_task_run = mock_task.runs()[0]
    assert mock_task_run.parent_task() == mock_task
    # It should just use the reasoning output if both thinking and chain_of_thought are present
    mock_task_run.intermediate_outputs = {
        "reasoning": "thinking output",
        "chain_of_thought": "cot output",
    }
    mock_task_run.thinking_training_data.return_value = "thinking output"
    mock_task.thinking_instruction = "thinking instructions"
    assert mock_task.thinking_instruction == "thinking instructions"

    messages = build_training_chat(
        mock_task_run,
        "system message",
        ChatStrategy.two_message_cot,
        thinking_instructions="thinking instructions",
    )

    assert len(messages) == 5
    system_msg = messages[0]
    assert system_msg.role == "system"
    assert system_msg.content == "system message"

    user_msg = messages[1]
    assert user_msg.role == "user"
    assert (
        user_msg.content
        == 'The input is:\n<user_input>\n{"test": "input 你好"}\n</user_input>\n\nthinking instructions'
    )

    assistant_msg = messages[2]
    assert assistant_msg.role == "assistant"
    assert assistant_msg.content == "thinking output"

    final_answer_prompt_msg = messages[3]
    assert final_answer_prompt_msg.role == "user"
    assert final_answer_prompt_msg.content == COT_FINAL_ANSWER_PROMPT

    final_msg = messages[4]
    assert final_msg.role == "assistant"
    assert final_msg.content == '{"test":   "output 你好"}'


def test_build_training_data_with_thinking_r1_style(mock_task):
    # Setup with needed fields for thinking
    mock_task_run = mock_task.runs()[0]
    assert mock_task_run.parent_task() == mock_task
    # It should just use the reasoning output if both thinking and chain_of_thought are present
    mock_task_run.intermediate_outputs = {
        "reasoning": "thinking output",
        "chain_of_thought": "cot output",
    }
    mock_task_run.thinking_training_data.return_value = "thinking output"
    mock_task.thinking_instruction = "thinking instructions"

    assert mock_task.thinking_instruction == "thinking instructions"

    messages = build_training_chat(
        mock_task_run,
        "system message",
        ChatStrategy.single_turn_r1_thinking,
        thinking_instructions=None,
    )

    assert len(messages) == 3
    system_msg = messages[0]
    assert system_msg.role == "system"
    assert system_msg.content == "system message"

    user_msg = messages[1]
    assert user_msg.role == "user"
    assert user_msg.content == '{"test": "input 你好"}'

    final_msg = messages[2]
    assert final_msg.role == "assistant"
    assert (
        final_msg.content
        == '<think>\nthinking output\n</think>\n\n{"test":   "output 你好"}'
    )


def test_build_training_data_with_repaired_output(mock_task):
    # use repaired output if available
    mock_task_run = mock_task.runs()[0]
    mock_task_run.repair_instructions = "repair instructions"
    mock_task_run.repaired_output = TaskOutput(
        output='{"test": "repaired output"}',
        source=DataSource(
            type=DataSourceType.human,
            properties={"created_by": "test-user"},
        ),
    )

    messages = build_training_chat(
        mock_task_run,
        "system message",
        data_strategy=ChatStrategy.single_turn,
    )

    assert len(messages) == 3
    system_msg = messages[0]
    assert system_msg.role == "system"
    assert system_msg.content == "system message"

    user_msg = messages[1]
    assert user_msg.role == "user"
    assert user_msg.content == '{"test": "input 你好"}'

    final_msg = messages[2]
    assert final_msg.role == "assistant"
    # Note we re-format the json
    assert final_msg.content == '{"test": "repaired output"}'


def test_dataset_formatter_dump_to_file_json_schema_format(mock_dataset, tmp_path):
    formatter = DatasetFormatter(mock_dataset, "system message")
    output_path = tmp_path / "output.jsonl"

    result_path = formatter.dump_to_file(
        "train",
        DatasetFormat.OPENAI_CHAT_JSON_SCHEMA_JSONL,
        path=output_path,
        data_strategy=ChatStrategy.single_turn,
    )

    assert result_path == output_path
    assert output_path.exists()

    # Verify file contents
    with open(output_path) as f:
        lines = f.readlines()
        assert len(lines) == 2  # Should have 2 entries for train split
        for line in lines:
            data = json.loads(line)
            assert "messages" in data
            assert len(data["messages"]) == 3
            # Check system and user messages
            assert data["messages"][0]["content"] == "system message"
            assert data["messages"][1]["content"] == '{"test": "input 你好"}'
            # Check JSON format
            assistant_msg = data["messages"][2]
            assert assistant_msg["role"] == "assistant"
            # Verify the content is valid JSON
            assert assistant_msg["content"] == '{"test": "output 你好"}'
            json_content = json.loads(assistant_msg["content"])
            assert json_content == {"test": "output 你好"}


@pytest.mark.parametrize(
    "thinking,final_output,expected_output",
    [
        ("thinking", "final output", "<think>\nthinking\n</think>\n\nfinal output"),
        ("thinking", '{"name":"joe"}', '<think>\nthinking\n</think>\n\n{"name":"joe"}'),
    ],
)
def test_serialize_r1_style_message(thinking, final_output, expected_output):
    assert (
        serialize_r1_style_message(thinking=thinking, final_output=final_output)
        == expected_output
    )


@pytest.mark.parametrize(
    "thinking,final_output",
    [
        (None, "final output"),
        ("", "final output"),
        (" ", "final output"),
    ],
)
def test_serialize_r1_style_message_missing_thinking(thinking, final_output):
    with pytest.raises(
        ValueError,
        match=re.escape(
            "Thinking data is required when fine-tuning thinking models (R1, QwQ, etc). Please ensure your fine-tuning dataset contains reasoning or chain of thought output for every entry."
        ),
    ):
        serialize_r1_style_message(thinking=thinking, final_output=final_output)


def test_vertex_gemini_role_map_coverage():
    """Test that VERTEX_GEMINI_ROLE_MAP covers all possible ChatMessage.role values"""
    from typing import get_type_hints

    # Get the Literal type from ChatMessage.role
    role_type = get_type_hints(ChatMessage)["role"]
    # Extract the possible values from the Literal type
    possible_roles = role_type.__args__  # type: ignore

    # Check that every possible role is in the map
    for role in possible_roles:
        assert role in VERTEX_GEMINI_ROLE_MAP, (
            f"Role {role} is not mapped in VERTEX_GEMINI_ROLE_MAP"
        )

    # Check that there are no extra mappings
    assert set(VERTEX_GEMINI_ROLE_MAP.keys()) == set(possible_roles), (
        "VERTEX_GEMINI_ROLE_MAP has extra mappings"
    )
