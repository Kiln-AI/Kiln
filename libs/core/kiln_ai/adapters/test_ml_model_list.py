import json
from unittest.mock import patch

import pytest

from kiln_ai.adapters.ml_model_list import (
    ModelProviderName,
    OllamaConnection,
    check_provider_warnings,
    ollama_model_supported,
    parse_ollama_tags,
    provider_name_from_id,
    provider_warnings,
)


@pytest.fixture
def mock_config():
    with patch("kiln_ai.adapters.ml_model_list.get_config_value") as mock:
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
    ],
)
def test_provider_name_from_id_parametrized(provider_id, expected_name):
    assert provider_name_from_id(provider_id) == expected_name


def test_parse_ollama_tags_no_models():
    json_response = '{"models":[{"name":"phi3.5:latest","model":"phi3.5:latest","modified_at":"2024-10-02T12:04:35.191519822-04:00","size":2176178843,"digest":"61819fb370a3c1a9be6694869331e5f85f867a079e9271d66cb223acb81d04ba","details":{"parent_model":"","format":"gguf","family":"phi3","families":["phi3"],"parameter_size":"3.8B","quantization_level":"Q4_0"}},{"name":"gemma2:2b","model":"gemma2:2b","modified_at":"2024-09-09T16:46:38.64348929-04:00","size":1629518495,"digest":"8ccf136fdd5298f3ffe2d69862750ea7fb56555fa4d5b18c04e3fa4d82ee09d7","details":{"parent_model":"","format":"gguf","family":"gemma2","families":["gemma2"],"parameter_size":"2.6B","quantization_level":"Q4_0"}},{"name":"llama3.1:latest","model":"llama3.1:latest","modified_at":"2024-09-01T17:19:43.481523695-04:00","size":4661230720,"digest":"f66fc8dc39ea206e03ff6764fcc696b1b4dfb693f0b6ef751731dd4e6269046e","details":{"parent_model":"","format":"gguf","family":"llama","families":["llama"],"parameter_size":"8.0B","quantization_level":"Q4_0"}}]}'
    tags = json.loads(json_response)
    print(json.dumps(tags, indent=2))
    conn = parse_ollama_tags(tags)
    assert "phi3.5:latest" in conn.models
    assert "gemma2:2b" in conn.models
    assert "llama3.1:latest" in conn.models


def test_ollama_model_supported():
    conn = OllamaConnection(
        models=["phi3.5:latest", "gemma2:2b", "llama3.1:latest"], message="Connected"
    )
    assert ollama_model_supported(conn, "phi3.5:latest")
    assert ollama_model_supported(conn, "phi3.5")
    assert ollama_model_supported(conn, "gemma2:2b")
    assert ollama_model_supported(conn, "llama3.1:latest")
    assert ollama_model_supported(conn, "llama3.1")
    assert not ollama_model_supported(conn, "unknown_model")
