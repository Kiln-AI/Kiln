from pathlib import Path
from typing import Dict

import jsonschema
import jsonschema.exceptions
import pytest

import kiln_ai.datamodel as datamodel
from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.base_adapter import AdapterInfo, BaseAdapter, RunOutput
from kiln_ai.adapters.ml_model_list import (
    built_in_models,
)
from kiln_ai.adapters.ollama_tools import ollama_online
from kiln_ai.adapters.prompt_builders import (
    BasePromptBuilder,
    SimpleChainOfThoughtPromptBuilder,
)
from kiln_ai.adapters.test_prompt_adaptors import get_all_models_and_providers
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


@pytest.mark.parametrize("model_name", ["llama_3_1_8b"])
@pytest.mark.ollama
async def test_structured_output_ollama_llama(tmp_path, model_name):
    if not await ollama_online():
        pytest.skip("Ollama API not running. Expect it running on localhost:11434")
    await run_structured_output_test(tmp_path, model_name, "ollama")


class MockAdapter(BaseAdapter):
    def __init__(self, kiln_task: datamodel.Task, response: Dict | str | None):
        super().__init__(kiln_task, model_name="phi_3_5", model_provider_name="ollama")
        self.response = response

    async def _run(self, input: str) -> RunOutput:
        return RunOutput(output=self.response, intermediate_outputs=None)

    def adapter_info(self) -> AdapterInfo:
        return AdapterInfo(
            adapter_name="mock_adapter",
            model_name="mock_model",
            model_provider="mock_provider",
            prompt_builder_name="mock_prompt_builder",
        )


async def test_mock_unstructred_response(tmp_path):
    task = build_structured_output_test_task(tmp_path)

    # don't error on valid response
    adapter = MockAdapter(task, response={"setup": "asdf", "punchline": "asdf"})
    answer = await adapter.invoke_returning_raw("You are a mock, send me the response!")
    assert answer["setup"] == "asdf"
    assert answer["punchline"] == "asdf"

    # error on response that doesn't match schema
    adapter = MockAdapter(task, response={"setup": "asdf"})
    with pytest.raises(Exception):
        answer = await adapter.invoke("You are a mock, send me the response!")

    adapter = MockAdapter(task, response="string instead of dict")
    with pytest.raises(RuntimeError):
        # Not a structed response so should error
        answer = await adapter.invoke("You are a mock, send me the response!")

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


@pytest.mark.paid
@pytest.mark.ollama
@pytest.mark.parametrize("model_name,provider_name", get_all_models_and_providers())
async def test_all_built_in_models_structured_output(
    tmp_path, model_name, provider_name
):
    for model in built_in_models:
        if model.name != model_name:
            continue
        if not model.supports_structured_output:
            pytest.skip(
                f"Skipping {model.name} because it does not support structured output"
            )
        for provider in model.providers:
            if provider.name != provider_name:
                continue
            if not provider.supports_structured_output:
                pytest.skip(
                    f"Skipping {model.name} {provider.name} because it does not support structured output"
                )
            await run_structured_output_test(tmp_path, model.name, provider.name)
            return
    raise RuntimeError(f"No model {model_name} {provider_name} found")


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
    a = adapter_for_task(task, model_name=model_name, provider=provider)
    parsed = await a.invoke_returning_raw("Cows")  # a joke about cows
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


def build_structured_input_test_task(tmp_path: Path):
    project = datamodel.Project(name="test", path=tmp_path / "test.kiln")
    project.save_to_file()
    task = datamodel.Task(
        parent=project,
        name="test task",
        instruction="You are an assistant which classifies a triangle given the lengths of its sides. If all sides are of equal length, the triangle is equilateral. If two sides are equal, the triangle is isosceles. Otherwise, it is scalene.\n\nAt the end of your response return the result in double square brackets. It should be plain text. It should be exactly one of the three following strings: '[[equilateral]]', or '[[isosceles]]', or '[[scalene]]'.",
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


async def run_structured_input_test(tmp_path: Path, model_name: str, provider: str):
    task = build_structured_input_test_task(tmp_path)
    await run_structured_input_task(task, model_name, provider)


async def run_structured_input_task(
    task: datamodel.Task,
    model_name: str,
    provider: str,
    pb: BasePromptBuilder | None = None,
):
    a = adapter_for_task(
        task, model_name=model_name, provider=provider, prompt_builder=pb
    )
    with pytest.raises(ValueError):
        # not structured input in dictionary
        await a.invoke("a=1, b=2, c=3")
    with pytest.raises(jsonschema.exceptions.ValidationError):
        # invalid structured input
        await a.invoke({"a": 1, "b": 2, "d": 3})

    response = await a.invoke_returning_raw({"a": 2, "b": 2, "c": 2})
    assert response is not None
    assert isinstance(response, str)
    assert "[[equilateral]]" in response
    adapter_info = a.adapter_info()
    expected_pb_name = "simple_prompt_builder"
    if pb is not None:
        expected_pb_name = pb.__class__.prompt_builder_name()
    assert adapter_info.prompt_builder_name == expected_pb_name
    assert adapter_info.model_name == model_name
    assert adapter_info.model_provider == provider
    assert adapter_info.adapter_name == "kiln_langchain_adapter"


@pytest.mark.paid
async def test_structured_input_gpt_4o_mini(tmp_path):
    await run_structured_input_test(tmp_path, "llama_3_1_8b", "groq")


@pytest.mark.paid
@pytest.mark.ollama
@pytest.mark.parametrize("model_name,provider_name", get_all_models_and_providers())
async def test_all_built_in_models_structured_input(
    tmp_path, model_name, provider_name
):
    await run_structured_input_test(tmp_path, model_name, provider_name)


@pytest.mark.paid
@pytest.mark.ollama
@pytest.mark.parametrize("model_name,provider_name", get_all_models_and_providers())
async def test_structured_cot_prompt_builder(tmp_path, model_name, provider_name):
    task = build_structured_input_test_task(tmp_path)
    pb = SimpleChainOfThoughtPromptBuilder(task)
    await run_structured_input_task(task, model_name, provider_name, pb)
