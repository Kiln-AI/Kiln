import json
import logging
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from kiln_ai.adapters.fine_tune.dataset_formatter import (
    DatasetFormat,
    DatasetFormatter,
    ModelTrainingData,
    build_training_data,
    generate_chat_message_response,
    generate_chat_message_toolcall,
    generate_huggingface_chat_template,
    generate_huggingface_chat_template_toolcall,
    generate_vertex_gemini_1_5,
)
from kiln_ai.adapters.model_adapters.base_adapter import COT_FINAL_ANSWER_PROMPT
from kiln_ai.datamodel import (
    DatasetSplit,
    DataSource,
    DataSourceType,
    FinetuneDataStrategy,
    Task,
    TaskOutput,
    TaskRun,
)

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
    mock_task.thinking_instruction = "thinking instructions"
    return mock_task


@pytest.fixture
def mock_dataset(mock_task):
    dataset = Mock(spec=DatasetSplit)
    dataset.name = "test_dataset"
    dataset.parent_task.return_value = mock_task
    dataset.split_contents = {"train": ["run1", "run2"], "test": ["run3"]}
    return dataset


def test_generate_chat_message_response():
    thinking_data = ModelTrainingData(
        input="test input",
        system_message="system message",
        final_output="test output",
    )

    result = generate_chat_message_response(thinking_data)

    assert result == {
        "messages": [
            {"role": "system", "content": "system message"},
            {"role": "user", "content": "test input"},
            {"role": "assistant", "content": "test output"},
        ]
    }


def test_generate_chat_message_response_thinking():
    thinking_data = ModelTrainingData(
        input="test input",
        system_message="system message",
        final_output="test output",
        thinking="thinking output",
        thinking_instructions="thinking instructions",
        thinking_final_answer_prompt="thinking final answer prompt",
    )

    result = generate_chat_message_response(thinking_data)

    assert result == {
        "messages": [
            {"role": "system", "content": "system message"},
            {"role": "user", "content": "test input"},
            {"role": "user", "content": "thinking instructions"},
            {"role": "assistant", "content": "thinking output"},
            {"role": "user", "content": "thinking final answer prompt"},
            {"role": "assistant", "content": "test output"},
        ]
    }


def test_generate_chat_message_toolcall():
    training_data = ModelTrainingData(
        input="test input 你好",
        system_message="system message 你好",
        final_output='{"key": "value 你好"}',
    )

    result = generate_chat_message_toolcall(training_data)

    assert result == {
        "messages": [
            {"role": "system", "content": "system message 你好"},
            {"role": "user", "content": "test input 你好"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "task_response",
                            "arguments": '{"key": "value 你好"}',
                        },
                    }
                ],
            },
        ]
    }


def test_generate_chat_message_toolcall_thinking():
    training_data = ModelTrainingData(
        input="test input",
        system_message="system message",
        final_output='{"key": "value"}',
        thinking="thinking output",
        thinking_instructions="thinking instructions",
        thinking_final_answer_prompt="thinking final answer prompt",
    )

    result = generate_chat_message_toolcall(training_data)

    assert result == {
        "messages": [
            {"role": "system", "content": "system message"},
            {"role": "user", "content": "test input"},
            {"role": "user", "content": "thinking instructions"},
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
                            "arguments": '{"key": "value"}',
                        },
                    }
                ],
            },
        ]
    }


def test_generate_chat_message_toolcall_invalid_json():
    training_data = ModelTrainingData(
        input="test input",
        system_message="system message",
        final_output="invalid json",
    )

    with pytest.raises(ValueError, match="Invalid JSON in for tool call"):
        generate_chat_message_toolcall(training_data)


def test_dataset_formatter_init_no_parent_task(mock_dataset):
    mock_dataset.parent_task.return_value = None

    with pytest.raises(ValueError, match="Dataset has no parent task"):
        DatasetFormatter(mock_dataset, "system message")


def test_dataset_formatter_dump_invalid_format(mock_dataset):
    formatter = DatasetFormatter(mock_dataset, "system message")

    with pytest.raises(ValueError, match="Unsupported format"):
        formatter.dump_to_file(
            "train", "invalid_format", FinetuneDataStrategy.final_only
        )  # type: ignore


def test_dataset_formatter_dump_invalid_split(mock_dataset):
    formatter = DatasetFormatter(mock_dataset, "system message")

    with pytest.raises(ValueError, match="Split invalid_split not found in dataset"):
        formatter.dump_to_file(
            "invalid_split",
            DatasetFormat.OPENAI_CHAT_JSONL,
            FinetuneDataStrategy.final_only,
        )


def test_dataset_formatter_dump_to_file(mock_dataset, tmp_path):
    formatter = DatasetFormatter(mock_dataset, "system message")
    output_path = tmp_path / "output.jsonl"

    result_path = formatter.dump_to_file(
        "train",
        DatasetFormat.OPENAI_CHAT_JSONL,
        path=output_path,
        data_strategy=FinetuneDataStrategy.final_only,
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
        data_strategy=FinetuneDataStrategy.final_only,
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
        data_strategy=FinetuneDataStrategy.final_only,
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
        data_strategy=FinetuneDataStrategy.final_and_intermediate,
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


def test_dataset_formatter_dump_with_intermediate_data_custom_instructions(
    mock_dataset, mock_intermediate_outputs
):
    formatter = DatasetFormatter(
        mock_dataset, "custom system message 你好", "custom thinking instructions"
    )

    result_path = formatter.dump_to_file(
        "train",
        DatasetFormat.OPENAI_CHAT_JSONL,
        data_strategy=FinetuneDataStrategy.final_and_intermediate,
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


def test_generate_huggingface_chat_template():
    training_data = ModelTrainingData(
        input="test input",
        system_message="system message",
        final_output="test output",
    )

    result = generate_huggingface_chat_template(training_data)

    assert result == {
        "conversations": [
            {"role": "system", "content": "system message"},
            {"role": "user", "content": "test input"},
            {"role": "assistant", "content": "test output"},
        ]
    }


def test_generate_huggingface_chat_template_thinking():
    training_data = ModelTrainingData(
        input="test input",
        system_message="system message",
        final_output="test output",
        thinking="thinking output",
        thinking_instructions="thinking instructions",
        thinking_final_answer_prompt="thinking final answer prompt",
    )

    result = generate_huggingface_chat_template(training_data)

    assert result == {
        "conversations": [
            {"role": "system", "content": "system message"},
            {"role": "user", "content": "test input"},
            {"role": "user", "content": "thinking instructions"},
            {"role": "assistant", "content": "thinking output"},
            {"role": "user", "content": "thinking final answer prompt"},
            {"role": "assistant", "content": "test output"},
        ]
    }


def test_generate_vertex_template():
    training_data = ModelTrainingData(
        input="test input",
        system_message="system message",
        final_output="test output",
    )

    result = generate_vertex_gemini_1_5(training_data)

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


def test_generate_vertex_template_thinking():
    training_data = ModelTrainingData(
        input="test input",
        system_message="system message",
        final_output="test output",
        thinking="thinking output",
        thinking_instructions="thinking instructions",
        thinking_final_answer_prompt="thinking final answer prompt",
    )

    result = generate_vertex_gemini_1_5(training_data)

    logger.info(result)

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
            {"role": "user", "parts": [{"text": "thinking instructions"}]},
            {"role": "model", "parts": [{"text": "thinking output"}]},
            {"role": "user", "parts": [{"text": "thinking final answer prompt"}]},
            {"role": "model", "parts": [{"text": "test output"}]},
        ],
    }


def test_generate_huggingface_chat_template_toolcall():
    training_data = ModelTrainingData(
        input="test input",
        system_message="system message",
        final_output='{"key": "value"}',
    )

    result = generate_huggingface_chat_template_toolcall(training_data)

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


def test_generate_huggingface_chat_template_toolcall_thinking():
    training_data = ModelTrainingData(
        input="test input",
        system_message="system message",
        final_output='{"key": "value"}',
        thinking="thinking output",
        thinking_instructions="thinking instructions",
        thinking_final_answer_prompt="thinking final answer prompt",
    )

    result = generate_huggingface_chat_template_toolcall(training_data)

    assert result["conversations"][0] == {"role": "system", "content": "system message"}
    assert result["conversations"][1] == {"role": "user", "content": "test input"}
    assert result["conversations"][2] == {
        "role": "user",
        "content": "thinking instructions",
    }
    assert result["conversations"][3] == {
        "role": "assistant",
        "content": "thinking output",
    }
    assert result["conversations"][4] == {
        "role": "user",
        "content": "thinking final answer prompt",
    }

    assistant_msg = result["conversations"][5]
    assert assistant_msg["role"] == "assistant"
    assert len(assistant_msg["tool_calls"]) == 1
    tool_call = assistant_msg["tool_calls"][0]
    assert tool_call["type"] == "function"
    assert tool_call["function"]["name"] == "task_response"
    assert len(tool_call["function"]["id"]) == 9  # UUID is truncated to 9 chars
    assert tool_call["function"]["id"].isalnum()  # Check ID is alphanumeric
    assert tool_call["function"]["arguments"] == {"key": "value"}


def test_generate_huggingface_chat_template_toolcall_invalid_json():
    training_data = ModelTrainingData(
        input="test input",
        system_message="system message",
        final_output="invalid json",
    )

    with pytest.raises(ValueError, match="Invalid JSON in for tool call"):
        generate_huggingface_chat_template_toolcall(training_data)


def test_build_training_data(mock_task):
    # Non repaired should use original output
    mock_task_run = mock_task.runs()[0]
    training_data_output = build_training_data(mock_task_run, "system message", False)
    assert training_data_output.final_output == '{"test":   "output 你好"}'
    assert training_data_output.thinking is None
    assert training_data_output.thinking_instructions is None
    assert training_data_output.thinking_final_answer_prompt is None
    assert training_data_output.input == '{"test": "input 你好"}'
    assert training_data_output.system_message == "system message"
    assert not training_data_output.supports_cot()


def test_build_training_data_with_COT(mock_task):
    # Setup with needed fields for thinking
    mock_task_run = mock_task.runs()[0]
    assert mock_task_run.parent_task() == mock_task
    mock_task_run.intermediate_outputs = {"chain_of_thought": "cot output"}

    training_data_output = build_training_data(
        mock_task_run,
        "system message",
        True,
        thinking_instructions="thinking instructions",
    )
    assert training_data_output.final_output == '{"test":   "output 你好"}'
    assert training_data_output.thinking == "cot output"
    assert training_data_output.thinking_instructions == "thinking instructions"
    assert training_data_output.thinking_final_answer_prompt == COT_FINAL_ANSWER_PROMPT
    assert training_data_output.input == '{"test": "input 你好"}'
    assert training_data_output.system_message == "system message"
    assert training_data_output.supports_cot()


def test_build_training_data_with_thinking(mock_task):
    # Setup with needed fields for thinking
    mock_task_run = mock_task.runs()[0]
    assert mock_task_run.parent_task() == mock_task
    # It should just use the reasoning output if both thinking and chain_of_thought are present
    mock_task_run.intermediate_outputs = {
        "reasoning": "thinking output",
        "chain_of_thought": "cot output",
    }
    mock_task.thinking_instruction = "thinking instructions"
    assert mock_task.thinking_instruction == "thinking instructions"

    training_data_output = build_training_data(
        mock_task_run,
        "system message",
        True,
        thinking_instructions="thinking instructions",
    )
    assert training_data_output.final_output == '{"test":   "output 你好"}'
    assert training_data_output.thinking == "thinking output"
    assert training_data_output.thinking_instructions == "thinking instructions"
    assert training_data_output.thinking_final_answer_prompt == COT_FINAL_ANSWER_PROMPT
    assert training_data_output.input == '{"test": "input 你好"}'
    assert training_data_output.system_message == "system message"
    assert training_data_output.supports_cot()


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

    training_data_output = build_training_data(mock_task_run, "system message", False)
    assert training_data_output.final_output == '{"test": "repaired output"}'
    assert training_data_output.thinking is None
    assert training_data_output.thinking_instructions is None
    assert training_data_output.thinking_final_answer_prompt is None
    assert training_data_output.input == '{"test": "input 你好"}'
    assert training_data_output.system_message == "system message"


def test_dataset_formatter_dump_to_file_json_schema_format(mock_dataset, tmp_path):
    formatter = DatasetFormatter(mock_dataset, "system message")
    output_path = tmp_path / "output.jsonl"

    result_path = formatter.dump_to_file(
        "train",
        DatasetFormat.OPENAI_CHAT_JSON_SCHEMA_JSONL,
        path=output_path,
        data_strategy=FinetuneDataStrategy.final_only,
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
