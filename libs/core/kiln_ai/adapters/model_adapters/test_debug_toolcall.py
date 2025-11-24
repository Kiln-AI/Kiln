import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from kiln_ai import datamodel
from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.datamodel import PromptId
from kiln_ai.datamodel.datamodel_enums import ModelProviderName, StructuredOutputMode
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
        instruction="Always use the tools provided for math tasks",
    )
    r4 = datamodel.TaskRequirement(
        name="Answer format",
        instruction="The answer can contain any content about your reasoning, but at the end it should include the final answer in numerals in square brackets. For example if the answer is one hundred, the end of your response should be [100].",
    )
    task = datamodel.Task(
        parent=project,
        name="test task",
        instruction="You are an assistant which performs math tasks provided in plain text using functions/tools.\n\nYou must use function calling (tools) for math tasks or you will be penalized. For example if requested to answer 2+2, you must call the 'add' function with a=2 and b=2 or the answer will be rejected.",
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
    simplified: bool = False,
    prompt_id: PromptId | None = None,
) -> datamodel.TaskRun:
    adapter = adapter_for_task(
        task,
        RunConfigProperties(
            structured_output_mode=StructuredOutputMode.json_schema,
            model_name=model_name,
            model_provider_name=ModelProviderName(provider),
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
        if simplified:
            run = await adapter.invoke("what is 2+2")

            # Verify that AddTool.run was called with correct parameters
            add_spy.run.assert_called()
            add_call_args = add_spy.run.call_args
            assert add_call_args.args[0].allow_saving  # First arg is ToolCallContext
            add_kwargs = add_call_args.kwargs
            assert add_kwargs.get("a") == 2
            assert add_kwargs.get("b") == 2

            assert "4" in run.output.output

            trace = run.trace
            assert trace is not None
            assert len(trace) == 5
            assert trace[0]["role"] == "system"
            assert trace[1]["role"] == "user"
            assert trace[2]["role"] == "assistant"
            assert trace[3]["role"] == "tool"
            assert trace[3]["content"] == "4"
            assert trace[3]["tool_call_id"] is not None
            assert trace[4]["role"] == "assistant"
            assert "[4]" in trace[4]["content"]  # type: ignore

            # Deep dive on tool_calls, which we build ourselves
            tool_calls = trace[2].get("tool_calls", None)
            assert tool_calls is not None
            assert len(tool_calls) == 1
            assert tool_calls[0]["id"]  # not None or empty
            assert tool_calls[0]["function"]["name"] == "add"
            json_args = json.loads(tool_calls[0]["function"]["arguments"])
            assert json_args["a"] == 2
            assert json_args["b"] == 2
        else:
            run = await adapter.invoke(
                "You should answer the following question: four plus six times 10"
            )

            # Verify that MultiplyTool.run was called with correct parameters
            multiply_spy.run.assert_called()
            multiply_call_args = multiply_spy.run.call_args
            assert multiply_call_args.args[
                0
            ].allow_saving  # First arg is ToolCallContext
            multiply_kwargs = multiply_call_args.kwargs
            # Check that multiply was called with a=6, b=10 (or vice versa)
            assert (
                multiply_kwargs.get("a") == 6 and multiply_kwargs.get("b") == 10
            ) or (multiply_kwargs.get("a") == 10 and multiply_kwargs.get("b") == 6), (
                f"Expected multiply to be called with a=6, b=10 or a=10, b=6, but got {multiply_kwargs}"
            )

            # Verify that AddTool.run was called with correct parameters
            add_spy.run.assert_called()
            add_call_args = add_spy.run.call_args
            assert add_call_args.args[0].allow_saving  # First arg is ToolCallContext
            add_kwargs = add_call_args.kwargs
            # Check that add was called with a=60, b=4 (or vice versa)
            assert (add_kwargs.get("a") == 60 and add_kwargs.get("b") == 4) or (
                add_kwargs.get("a") == 4 and add_kwargs.get("b") == 60
            ), (
                f"Expected add to be called with a=60, b=4 or a=4, b=60, but got {add_kwargs}"
            )

            assert "64" in run.output.output
            assert (
                run.input
                == "You should answer the following question: four plus six times 10"
            )
            assert "64" in run.output.output

            trace = run.trace
            assert trace is not None
            assert len(trace) == 7
            assert trace[0]["role"] == "system"
            assert trace[1]["role"] == "user"
            assert trace[2]["role"] == "assistant"
            assert trace[3]["role"] == "tool"
            assert trace[3]["content"] == "60"
            assert trace[4]["role"] == "assistant"
            assert trace[5]["role"] == "tool"
            assert trace[5]["content"] == "64"
            assert trace[6]["role"] == "assistant"
            assert "[64]" in trace[6]["content"]  # type: ignore

        assert run.id is not None
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
async def test_debug_tool_call_gemini_3_pro_preview_openrouter(tmp_path):
    task = build_test_task(tmp_path)
    await run_simple_task_with_tools(
        task, "gemini_3_pro_preview", ModelProviderName.openrouter, simplified=True
    )


@pytest.mark.paid
async def test_debug_tool_call_gemini_3_pro_preview_gemini(tmp_path):
    task = build_test_task(tmp_path)
    await run_simple_task_with_tools(
        task, "gemini_3_pro_preview", ModelProviderName.gemini_api, simplified=True
    )
