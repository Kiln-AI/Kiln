from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from litellm.types.utils import ModelResponse

from kiln_ai import datamodel
from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.datamodel import PromptId
from kiln_ai.datamodel.task import RunConfigProperties
from kiln_ai.tools.built_in_tools.math_tools import (
    AddTool,
    DivideTool,
    MultiplyTool,
    SubtractTool,
)


def build_test_task(tmp_path: Path):
    project = datamodel.Project(name="test", path=tmp_path / "test.kiln")
    project.save_to_file()
    assert project.name == "test"

    r1 = datamodel.TaskRequirement(
        name="BEDMAS",
        instruction="You follow order of mathematical operation (BEDMAS)",
    )
    r2 = datamodel.TaskRequirement(
        name="only basic math",
        instruction="If the problem has anything other than addition, subtraction, multiplication, division, and brackets, you will not answer it. Reply instead with 'I'm just a basic calculator, I don't know how to do that'.",
    )
    r3 = datamodel.TaskRequirement(
        name="use tools for math",
        instruction="Use the tools provided for math tasks",
    )
    r4 = datamodel.TaskRequirement(
        name="Answer format",
        instruction="The answer can contain any content about your reasoning, but at the end it should include the final answer in numerals in square brackets. For example if the answer is one hundred, the end of your response should be [100].",
    )
    task = datamodel.Task(
        parent=project,
        name="test task",
        instruction="You are an assistant which performs math tasks provided in plain text.",
        requirements=[r1, r2, r3, r4],
    )
    task.save_to_file()
    assert task.name == "test task"
    assert len(task.requirements) == 4
    return task


async def run_simple_task_with_tools(
    task: datamodel.Task,
    model_name: str,
    provider: str,
    prompt_id: PromptId | None = None,
) -> datamodel.TaskRun:
    adapter = adapter_for_task(
        task,
        RunConfigProperties(
            structured_output_mode="json_schema",
            model_name=model_name,
            model_provider_name=provider,
            prompt_id=prompt_id or "simple_prompt_builder",
        ),
    )

    # Create tools with MultiplyTool wrapped in a spy
    multiply_tool = MultiplyTool()
    multiply_spy = Mock(wraps=multiply_tool)
    add_tool = AddTool()
    add_spy = Mock(wraps=add_tool)
    mock_math_tools = [add_spy, SubtractTool(), multiply_spy, DivideTool()]

    with patch.object(adapter, "available_tools", return_value=mock_math_tools):
        run = await adapter.invoke(
            "You should answer the following question: four plus six times 10"
        )

        # Verify that MultiplyTool.run was called with correct parameters
        multiply_spy.run.assert_called()
        multiply_call_args = multiply_spy.run.call_args
        multiply_kwargs = multiply_call_args.kwargs
        # Check that multiply was called with a=6, b=10 (or vice versa)
        assert (multiply_kwargs.get("a") == 6 and multiply_kwargs.get("b") == 10) or (
            multiply_kwargs.get("a") == 10 and multiply_kwargs.get("b") == 6
        ), (
            f"Expected multiply to be called with a=6, b=10 or a=10, b=6, but got {multiply_kwargs}"
        )

        # Verify that AddTool.run was called with correct parameters
        add_spy.run.assert_called()
        add_call_args = add_spy.run.call_args
        add_kwargs = add_call_args.kwargs
        # Check that add was called with a=60, b=4 (or vice versa)
        assert (add_kwargs.get("a") == 60 and add_kwargs.get("b") == 4) or (
            add_kwargs.get("a") == 4 and add_kwargs.get("b") == 60
        ), (
            f"Expected add to be called with a=60, b=4 or a=4, b=60, but got {add_kwargs}"
        )

        assert "64" in run.output.output
        assert run.id is not None
        assert (
            run.input
            == "You should answer the following question: four plus six times 10"
        )
        assert "64" in run.output.output
        source_props = run.output.source.properties if run.output.source else {}
        assert source_props["adapter_name"] in [
            "kiln_langchain_adapter",
            "kiln_openai_compatible_adapter",
        ]
        assert source_props["model_name"] == model_name
        assert source_props["model_provider"] == provider
        if prompt_id is None:
            assert source_props["prompt_id"] == "simple_prompt_builder"
        else:
            assert source_props["prompt_id"] == prompt_id
        return run


@pytest.mark.paid
async def test_tools_gpt_4_1_mini(tmp_path):
    task = build_test_task(tmp_path)
    await run_simple_task_with_tools(task, "gpt_4_1_mini", "openai")


async def test_tools_mocked(tmp_path):
    task = build_test_task(tmp_path)

    # Mock 3 responses using tool calls for BEDMAS operations matching the test math problem: (6*10)+4
    # First response: requests multiply tool call for 6*10
    # Second response: requests add tool call for 60+4
    # Third response: final answer: 64
    # this should trigger proper asserts in the run_simple_task_with_tools function

    # First response: requests multiply tool call
    mock_response_1 = ModelResponse(
        model="gpt-4o-mini",
        choices=[
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "tool_call_multiply",
                            "type": "function",
                            "function": {
                                "name": "multiply",
                                "arguments": '{"a": 6, "b": 10}',
                            },
                        }
                    ],
                }
            }
        ],
    )

    # Second response: requests add tool call
    mock_response_2 = ModelResponse(
        model="gpt-4o-mini",
        choices=[
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "tool_call_add",
                            "type": "function",
                            "function": {
                                "name": "add",
                                "arguments": '{"a": 60, "b": 4}',
                            },
                        }
                    ],
                }
            }
        ],
    )

    # Third response: final answer
    mock_response_3 = ModelResponse(
        model="gpt-4o-mini",
        choices=[{"message": {"content": "The answer is [64]", "tool_calls": None}}],
    )

    with patch(
        "litellm.acompletion",
        side_effect=[mock_response_1, mock_response_2, mock_response_3],
    ):
        await run_simple_task_with_tools(task, "gpt_4_1_mini", "openai")
