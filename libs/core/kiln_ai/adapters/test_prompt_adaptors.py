import os
from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

import kiln_ai.datamodel as datamodel
from kiln_ai.adapters.langchain_adapters import LangChainPromptAdapter
from kiln_ai.adapters.ml_model_list import built_in_models, ollama_online


@pytest.mark.paid
async def test_groq(tmp_path):
    if os.getenv("GROQ_API_KEY") is None:
        pytest.skip("GROQ_API_KEY not set")
    await run_simple_test(tmp_path, "llama_3_1_8b", "groq")


@pytest.mark.paid
async def test_openrouter(tmp_path):
    await run_simple_test(tmp_path, "llama_3_1_8b", "openrouter")


@pytest.mark.ollama
async def test_ollama_phi(tmp_path):
    # Check if Ollama API is running
    if not await ollama_online():
        pytest.skip("Ollama API not running. Expect it running on localhost:11434")

    await run_simple_test(tmp_path, "phi_3_5", "ollama")


@pytest.mark.ollama
async def test_ollama_gemma(tmp_path):
    # Check if Ollama API is running
    if not await ollama_online():
        pytest.skip("Ollama API not running. Expect it running on localhost:11434")

    await run_simple_test(tmp_path, "gemma_2_2b", "ollama")


@pytest.mark.ollama
async def test_autoselect_provider(tmp_path):
    # Check if Ollama API is running
    if not await ollama_online():
        pytest.skip("Ollama API not running. Expect it running on localhost:11434")

    await run_simple_test(tmp_path, "phi_3_5")


@pytest.mark.ollama
async def test_ollama_llama(tmp_path):
    # Check if Ollama API is running
    if not await ollama_online():
        pytest.skip("Ollama API not running. Expect it running on localhost:11434")

    await run_simple_test(tmp_path, "llama_3_1_8b", "ollama")


@pytest.mark.paid
async def test_openai(tmp_path):
    if os.getenv("OPENAI_API_KEY") is None:
        pytest.skip("OPENAI_API_KEY not set")
    await run_simple_test(tmp_path, "gpt_4o_mini", "openai")


@pytest.mark.paid
async def test_amazon_bedrock(tmp_path):
    if (
        os.getenv("AWS_SECRET_ACCESS_KEY") is None
        or os.getenv("AWS_ACCESS_KEY_ID") is None
    ):
        pytest.skip("AWS keys not set")
    await run_simple_test(tmp_path, "llama_3_1_8b", "amazon_bedrock")


async def test_mock(tmp_path):
    task = build_test_task(tmp_path)
    mockChatModel = FakeListChatModel(responses=["mock response"])
    adapter = LangChainPromptAdapter(task, custom_model=mockChatModel)
    run = await adapter.invoke("You are a mock, send me the response!")
    assert "mock response" in run.output.output


async def test_mock_returning_run(tmp_path):
    task = build_test_task(tmp_path)
    mockChatModel = FakeListChatModel(responses=["mock response"])
    adapter = LangChainPromptAdapter(task, custom_model=mockChatModel)
    run = await adapter.invoke("You are a mock, send me the response!")
    assert run.output.output == "mock response"
    assert run is not None
    assert run.id is not None
    assert run.input == "You are a mock, send me the response!"
    assert run.output.output == "mock response"
    assert "created_by" in run.input_source.properties
    assert run.output.source.properties == {
        "adapter_name": "kiln_langchain_adapter",
        "model_name": "custom.langchain:unknown_model",
        "model_provider": "custom.langchain:FakeListChatModel",
        "prompt_builder_name": "simple_prompt_builder",
    }


@pytest.mark.paid
@pytest.mark.ollama
async def test_all_built_in_models(tmp_path):
    task = build_test_task(tmp_path)
    for model in built_in_models:
        for provider in model.providers:
            try:
                print(f"Running {model.name} {provider.name}")
                await run_simple_task(task, model.name, provider.name)
            except Exception as e:
                raise RuntimeError(f"Error running {model.name} {provider}") from e


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
        name="Answer format",
        instruction="The answer can contain any content about your reasoning, but at the end it should include the final answer in numerals in square brackets. For example if the answer is one hundred, the end of your response should be [100].",
    )
    task = datamodel.Task(
        parent=project,
        name="test task",
        instruction="You are an assistant which performs math tasks provided in plain text.",
        requirements=[r1, r2, r3],
    )
    task.save_to_file()
    assert task.name == "test task"
    assert len(task.requirements) == 3
    return task


async def run_simple_test(tmp_path: Path, model_name: str, provider: str | None = None):
    task = build_test_task(tmp_path)
    return await run_simple_task(task, model_name, provider)


async def run_simple_task(task: datamodel.Task, model_name: str, provider: str):
    adapter = LangChainPromptAdapter(task, model_name=model_name, provider=provider)

    run = await adapter.invoke(
        "You should answer the following question: four plus six times 10"
    )
    assert "64" in run.output.output
    assert run.id is not None
    assert (
        run.input == "You should answer the following question: four plus six times 10"
    )
    assert "64" in run.output.output
    assert run.output.source.properties == {
        "adapter_name": "kiln_langchain_adapter",
        "model_name": model_name,
        "model_provider": provider,
        "prompt_builder_name": "simple_prompt_builder",
    }
