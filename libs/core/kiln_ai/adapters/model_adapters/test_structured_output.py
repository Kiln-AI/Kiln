import json
from pathlib import Path
from typing import Dict
from unittest.mock import Mock, patch

import pytest
from litellm.types.utils import ModelResponse

import kiln_ai.datamodel as datamodel
from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.ml_model_list import built_in_models
from kiln_ai.adapters.model_adapters.base_adapter import BaseAdapter, RunOutput, Usage
from kiln_ai.adapters.ollama_tools import ollama_online
from kiln_ai.adapters.test_prompt_adaptors import get_all_models_and_providers
from kiln_ai.datamodel import PromptId
from kiln_ai.datamodel.task import RunConfigProperties
from kiln_ai.datamodel.test_json_schema import json_joke_schema, json_triangle_schema


@pytest.mark.ollama
async def test_structured_output_ollama_phi(tmp_path):
    # https://python.langchain.com/v0.2/docs/how_to/structured_output/#advanced-specifying-the-method-for-structuring-outputs
    pytest.skip(
        "not working yet - phi3.5 does not support tools. Need json_mode + format in prompt"
    )
    await run_structured_output_test(tmp_path, "phi_3_5", "ollama")


@pytest.mark.paid
async def test_structured_output_gpt_4o_mini(tmp_path):
    await run_structured_output_test(tmp_path, "gpt_4o_mini", "openai")


@pytest.mark.parametrize("model_name", ["llama_3_1_8b", "gemma_2_2b"])
@pytest.mark.ollama
async def test_structured_output_ollama(tmp_path, model_name):
    if not await ollama_online():
        pytest.skip("Ollama API not running. Expect it running on localhost:11434")
    await run_structured_output_test(tmp_path, model_name, "ollama")


class MockAdapter(BaseAdapter):
    def __init__(self, kiln_task: datamodel.Task, response: Dict | str | None):
        super().__init__(
            task=kiln_task,
            run_config=RunConfigProperties(
                model_name="phi_3_5",
                model_provider_name="ollama",
                prompt_id="simple_chain_of_thought_prompt_builder",
                structured_output_mode="json_schema",
            ),
        )
        self.response = response

    async def _run(self, input: str) -> tuple[RunOutput, Usage | None]:
        return RunOutput(output=self.response, intermediate_outputs=None), None

    def adapter_name(self) -> str:
        return "mock_adapter"


async def test_mock_unstructred_response(tmp_path):
    task = build_structured_output_test_task(tmp_path)

    # don't error on valid response
    adapter = MockAdapter(task, response={"setup": "asdf", "punchline": "asdf"})
    run = await adapter.invoke("You are a mock, send me the response!")
    answer = json.loads(run.output.output)
    assert answer["setup"] == "asdf"
    assert answer["punchline"] == "asdf"

    # error on response that doesn't match schema
    adapter = MockAdapter(task, response={"setup": "asdf"})
    with pytest.raises(Exception):
        answer = await adapter.invoke("You are a mock, send me the response!")

    adapter = MockAdapter(task, response="string instead of dict")
    with pytest.raises(
        ValueError,
        match="This task requires JSON output but the model didn't return valid JSON",
    ):
        # Not a structed response so should error
        run = await adapter.invoke("You are a mock, send me the response!")

    # Should error, expecting a string, not a dict
    project = datamodel.Project(name="test", path=tmp_path / "test.kiln")
    task = datamodel.Task(
        parent=project,
        name="test task",
        instruction="You are an assistant which performs math tasks provided in plain text.",
    )
    task.instruction = (
        "You are an assistant which performs math tasks provided in plain text."
    )
    adapter = MockAdapter(task, response={"dict": "value"})
    with pytest.raises(RuntimeError):
        answer = await adapter.invoke("You are a mock, send me the response!")


def check_supports_structured_output(model_name: str, provider_name: str):
    for model in built_in_models:
        if model.name != model_name:
            continue
        for provider in model.providers:
            if provider.name != provider_name:
                continue
            if not provider.supports_structured_output:
                pytest.skip(
                    f"Skipping {model.name} {provider.name} because it does not support structured output"
                )
            return
    raise RuntimeError(f"No model {model_name} {provider_name} found")


@pytest.mark.paid
@pytest.mark.ollama
@pytest.mark.parametrize("model_name,provider_name", get_all_models_and_providers())
async def test_all_built_in_models_structured_output(
    tmp_path, model_name, provider_name
):
    check_supports_structured_output(model_name, provider_name)
    await run_structured_output_test(tmp_path, model_name, provider_name)


def build_structured_output_test_task(tmp_path: Path):
    project = datamodel.Project(name="test", path=tmp_path / "test.kiln")
    project.save_to_file()
    task = datamodel.Task(
        parent=project,
        name="test task",
        instruction="You are an assistant which tells a joke, given a subject.",
    )
    task.output_json_schema = json_joke_schema
    schema = task.output_schema()
    assert schema is not None
    assert schema["properties"]["setup"]["type"] == "string"
    assert schema["properties"]["punchline"]["type"] == "string"
    task.save_to_file()
    assert task.name == "test task"
    assert len(task.requirements) == 0
    return task


async def run_structured_output_test(tmp_path: Path, model_name: str, provider: str):
    task = build_structured_output_test_task(tmp_path)
    a = adapter_for_task(
        task,
        run_config_properties=RunConfigProperties(
            model_name=model_name,
            model_provider_name=provider,
            prompt_id="simple_prompt_builder",
            structured_output_mode="unknown",
        ),
    )
    try:
        run = await a.invoke("Cows")  # a joke about cows
        parsed = json.loads(run.output.output)
    except ValueError as e:
        if str(e) == "Failed to connect to Ollama. Ensure Ollama is running.":
            pytest.skip(
                f"Skipping {model_name} {provider} because Ollama is not running"
            )
        raise e
    if parsed is None or not isinstance(parsed, Dict):
        raise RuntimeError(f"structured response is not a dict: {parsed}")
    assert parsed["setup"] is not None
    assert parsed["punchline"] is not None
    if "rating" in parsed and parsed["rating"] is not None:
        rating = parsed["rating"]
        # Note: really should be an int according to json schema, but mistral returns a string
        if isinstance(rating, str):
            rating = int(rating)
        assert rating >= 0
        assert rating <= 10

    # Check reasoning models
    assert a._model_provider is not None
    if a._model_provider.reasoning_capable:
        # some providers have reasoning_capable models that do not return the reasoning
        # for structured output responses (they provide it only for non-structured output)
        if a._model_provider.reasoning_optional_for_structured_output:
            # models may be updated to include the reasoning in the future
            assert "reasoning" not in run.intermediate_outputs
        else:
            assert "reasoning" in run.intermediate_outputs
            assert isinstance(run.intermediate_outputs["reasoning"], str)


def build_structured_input_test_task(tmp_path: Path):
    project = datamodel.Project(name="test", path=tmp_path / "test.kiln")
    project.save_to_file()
    task = datamodel.Task(
        parent=project,
        name="test task",
        instruction="You are an assistant which classifies a triangle given the lengths of its sides. If all sides are of equal length, the triangle is equilateral. If two sides are equal, the triangle is isosceles. Otherwise, it is scalene.\n\nAt the end of your response return the result in double square brackets. It should be plain text. It should be exactly one of the three following strings: '[[equilateral]]', or '[[isosceles]]', or '[[scalene]]'.",
        thinking_prompt="Think step by step.",
    )
    task.input_json_schema = json_triangle_schema
    schema = task.input_schema()
    assert schema is not None
    assert schema["properties"]["a"]["type"] == "integer"
    assert schema["properties"]["b"]["type"] == "integer"
    assert schema["properties"]["c"]["type"] == "integer"
    assert schema["required"] == ["a", "b", "c"]
    task.save_to_file()
    assert task.name == "test task"
    assert len(task.requirements) == 0
    return task


async def run_structured_input_test(
    tmp_path: Path, model_name: str, provider: str, prompt_id: PromptId
):
    task = build_structured_input_test_task(tmp_path)
    try:
        await run_structured_input_task(task, model_name, provider, prompt_id)
    except ValueError as e:
        if str(e) == "Failed to connect to Ollama. Ensure Ollama is running.":
            pytest.skip(
                f"Skipping {model_name} {provider} because Ollama is not running"
            )
        raise e


async def run_structured_input_task_no_validation(
    task: datamodel.Task,
    model_name: str,
    provider: str,
    prompt_id: PromptId,
):
    a = adapter_for_task(
        task,
        run_config_properties=RunConfigProperties(
            model_name=model_name,
            model_provider_name=provider,
            prompt_id=prompt_id,
            structured_output_mode="unknown",
        ),
    )
    with pytest.raises(ValueError):
        # not structured input in dictionary
        await a.invoke("a=1, b=2, c=3")
    with pytest.raises(ValueError, match="This task requires a specific input"):
        # invalid structured input
        await a.invoke({"a": 1, "b": 2, "d": 3})

    try:
        run = await a.invoke({"a": 2, "b": 2, "c": 2})
        response = run.output.output
        return response, a, run
    except ValueError as e:
        if str(e) == "Failed to connect to Ollama. Ensure Ollama is running.":
            pytest.skip(
                f"Skipping {model_name} {provider} because Ollama is not running"
            )
        raise e


async def run_structured_input_task(
    task: datamodel.Task,
    model_name: str,
    provider: str,
    prompt_id: PromptId,
    verify_trace_cot: bool = False,
):
    response, a, run = await run_structured_input_task_no_validation(
        task, model_name, provider, prompt_id
    )
    assert response is not None
    if isinstance(response, str):
        assert "[[equilateral]]" in response
    else:
        assert response["is_equilateral"] is True
    expected_pb_name = "simple_prompt_builder"
    if prompt_id is not None:
        expected_pb_name = prompt_id
    assert a.run_config.prompt_id == expected_pb_name

    assert a.run_config.model_name == model_name
    assert a.run_config.model_provider_name == provider

    # Check reasoning models
    assert a._model_provider is not None
    if a._model_provider.reasoning_capable:
        assert "reasoning" in run.intermediate_outputs
        assert isinstance(run.intermediate_outputs["reasoning"], str)

    # Check the trace
    trace = run.trace
    assert trace is not None
    if verify_trace_cot:
        assert len(trace) == 5
        assert trace[0]["role"] == "system"
        assert "You are an assistant which classifies a triangle" in trace[0]["content"]
        assert trace[1]["role"] == "user"
        assert trace[2]["role"] == "assistant"
        assert trace[2].get("tool_calls") is None
        assert trace[3]["role"] == "user"
        assert trace[4]["role"] == "assistant"
        assert trace[4].get("tool_calls") is None
    else:
        assert len(trace) == 3
        assert trace[0]["role"] == "system"
        assert "You are an assistant which classifies a triangle" in trace[0]["content"]
        assert trace[1]["role"] == "user"
        json_content = json.loads(trace[1]["content"])
        assert json_content["a"] == 2
        assert json_content["b"] == 2
        assert json_content["c"] == 2
        assert trace[2]["role"] == "assistant"
        assert trace[2].get("tool_calls") is None
        assert "[[equilateral]]" in trace[2]["content"]


@pytest.mark.paid
async def test_structured_input_gpt_4o_mini(tmp_path):
    await run_structured_input_test(tmp_path, "llama_3_1_8b", "groq")


@pytest.mark.paid
@pytest.mark.ollama
@pytest.mark.parametrize("model_name,provider_name", get_all_models_and_providers())
async def test_all_built_in_models_structured_input(
    tmp_path, model_name, provider_name
):
    await run_structured_input_test(
        tmp_path, model_name, provider_name, "simple_prompt_builder"
    )


async def test_all_built_in_models_structured_input_mocked(tmp_path):
    mock_response = ModelResponse(
        model="gpt-4o-mini",
        choices=[
            {
                "message": {
                    "content": "The answer is [[equilateral]]",
                }
            }
        ],
    )

    # Mock the Config.shared() method to return a mock config with required attributes
    mock_config = Mock()
    mock_config.open_ai_api_key = "mock_api_key"
    mock_config.user_id = "test_user"

    with (
        patch(
            "litellm.acompletion",
            side_effect=[mock_response],
        ),
        patch("kiln_ai.utils.config.Config.shared", return_value=mock_config),
    ):
        await run_structured_input_test(
            tmp_path, "llama_3_1_8b", "groq", "simple_prompt_builder"
        )


@pytest.mark.paid
@pytest.mark.ollama
@pytest.mark.parametrize("model_name,provider_name", get_all_models_and_providers())
async def test_structured_input_cot_prompt_builder(tmp_path, model_name, provider_name):
    task = build_structured_input_test_task(tmp_path)
    await run_structured_input_task(
        task,
        model_name,
        provider_name,
        "simple_chain_of_thought_prompt_builder",
        verify_trace_cot=True,
    )


async def test_structured_input_cot_prompt_builder_mocked(tmp_path):
    task = build_structured_input_test_task(tmp_path)
    mock_response_1 = ModelResponse(
        model="gpt-4o-mini",
        choices=[
            {
                "message": {
                    "content": "I'm thinking real hard... oh!",
                }
            }
        ],
    )
    mock_response_2 = ModelResponse(
        model="gpt-4o-mini",
        choices=[
            {
                "message": {
                    "content": "After thinking, I've decided the answer is [[equilateral]]",
                }
            }
        ],
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
        await run_structured_input_task(
            task,
            "llama_3_1_8b",
            "groq",
            "simple_chain_of_thought_prompt_builder",
            verify_trace_cot=True,
        )


@pytest.mark.paid
@pytest.mark.ollama
@pytest.mark.parametrize("model_name,provider_name", get_all_models_and_providers())
async def test_structured_output_cot_prompt_builder(
    tmp_path, model_name, provider_name
):
    check_supports_structured_output(model_name, provider_name)
    triangle_schema = {
        "type": "object",
        "properties": {
            "is_equilateral": {
                "type": "boolean",
                "description": "True if all sides of the triangle are equal in length",
            },
            "is_scalene": {
                "type": "boolean",
                "description": "True if all sides of the triangle have different lengths",
            },
            "is_obtuse": {
                "type": "boolean",
                "description": "True if one of the angles is greater than 90 degrees",
            },
        },
        "required": ["is_equilateral", "is_scalene", "is_obtuse"],
        "additionalProperties": False,
    }
    task = build_structured_input_test_task(tmp_path)
    task.instruction = """
You are an assistant which classifies a triangle given the lengths of its sides. If all sides are of equal length, the triangle is equilateral. If two sides are equal, the triangle is isosceles. Otherwise, it is scalene.\n\n"

When asked for a final result, this is the format (for an equilateral example):
```json
{
    "is_equilateral": true,
    "is_scalene": false,
    "is_obtuse": false
}
```
"""
    task.output_json_schema = json.dumps(triangle_schema)
    task.save_to_file()
    response, adapter, _ = await run_structured_input_task_no_validation(
        task, model_name, provider_name, "simple_chain_of_thought_prompt_builder"
    )

    formatted_response = json.loads(response)
    assert formatted_response["is_equilateral"] is True
    assert formatted_response["is_scalene"] is False
    assert formatted_response["is_obtuse"] is False
