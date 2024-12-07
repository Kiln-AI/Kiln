import json
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from kiln_ai.adapters.fine_tune.dataset_formatter import (
    DatasetFormat,
    DatasetFormatter,
    generate_chat_message_response,
    generate_chat_message_toolcall,
    generate_huggingface_chat_template,
    generate_huggingface_chat_template_toolcall,
)
from kiln_ai.datamodel import (
    DatasetSplit,
    DataSource,
    DataSourceType,
    Task,
    TaskOutput,
    TaskRun,
)


@pytest.fixture
def mock_task():
    task = Mock(spec=Task)
    task_runs = [
        TaskRun(
            id=f"run{i}",
            input='{"test": "input"}',
            input_source=DataSource(
                type=DataSourceType.human, properties={"created_by": "test"}
            ),
            output=TaskOutput(
                output='{"test": "output"}',
                source=DataSource(
                    type=DataSourceType.synthetic,
                    properties={
                        "model_name": "test",
                        "model_provider": "test",
                        "adapter_name": "test",
                    },
                ),
            ),
        )
        for i in range(1, 4)
    ]
    task.runs.return_value = task_runs
    return task


@pytest.fixture
def mock_dataset(mock_task):
    dataset = Mock(spec=DatasetSplit)
    dataset.name = "test_dataset"
    dataset.parent_task.return_value = mock_task
    dataset.split_contents = {"train": ["run1", "run2"], "test": ["run3"]}
    return dataset


def test_generate_chat_message_response():
    task_run = TaskRun(
        id="run1",
        input="test input",
        input_source=DataSource(
            type=DataSourceType.human, properties={"created_by": "test"}
        ),
        output=TaskOutput(
            output="test output",
            source=DataSource(
                type=DataSourceType.synthetic,
                properties={
                    "model_name": "test",
                    "model_provider": "test",
                    "adapter_name": "test",
                },
            ),
        ),
    )

    result = generate_chat_message_response(task_run, "system message")

    assert result == {
        "messages": [
            {"role": "system", "content": "system message"},
            {"role": "user", "content": "test input"},
            {"role": "assistant", "content": "test output"},
        ]
    }


def test_generate_chat_message_toolcall():
    task_run = TaskRun(
        id="run1",
        input="test input",
        input_source=DataSource(
            type=DataSourceType.human, properties={"created_by": "test"}
        ),
        output=TaskOutput(
            output='{"key": "value"}',
            source=DataSource(
                type=DataSourceType.synthetic,
                properties={
                    "model_name": "test",
                    "model_provider": "test",
                    "adapter_name": "test",
                },
            ),
        ),
    )

    result = generate_chat_message_toolcall(task_run, "system message")

    assert result == {
        "messages": [
            {"role": "system", "content": "system message"},
            {"role": "user", "content": "test input"},
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
    task_run = TaskRun(
        id="run1",
        input="test input",
        input_source=DataSource(
            type=DataSourceType.human, properties={"created_by": "test"}
        ),
        output=TaskOutput(
            output="invalid json",
            source=DataSource(
                type=DataSourceType.synthetic,
                properties={
                    "model_name": "test",
                    "model_provider": "test",
                    "adapter_name": "test",
                },
            ),
        ),
    )

    with pytest.raises(ValueError, match="Invalid JSON in for tool call"):
        generate_chat_message_toolcall(task_run, "system message")


def test_dataset_formatter_init_no_parent_task(mock_dataset):
    mock_dataset.parent_task.return_value = None

    with pytest.raises(ValueError, match="Dataset has no parent task"):
        DatasetFormatter(mock_dataset, "system message")


def test_dataset_formatter_dump_invalid_format(mock_dataset):
    formatter = DatasetFormatter(mock_dataset, "system message")

    with pytest.raises(ValueError, match="Unsupported format"):
        formatter.dump_to_file("train", "invalid_format")  # type: ignore


def test_dataset_formatter_dump_invalid_split(mock_dataset):
    formatter = DatasetFormatter(mock_dataset, "system message")

    with pytest.raises(ValueError, match="Split invalid_split not found in dataset"):
        formatter.dump_to_file("invalid_split", DatasetFormat.OPENAI_CHAT_JSONL)


def test_dataset_formatter_dump_to_file(mock_dataset, tmp_path):
    formatter = DatasetFormatter(mock_dataset, "system message")
    output_path = tmp_path / "output.jsonl"

    result_path = formatter.dump_to_file(
        "train", DatasetFormat.OPENAI_CHAT_JSONL, output_path
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
            assert data["messages"][1]["content"] == '{"test": "input"}'
            assert data["messages"][2]["content"] == '{"test": "output"}'


def test_dataset_formatter_dump_to_temp_file(mock_dataset):
    formatter = DatasetFormatter(mock_dataset, "system message")

    result_path = formatter.dump_to_file("train", DatasetFormat.OPENAI_CHAT_JSONL)

    assert result_path.exists()
    assert result_path.parent == Path(tempfile.gettempdir())
    assert result_path.name.startswith("test_dataset_train_")
    assert result_path.name.endswith(".jsonl")
    # Verify file contents
    with open(result_path) as f:
        lines = f.readlines()
        assert len(lines) == 2


def test_dataset_formatter_dump_to_file_tool_format(mock_dataset, tmp_path):
    formatter = DatasetFormatter(mock_dataset, "system message")
    output_path = tmp_path / "output.jsonl"

    result_path = formatter.dump_to_file(
        "train", DatasetFormat.OPENAI_CHAT_TOOLCALL_JSONL, output_path
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
            assert data["messages"][1]["content"] == '{"test": "input"}'
            # Check tool call format
            assistant_msg = data["messages"][2]
            assert assistant_msg["content"] is None
            assert "tool_calls" in assistant_msg
            assert len(assistant_msg["tool_calls"]) == 1
            tool_call = assistant_msg["tool_calls"][0]
            assert tool_call["type"] == "function"
            assert tool_call["function"]["name"] == "task_response"
            assert tool_call["function"]["arguments"] == '{"test": "output"}'


def test_generate_huggingface_chat_template():
    task_run = TaskRun(
        id="run1",
        input="test input",
        input_source=DataSource(
            type=DataSourceType.human, properties={"created_by": "test"}
        ),
        output=TaskOutput(
            output="test output",
            source=DataSource(
                type=DataSourceType.synthetic,
                properties={
                    "model_name": "test",
                    "model_provider": "test",
                    "adapter_name": "test",
                },
            ),
        ),
    )

    result = generate_huggingface_chat_template(task_run, "system message")

    assert result == {
        "conversations": [
            {"role": "system", "content": "system message"},
            {"role": "user", "content": "test input"},
            {"role": "assistant", "content": "test output"},
        ]
    }


def test_generate_huggingface_chat_template_toolcall():
    task_run = TaskRun(
        id="run1",
        input="test input",
        input_source=DataSource(
            type=DataSourceType.human, properties={"created_by": "test"}
        ),
        output=TaskOutput(
            output='{"key": "value"}',
            source=DataSource(
                type=DataSourceType.synthetic,
                properties={
                    "model_name": "test",
                    "model_provider": "test",
                    "adapter_name": "test",
                },
            ),
        ),
    )

    result = generate_huggingface_chat_template_toolcall(task_run, "system message")

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


def test_generate_huggingface_chat_template_toolcall_invalid_json():
    task_run = TaskRun(
        id="run1",
        input="test input",
        input_source=DataSource(
            type=DataSourceType.human, properties={"created_by": "test"}
        ),
        output=TaskOutput(
            output="invalid json",
            source=DataSource(
                type=DataSourceType.synthetic,
                properties={
                    "model_name": "test",
                    "model_provider": "test",
                    "adapter_name": "test",
                },
            ),
        ),
    )

    with pytest.raises(ValueError, match="Invalid JSON in for tool call"):
        generate_huggingface_chat_template_toolcall(task_run, "system message")
