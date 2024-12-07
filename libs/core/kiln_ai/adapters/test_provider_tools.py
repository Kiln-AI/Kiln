from unittest.mock import AsyncMock, patch

import pytest

from kiln_ai.adapters.ml_model_list import (
    ModelName,
    ModelProviderName,
)
from kiln_ai.adapters.ollama_tools import OllamaConnection
from kiln_ai.adapters.provider_tools import (
    check_provider_warnings,
    get_model_and_provider,
    kiln_model_provider_from,
    provider_enabled,
    provider_name_from_id,
    provider_options_for_custom_model,
    provider_warnings,
)


@pytest.fixture
def mock_config():
    with patch("kiln_ai.adapters.provider_tools.get_config_value") as mock:
        yield mock


def test_check_provider_warnings_no_warning(mock_config):
    mock_config.return_value = "some_value"

    # This should not raise an exception
    check_provider_warnings(ModelProviderName.amazon_bedrock)


def test_check_provider_warnings_missing_key(mock_config):
    mock_config.return_value = None

    with pytest.raises(ValueError) as exc_info:
        check_provider_warnings(ModelProviderName.amazon_bedrock)

    assert provider_warnings[ModelProviderName.amazon_bedrock].message in str(
        exc_info.value
    )


def test_check_provider_warnings_unknown_provider():
    # This should not raise an exception, as no settings are required for unknown providers
    check_provider_warnings("unknown_provider")


@pytest.mark.parametrize(
    "provider_name",
    [
        ModelProviderName.amazon_bedrock,
        ModelProviderName.openrouter,
        ModelProviderName.groq,
        ModelProviderName.openai,
        ModelProviderName.fireworks_ai,
    ],
)
def test_check_provider_warnings_all_providers(mock_config, provider_name):
    mock_config.return_value = None

    with pytest.raises(ValueError) as exc_info:
        check_provider_warnings(provider_name)

    assert provider_warnings[provider_name].message in str(exc_info.value)


def test_check_provider_warnings_partial_keys_set(mock_config):
    def mock_get(key):
        return "value" if key == "bedrock_access_key" else None

    mock_config.side_effect = mock_get

    with pytest.raises(ValueError) as exc_info:
        check_provider_warnings(ModelProviderName.amazon_bedrock)

    assert provider_warnings[ModelProviderName.amazon_bedrock].message in str(
        exc_info.value
    )


def test_provider_name_from_id_unknown_provider():
    assert (
        provider_name_from_id("unknown_provider")
        == "Unknown provider: unknown_provider"
    )


def test_provider_name_from_id_case_sensitivity():
    assert (
        provider_name_from_id(ModelProviderName.amazon_bedrock.upper())
        == "Unknown provider: AMAZON_BEDROCK"
    )


@pytest.mark.parametrize(
    "provider_id, expected_name",
    [
        (ModelProviderName.amazon_bedrock, "Amazon Bedrock"),
        (ModelProviderName.openrouter, "OpenRouter"),
        (ModelProviderName.groq, "Groq"),
        (ModelProviderName.ollama, "Ollama"),
        (ModelProviderName.openai, "OpenAI"),
        (ModelProviderName.fireworks_ai, "Fireworks AI"),
    ],
)
def test_provider_name_from_id_parametrized(provider_id, expected_name):
    assert provider_name_from_id(provider_id) == expected_name


def test_get_model_and_provider_valid():
    # Test with a known valid model and provider combination
    model, provider = get_model_and_provider(
        ModelName.phi_3_5, ModelProviderName.ollama
    )

    assert model is not None
    assert provider is not None
    assert model.name == ModelName.phi_3_5
    assert provider.name == ModelProviderName.ollama
    assert provider.provider_options["model"] == "phi3.5"


def test_get_model_and_provider_invalid_model():
    # Test with an invalid model name
    model, provider = get_model_and_provider(
        "nonexistent_model", ModelProviderName.ollama
    )

    assert model is None
    assert provider is None


def test_get_model_and_provider_invalid_provider():
    # Test with a valid model but invalid provider
    model, provider = get_model_and_provider(ModelName.phi_3_5, "nonexistent_provider")

    assert model is None
    assert provider is None


def test_get_model_and_provider_valid_model_wrong_provider():
    # Test with a valid model but a provider that doesn't support it
    model, provider = get_model_and_provider(
        ModelName.phi_3_5, ModelProviderName.amazon_bedrock
    )

    assert model is None
    assert provider is None


def test_get_model_and_provider_multiple_providers():
    # Test with a model that has multiple providers
    model, provider = get_model_and_provider(
        ModelName.llama_3_1_70b, ModelProviderName.groq
    )

    assert model is not None
    assert provider is not None
    assert model.name == ModelName.llama_3_1_70b
    assert provider.name == ModelProviderName.groq
    assert provider.provider_options["model"] == "llama-3.1-70b-versatile"


@pytest.mark.asyncio
async def test_provider_enabled_ollama_success():
    with patch(
        "kiln_ai.adapters.provider_tools.get_ollama_connection", new_callable=AsyncMock
    ) as mock_get_ollama:
        # Mock successful Ollama connection with models
        mock_get_ollama.return_value = OllamaConnection(
            message="Connected", supported_models=["phi3.5:latest"]
        )

        result = await provider_enabled(ModelProviderName.ollama)
        assert result is True


@pytest.mark.asyncio
async def test_provider_enabled_ollama_no_models():
    with patch(
        "kiln_ai.adapters.provider_tools.get_ollama_connection", new_callable=AsyncMock
    ) as mock_get_ollama:
        # Mock Ollama connection but with no models
        mock_get_ollama.return_value = OllamaConnection(
            message="Connected but no models",
            supported_models=[],
            unsupported_models=[],
        )

        result = await provider_enabled(ModelProviderName.ollama)
        assert result is False


@pytest.mark.asyncio
async def test_provider_enabled_ollama_connection_error():
    with patch(
        "kiln_ai.adapters.provider_tools.get_ollama_connection", new_callable=AsyncMock
    ) as mock_get_ollama:
        # Mock Ollama connection failure
        mock_get_ollama.side_effect = Exception("Connection failed")

        result = await provider_enabled(ModelProviderName.ollama)
        assert result is False


@pytest.mark.asyncio
async def test_provider_enabled_openai_with_key(mock_config):
    # Mock config to return API key
    mock_config.return_value = "fake-api-key"

    result = await provider_enabled(ModelProviderName.openai)
    assert result is True
    mock_config.assert_called_with("open_ai_api_key")


@pytest.mark.asyncio
async def test_provider_enabled_openai_without_key(mock_config):
    # Mock config to return None for API key
    mock_config.return_value = None

    result = await provider_enabled(ModelProviderName.openai)
    assert result is False
    mock_config.assert_called_with("open_ai_api_key")


@pytest.mark.asyncio
async def test_provider_enabled_unknown_provider():
    # Test with a provider that isn't in provider_warnings
    result = await provider_enabled("unknown_provider")
    assert result is False


@pytest.mark.asyncio
async def test_kiln_model_provider_from_custom_model_no_provider():
    with pytest.raises(ValueError) as exc_info:
        await kiln_model_provider_from("custom_model")
    assert str(exc_info.value) == "Provider name is required for custom models"


@pytest.mark.asyncio
async def test_kiln_model_provider_from_invalid_provider():
    with pytest.raises(ValueError) as exc_info:
        await kiln_model_provider_from("custom_model", "invalid_provider")
    assert str(exc_info.value) == "Invalid provider name: invalid_provider"


@pytest.mark.asyncio
async def test_kiln_model_provider_from_custom_model_valid(mock_config):
    # Mock config to pass provider warnings check
    mock_config.return_value = "fake-api-key"

    provider = await kiln_model_provider_from("custom_model", ModelProviderName.openai)

    assert provider.name == ModelProviderName.openai
    assert provider.supports_structured_output is False
    assert provider.supports_data_gen is False
    assert provider.untested_model is True
    assert "model" in provider.provider_options
    assert provider.provider_options["model"] == "custom_model"


def test_provider_options_for_custom_model_basic():
    """Test basic case with custom model name"""
    options = provider_options_for_custom_model(
        "custom_model_name", ModelProviderName.openai
    )
    assert options == {"model": "custom_model_name"}


def test_provider_options_for_custom_model_bedrock():
    """Test Amazon Bedrock provider options"""
    options = provider_options_for_custom_model(
        ModelName.llama_3_1_8b, ModelProviderName.amazon_bedrock
    )
    assert options == {"model": ModelName.llama_3_1_8b, "region_name": "us-west-2"}


@pytest.mark.parametrize(
    "provider",
    [
        ModelProviderName.openai,
        ModelProviderName.ollama,
        ModelProviderName.fireworks_ai,
        ModelProviderName.openrouter,
        ModelProviderName.groq,
    ],
)
def test_provider_options_for_custom_model_simple_providers(provider):
    """Test providers that just need model name"""

    options = provider_options_for_custom_model(ModelName.llama_3_1_8b, provider)
    assert options == {"model": ModelName.llama_3_1_8b}


def test_provider_options_for_custom_model_kiln_fine_tune():
    """Test that kiln_fine_tune raises appropriate error"""
    with pytest.raises(ValueError) as exc_info:
        provider_options_for_custom_model(
            "model_name", ModelProviderName.kiln_fine_tune
        )
    assert (
        str(exc_info.value)
        == "Fine tuned models should populate provider options via another path"
    )


def test_provider_options_for_custom_model_invalid_enum():
    """Test handling of invalid enum value"""
    with pytest.raises(ValueError):
        provider_options_for_custom_model("model_name", "invalid_enum_value")
