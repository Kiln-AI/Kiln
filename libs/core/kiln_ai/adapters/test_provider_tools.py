from unittest.mock import AsyncMock, Mock, patch

import pytest

from kiln_ai.adapters.ml_model_list import (
    KilnModel,
    ModelName,
    ModelProviderName,
)
from kiln_ai.adapters.ollama_tools import OllamaConnection
from kiln_ai.adapters.provider_tools import (
    builtin_model_from,
    check_provider_warnings,
    core_provider,
    finetune_cache,
    finetune_from_id,
    finetune_provider_model,
    get_model_and_provider,
    kiln_model_provider_from,
    lite_llm_config,
    lite_llm_provider_model,
    parse_custom_model_id,
    provider_enabled,
    provider_name_from_id,
    provider_warnings,
)
from kiln_ai.datamodel import Finetune, StructuredOutputMode, Task


@pytest.fixture(autouse=True)
def clear_finetune_cache():
    """Clear the finetune provider model cache before each test"""
    finetune_cache.clear()
    yield


@pytest.fixture
def mock_config():
    with patch("kiln_ai.adapters.provider_tools.get_config_value") as mock:
        yield mock


@pytest.fixture
def mock_project():
    with patch("kiln_ai.adapters.provider_tools.project_from_id") as mock:
        project = Mock()
        project.path = "/fake/path"
        mock.return_value = project
        yield mock


@pytest.fixture
def mock_task():
    with patch("kiln_ai.datamodel.Task.from_id_and_parent_path") as mock:
        task = Mock(spec=Task)
        task.path = "/fake/path/task"
        mock.return_value = task
        yield mock


@pytest.fixture
def mock_finetune():
    with patch("kiln_ai.datamodel.Finetune.from_id_and_parent_path") as mock:
        finetune = Mock(spec=Finetune)
        finetune.provider = ModelProviderName.openai
        finetune.fine_tune_model_id = "ft:gpt-3.5-turbo:custom:model-123"
        finetune.structured_output_mode = StructuredOutputMode.json_schema
        mock.return_value = finetune
        yield mock


@pytest.fixture
def mock_shared_config():
    with patch("kiln_ai.adapters.provider_tools.Config.shared") as mock:
        config = Mock()
        config.openai_compatible_providers = [
            {
                "name": "test_provider",
                "base_url": "https://api.test.com",
                "api_key": "test-key",
            },
            {
                "name": "no_key_provider",
                "base_url": "https://api.nokey.com",
            },
        ]
        mock.return_value = config
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
        (ModelProviderName.kiln_fine_tune, "Fine Tuned Models"),
        (ModelProviderName.kiln_custom_registry, "Custom Models"),
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
    assert provider.model_id == "phi3.5"


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
        ModelName.llama_3_3_70b, ModelProviderName.groq
    )

    assert model is not None
    assert provider is not None
    assert model.name == ModelName.llama_3_3_70b
    assert provider.name == ModelProviderName.groq
    assert provider.model_id == "llama-3.3-70b-versatile"


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

    provider = kiln_model_provider_from("custom_model", ModelProviderName.openai)

    assert provider.name == ModelProviderName.openai
    assert provider.supports_structured_output is False
    assert provider.supports_data_gen is False
    assert provider.untested_model is True
    assert provider.model_id == "custom_model"


@pytest.mark.asyncio
async def test_kiln_model_provider_from_custom_registry(mock_config):
    # Mock config to pass provider warnings check
    mock_config.return_value = "fake-api-key"

    # Test with a custom registry model ID in format "provider::model_name"
    provider = kiln_model_provider_from(
        "openai::gpt-4-turbo", ModelProviderName.kiln_custom_registry
    )

    assert provider.name == ModelProviderName.openai
    assert provider.supports_structured_output is False
    assert provider.supports_data_gen is False
    assert provider.untested_model is True
    assert provider.model_id == "gpt-4-turbo"


@pytest.mark.asyncio
async def test_builtin_model_from_invalid_model():
    """Test that an invalid model name returns None"""
    result = builtin_model_from("non_existent_model")
    assert result is None


@pytest.mark.asyncio
async def test_builtin_model_from_valid_model_default_provider(mock_config):
    """Test getting a valid model with default provider"""
    mock_config.return_value = "fake-api-key"

    provider = builtin_model_from(ModelName.phi_3_5)

    assert provider is not None
    assert provider.name == ModelProviderName.ollama
    assert provider.model_id == "phi3.5"


@pytest.mark.asyncio
async def test_builtin_model_from_valid_model_specific_provider(mock_config):
    """Test getting a valid model with specific provider"""
    mock_config.return_value = "fake-api-key"

    provider = builtin_model_from(
        ModelName.llama_3_3_70b, provider_name=ModelProviderName.groq
    )

    assert provider is not None
    assert provider.name == ModelProviderName.groq
    assert provider.model_id == "llama-3.3-70b-versatile"


@pytest.mark.asyncio
async def test_builtin_model_from_invalid_provider(mock_config):
    """Test that requesting an invalid provider returns None"""
    mock_config.return_value = "fake-api-key"

    provider = builtin_model_from(ModelName.phi_3_5, provider_name="invalid_provider")

    assert provider is None


@pytest.mark.asyncio
async def test_builtin_model_from_model_no_providers():
    """Test handling of a model with no providers"""
    with patch("kiln_ai.adapters.provider_tools.built_in_models") as mock_models:
        # Create a mock model with no providers
        mock_model = KilnModel(
            name=ModelName.phi_3_5,
            friendly_name="Test Model",
            providers=[],
            family="test_family",
        )
        mock_models.__iter__.return_value = [mock_model]

        with pytest.raises(ValueError) as exc_info:
            await builtin_model_from(ModelName.phi_3_5)

        assert str(exc_info.value) == f"Model {ModelName.phi_3_5} has no providers"


@pytest.mark.asyncio
async def test_builtin_model_from_provider_warning_check(mock_config):
    """Test that provider warnings are checked"""
    # Make the config check fail
    mock_config.return_value = None

    with pytest.raises(ValueError) as exc_info:
        await builtin_model_from(ModelName.llama_3_3_70b, ModelProviderName.groq)

    assert provider_warnings[ModelProviderName.groq].message in str(exc_info.value)


def test_finetune_provider_model_success(mock_project, mock_task, mock_finetune):
    """Test successful creation of a fine-tuned model provider"""
    model_id = "project-123::task-456::finetune-789"

    provider = finetune_provider_model(model_id)

    assert provider.name == ModelProviderName.openai
    assert provider.model_id == "ft:gpt-3.5-turbo:custom:model-123"
    assert provider.structured_output_mode == StructuredOutputMode.json_schema


def test_finetune_provider_model_invalid_id():
    """Test handling of invalid model ID format"""
    with pytest.raises(ValueError) as exc_info:
        finetune_provider_model("invalid-id-format")
    assert str(exc_info.value) == "Invalid fine tune ID: invalid-id-format"


def test_finetune_provider_model_project_not_found(mock_project):
    """Test handling of non-existent project"""
    mock_project.return_value = None

    with pytest.raises(ValueError) as exc_info:
        finetune_provider_model("project-123::task-456::finetune-789")
    assert str(exc_info.value) == "Project project-123 not found"


def test_finetune_provider_model_task_not_found(mock_project, mock_task):
    """Test handling of non-existent task"""
    mock_task.return_value = None

    with pytest.raises(ValueError) as exc_info:
        finetune_provider_model("project-123::task-456::finetune-789")
    assert str(exc_info.value) == "Task task-456 not found"


def test_finetune_provider_model_finetune_not_found(
    mock_project, mock_task, mock_finetune
):
    """Test handling of non-existent fine-tune"""
    mock_finetune.return_value = None

    with pytest.raises(ValueError) as exc_info:
        finetune_provider_model("project-123::task-456::finetune-789")
    assert str(exc_info.value) == "Fine tune finetune-789 not found"


def test_finetune_provider_model_incomplete_finetune(
    mock_project, mock_task, mock_finetune
):
    """Test handling of incomplete fine-tune"""
    finetune = Mock(spec=Finetune)
    finetune.fine_tune_model_id = None
    mock_finetune.return_value = finetune

    with pytest.raises(ValueError) as exc_info:
        finetune_provider_model("project-123::task-456::finetune-789")
    assert (
        str(exc_info.value)
        == "Fine tune finetune-789 not completed. Refresh it's status in the fine-tune tab."
    )


@pytest.mark.parametrize(
    "structured_output_mode, provider_name, expected_mode",
    [
        (
            StructuredOutputMode.json_mode,
            ModelProviderName.fireworks_ai,
            StructuredOutputMode.json_mode,
        ),
        (
            StructuredOutputMode.json_schema,
            ModelProviderName.openai,
            StructuredOutputMode.json_schema,
        ),
        (
            StructuredOutputMode.function_calling,
            ModelProviderName.openai,
            StructuredOutputMode.function_calling,
        ),
        (None, ModelProviderName.fireworks_ai, StructuredOutputMode.json_mode),
        (None, ModelProviderName.openai, StructuredOutputMode.json_schema),
    ],
)
def test_finetune_provider_model_structured_mode(
    mock_project,
    mock_task,
    mock_finetune,
    structured_output_mode,
    provider_name,
    expected_mode,
):
    """Test creation of provider with different structured output modes"""
    finetune = Mock(spec=Finetune)
    finetune.provider = provider_name
    finetune.fine_tune_model_id = "fireworks-model-123"
    finetune.structured_output_mode = structured_output_mode
    mock_finetune.return_value = finetune

    provider = finetune_provider_model("project-123::task-456::finetune-789")

    assert provider.name == provider_name
    assert provider.model_id == "fireworks-model-123"
    assert provider.structured_output_mode == expected_mode


def test_openai_compatible_provider_config(mock_shared_config):
    """Test successful creation of an OpenAI compatible provider"""
    model_id = "test_provider::gpt-4"

    config = lite_llm_config(model_id)

    assert config.provider_name == ModelProviderName.openai_compatible
    assert config.model_name == "gpt-4"
    assert config.additional_body_options == {"api_key": "test-key"}
    assert config.base_url == "https://api.test.com"


def test_litellm_provider_model_success(mock_shared_config):
    """Test successful creation of an OpenAI compatible provider"""
    model_id = "test_provider::gpt-4"

    provider = lite_llm_provider_model(model_id)

    assert provider.name == ModelProviderName.openai_compatible
    assert provider.model_id == model_id
    assert provider.supports_structured_output is False
    assert provider.supports_data_gen is False
    assert provider.untested_model is True


def test_lite_llm_config_no_api_key(mock_shared_config):
    """Test provider creation without API key (should work as some providers don't require it, but should pass NA to LiteLLM as it requires one)"""
    model_id = "no_key_provider::gpt-4"

    config = lite_llm_config(model_id)

    assert config.provider_name == ModelProviderName.openai_compatible
    assert config.model_name == "gpt-4"
    assert config.additional_body_options == {"api_key": "NA"}
    assert config.base_url == "https://api.nokey.com"


def test_lite_llm_config_invalid_id():
    """Test handling of invalid model ID format"""
    with pytest.raises(ValueError) as exc_info:
        lite_llm_config("invalid-id-format")
    assert (
        str(exc_info.value) == "Invalid openai compatible model ID: invalid-id-format"
    )


def test_lite_llm_config_no_providers(mock_shared_config):
    """Test handling when no providers are configured"""
    mock_shared_config.return_value.openai_compatible_providers = None

    with pytest.raises(ValueError) as exc_info:
        lite_llm_config("test_provider::gpt-4")
    assert str(exc_info.value) == "OpenAI compatible provider test_provider not found"


def test_lite_llm_config_provider_not_found(mock_shared_config):
    """Test handling of non-existent provider"""
    with pytest.raises(ValueError) as exc_info:
        lite_llm_config("unknown_provider::gpt-4")
    assert (
        str(exc_info.value) == "OpenAI compatible provider unknown_provider not found"
    )


def test_lite_llm_config_no_base_url(mock_shared_config):
    """Test handling of provider without base URL"""
    mock_shared_config.return_value.openai_compatible_providers = [
        {
            "name": "test_provider",
            "api_key": "test-key",
        }
    ]

    with pytest.raises(ValueError) as exc_info:
        lite_llm_config("test_provider::gpt-4")
    assert (
        str(exc_info.value)
        == "OpenAI compatible provider test_provider has no base URL"
    )


def test_parse_custom_model_id_valid():
    """Test parsing a valid custom model ID"""
    provider_name, model_name = parse_custom_model_id(
        "openai::gpt-4-turbo-elite-enterprise-editon"
    )
    assert provider_name == ModelProviderName.openai
    assert model_name == "gpt-4-turbo-elite-enterprise-editon"


def test_parse_custom_model_id_no_separator():
    """Test parsing an invalid model ID without separator"""
    with pytest.raises(ValueError) as exc_info:
        parse_custom_model_id("invalid-model-id")
    assert str(exc_info.value) == "Invalid custom model ID: invalid-model-id"


def test_parse_custom_model_id_invalid_provider():
    """Test parsing model ID with invalid provider"""
    with pytest.raises(ValueError) as exc_info:
        parse_custom_model_id("invalid_provider::model")
    assert str(exc_info.value) == "Invalid provider name: invalid_provider"


def test_parse_custom_model_id_empty_parts():
    """Test parsing model ID with empty provider or model name"""
    with pytest.raises(ValueError) as exc_info:
        parse_custom_model_id("::model")
    assert str(exc_info.value) == "Invalid provider name: "


def test_core_provider_basic_provider():
    """Test core_provider with a basic provider that doesn't need mapping"""
    result = core_provider("gpt-4", ModelProviderName.openai)
    assert result == ModelProviderName.openai


def test_core_provider_custom_registry():
    """Test core_provider with custom registry provider"""
    result = core_provider("openai::gpt-4", ModelProviderName.kiln_custom_registry)
    assert result == ModelProviderName.openai


def test_core_provider_finetune():
    """Test core_provider with fine-tune provider"""
    model_id = "project-123::task-456::finetune-789"

    with patch(
        "kiln_ai.adapters.provider_tools.finetune_from_id"
    ) as mock_finetune_from_id:
        # Mock the finetune object
        finetune = Mock(spec=Finetune)
        finetune.provider = ModelProviderName.openai
        mock_finetune_from_id.return_value = finetune

        result = core_provider(model_id, ModelProviderName.kiln_fine_tune)
        assert result == ModelProviderName.openai
        mock_finetune_from_id.assert_called_once_with(model_id)


def test_core_provider_finetune_invalid_provider():
    """Test core_provider with fine-tune having invalid provider"""
    model_id = "project-123::task-456::finetune-789"

    with patch(
        "kiln_ai.adapters.provider_tools.finetune_from_id"
    ) as mock_finetune_from_id:
        # Mock finetune with invalid provider
        finetune = Mock(spec=Finetune)
        finetune.provider = "invalid_provider"
        mock_finetune_from_id.return_value = finetune

        with pytest.raises(ValueError) as exc_info:
            core_provider(model_id, ModelProviderName.kiln_fine_tune)
        assert (
            str(exc_info.value)
            == f"Finetune {model_id} has no underlying provider invalid_provider"
        )
        mock_finetune_from_id.assert_called_once_with(model_id)


def test_finetune_from_id_success(mock_project, mock_task, mock_finetune):
    """Test successful retrieval of a finetune model"""
    model_id = "project-123::task-456::finetune-789"

    # First call should hit the database
    finetune = finetune_from_id(model_id)

    assert finetune.provider == ModelProviderName.openai
    assert finetune.fine_tune_model_id == "ft:gpt-3.5-turbo:custom:model-123"

    # Verify mocks were called correctly
    mock_project.assert_called_once_with("project-123")
    mock_task.assert_called_once_with("task-456", "/fake/path")
    mock_finetune.assert_called_once_with("finetune-789", "/fake/path/task")

    # Second call should use cache
    cached_finetune = finetune_from_id(model_id)
    assert cached_finetune is finetune

    # Verify no additional disk calls were made
    mock_project.assert_called_once()
    mock_task.assert_called_once()
    mock_finetune.assert_called_once()


def test_finetune_from_id_invalid_id():
    """Test handling of invalid model ID format"""
    with pytest.raises(ValueError) as exc_info:
        finetune_from_id("invalid-id-format")
    assert str(exc_info.value) == "Invalid fine tune ID: invalid-id-format"


def test_finetune_from_id_project_not_found(mock_project):
    """Test handling of non-existent project"""
    mock_project.return_value = None
    model_id = "project-123::task-456::finetune-789"

    with pytest.raises(ValueError) as exc_info:
        finetune_from_id(model_id)
    assert str(exc_info.value) == "Project project-123 not found"

    # Verify cache was not populated
    assert model_id not in finetune_cache


def test_finetune_from_id_task_not_found(mock_project, mock_task):
    """Test handling of non-existent task"""
    mock_task.return_value = None
    model_id = "project-123::task-456::finetune-789"

    with pytest.raises(ValueError) as exc_info:
        finetune_from_id(model_id)
    assert str(exc_info.value) == "Task task-456 not found"

    # Verify cache was not populated
    assert model_id not in finetune_cache


def test_finetune_from_id_finetune_not_found(mock_project, mock_task, mock_finetune):
    """Test handling of non-existent finetune"""
    mock_finetune.return_value = None
    model_id = "project-123::task-456::finetune-789"

    with pytest.raises(ValueError) as exc_info:
        finetune_from_id(model_id)
    assert str(exc_info.value) == "Fine tune finetune-789 not found"

    # Verify cache was not populated
    assert model_id not in finetune_cache


def test_finetune_from_id_incomplete_finetune(mock_project, mock_task, mock_finetune):
    """Test handling of incomplete finetune"""
    finetune = Mock(spec=Finetune)
    finetune.fine_tune_model_id = None
    mock_finetune.return_value = finetune
    model_id = "project-123::task-456::finetune-789"

    with pytest.raises(ValueError) as exc_info:
        finetune_from_id(model_id)
    assert (
        str(exc_info.value)
        == "Fine tune finetune-789 not completed. Refresh it's status in the fine-tune tab."
    )

    # Verify cache was not populated with incomplete finetune
    assert model_id not in finetune_cache


def test_finetune_from_id_cache_hit(mock_project, mock_task, mock_finetune):
    """Test that cached finetune is returned without database calls"""
    model_id = "project-123::task-456::finetune-789"

    # Pre-populate cache
    finetune = Mock(spec=Finetune)
    finetune.fine_tune_model_id = "ft:gpt-3.5-turbo:custom:model-123"
    finetune_cache[model_id] = finetune

    # Get finetune from cache
    result = finetune_from_id(model_id)

    assert result == finetune
    # Verify no database calls were made
    mock_project.assert_not_called()
    mock_task.assert_not_called()
    mock_finetune.assert_not_called()
