import json
import os
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.model_adapters.base_adapter import RunOutput
from kiln_ai.adapters.model_adapters.litellm_adapter import LiteLlmAdapter
from kiln_ai.adapters.repair.repair_task import (
    RepairTaskInput,
    RepairTaskRun,
)
from kiln_ai.datamodel import (
    DataSource,
    DataSourceType,
    Priority,
    Task,
    TaskOutput,
    TaskRequirement,
    TaskRun,
)

json_joke_schema = """{
  "type": "object",
  "properties": {
    "setup": {
      "description": "The setup of the joke",
      "title": "Setup",
      "type": "string"
    },
    "punchline": {
      "description": "The punchline to the joke",
      "title": "Punchline",
      "type": "string"
    },
    "rating": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "How funny the joke is, from 1 to 10",
      "title": "Rating"
    }
  },
  "required": [
    "setup",
    "punchline"
  ]
}
"""


@pytest.fixture
def sample_task(tmp_path):
    task_path = tmp_path / "task.kiln"
    task = Task(
        name="Joke Generator",
        path=task_path,
        description="Generate a funny joke",
        instruction="Create a joke with a setup and punchline",
        requirements=[
            TaskRequirement(
                id="req1",
                name="Humor",
                instruction="The joke should be funny and appropriate",
                priority=Priority.p1,
            )
        ],
        output_json_schema=json_joke_schema,
    )
    task.save_to_file()
    return task


@pytest.fixture
def sample_task_run(sample_task):
    task_run = TaskRun(
        parent=sample_task,
        input='{"topic": "chicken"}',
        input_source=DataSource(
            type=DataSourceType.human, properties={"created_by": "Jane Doe"}
        ),
        output=TaskOutput(
            output='{"setup": "Why did the chicken cross the road?", "punchline": "To get to the other side", "rating": null}',
            source=DataSource(
                type=DataSourceType.synthetic,
                properties={
                    "model_name": "gpt_4o",
                    "model_provider": "openai",
                    "adapter_name": "langchain_adapter",
                    "prompt_id": "simple_prompt_builder",
                },
            ),
        ),
    )
    task_run.save_to_file()
    return task_run


@pytest.fixture
def sample_repair_data(sample_task, sample_task_run):
    return {
        "original_task": sample_task,
        "task_run": sample_task_run,
        "evaluator_feedback": "The joke is too cliché. Please come up with a more original chicken-related joke.",
    }


def test_build_repair_task_input(sample_repair_data):
    result = RepairTaskRun.build_repair_task_input(**sample_repair_data)

    assert isinstance(result, RepairTaskInput)
    assert "Create a joke with a setup and punchline" in result.original_prompt
    assert "1) The joke should be funny and appropriate" in result.original_prompt
    assert result.original_input == '{"topic": "chicken"}'
    assert (
        result.original_output
        == '{"setup": "Why did the chicken cross the road?", "punchline": "To get to the other side", "rating": null}'
    )
    assert (
        result.evaluator_feedback
        == "The joke is too cliché. Please come up with a more original chicken-related joke."
    )


def test_repair_input_schema():
    schema = RepairTaskInput.model_json_schema()
    assert schema["type"] == "object"
    assert "original_prompt" in schema["properties"]
    assert "original_input" in schema["properties"]
    assert "original_output" in schema["properties"]
    assert "evaluator_feedback" in schema["properties"]


def test_repair_task_initialization(sample_task):
    repair_task = RepairTaskRun(sample_task)

    assert repair_task.name == "Repair"
    assert "Repair a task run" in repair_task.description
    assert "You are an assistant which helps improve output" in repair_task.instruction
    assert len(repair_task.requirements) == 1
    assert repair_task.requirements[0].name == "Follow Eval Feedback"
    assert repair_task.input_json_schema == json.dumps(
        RepairTaskInput.model_json_schema()
    )
    assert repair_task.output_json_schema == sample_task.output_json_schema


def test_build_repair_task_input_with_empty_values(sample_task, sample_task_run):
    # Arrange
    sample_task_run.input = ""
    sample_task_run.output.output = ""

    # Act & Assert
    with pytest.raises(ValidationError, match="evaluator_feedback"):
        RepairTaskRun.build_repair_task_input(
            original_task=sample_task, task_run=sample_task_run, evaluator_feedback=""
        )

    # Test that it works with non-empty feedback
    result = RepairTaskRun.build_repair_task_input(
        original_task=sample_task,
        task_run=sample_task_run,
        evaluator_feedback="Some feedback",
    )
    assert isinstance(result, RepairTaskInput)
    assert result.evaluator_feedback == "Some feedback"


@pytest.mark.parametrize("invalid_input", [{}])
def test_build_repair_task_input_with_invalid_input(invalid_input):
    # Act & Assert
    with pytest.raises(TypeError):
        RepairTaskRun.build_repair_task_input(invalid_input)


@pytest.mark.paid
async def test_live_run(sample_task, sample_task_run, sample_repair_data):
    if os.getenv("GROQ_API_KEY") is None:
        pytest.skip("GROQ_API_KEY not set")
    repair_task = RepairTaskRun(sample_task)
    repair_task_input = RepairTaskRun.build_repair_task_input(**sample_repair_data)
    assert isinstance(repair_task_input, RepairTaskInput)

    adapter = adapter_for_task(repair_task, model_name="llama_3_1_8b", provider="groq")

    run = await adapter.invoke(repair_task_input.model_dump())
    assert run is not None
    assert "Please come up with a more original chicken-related joke." in run.input
    parsed_output = json.loads(run.output.output)
    assert "setup" in parsed_output
    assert "punchline" in parsed_output
    assert run.output.source.properties == {
        "adapter_name": "kiln_langchain_adapter",
        "model_name": "llama_3_1_8b",
        "model_provider": "groq",
        "prompt_id": "simple_prompt_builder",
    }


@pytest.mark.asyncio
async def test_mocked_repair_task_run(sample_task, sample_task_run, sample_repair_data):
    repair_task = RepairTaskRun(sample_task)
    repair_task_input = RepairTaskRun.build_repair_task_input(**sample_repair_data)
    assert isinstance(repair_task_input, RepairTaskInput)

    mocked_output = {
        "setup": "Why did the chicken join a band?",
        "punchline": "Because it had excellent drumsticks!",
        "rating": 8,
    }

    with patch.object(LiteLlmAdapter, "_run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = RunOutput(
            output=mocked_output, intermediate_outputs=None
        )

        adapter = adapter_for_task(
            repair_task, model_name="llama_3_1_8b", provider="ollama"
        )

        run = await adapter.invoke(repair_task_input.model_dump())

    assert run is not None
    assert run.id is None
    assert "Please come up with a more original chicken-related joke." in run.input

    parsed_output = json.loads(run.output.output)
    assert parsed_output == mocked_output
    assert run.output.source.properties == {
        "adapter_name": "kiln_openai_compatible_adapter",
        "model_name": "llama_3_1_8b",
        "model_provider": "ollama",
        "prompt_id": "simple_prompt_builder",
    }
    assert run.input_source.type == DataSourceType.human
    assert "created_by" in run.input_source.properties

    # Verify that the mock was called
    mock_run.assert_called_once()
