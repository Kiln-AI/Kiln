import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_fireworks import ChatFireworks
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama

from kiln_ai.adapters.ml_model_list import (
    KilnModelProvider,
    ModelProviderName,
    StructuredOutputMode,
)
from kiln_ai.adapters.model_adapters.base_adapter import COT_FINAL_ANSWER_PROMPT
from kiln_ai.adapters.model_adapters.langchain_adapters import (
    LangchainAdapter,
    langchain_model_from_provider,
)
from kiln_ai.adapters.test_prompt_adaptors import build_test_task
from kiln_ai.datamodel.task import RunConfig


@pytest.fixture
def mock_adapter(tmp_path):
    return LangchainAdapter(
        kiln_task=build_test_task(tmp_path),
        model_name="llama_3_1_8b",
        provider="ollama",
    )


def test_langchain_adapter_munge_response(mock_adapter):
    # Mistral Large tool calling format is a bit different
    response = {
        "name": "task_response",
        "arguments": {
            "setup": "Why did the cow join a band?",
            "punchline": "Because she wanted to be a moo-sician!",
        },
    }
    munged = mock_adapter._munge_response(response)
    assert munged["setup"] == "Why did the cow join a band?"
    assert munged["punchline"] == "Because she wanted to be a moo-sician!"

    # non mistral format should continue to work
    munged = mock_adapter._munge_response(response["arguments"])
    assert munged["setup"] == "Why did the cow join a band?"
    assert munged["punchline"] == "Because she wanted to be a moo-sician!"


def test_langchain_adapter_infer_model_name(tmp_path):
    task = build_test_task(tmp_path)
    custom = ChatGroq(model="llama-3.1-8b-instant", groq_api_key="test")

    lca = LangchainAdapter(kiln_task=task, custom_model=custom)

    assert lca.run_config.model_name == "custom.langchain:llama-3.1-8b-instant"
    assert lca.run_config.model_provider_name == "custom.langchain:ChatGroq"


def test_langchain_adapter_info(tmp_path):
    task = build_test_task(tmp_path)

    lca = LangchainAdapter(kiln_task=task, model_name="llama_3_1_8b", provider="ollama")

    assert lca.adapter_name() == "kiln_langchain_adapter"
    assert lca.run_config.model_name == "llama_3_1_8b"
    assert lca.run_config.model_provider_name == "ollama"


async def test_langchain_adapter_with_cot(tmp_path):
    task = build_test_task(tmp_path)
    task.output_json_schema = (
        '{"type": "object", "properties": {"count": {"type": "integer"}}}'
    )
    lca = LangchainAdapter(
        kiln_task=task,
        model_name="llama_3_1_8b",
        provider="ollama",
        prompt_id="simple_chain_of_thought_prompt_builder",
    )

    # Mock the base model and its invoke method
    mock_base_model = MagicMock()
    mock_base_model.ainvoke = AsyncMock(
        return_value=AIMessage(content="Chain of thought reasoning...")
    )

    # Create a separate mock for self.model()
    mock_model_instance = MagicMock()
    mock_model_instance.ainvoke = AsyncMock(return_value={"parsed": {"count": 1}})

    # Mock the langchain_model_from function to return the base model
    mock_model_from = AsyncMock(return_value=mock_base_model)

    # Patch both the langchain_model_from function and self.model()
    with (
        patch.object(LangchainAdapter, "langchain_model_from", mock_model_from),
        patch.object(LangchainAdapter, "model", return_value=mock_model_instance),
    ):
        response = await lca._run("test input")

    # First 3 messages are the same for both calls
    for invoke_args in [
        mock_base_model.ainvoke.call_args[0][0],
        mock_model_instance.ainvoke.call_args[0][0],
    ]:
        assert isinstance(
            invoke_args[0], SystemMessage
        )  # First message should be system prompt
        assert (
            "You are an assistant which performs math tasks provided in plain text."
            in invoke_args[0].content
        )
        assert isinstance(invoke_args[1], HumanMessage)
        assert "test input" in invoke_args[1].content
        assert isinstance(invoke_args[2], SystemMessage)
        assert "step by step" in invoke_args[2].content

    # the COT should only have 3 messages
    assert len(mock_base_model.ainvoke.call_args[0][0]) == 3
    assert len(mock_model_instance.ainvoke.call_args[0][0]) == 5

    # the final response should have the COT content and the final instructions
    invoke_args = mock_model_instance.ainvoke.call_args[0][0]
    assert isinstance(invoke_args[3], AIMessage)
    assert "Chain of thought reasoning..." in invoke_args[3].content
    assert isinstance(invoke_args[4], HumanMessage)
    assert COT_FINAL_ANSWER_PROMPT in invoke_args[4].content

    assert (
        response.intermediate_outputs["chain_of_thought"]
        == "Chain of thought reasoning..."
    )
    assert response.output == {"count": 1}


@pytest.mark.parametrize(
    "structured_output_mode,expected_method",
    [
        (StructuredOutputMode.function_calling, "function_calling"),
        (StructuredOutputMode.json_mode, "json_mode"),
        (StructuredOutputMode.json_schema, "json_schema"),
        (StructuredOutputMode.json_instruction_and_object, "json_mode"),
        (StructuredOutputMode.default, None),
    ],
)
async def test_get_structured_output_options(
    mock_adapter, structured_output_mode, expected_method
):
    # Mock the provider response
    mock_provider = MagicMock()
    mock_provider.structured_output_mode = structured_output_mode

    # Mock adapter.model_provider()
    mock_adapter.model_provider = MagicMock(return_value=mock_provider)

    options = mock_adapter.get_structured_output_options("model_name", "provider")
    assert options.get("method") == expected_method


@pytest.mark.asyncio
async def test_langchain_model_from_provider_groq():
    provider = KilnModelProvider(
        name=ModelProviderName.groq, provider_options={"model": "mixtral-8x7b"}
    )

    with patch(
        "kiln_ai.adapters.model_adapters.langchain_adapters.Config.shared"
    ) as mock_config:
        mock_config.return_value.groq_api_key = "test_key"
        model = await langchain_model_from_provider(provider, "mixtral-8x7b")
        assert isinstance(model, ChatGroq)
        assert model.model_name == "mixtral-8x7b"


@pytest.mark.asyncio
async def test_langchain_model_from_provider_bedrock():
    provider = KilnModelProvider(
        name=ModelProviderName.amazon_bedrock,
        provider_options={"model": "anthropic.claude-v2", "region_name": "us-east-1"},
    )

    with patch(
        "kiln_ai.adapters.model_adapters.langchain_adapters.Config.shared"
    ) as mock_config:
        mock_config.return_value.bedrock_access_key = "test_access"
        mock_config.return_value.bedrock_secret_key = "test_secret"
        model = await langchain_model_from_provider(provider, "anthropic.claude-v2")
        assert isinstance(model, ChatBedrockConverse)
        assert os.environ.get("AWS_ACCESS_KEY_ID") == "test_access"
        assert os.environ.get("AWS_SECRET_ACCESS_KEY") == "test_secret"


@pytest.mark.asyncio
async def test_langchain_model_from_provider_fireworks():
    provider = KilnModelProvider(
        name=ModelProviderName.fireworks_ai, provider_options={"model": "mixtral-8x7b"}
    )

    with patch(
        "kiln_ai.adapters.model_adapters.langchain_adapters.Config.shared"
    ) as mock_config:
        mock_config.return_value.fireworks_api_key = "test_key"
        model = await langchain_model_from_provider(provider, "mixtral-8x7b")
        assert isinstance(model, ChatFireworks)


@pytest.mark.asyncio
async def test_langchain_model_from_provider_ollama():
    provider = KilnModelProvider(
        name=ModelProviderName.ollama,
        provider_options={"model": "llama2", "model_aliases": ["llama2-uncensored"]},
    )

    mock_connection = MagicMock()
    with (
        patch(
            "kiln_ai.adapters.model_adapters.langchain_adapters.get_ollama_connection",
            return_value=AsyncMock(return_value=mock_connection),
        ),
        patch(
            "kiln_ai.adapters.model_adapters.langchain_adapters.ollama_model_installed",
            return_value=True,
        ),
        patch(
            "kiln_ai.adapters.model_adapters.langchain_adapters.ollama_base_url",
            return_value="http://localhost:11434",
        ),
    ):
        model = await langchain_model_from_provider(provider, "llama2")
        assert isinstance(model, ChatOllama)
        assert model.model == "llama2"


@pytest.mark.asyncio
async def test_langchain_model_from_provider_invalid():
    provider = KilnModelProvider.model_construct(
        name="invalid_provider", provider_options={}
    )

    with pytest.raises(ValueError, match="Invalid model or provider"):
        await langchain_model_from_provider(provider, "test_model")


@pytest.mark.asyncio
async def test_langchain_adapter_model_caching(tmp_path):
    task = build_test_task(tmp_path)
    custom_model = ChatGroq(model="mixtral-8x7b", groq_api_key="test")

    adapter = LangchainAdapter(kiln_task=task, custom_model=custom_model)

    # First call should return the cached model
    model1 = await adapter.model()
    assert model1 is custom_model

    # Second call should return the same cached instance
    model2 = await adapter.model()
    assert model2 is model1


@pytest.mark.asyncio
async def test_langchain_adapter_model_structured_output(tmp_path):
    task = build_test_task(tmp_path)
    task.output_json_schema = """
    {
        "type": "object",
        "properties": {
            "count": {"type": "integer"}
        }
    }
    """

    mock_model = MagicMock()
    mock_model.with_structured_output = MagicMock(return_value="structured_model")

    adapter = LangchainAdapter(
        kiln_task=task, model_name="test_model", provider="ollama"
    )
    adapter.get_structured_output_options = MagicMock(
        return_value={"option1": "value1"}
    )
    adapter.langchain_model_from = AsyncMock(return_value=mock_model)

    model = await adapter.model()

    # Verify the model was configured with structured output
    mock_model.with_structured_output.assert_called_once_with(
        {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
            "title": "task_response",
            "description": "A response from the task",
        },
        include_raw=True,
        option1="value1",
    )
    assert model == "structured_model"


@pytest.mark.asyncio
async def test_langchain_adapter_model_no_structured_output_support(tmp_path):
    task = build_test_task(tmp_path)
    task.output_json_schema = (
        '{"type": "object", "properties": {"count": {"type": "integer"}}}'
    )

    mock_model = MagicMock()
    # Remove with_structured_output method
    del mock_model.with_structured_output

    adapter = LangchainAdapter(
        kiln_task=task, model_name="test_model", provider="ollama"
    )
    adapter.langchain_model_from = AsyncMock(return_value=mock_model)

    with pytest.raises(ValueError, match="does not support structured output"):
        await adapter.model()


import pytest


@pytest.mark.parametrize(
    "provider_name",
    [
        (ModelProviderName.openai),
        (ModelProviderName.openai_compatible),
        (ModelProviderName.openrouter),
    ],
)
@pytest.mark.asyncio
async def test_langchain_model_from_provider_unsupported_providers(provider_name):
    # Arrange
    provider = KilnModelProvider(
        name=provider_name, provider_options={}, structured_output_mode="default"
    )

    # Assert unsupported providers raise an error
    with pytest.raises(ValueError):
        await langchain_model_from_provider(provider, "test-model")
