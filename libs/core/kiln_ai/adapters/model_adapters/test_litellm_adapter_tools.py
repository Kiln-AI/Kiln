import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from litellm.types.utils import ModelResponse
from litellm.types.utils import Usage as LiteLlmUsage

from kiln_ai import datamodel
from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.ml_model_list import KilnModelProvider, built_in_models
from kiln_ai.adapters.model_adapters.litellm_adapter import (
    LiteLlmAdapter,
    ModelTurnResult,
)
from kiln_ai.adapters.model_adapters.litellm_config import LiteLlmConfig
from kiln_ai.adapters.test_prompt_adaptors import get_all_models_and_providers
from kiln_ai.datamodel import PromptId
from kiln_ai.datamodel.datamodel_enums import ModelProviderName, StructuredOutputMode
from kiln_ai.datamodel.task import RunConfigProperties
from kiln_ai.tools.built_in_tools.math_tools import (
    AddTool,
    DivideTool,
    MultiplyTool,
    SubtractTool,
)
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam


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
async def test_tools_gpt_4_1_mini(tmp_path):
    task = build_test_task(tmp_path)
    await run_simple_task_with_tools(task, "gpt_4_1_mini", ModelProviderName.openai)


@pytest.mark.paid
async def test_tools_gpt_4_1_mini_simplified(tmp_path):
    task = build_test_task(tmp_path)
    await run_simple_task_with_tools(
        task, "gpt_4_1_mini", ModelProviderName.openai, simplified=True
    )


def check_supports_structured_output(model_name: str, provider_name: str):
    for model in built_in_models:
        if model.name != model_name:
            continue
        for provider in model.providers:
            if provider.name != provider_name:
                continue
            if not provider.supports_function_calling:
                pytest.skip(
                    f"Skipping {model.name} {provider.name} because it does not support function calling"
                )
            return
    raise RuntimeError(f"No model {model_name} {provider_name} found")


@pytest.mark.paid
@pytest.mark.ollama
@pytest.mark.parametrize("model_name,provider_name", get_all_models_and_providers())
async def test_tools_all_built_in_models(tmp_path, model_name, provider_name):
    check_supports_structured_output(model_name, provider_name)
    task = build_test_task(tmp_path)
    # For the test of all models run the simplified test, we're checking if it can handle any tool calls, not getting fancy with it
    await run_simple_task_with_tools(task, model_name, provider_name, simplified=True)


async def test_tools_simplied_mocked(tmp_path):
    task = build_test_task(tmp_path)

    # Usage should add up, not just return the last one.
    usage = LiteLlmUsage(
        prompt_tokens=10,
        completion_tokens=20,
        total_tokens=30,
        cost=0.5,
    )

    # Mock 2 responses using tool calls adding 2+2
    # First response: requests add tool call for 2+2
    # Second response: final answer: 4
    # this should trigger proper asserts in the run_simple_task_with_tools function

    # First response: requests add tool call
    mock_response_1 = ModelResponse(
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
                                "arguments": '{"a": 2, "b": 2}',
                            },
                        }
                    ],
                }
            }
        ],
        usage=usage,
    )

    # Second response: final answer
    mock_response_2 = ModelResponse(
        model="gpt-4o-mini",
        choices=[
            {
                "message": {
                    "content": "The answer is [4]",
                    "tool_calls": None,
                    "reasoning_content": "I used a tool",
                }
            }
        ],
        usage=usage,
    )

    # Mock the Config.shared() method to return a mock config with required attributes
    mock_config = Mock()
    mock_config.open_ai_api_key = "mock_api_key"
    mock_config.user_id = "test_user"

    with (
        patch(
            "litellm.acompletion",
            side_effect=[mock_response_1, mock_response_2],
        ),
        patch("kiln_ai.utils.config.Config.shared", return_value=mock_config),
    ):
        task_run = await run_simple_task_with_tools(
            task, "gpt_4_1_mini", ModelProviderName.openai, simplified=True
        )
        assert task_run.usage is not None
        assert task_run.usage.input_tokens == 20
        assert task_run.usage.output_tokens == 40
        assert task_run.usage.total_tokens == 60
        assert task_run.usage.cost == 1.0

        # Check reasoning content in the trace
        trace = task_run.trace
        assert trace is not None
        assert len(trace) == 5
        assert trace[4].get("reasoning_content") == "I used a tool"


async def test_tools_mocked(tmp_path):
    task = build_test_task(tmp_path)

    # Usage should add up, not just return the last one.
    usage = LiteLlmUsage(
        prompt_tokens=10,
        completion_tokens=20,
        total_tokens=30,
        cost=0.5,
    )

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
        usage=usage,
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
        usage=usage,
    )

    # Third response: final answer
    mock_response_3 = ModelResponse(
        model="gpt-4o-mini",
        choices=[{"message": {"content": "The answer is [64]", "tool_calls": None}}],
        usage=usage,
    )

    # Mock the Config.shared() method to return a mock config with required attributes
    mock_config = Mock()
    mock_config.open_ai_api_key = "mock_api_key"
    mock_config.user_id = "test_user"

    with (
        patch(
            "litellm.acompletion",
            side_effect=[mock_response_1, mock_response_2, mock_response_3],
        ),
        patch("kiln_ai.utils.config.Config.shared", return_value=mock_config),
    ):
        task_run = await run_simple_task_with_tools(
            task, "gpt_4_1_mini", ModelProviderName.openai
        )
        assert task_run.usage is not None
        assert task_run.usage.input_tokens == 30
        assert task_run.usage.output_tokens == 60
        assert task_run.usage.total_tokens == 90
        assert task_run.usage.cost == 1.5


async def test_run_model_turn_parallel_tools(tmp_path):
    """Test _run_model_turn with multiple parallel tool calls in a single response."""
    task = build_test_task(tmp_path)
    # Cast to LiteLlmAdapter to access _run_model_turn
    config = LiteLlmConfig(
        run_config_properties=RunConfigProperties(
            structured_output_mode=StructuredOutputMode.json_schema,
            model_name="gpt_4_1_mini",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
        )
    )
    litellm_adapter = LiteLlmAdapter(config=config, kiln_task=task)

    # Mock multiple parallel tool calls
    mock_response = ModelResponse(
        model="gpt-4o-mini",
        choices=[
            {
                "message": {
                    "content": "I'll solve this step by step using the tools.",
                    "tool_calls": [
                        {
                            "id": "tool_call_multiply",
                            "type": "function",
                            "function": {
                                "name": "multiply",
                                "arguments": '{"a": 6, "b": 10}',
                            },
                        },
                        {
                            "id": "tool_call_add",
                            "type": "function",
                            "function": {
                                "name": "add",
                                "arguments": '{"a": 2, "b": 3}',
                            },
                        },
                    ],
                }
            }
        ],
    )

    # Mock final response after tool execution
    final_response = ModelResponse(
        model="gpt-4o-mini",
        choices=[
            {"message": {"content": "The results are 60 and 5", "tool_calls": None}}
        ],
    )

    provider = KilnModelProvider(name=ModelProviderName.openai, model_id="gpt_4_1_mini")

    prior_messages: list[ChatCompletionMessageParam] = [
        {"role": "user", "content": "Calculate 6*10 and 2+3"}
    ]

    # Create tools with spies
    multiply_tool = MultiplyTool()
    multiply_spy = Mock(wraps=multiply_tool)

    add_tool = AddTool()
    add_spy = Mock(wraps=add_tool)

    with patch.object(
        litellm_adapter, "cached_available_tools", return_value=[multiply_spy, add_spy]
    ):
        with patch(
            "litellm.acompletion",
            side_effect=[mock_response, final_response],
        ):
            with patch.object(
                litellm_adapter, "build_completion_kwargs", return_value={}
            ):
                with patch.object(
                    litellm_adapter,
                    "acompletion_checking_response",
                    side_effect=[
                        (mock_response, mock_response.choices[0]),
                        (final_response, final_response.choices[0]),
                    ],
                ):
                    result = await litellm_adapter._run_model_turn(
                        provider, prior_messages, None, False
                    )

    # Verify both tools were called in parallel
    multiply_spy.run.assert_called_once_with(a=6, b=10)
    add_spy.run.assert_called_once_with(a=2, b=3)

    # Verify the result structure
    assert isinstance(result, ModelTurnResult)
    assert result.assistant_message == "The results are 60 and 5"
    assert (
        len(result.all_messages) == 5
    )  # user + assistant + 2 tool results + final assistant


async def test_run_model_turn_sequential_tools(tmp_path):
    """Test _run_model_turn with sequential tool calls across multiple turns."""
    task = build_test_task(tmp_path)
    # Cast to LiteLlmAdapter to access _run_model_turn
    config = LiteLlmConfig(
        run_config_properties=RunConfigProperties(
            structured_output_mode=StructuredOutputMode.json_schema,
            model_name="gpt_4_1_mini",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
        )
    )
    litellm_adapter = LiteLlmAdapter(config=config, kiln_task=task)

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

    # Second response: requests add tool call using result from first
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

    # Final response with answer
    mock_response_3 = ModelResponse(
        model="gpt-4o-mini",
        choices=[
            {"message": {"content": "The final answer is 64", "tool_calls": None}}
        ],
    )

    provider = KilnModelProvider(name=ModelProviderName.openai, model_id="gpt_4_1_mini")

    prior_messages: list[ChatCompletionMessageParam] = [
        {"role": "user", "content": "Calculate (6*10)+4"}
    ]

    # Create tools with spies
    multiply_tool = MultiplyTool()
    multiply_spy = Mock(wraps=multiply_tool)

    add_tool = AddTool()
    add_spy = Mock(wraps=add_tool)

    with patch.object(
        litellm_adapter, "cached_available_tools", return_value=[multiply_spy, add_spy]
    ):
        with patch(
            "litellm.acompletion",
            side_effect=[mock_response_1, mock_response_2, mock_response_3],
        ):
            with patch.object(
                litellm_adapter, "build_completion_kwargs", return_value={}
            ):
                with patch.object(
                    litellm_adapter,
                    "acompletion_checking_response",
                    side_effect=[
                        (mock_response_1, mock_response_1.choices[0]),
                        (mock_response_2, mock_response_2.choices[0]),
                        (mock_response_3, mock_response_3.choices[0]),
                    ],
                ):
                    result = await litellm_adapter._run_model_turn(
                        provider, prior_messages, None, False
                    )

    # Verify tools were called sequentially
    multiply_spy.run.assert_called_once_with(a=6, b=10)
    add_spy.run.assert_called_once_with(a=60, b=4)

    # Verify the result structure
    assert isinstance(result, ModelTurnResult)
    assert result.assistant_message == "The final answer is 64"
    # Messages: user + assistant1 + tool1 + assistant2 + tool2 + final assistant
    assert len(result.all_messages) == 6


async def test_run_model_turn_max_tool_calls_exceeded(tmp_path):
    """Test _run_model_turn raises error when MAX_TOOL_CALLS_PER_TURN is exceeded."""
    task = build_test_task(tmp_path)
    # Cast to LiteLlmAdapter to access _run_model_turn
    config = LiteLlmConfig(
        run_config_properties=RunConfigProperties(
            structured_output_mode=StructuredOutputMode.json_schema,
            model_name="gpt_4_1_mini",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
        )
    )
    litellm_adapter = LiteLlmAdapter(config=config, kiln_task=task)

    # Mock response that always returns a tool call (creates infinite loop)
    mock_response = ModelResponse(
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
                                "arguments": '{"a": 1, "b": 1}',
                            },
                        }
                    ],
                }
            }
        ],
    )

    provider = KilnModelProvider(name=ModelProviderName.openai, model_id="gpt_4_1_mini")

    prior_messages: list[ChatCompletionMessageParam] = [
        {"role": "user", "content": "Keep adding 1+1"}
    ]

    # Create tool with spy
    add_tool = AddTool()
    add_spy = Mock(wraps=add_tool)

    with patch.object(
        litellm_adapter, "cached_available_tools", return_value=[add_spy]
    ):
        with patch(
            "litellm.acompletion",
            return_value=mock_response,
        ):
            with patch.object(
                litellm_adapter, "build_completion_kwargs", return_value={}
            ):
                with patch.object(
                    litellm_adapter,
                    "acompletion_checking_response",
                    return_value=(mock_response, mock_response.choices[0]),
                ):
                    with pytest.raises(RuntimeError, match="Too many tool calls"):
                        await litellm_adapter._run_model_turn(
                            provider, prior_messages, None, False
                        )


async def test_run_model_turn_no_tool_calls(tmp_path):
    """Test _run_model_turn with a simple response that doesn't use tools."""
    task = build_test_task(tmp_path)
    # Cast to LiteLlmAdapter to access _run_model_turn
    config = LiteLlmConfig(
        run_config_properties=RunConfigProperties(
            structured_output_mode=StructuredOutputMode.json_schema,
            model_name="gpt_4_1_mini",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
        )
    )
    litellm_adapter = LiteLlmAdapter(config=config, kiln_task=task)

    # Mock response without tool calls
    mock_response = ModelResponse(
        model="gpt-4o-mini",
        choices=[
            {"message": {"content": "This is a simple response", "tool_calls": None}}
        ],
    )

    provider = KilnModelProvider(name=ModelProviderName.openai, model_id="gpt_4_1_mini")

    prior_messages: list[ChatCompletionMessageParam] = [
        {"role": "user", "content": "Hello, how are you?"}
    ]

    with patch.object(litellm_adapter, "build_completion_kwargs", return_value={}):
        with patch.object(
            litellm_adapter,
            "acompletion_checking_response",
            return_value=(mock_response, mock_response.choices[0]),
        ):
            result = await litellm_adapter._run_model_turn(
                provider, prior_messages, None, False
            )

    # Verify the result structure
    assert isinstance(result, ModelTurnResult)
    assert result.assistant_message == "This is a simple response"
    assert len(result.all_messages) == 2  # user + assistant


# Unit tests for process_tool_calls method
class MockToolCall:
    """Mock class for ChatCompletionMessageToolCall"""

    def __init__(self, id: str, function_name: str, arguments: str):
        self.id = id
        self.function = Mock()
        self.function.name = function_name
        self.function.arguments = arguments
        self.type = "function"


class MockTool:
    """Mock tool class for testing"""

    def __init__(
        self,
        name: str,
        raise_on_run: Exception | None = None,
        return_value: str = "test_result",
    ):
        self._name = name
        self._raise_on_run = raise_on_run
        self._return_value = return_value

    async def name(self) -> str:
        return self._name

    async def toolcall_definition(self) -> dict:
        return {
            "function": {
                "parameters": {
                    "type": "object",
                    "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                    "required": ["a", "b"],
                }
            }
        }

    async def run(self, **kwargs) -> str:
        if self._raise_on_run:
            raise self._raise_on_run
        return self._return_value


async def test_process_tool_calls_none_input(tmp_path):
    """Test process_tool_calls with None input"""
    task = build_test_task(tmp_path)
    config = LiteLlmConfig(
        run_config_properties=RunConfigProperties(
            structured_output_mode=StructuredOutputMode.json_schema,
            model_name="gpt_4_1_mini",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
        )
    )
    litellm_adapter = LiteLlmAdapter(config=config, kiln_task=task)

    assistant_output, tool_messages = await litellm_adapter.process_tool_calls(None)

    assert assistant_output is None
    assert tool_messages == []


async def test_process_tool_calls_empty_list(tmp_path):
    """Test process_tool_calls with empty tool calls list"""
    task = build_test_task(tmp_path)
    config = LiteLlmConfig(
        run_config_properties=RunConfigProperties(
            structured_output_mode=StructuredOutputMode.json_schema,
            model_name="gpt_4_1_mini",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
        )
    )
    litellm_adapter = LiteLlmAdapter(config=config, kiln_task=task)

    assistant_output, tool_messages = await litellm_adapter.process_tool_calls([])

    assert assistant_output is None
    assert tool_messages == []


async def test_process_tool_calls_task_response_only(tmp_path):
    """Test process_tool_calls with only task_response tool call"""
    task = build_test_task(tmp_path)
    config = LiteLlmConfig(
        run_config_properties=RunConfigProperties(
            structured_output_mode=StructuredOutputMode.json_schema,
            model_name="gpt_4_1_mini",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
        )
    )
    litellm_adapter = LiteLlmAdapter(config=config, kiln_task=task)

    tool_calls = [MockToolCall("call_1", "task_response", '{"answer": "42"}')]

    assistant_output, tool_messages = await litellm_adapter.process_tool_calls(
        tool_calls  # type: ignore
    )

    assert assistant_output == '{"answer": "42"}'
    assert tool_messages == []


async def test_process_tool_calls_multiple_task_response(tmp_path):
    """Test process_tool_calls with multiple task_response calls - should keep the last one"""
    task = build_test_task(tmp_path)
    config = LiteLlmConfig(
        run_config_properties=RunConfigProperties(
            structured_output_mode=StructuredOutputMode.json_schema,
            model_name="gpt_4_1_mini",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
        )
    )
    litellm_adapter = LiteLlmAdapter(config=config, kiln_task=task)

    tool_calls = [
        MockToolCall("call_1", "task_response", '{"answer": "first"}'),
        MockToolCall("call_2", "task_response", '{"answer": "second"}'),
    ]

    assistant_output, tool_messages = await litellm_adapter.process_tool_calls(
        tool_calls  # type: ignore
    )

    # Should keep the last task_response
    assert assistant_output == '{"answer": "second"}'
    assert tool_messages == []


async def test_process_tool_calls_normal_tool_success(tmp_path):
    """Test process_tool_calls with successful normal tool call"""
    task = build_test_task(tmp_path)
    config = LiteLlmConfig(
        run_config_properties=RunConfigProperties(
            structured_output_mode=StructuredOutputMode.json_schema,
            model_name="gpt_4_1_mini",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
        )
    )
    litellm_adapter = LiteLlmAdapter(config=config, kiln_task=task)

    mock_tool = MockTool("add", return_value="5")
    tool_calls = [MockToolCall("call_1", "add", '{"a": 2, "b": 3}')]

    with patch.object(
        litellm_adapter, "cached_available_tools", return_value=[mock_tool]
    ):
        assistant_output, tool_messages = await litellm_adapter.process_tool_calls(
            tool_calls  # type: ignore
        )

    assert assistant_output is None
    assert len(tool_messages) == 1
    assert tool_messages[0] == {
        "role": "tool",
        "tool_call_id": "call_1",
        "content": "5",
    }


async def test_process_tool_calls_multiple_normal_tools(tmp_path):
    """Test process_tool_calls with multiple normal tool calls"""
    task = build_test_task(tmp_path)
    config = LiteLlmConfig(
        run_config_properties=RunConfigProperties(
            structured_output_mode=StructuredOutputMode.json_schema,
            model_name="gpt_4_1_mini",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
        )
    )
    litellm_adapter = LiteLlmAdapter(config=config, kiln_task=task)

    mock_tool_add = MockTool("add", return_value="5")
    mock_tool_multiply = MockTool("multiply", return_value="6")
    tool_calls = [
        MockToolCall("call_1", "add", '{"a": 2, "b": 3}'),
        MockToolCall("call_2", "multiply", '{"a": 2, "b": 3}'),
    ]

    with patch.object(
        litellm_adapter,
        "cached_available_tools",
        return_value=[mock_tool_add, mock_tool_multiply],
    ):
        assistant_output, tool_messages = await litellm_adapter.process_tool_calls(
            tool_calls  # type: ignore
        )

    assert assistant_output is None
    assert len(tool_messages) == 2
    assert tool_messages[0]["tool_call_id"] == "call_1"
    assert tool_messages[0]["content"] == "5"
    assert tool_messages[1]["tool_call_id"] == "call_2"
    assert tool_messages[1]["content"] == "6"


async def test_process_tool_calls_tool_not_found(tmp_path):
    """Test process_tool_calls when tool is not found"""
    task = build_test_task(tmp_path)
    config = LiteLlmConfig(
        run_config_properties=RunConfigProperties(
            structured_output_mode=StructuredOutputMode.json_schema,
            model_name="gpt_4_1_mini",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
        )
    )
    litellm_adapter = LiteLlmAdapter(config=config, kiln_task=task)

    tool_calls = [MockToolCall("call_1", "nonexistent_tool", '{"a": 2, "b": 3}')]

    with patch.object(litellm_adapter, "cached_available_tools", return_value=[]):
        with pytest.raises(
            RuntimeError,
            match="A tool named 'nonexistent_tool' was invoked by a model, but was not available",
        ):
            await litellm_adapter.process_tool_calls(tool_calls)  # type: ignore


async def test_process_tool_calls_invalid_json_arguments(tmp_path):
    """Test process_tool_calls with invalid JSON arguments"""
    task = build_test_task(tmp_path)
    config = LiteLlmConfig(
        run_config_properties=RunConfigProperties(
            structured_output_mode=StructuredOutputMode.json_schema,
            model_name="gpt_4_1_mini",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
        )
    )
    litellm_adapter = LiteLlmAdapter(config=config, kiln_task=task)

    mock_tool = MockTool("add")
    tool_calls = [MockToolCall("call_1", "add", "invalid json")]

    with patch.object(
        litellm_adapter, "cached_available_tools", return_value=[mock_tool]
    ):
        with pytest.raises(
            RuntimeError, match="Failed to parse arguments for tool 'add'"
        ):
            await litellm_adapter.process_tool_calls(tool_calls)  # type: ignore


async def test_process_tool_calls_empty_arguments(tmp_path):
    """Test process_tool_calls with empty arguments string"""
    task = build_test_task(tmp_path)
    config = LiteLlmConfig(
        run_config_properties=RunConfigProperties(
            structured_output_mode=StructuredOutputMode.json_schema,
            model_name="gpt_4_1_mini",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
        )
    )
    litellm_adapter = LiteLlmAdapter(config=config, kiln_task=task)

    mock_tool = MockTool("add")
    tool_calls = [MockToolCall("call_1", "add", "")]

    with patch.object(
        litellm_adapter, "cached_available_tools", return_value=[mock_tool]
    ):
        with pytest.raises(
            RuntimeError, match="Failed to parse arguments for tool 'add'"
        ):
            await litellm_adapter.process_tool_calls(tool_calls)  # type: ignore


async def test_process_tool_calls_schema_validation_error(tmp_path):
    """Test process_tool_calls with schema validation error"""
    task = build_test_task(tmp_path)
    config = LiteLlmConfig(
        run_config_properties=RunConfigProperties(
            structured_output_mode=StructuredOutputMode.json_schema,
            model_name="gpt_4_1_mini",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
        )
    )
    litellm_adapter = LiteLlmAdapter(config=config, kiln_task=task)

    mock_tool = MockTool("add")
    # Missing required field 'b'
    tool_calls = [MockToolCall("call_1", "add", '{"a": 2}')]

    with patch.object(
        litellm_adapter, "cached_available_tools", return_value=[mock_tool]
    ):
        with pytest.raises(
            RuntimeError, match="Failed to validate arguments for tool 'add'"
        ):
            await litellm_adapter.process_tool_calls(tool_calls)  # type: ignore


async def test_process_tool_calls_tool_execution_error(tmp_path):
    """Test process_tool_calls when tool execution raises exception"""
    task = build_test_task(tmp_path)
    config = LiteLlmConfig(
        run_config_properties=RunConfigProperties(
            structured_output_mode=StructuredOutputMode.json_schema,
            model_name="gpt_4_1_mini",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
        )
    )
    litellm_adapter = LiteLlmAdapter(config=config, kiln_task=task)

    # Mock tool that raises exception when run
    mock_tool = MockTool("add", raise_on_run=ValueError("Tool execution failed"))
    tool_calls = [MockToolCall("call_1", "add", '{"a": 2, "b": 3}')]

    with patch.object(
        litellm_adapter, "cached_available_tools", return_value=[mock_tool]
    ):
        # This should raise the ValueError from the tool
        with pytest.raises(ValueError, match="Tool execution failed"):
            await litellm_adapter.process_tool_calls(tool_calls)  # type: ignore


async def test_process_tool_calls_complex_result(tmp_path):
    """Test process_tool_calls when tool returns complex object"""
    task = build_test_task(tmp_path)
    config = LiteLlmConfig(
        run_config_properties=RunConfigProperties(
            structured_output_mode=StructuredOutputMode.json_schema,
            model_name="gpt_4_1_mini",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
        )
    )
    litellm_adapter = LiteLlmAdapter(config=config, kiln_task=task)

    complex_result = json.dumps(
        {"status": "success", "result": 42, "metadata": [1, 2, 3]}
    )
    mock_tool = MockTool("add", return_value=complex_result)
    tool_calls = [MockToolCall("call_1", "add", '{"a": 2, "b": 3}')]

    with patch.object(
        litellm_adapter, "cached_available_tools", return_value=[mock_tool]
    ):
        assistant_output, tool_messages = await litellm_adapter.process_tool_calls(
            tool_calls  # type: ignore
        )

    assert assistant_output is None
    assert len(tool_messages) == 1
    assert tool_messages[0]["content"] == complex_result


async def test_process_tool_calls_task_response_with_normal_tools_error(tmp_path):
    """Test process_tool_calls raises error when mixing task_response with normal tools"""
    task = build_test_task(tmp_path)
    config = LiteLlmConfig(
        run_config_properties=RunConfigProperties(
            structured_output_mode=StructuredOutputMode.json_schema,
            model_name="gpt_4_1_mini",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
        )
    )
    litellm_adapter = LiteLlmAdapter(config=config, kiln_task=task)

    mock_tool = MockTool("add", return_value="5")
    tool_calls = [
        MockToolCall("call_1", "task_response", '{"answer": "42"}'),
        MockToolCall("call_2", "add", '{"a": 2, "b": 3}'),
    ]

    with patch.object(
        litellm_adapter, "cached_available_tools", return_value=[mock_tool]
    ):
        with pytest.raises(
            RuntimeError,
            match="task_response tool call and other tool calls were both provided",
        ):
            await litellm_adapter.process_tool_calls(tool_calls)  # type: ignore
