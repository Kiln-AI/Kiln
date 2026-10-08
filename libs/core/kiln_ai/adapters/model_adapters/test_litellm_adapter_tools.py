import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from litellm.types.utils import Message as LiteLLMMessage
from litellm.types.utils import ModelResponse
from litellm.types.utils import Usage as LiteLlmUsage

from kiln_ai import datamodel
from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.ml_model_list import KilnModelProvider, built_in_models
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.adapters.model_adapters.litellm_adapter import (
    LiteLlmAdapter,
    ModelTurnResult,
)
from kiln_ai.adapters.model_adapters.litellm_config import LiteLlmConfig
from kiln_ai.adapters.test_prompt_adaptors import get_all_models_and_providers
from kiln_ai.datamodel import PromptId
from kiln_ai.datamodel.datamodel_enums import ModelProviderName, StructuredOutputMode
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.datamodel.tool_id import ToolId, build_world_tool_id
from kiln_ai.datamodel.world import OpenEnvTool, World, WorldEpisode, WorldReset
from kiln_ai.run_context import EpisodeContext
from kiln_ai.tools.base_tool import ToolCallContext, ToolCallResult, UnmanagedKilnTool
from kiln_ai.tools.built_in_tools.math_tools import (
    AddTool,
    DivideTool,
    MultiplyTool,
    SubtractTool,
)
from kiln_ai.tools.kiln_task_tool import KilnTaskToolResult
from kiln_ai.tools.world_tool import OpenEnvToolProxy
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam
from kiln_ai.worlds.session_manager import ToolCallOutcome


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
        KilnAgentRunConfigProperties(
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
            assert trace[3]["content"] in ["4", "4.0"]
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
@pytest.mark.prerelease
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

    responses = [mock_response_1, mock_response_2]

    async def mock_acompletion_checking_response(self, **kwargs):
        response = responses.pop(0)
        return response, response.choices[0]

    with (
        patch.object(
            LiteLlmAdapter,
            "acompletion_checking_response",
            new=mock_acompletion_checking_response,
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
        patch.object(
            LiteLlmAdapter,
            "acompletion_checking_response",
            new=AsyncMock(
                side_effect=[
                    (mock_response_1, mock_response_1.choices[0]),
                    (mock_response_2, mock_response_2.choices[0]),
                    (mock_response_3, mock_response_3.choices[0]),
                ]
            ),
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
        run_config_properties=KilnAgentRunConfigProperties(
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
    # The context is passed as the first positional argument, not as a keyword argument
    multiply_spy.run.assert_called_once()
    multiply_call_args = multiply_spy.run.call_args
    assert multiply_call_args.args[0].allow_saving  # First arg is ToolCallContext
    assert multiply_call_args.kwargs == {"a": 6, "b": 10}

    add_spy.run.assert_called_once()
    add_call_args = add_spy.run.call_args
    assert add_call_args.args[0].allow_saving  # First arg is ToolCallContext
    assert add_call_args.kwargs == {"a": 2, "b": 3}

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
        run_config_properties=KilnAgentRunConfigProperties(
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
    # The context is passed as the first positional argument, not as a keyword argument
    multiply_spy.run.assert_called_once()
    multiply_call_args = multiply_spy.run.call_args
    assert multiply_call_args.args[0].allow_saving  # First arg is ToolCallContext
    assert multiply_call_args.kwargs == {"a": 6, "b": 10}

    add_spy.run.assert_called_once()
    add_call_args = add_spy.run.call_args
    assert add_call_args.args[0].allow_saving  # First arg is ToolCallContext
    assert add_call_args.kwargs == {"a": 60, "b": 4}

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
        run_config_properties=KilnAgentRunConfigProperties(
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
        run_config_properties=KilnAgentRunConfigProperties(
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

    async def run(
        self, context: ToolCallContext | None = None, **kwargs
    ) -> ToolCallResult:
        if self._raise_on_run:
            raise self._raise_on_run
        return ToolCallResult(output=self._return_value)

    async def id(self) -> ToolId:
        """Mock implementation of id for testing."""
        return f"mock_tool_{self._name}"


class MockKilnTaskTool:
    """Mock tool class that returns KilnTaskToolResult for testing"""

    def __init__(
        self,
        name: str,
        raise_on_run: Exception | None = None,
        output: str = "kiln_task_output",
        kiln_task_tool_data: str = "project_id:::tool_id:::task_id:::run_id",
    ):
        self._name = name
        self._raise_on_run = raise_on_run
        self._output = output
        self._kiln_task_tool_data = kiln_task_tool_data

    async def name(self) -> str:
        return self._name

    async def toolcall_definition(self) -> dict:
        return {
            "function": {
                "parameters": {
                    "type": "object",
                    "properties": {"input": {"type": "string"}},
                    "required": ["input"],
                }
            }
        }

    async def run(
        self, context: ToolCallContext | None = None, **kwargs
    ) -> KilnTaskToolResult:
        if self._raise_on_run:
            raise self._raise_on_run
        return KilnTaskToolResult(
            output=self._output,
            kiln_task_tool_data=self._kiln_task_tool_data,
        )

    async def id(self) -> ToolId:
        """Mock implementation of id for testing."""
        return f"mock_kiln_task_tool_{self._name}"


async def test_process_tool_calls_none_input(tmp_path):
    """Test process_tool_calls with None input"""
    task = build_test_task(tmp_path)
    config = LiteLlmConfig(
        run_config_properties=KilnAgentRunConfigProperties(
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
        run_config_properties=KilnAgentRunConfigProperties(
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
        run_config_properties=KilnAgentRunConfigProperties(
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
        run_config_properties=KilnAgentRunConfigProperties(
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
        run_config_properties=KilnAgentRunConfigProperties(
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
        "kiln_task_tool_data": None,
        "is_error": None,
        "error_message": None,
    }


class _RunnableUnmanagedKilnToolForTest(UnmanagedKilnTool):
    async def run(
        self, context: ToolCallContext | None = None, **kwargs
    ) -> ToolCallResult:
        return ToolCallResult(output="from_unmanaged")


async def test_process_tool_calls_unmanaged_tool_success(tmp_path):
    """process_tool_calls resolves and runs tools from AdapterConfig.unmanaged_tools."""
    task = build_test_task(tmp_path)
    ext = _RunnableUnmanagedKilnToolForTest(
        tool_id="kiln_unmanaged::proc_test",
        name="unmanaged_do",
        description="test unmanaged",
        parameters_schema={
            "type": "object",
            "properties": {"x": {"type": "number"}},
            "required": ["x"],
        },
    )
    config = LiteLlmConfig(
        run_config_properties=KilnAgentRunConfigProperties(
            structured_output_mode=StructuredOutputMode.json_schema,
            model_name="gpt_4_1_mini",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
        )
    )
    litellm_adapter = LiteLlmAdapter(
        config=config,
        kiln_task=task,
        base_adapter_config=AdapterConfig(unmanaged_tools=[ext]),
    )
    tool_calls = [MockToolCall("call_1", "unmanaged_do", '{"x": 1}')]

    with patch.object(litellm_adapter, "cached_available_tools", return_value=[]):
        assistant_output, tool_messages = await litellm_adapter.process_tool_calls(
            tool_calls  # type: ignore
        )

    assert assistant_output is None
    assert len(tool_messages) == 1
    assert tool_messages[0]["content"] == "from_unmanaged"
    assert tool_messages[0]["tool_call_id"] == "call_1"


async def test_process_tool_calls_multiple_normal_tools(tmp_path):
    """Test process_tool_calls with multiple normal tool calls"""
    task = build_test_task(tmp_path)
    config = LiteLlmConfig(
        run_config_properties=KilnAgentRunConfigProperties(
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
    assert tool_messages[0].get("kiln_task_tool_data") is None
    assert tool_messages[1]["tool_call_id"] == "call_2"
    assert tool_messages[1]["content"] == "6"
    assert tool_messages[1].get("kiln_task_tool_data") is None


def build_tools_adapter(tmp_path: Path) -> LiteLlmAdapter:
    config = LiteLlmConfig(
        run_config_properties=KilnAgentRunConfigProperties(
            structured_output_mode=StructuredOutputMode.json_schema,
            model_name="gpt_4_1_mini",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
        )
    )
    return LiteLlmAdapter(config=config, kiln_task=build_test_task(tmp_path))


SCHEMA_ERROR_PREFIX = "Failed to validate arguments for tool 'add'. The arguments didn't match the tool's schema. The arguments were: "


@pytest.mark.parametrize(
    "tool_name,arguments,expected_prefix,expected_detail",
    [
        pytest.param(
            "nonexistent_tool",
            '{"a": 2, "b": 3}',
            "A tool named 'nonexistent_tool' was invoked by a model, but was not available.",
            None,
            id="unknown",
        ),
        pytest.param(
            "add",
            "invalid json",
            "Failed to parse arguments for tool 'add' (should be JSON): invalid json",
            None,
            id="invalid_json",
        ),
        pytest.param(
            "add",
            "",
            "Failed to parse arguments for tool 'add' (should be JSON): ",
            None,
            id="empty",
        ),
        pytest.param(
            "add",
            None,
            "Failed to parse arguments for tool 'add' (should be JSON): None",
            None,
            id="none_args",
        ),
        pytest.param(
            "add",
            '{"a": 2}',
            SCHEMA_ERROR_PREFIX + "{'a': 2}\n The error was: ",
            "'b' is a required property",
            id="schema_miss",
        ),
        pytest.param(
            "add",
            "[1, 2]",
            SCHEMA_ERROR_PREFIX + "[1, 2]\n The error was: ",
            "is not of type 'object'",
            id="non_object_json",
        ),
    ],
)
async def test_process_tool_calls_bad_call_returns_tool_error(
    tmp_path, tool_name, arguments, expected_prefix, expected_detail
):
    """A call the adapter can't run comes back to the model as an error tool message."""
    litellm_adapter = build_tools_adapter(tmp_path)
    tool_calls = [MockToolCall("call_1", tool_name, arguments)]

    with patch.object(
        litellm_adapter, "cached_available_tools", return_value=[MockTool("add")]
    ):
        assistant_output, tool_messages = await litellm_adapter.process_tool_calls(
            tool_calls  # type: ignore
        )

    assert assistant_output is None
    assert len(tool_messages) == 1
    message = tool_messages[0]
    assert message["role"] == "tool"
    assert message["tool_call_id"] == "call_1"
    assert message.get("is_error") is True
    content = message["content"]
    assert isinstance(content, str)
    assert message.get("error_message") == content
    if expected_detail is None:
        assert content == expected_prefix
    else:
        assert content.startswith(expected_prefix)
        assert expected_detail in content.removeprefix(expected_prefix)


async def test_process_tool_calls_bad_call_does_not_block_other_calls(tmp_path):
    litellm_adapter = build_tools_adapter(tmp_path)
    tool_calls = [
        MockToolCall("call_1", "add", '{"a": 2, "b": 3}'),
        MockToolCall("call_2", "nonexistent_tool", '{"a": 2, "b": 3}'),
        MockToolCall("call_3", "multiply", '{"a": 2, "b": 3}'),
        MockToolCall("call_4", "add", "invalid json"),
    ]

    with patch.object(
        litellm_adapter,
        "cached_available_tools",
        return_value=[
            MockTool("add", return_value="5"),
            MockTool("multiply", return_value="6"),
        ],
    ):
        assistant_output, tool_messages = await litellm_adapter.process_tool_calls(
            tool_calls  # type: ignore
        )

    assert assistant_output is None
    assert [m["tool_call_id"] for m in tool_messages] == [
        "call_1",
        "call_2",
        "call_3",
        "call_4",
    ]
    assert tool_messages[0]["content"] == "5"
    assert tool_messages[0].get("is_error") is None
    assert tool_messages[2]["content"] == "6"
    assert tool_messages[2].get("is_error") is None
    assert tool_messages[1].get("is_error") is True
    assert tool_messages[1]["content"] == (
        "A tool named 'nonexistent_tool' was invoked by a model, but was not available."
    )
    assert tool_messages[3].get("is_error") is True
    assert tool_messages[3]["content"] == (
        "Failed to parse arguments for tool 'add' (should be JSON): invalid json"
    )


async def test_process_tool_calls_invalid_args_tool_not_run(tmp_path):
    litellm_adapter = build_tools_adapter(tmp_path)
    tool = MockTool("add", raise_on_run=AssertionError("must not run"))
    tool_calls = [MockToolCall("call_1", "add", '{"a": "two"}')]

    with patch.object(litellm_adapter, "cached_available_tools", return_value=[tool]):
        _, tool_messages = await litellm_adapter.process_tool_calls(
            tool_calls  # type: ignore
        )

    assert len(tool_messages) == 1
    assert tool_messages[0].get("is_error") is True
    assert str(tool_messages[0]["content"]).startswith(SCHEMA_ERROR_PREFIX)


async def test_process_tool_calls_task_response_with_invalid_call_raises(tmp_path):
    litellm_adapter = build_tools_adapter(tmp_path)
    tool_calls = [
        MockToolCall("call_1", "task_response", '{"answer": "42"}'),
        MockToolCall("call_2", "nonexistent_tool", "{}"),
    ]

    with patch.object(litellm_adapter, "cached_available_tools", return_value=[]):
        with pytest.raises(
            RuntimeError,
            match="task_response tool call and other tool calls were both provided",
        ):
            await litellm_adapter.process_tool_calls(tool_calls)  # type: ignore


async def test_process_tool_calls_tool_execution_error(tmp_path):
    """Test process_tool_calls when tool execution raises exception"""
    task = build_test_task(tmp_path)
    config = LiteLlmConfig(
        run_config_properties=KilnAgentRunConfigProperties(
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
        run_config_properties=KilnAgentRunConfigProperties(
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
    assert tool_messages[0].get("kiln_task_tool_data") is None


async def test_process_tool_calls_task_response_with_normal_tools_error(tmp_path):
    """Test process_tool_calls raises error when mixing task_response with normal tools"""
    task = build_test_task(tmp_path)
    config = LiteLlmConfig(
        run_config_properties=KilnAgentRunConfigProperties(
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


async def test_run_model_turn_return_on_tool_call_mixed_task_response_raises(
    tmp_path: Path,
):
    """return_on_tool_call must not short-circuit when task_response is mixed with other tools."""
    task = build_test_task(tmp_path)
    config = LiteLlmConfig(
        run_config_properties=KilnAgentRunConfigProperties(
            structured_output_mode=StructuredOutputMode.json_schema,
            model_name="gpt_4_1_mini",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
        )
    )
    litellm_adapter = LiteLlmAdapter(
        config=config,
        kiln_task=task,
        base_adapter_config=AdapterConfig(return_on_tool_call=True),
    )

    mock_response = ModelResponse(
        model="gpt-4o-mini",
        choices=[
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_tr",
                            "type": "function",
                            "function": {
                                "name": "task_response",
                                "arguments": '{"answer": "42"}',
                            },
                        },
                        {
                            "id": "call_add",
                            "type": "function",
                            "function": {
                                "name": "add",
                                "arguments": '{"a": 1, "b": 2}',
                            },
                        },
                    ],
                }
            }
        ],
    )

    provider = KilnModelProvider(name=ModelProviderName.openai, model_id="gpt_4_1_mini")
    prior_messages: list[ChatCompletionMessageParam] = [
        {"role": "user", "content": "hello"}
    ]

    with patch.object(
        litellm_adapter, "cached_available_tools", return_value=[AddTool()]
    ):
        with patch.object(litellm_adapter, "build_completion_kwargs", return_value={}):
            with patch.object(
                litellm_adapter,
                "acompletion_checking_response",
                return_value=(mock_response, mock_response.choices[0]),
            ):
                with pytest.raises(
                    RuntimeError,
                    match="task_response tool call and other tool calls were both provided",
                ):
                    await litellm_adapter._run_model_turn(
                        provider, prior_messages, None, False
                    )


async def test_process_tool_calls_kiln_task_tool_result(tmp_path):
    """Test process_tool_calls with KilnTaskToolResult - tests the new if statement branch"""
    task = build_test_task(tmp_path)
    config = LiteLlmConfig(
        run_config_properties=KilnAgentRunConfigProperties(
            structured_output_mode=StructuredOutputMode.json_schema,
            model_name="gpt_4_1_mini",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
        )
    )
    litellm_adapter = LiteLlmAdapter(config=config, kiln_task=task)

    mock_kiln_task_tool = MockKilnTaskTool(
        "kiln_task_tool",
        output="Task completed successfully",
        kiln_task_tool_data="proj123:::tool456:::task789:::run101",
    )
    tool_calls = [MockToolCall("call_1", "kiln_task_tool", '{"input": "test input"}')]

    with patch.object(
        litellm_adapter, "cached_available_tools", return_value=[mock_kiln_task_tool]
    ):
        assistant_output, tool_messages = await litellm_adapter.process_tool_calls(
            tool_calls  # type: ignore
        )

    assert assistant_output is None
    assert len(tool_messages) == 1
    assert tool_messages[0]["role"] == "tool"
    assert tool_messages[0]["tool_call_id"] == "call_1"
    assert tool_messages[0]["content"] == "Task completed successfully"
    assert (
        tool_messages[0].get("kiln_task_tool_data")
        == "proj123:::tool456:::task789:::run101"
    )


def tool_call_response(*calls: tuple[str, str, str | None]) -> ModelResponse:
    """A model response whose message makes the given (id, name, arguments) calls."""
    return ModelResponse(
        model="gpt-4o-mini",
        choices=[
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {"name": name, "arguments": arguments},
                        }
                        for call_id, name, arguments in calls
                    ],
                }
            }
        ],
    )


def content_response(content: str) -> ModelResponse:
    return ModelResponse(
        model="gpt-4o-mini",
        choices=[{"message": {"content": content, "tool_calls": None}}],
    )


def completion_mock(*responses: ModelResponse) -> AsyncMock:
    return AsyncMock(side_effect=[(r, r.choices[0]) for r in responses])


@pytest.fixture
def openai_api_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "mock_api_key")


async def test_run_model_turn_continues_after_tool_call_error(tmp_path, openai_api_key):
    litellm_adapter = build_tools_adapter(tmp_path)
    provider = KilnModelProvider(name=ModelProviderName.openai, model_id="gpt_4_1_mini")
    acompletion = completion_mock(
        tool_call_response(("call_1", "nonexistent_tool", "{}")),
        content_response("Recovered"),
    )
    unknown_tool_error = (
        "A tool named 'nonexistent_tool' was invoked by a model, but was not available."
    )

    with (
        patch.object(litellm_adapter, "cached_available_tools", return_value=[]),
        patch.object(litellm_adapter, "acompletion_checking_response", acompletion),
    ):
        result = await litellm_adapter._run_model_turn(
            provider, [{"role": "user", "content": "hi"}], None, False
        )

    assert result.assistant_message == "Recovered"
    assert len(result.all_messages) == 4
    assistant_call = result.all_messages[1]
    assert isinstance(assistant_call, LiteLLMMessage)
    assert assistant_call.tool_calls is not None
    assert assistant_call.tool_calls[0].function.name == "nonexistent_tool"
    assert result.all_messages[2] == {
        "role": "tool",
        "tool_call_id": "call_1",
        "content": unknown_tool_error,
        "kiln_task_tool_data": None,
        "is_error": True,
        "error_message": unknown_tool_error,
    }

    second_request_messages = acompletion.call_args_list[1].kwargs["messages"]
    assert second_request_messages[-1] == {
        "role": "tool",
        "tool_call_id": "call_1",
        "content": unknown_tool_error,
    }


@dataclass
class FakeWorldSessionManager:
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def call_tool(self, episode, tool_name, arguments):
        self.calls.append(arguments)
        return ToolCallOutcome(result="found", error=None, reward=None, done=False)


async def test_invoke_saves_trace_with_tool_call_error(tmp_path, openai_api_key):
    """Tool-call mistakes against a world tool are answered as errors, and the run
    still reaches its final answer and is saved with the original calls in its trace."""
    task = build_test_task(tmp_path)
    world = World(name="w", parent=task.parent_project())
    world.save_to_file()
    session_manager = FakeWorldSessionManager()
    lookup = OpenEnvTool(
        name="lookup",
        input_schema={
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
    )
    world_tool = OpenEnvToolProxy(
        tool_id=build_world_tool_id(world.id, "lookup"),
        tool=lookup,
        context=EpisodeContext(
            episode=WorldEpisode(
                reset=WorldReset(world_id=world.id),
                episode_id="ep_test",
                world_version="w@1",
            ),
            world=world,
            session_manager=session_manager,  # type: ignore[arg-type]
            tools={"lookup": lookup},
        ),
    )
    adapter = adapter_for_task(
        task,
        KilnAgentRunConfigProperties(
            structured_output_mode=StructuredOutputMode.json_schema,
            model_name="gpt_4_1_mini",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
        ),
    )
    bad_calls = [
        ("call_unknown", "get_user_contexts", "{}"),
        ("call_json", "lookup", '{"id": "W-1"'),
        ("call_schema", "lookup", '{"id": 7}'),
    ]

    with (
        patch.object(adapter, "available_tools", return_value=[world_tool]),
        patch.object(
            LiteLlmAdapter,
            "acompletion_checking_response",
            new=completion_mock(
                tool_call_response(*bad_calls), content_response("Done [0]")
            ),
        ),
    ):
        run = await adapter.invoke("look up W-1")

    assert session_manager.calls == []
    assert run.output.output == "Done [0]"
    assert run.id is not None
    assert run.path is not None and run.path.exists()

    saved = datamodel.TaskRun.load_from_file(run.path)
    trace = saved.trace
    assert trace is not None
    assistant_call = trace[2]
    assert assistant_call["role"] == "assistant"
    assert [
        (c["id"], c["function"]["name"], c["function"]["arguments"])
        for c in assistant_call.get("tool_calls") or []
    ] == bad_calls

    expected_errors = {
        "call_unknown": "A tool named 'get_user_contexts' was invoked by a model, but was not available.",
        "call_json": 'Failed to parse arguments for tool \'lookup\' (should be JSON): {"id": "W-1"',
        "call_schema": "Failed to validate arguments for tool 'lookup'. The arguments didn't match the tool's schema. The arguments were: {'id': 7}\n The error was: ",
    }
    tool_messages = trace[3:6]
    assert [m.get("tool_call_id") for m in tool_messages] == list(expected_errors)
    for message in tool_messages:
        expected = expected_errors[message["tool_call_id"]]  # type: ignore[typeddict-item]
        assert message["role"] == "tool"
        assert message.get("is_error") is True
        assert message.get("error_message") == message["content"]
        assert str(message["content"]).startswith(expected)
    assert "7 is not of type 'string'" in str(tool_messages[2]["content"])
    assert trace[6]["role"] == "assistant"
    assert trace[6].get("content") == "Done [0]"
