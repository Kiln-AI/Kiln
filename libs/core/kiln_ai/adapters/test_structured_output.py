from pathlib import Path
from typing import Dict

import jsonschema
import jsonschema.exceptions
import pytest

import kiln_ai.datamodel as datamodel
from kiln_ai.adapters.base_adapter import AdapterInfo, BaseAdapter
from kiln_ai.adapters.langchain_adapters import LangChainPromptAdapter
from kiln_ai.adapters.ml_model_list import (
    built_in_models,
    ollama_online,
)
from kiln_ai.datamodel.test_json_schema import json_joke_schema, json_triangle_schema


@pytest.mark.parametrize(
    "model_name,provider",
    [
        ("llama_3_1_8b", "groq"),
        ("mistral_nemo", "openrouter"),
        ("llama_3_1_70b", "amazon_bedrock"),
        ("claude_3_5_sonnet", "openrouter"),
        ("gemini_1_5_pro", "openrouter"),
        ("gemini_1_5_flash", "openrouter"),
        ("gemini_1_5_flash_8b", "openrouter"),
    ],
)
@pytest.mark.paid
async def test_structured_output(tmp_path, model_name, provider):
    await run_structured_output_test(tmp_path, model_name, provider)


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
        super().__init__(kiln_task)
        self.response = response

    async def _run(self, input: str) -> Dict | str:
        return self.response

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
async def test_all_built_in_models_structured_output(tmp_path):
    errors = []
    for model in built_in_models:
        if not model.supports_structured_output:
            print(
                f"Skipping {model.name} because it does not support structured output"
            )
            continue
        for provider in model.providers:
            if not provider.supports_structured_output:
                print(
                    f"Skipping {model.name} {provider.name} because it does not support structured output"
                )
                continue
            try:
                print(f"Running {model.name} {provider.name}")
                await run_structured_output_test(tmp_path, model.name, provider.name)
            except Exception as e:
                print(f"Error running {model.name} {provider.name}")
                errors.append(f"{model.name} {provider.name}: {e}")
    if len(errors) > 0:
        raise RuntimeError(f"Errors: {errors}")


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
    a = LangChainPromptAdapter(task, model_name=model_name, provider=provider)
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
    a = LangChainPromptAdapter(task, model_name=model_name, provider=provider)
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
    assert adapter_info.prompt_builder_name == "SimplePromptBuilder"
    assert adapter_info.model_name == model_name
    assert adapter_info.model_provider == provider
    assert adapter_info.adapter_name == "kiln_langchain_adapter"


@pytest.mark.paid
async def test_structured_input_gpt_4o_mini(tmp_path):
    await run_structured_input_test(tmp_path, "llama_3_1_8b", "groq")


@pytest.mark.paid
@pytest.mark.ollama
async def test_all_built_in_models_structured_input(tmp_path):
    for model in built_in_models:
        for provider in model.providers:
            try:
                print(f"Running {model.name} {provider.name}")
                await run_structured_input_test(tmp_path, model.name, provider.name)
            except Exception as e:
                raise RuntimeError(f"Error running {model.name} {provider}") from e
