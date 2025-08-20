import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import httpx
import litellm
import openai
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from kiln_ai.adapters.ml_embedding_model_list import (
    EmbeddingModelName,
    KilnEmbeddingModel,
    KilnEmbeddingModelProvider,
    built_in_embedding_models,
)
from kiln_ai.adapters.ml_model_list import (
    KilnModel,
    KilnModelProvider,
    ModelName,
    ModelProviderName,
    StructuredOutputMode,
    built_in_models,
)
from kiln_ai.utils.config import Config

from app.desktop.studio_server.provider_api import (
    AvailableModels,
    ModelDetails,
    OllamaConnection,
    OpenAICompatibleProviderCache,
    all_fine_tuned_models,
    available_ollama_models,
    connect_anthropic,
    connect_azure_openai,
    connect_bedrock,
    connect_docker_model_runner,
    connect_gemini,
    connect_groq,
    connect_huggingface,
    connect_ollama,
    connect_openrouter,
    connect_provider_api,
    connect_siliconflow,
    connect_together,
    connect_vertex,
    connect_wandb,
    custom_models,
    models_from_ollama_tag,
    openai_compatible_providers,
    openai_compatible_providers_load_cache,
    parse_url,
)


@pytest.fixture
def app():
    app = FastAPI()
    connect_provider_api(app)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.mark.parametrize(
    "provider",
    [
        "openai",
        "groq",
        "openrouter",
        "fireworks_ai",
        "amazon_bedrock",
        "anthropic",
        "gemini_api",
        "azure_openai",
        "huggingface",
        "vertex",
        "together_ai",
        "siliconflow_cn",
    ],
)
def test_connect_api_key_invalid_payload(client, provider):
    response = client.post(
        "/api/provider/connect_api_key",
        json={"provider": provider, "key_data": "invalid"},
    )
    assert response.status_code == 400
    assert response.json() == {"message": "Invalid key_data or provider"}


def test_connect_api_key_unsupported_provider(client):
    response = client.post(
        "/api/provider/connect_api_key",
        json={"provider": "unsupported", "key_data": {"API Key": "test"}},
    )
    assert response.status_code == 400
    assert response.json() == {"message": "Provider unsupported not supported"}


@patch("app.desktop.studio_server.provider_api.connect_openai")
def test_connect_api_key_openai_success(mock_connect_openai, client):
    mock_connect_openai.return_value = {"message": "Connected to OpenAI"}
    response = client.post(
        "/api/provider/connect_api_key",
        json={"provider": "openai", "key_data": {"API Key": "test_key"}},
    )
    assert response.status_code == 200
    assert response.json() == {"message": "Connected to OpenAI"}
    mock_connect_openai.assert_called_once_with("test_key")


@patch("app.desktop.studio_server.provider_api.connect_siliconflow")
def test_connect_api_key_siliconflow_success(mock_connect_siliconflow, client):
    mock_connect_siliconflow.return_value = {"message": "Connected to Siliconflow"}
    response = client.post(
        "/api/provider/connect_api_key",
        json={"provider": "siliconflow_cn", "key_data": {"API Key": "test_key"}},
    )
    assert response.status_code == 200
    assert response.json() == {"message": "Connected to Siliconflow"}
    mock_connect_siliconflow.assert_called_once_with("test_key")


@patch("app.desktop.studio_server.provider_api.requests.get")
@patch("app.desktop.studio_server.provider_api.Config.shared")
def test_connect_openai_success(mock_config_shared, mock_requests_get, client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_requests_get.return_value = mock_response

    mock_config = MagicMock()
    mock_config_shared.return_value = mock_config

    response = client.post(
        "/api/provider/connect_api_key",
        json={"provider": "openai", "key_data": {"API Key": "test_key"}},
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Connected to OpenAI"}
    assert mock_config.open_ai_api_key == "test_key"


@patch("app.desktop.studio_server.provider_api.requests.get")
def test_connect_openai_invalid_key(mock_requests_get, client):
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_requests_get.return_value = mock_response

    response = client.post(
        "/api/provider/connect_api_key",
        json={"provider": "openai", "key_data": {"API Key": "invalid_key"}},
    )

    assert response.status_code == 401
    assert response.json() == {
        "message": "Failed to connect to OpenAI. Invalid API key."
    }


@patch("app.desktop.studio_server.provider_api.requests.get")
def test_connect_openai_request_exception(mock_requests_get, client):
    mock_requests_get.side_effect = Exception("Test error")

    response = client.post(
        "/api/provider/connect_api_key",
        json={"provider": "openai", "key_data": {"API Key": "test_key"}},
    )

    assert response.status_code == 400
    assert "Failed to connect to OpenAI. Error:" in response.json()["message"]


@pytest.fixture
def mock_requests_get():
    with patch("app.desktop.studio_server.provider_api.requests.get") as mock_get:
        yield mock_get


@pytest.fixture
def mock_config():
    with patch("app.desktop.studio_server.provider_api.Config") as mock_config:
        mock_config.shared.return_value = MagicMock()
        yield mock_config


@patch("app.desktop.studio_server.provider_api.requests.get")
@patch("app.desktop.studio_server.provider_api.Config.shared")
async def test_connect_groq_success(mock_config_shared, mock_requests_get):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '{"models": []}'
    mock_requests_get.return_value = mock_response

    mock_config = MagicMock()
    mock_config_shared.return_value = mock_config

    assert mock_config.shared.return_value.groq_api_key != "test_api_key"
    result = await connect_groq("test_api_key")

    assert result.status_code == 200
    assert result.body == b'{"message":"Connected to Groq"}'
    mock_config.shared.return_value.groq_api_key = "test_api_key"
    mock_requests_get.assert_called_once_with(
        "https://api.groq.com/openai/v1/models",
        headers={
            "Authorization": "Bearer test_api_key",
            "Content-Type": "application/json",
        },
    )
    assert mock_config.shared.return_value.groq_api_key == "test_api_key"


async def test_connect_groq_invalid_api_key(mock_requests_get):
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = "{a:'invalid_api_key'}"
    mock_requests_get.return_value = mock_response

    result = await connect_groq("invalid_key")

    assert result.status_code == 401
    response_data = json.loads(result.body)
    assert "Invalid API key" in response_data["message"]


async def test_connect_groq_request_error(mock_requests_get):
    mock_requests_get.side_effect = Exception("Connection error")

    result = await connect_groq("test_api_key")

    assert result.status_code == 400
    response_data = json.loads(result.body)
    assert "Failed to connect to Groq" in response_data["message"]


async def test_connect_groq_non_200_response(mock_requests_get):
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.raise_for_status.side_effect = Exception("Server error")
    mock_requests_get.return_value = mock_response

    result = await connect_groq("test_api_key")

    assert result.status_code == 400
    response_data = json.loads(result.body)
    assert "Failed to connect to Groq" in response_data["message"]


@pytest.mark.asyncio
async def test_connect_openrouter():
    # Test case 1: Valid API key
    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = (
            400  # Simulating an expected error due to empty body
        )
        mock_post.return_value = mock_response

        result = await connect_openrouter("valid_api_key")
        assert result.status_code == 200
        assert result.body == b'{"message":"Connected to OpenRouter"}'
        assert Config.shared().open_router_api_key == "valid_api_key"

    # Test case 2: Invalid API key
    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_post.return_value = mock_response

        result = await connect_openrouter("invalid_api_key")
        assert result.status_code == 401
        assert (
            result.body
            == b'{"message":"Failed to connect to OpenRouter. Invalid API key."}'
        )
        assert Config.shared().open_router_api_key != "invalid_api_key"

    # Test case 3: Unexpected error
    with patch("requests.post") as mock_post:
        mock_post.side_effect = Exception("Unexpected error")

        result = await connect_openrouter("api_key")
        assert result.status_code == 400
        assert (
            b"Failed to connect to OpenRouter. Error: Unexpected error" in result.body
        )
        assert Config.shared().open_router_api_key != "api_key"


@pytest.fixture
def mock_environ():
    with patch("os.environ", {}) as mock_env:
        yield mock_env


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.litellm.acompletion")
async def test_connect_bedrock_success(mock_litellm_acompletion, mock_environ):
    mock_litellm_acompletion.side_effect = litellm.exceptions.BadRequestError(
        "msg", "model", "provider"
    )
    result = await connect_bedrock(
        {"Access Key": "test_access_key", "Secret Key": "test_secret_key"}
    )

    assert isinstance(result, JSONResponse)
    assert result.status_code == 200
    assert result.body == b'{"message":"Connected to Bedrock"}'
    assert Config.shared().bedrock_access_key == "test_access_key"
    assert Config.shared().bedrock_secret_key == "test_secret_key"

    mock_litellm_acompletion.assert_called_once()


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.litellm.acompletion")
async def test_connect_bedrock_invalid_credentials(
    mock_litellm_acompletion, mock_environ
):
    mock_litellm_acompletion.side_effect = litellm.exceptions.AuthenticationError(
        "msg", "model", "provider"
    )

    result = await connect_bedrock(
        {"Access Key": "invalid_access_key", "Secret Key": "invalid_secret_key"}
    )

    assert isinstance(result, JSONResponse)
    assert result.status_code == 401
    assert (
        result.body
        == b'{"message":"Failed to connect to Bedrock. Invalid credentials."}'
    )

    assert "AWS_ACCESS_KEY_ID" not in mock_environ
    assert "AWS_SECRET_ACCESS_KEY" not in mock_environ


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.litellm.acompletion")
async def test_connect_bedrock_unknown_error(mock_litellm_acompletion, mock_environ):
    mock_litellm_acompletion.side_effect = Exception("Some unexpected error")

    with pytest.raises(Exception):
        await connect_bedrock(
            {"Access Key": "test_access_key", "Secret Key": "test_secret_key"}
        )


@pytest.mark.asyncio
async def test_connect_docker_model_runner_invalid_url():
    """Test connect_docker_model_runner with invalid URL format"""
    with pytest.raises(HTTPException) as exc_info:
        await connect_docker_model_runner("invalid-url")

    assert exc_info.value.status_code == 400
    assert "Invalid Docker Model Runner URL" in exc_info.value.detail


@pytest.mark.asyncio
async def test_connect_docker_model_runner_connection_failure():
    """Test connect_docker_model_runner when connection fails"""
    with patch(
        "app.desktop.studio_server.provider_api.get_docker_model_runner_connection"
    ) as mock_get_connection:
        mock_get_connection.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await connect_docker_model_runner("http://localhost:12434")

        assert exc_info.value.status_code == 417
        assert "Failed to connect" in exc_info.value.detail


@pytest.mark.asyncio
async def test_connect_docker_model_runner_api_error():
    """Test connect_docker_model_runner with API errors"""
    with patch(
        "app.desktop.studio_server.provider_api.get_docker_model_runner_connection"
    ) as mock_get_connection:
        mock_get_connection.side_effect = openai.APIConnectionError(request=Mock())

        with pytest.raises(HTTPException) as exc_info:
            await connect_docker_model_runner("http://localhost:12434")

        assert exc_info.value.status_code == 500
        assert "Failed to connect to Docker Model Runner" in exc_info.value.detail


@pytest.mark.asyncio
async def test_connect_docker_model_runner_http_error():
    """Test connect_docker_model_runner with HTTP errors"""
    import httpx

    with patch(
        "app.desktop.studio_server.provider_api.get_docker_model_runner_connection"
    ) as mock_get_connection:
        mock_get_connection.side_effect = httpx.RequestError("Connection error")

        with pytest.raises(HTTPException) as exc_info:
            await connect_docker_model_runner("http://localhost:12434")

        assert exc_info.value.status_code == 500
        assert "Failed to connect to Docker Model Runner" in exc_info.value.detail


@pytest.mark.asyncio
async def test_connect_docker_model_runner_preserves_http_exception():
    """Test connect_docker_model_runner preserves HTTPException from earlier raises"""
    with patch(
        "app.desktop.studio_server.provider_api.get_docker_model_runner_connection"
    ) as mock_get_connection:
        # First raise HTTPException for invalid URL, then it should be preserved
        original_exception = HTTPException(status_code=400, detail="Invalid URL")
        mock_get_connection.side_effect = original_exception

        with pytest.raises(HTTPException) as exc_info:
            await connect_docker_model_runner("http://localhost:12434")

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Invalid URL"


@pytest.mark.asyncio
async def test_connect_docker_model_runner_saves_custom_url():
    """Test connect_docker_model_runner saves custom URL on success"""
    from app.desktop.studio_server.provider_api import DockerModelRunnerConnection

    mock_connection = DockerModelRunnerConnection(
        message="Connected", supported_models=["model1"], untested_models=[]
    )

    with (
        patch(
            "app.desktop.studio_server.provider_api.get_docker_model_runner_connection"
        ) as mock_get_connection,
        patch("app.desktop.studio_server.provider_api.Config.shared") as mock_config,
    ):
        mock_get_connection.return_value = mock_connection
        mock_config_instance = MagicMock()
        mock_config_instance.docker_model_runner_base_url = (
            "http://localhost:12434/engines/llama.cpp"
        )
        mock_config.return_value = mock_config_instance

        custom_url = "http://custom:8080/engines/llama.cpp"
        result = await connect_docker_model_runner(custom_url)

        assert result == mock_connection
        mock_config_instance.save_setting.assert_called_once_with(
            "docker_model_runner_base_url", custom_url
        )


@pytest.mark.asyncio
async def test_connect_docker_model_runner_does_not_save_same_url():
    """Test connect_docker_model_runner doesn't save URL if it's the same as current"""
    from app.desktop.studio_server.provider_api import DockerModelRunnerConnection

    mock_connection = DockerModelRunnerConnection(
        message="Connected", supported_models=["model1"], untested_models=[]
    )

    with (
        patch(
            "app.desktop.studio_server.provider_api.get_docker_model_runner_connection"
        ) as mock_get_connection,
        patch("app.desktop.studio_server.provider_api.Config.shared") as mock_config,
    ):
        mock_get_connection.return_value = mock_connection
        mock_config_instance = MagicMock()
        same_url = "http://localhost:12434/engines/llama.cpp"
        mock_config_instance.docker_model_runner_base_url = same_url
        mock_config.return_value = mock_config_instance

        result = await connect_docker_model_runner(same_url)

        assert result == mock_connection
        mock_config_instance.save_setting.assert_not_called()


@pytest.mark.asyncio
async def test_connect_docker_model_runner_api_endpoint(client):
    """Test the /api/provider/docker_model_runner/connect endpoint"""
    from app.desktop.studio_server.provider_api import DockerModelRunnerConnection

    mock_connection = DockerModelRunnerConnection(
        message="Connected", supported_models=["model1"], untested_models=[]
    )

    with patch(
        "app.desktop.studio_server.provider_api.connect_docker_model_runner"
    ) as mock_connect:
        mock_connect.return_value = mock_connection

        response = client.get("/api/provider/docker_model_runner/connect")

        assert response.status_code == 200
        mock_connect.assert_called_once_with(None)


@pytest.mark.asyncio
async def test_connect_docker_model_runner_api_endpoint_with_custom_url(client):
    """Test the /api/provider/docker_model_runner/connect endpoint with custom URL"""
    from app.desktop.studio_server.provider_api import DockerModelRunnerConnection

    mock_connection = DockerModelRunnerConnection(
        message="Connected", supported_models=["model1"], untested_models=[]
    )

    with patch(
        "app.desktop.studio_server.provider_api.connect_docker_model_runner"
    ) as mock_connect:
        mock_connect.return_value = mock_connection

        custom_url = "http://custom:8080/engines/llama.cpp"
        response = client.get(
            "/api/provider/docker_model_runner/connect",
            params={"docker_model_runner_custom_url": custom_url},
        )

        assert response.status_code == 200
        mock_connect.assert_called_once_with(custom_url)


@pytest.mark.asyncio
async def test_available_docker_model_runner_models_success():
    """Test available_docker_model_runner_models with successful connection"""
    from app.desktop.studio_server.provider_api import (
        DockerModelRunnerConnection,
        available_docker_model_runner_models,
    )

    # Create mock connection
    mock_connection = DockerModelRunnerConnection(
        message="Connected",
        supported_models=["supported1", "supported2"],
        untested_models=["custom-model"],
    )

    # Create test models that match Docker Model Runner IDs
    test_models = [
        KilnModel(
            name="supported1",
            friendly_name="Supported 1",
            family="llama",
            providers=[
                KilnModelProvider(
                    name=ModelProviderName.docker_model_runner,
                    model_id="supported1",
                    supports_structured_output=True,
                    structured_output_mode=StructuredOutputMode.json_schema,
                )
            ],
        ),
        KilnModel(
            name="supported2",
            friendly_name="Supported 2",
            family="mistral",
            providers=[
                KilnModelProvider(
                    name=ModelProviderName.docker_model_runner,
                    model_id="supported2",
                    supports_structured_output=False,
                    structured_output_mode=StructuredOutputMode.json_schema,
                )
            ],
        ),
    ]

    with (
        patch(
            "app.desktop.studio_server.provider_api.get_docker_model_runner_connection"
        ) as mock_get_connection,
        patch("app.desktop.studio_server.provider_api.built_in_models", test_models),
    ):
        mock_get_connection.return_value = mock_connection

        result = await available_docker_model_runner_models()

        assert result is not None
        assert result.provider_name == "Docker Model Runner"
        assert result.provider_id == ModelProviderName.docker_model_runner
        assert len(result.models) == 3  # 2 supported + 1 untested

        # Check first supported model
        assert result.models[0].id == "supported1"
        assert result.models[0].name == "Supported 1"
        assert result.models[0].supports_structured_output is True
        assert (
            result.models[0].structured_output_mode == StructuredOutputMode.json_schema
        )
        assert result.models[0].untested_model is False

        # Check second supported model
        assert result.models[1].id == "supported2"
        assert result.models[1].name == "Supported 2"
        assert result.models[1].supports_structured_output is False
        assert (
            result.models[1].structured_output_mode == StructuredOutputMode.json_schema
        )
        assert result.models[1].untested_model is False

        # Check untested model
        assert result.models[2].id == "custom-model"
        assert result.models[2].name == "custom-model"
        assert result.models[2].supports_structured_output is True
        assert (
            result.models[2].structured_output_mode == StructuredOutputMode.json_schema
        )
        assert result.models[2].untested_model is True


@pytest.mark.asyncio
async def test_available_docker_model_runner_models_no_connection():
    """Test available_docker_model_runner_models when connection fails"""
    from app.desktop.studio_server.provider_api import (
        available_docker_model_runner_models,
    )

    with patch(
        "app.desktop.studio_server.provider_api.get_docker_model_runner_connection"
    ) as mock_get_connection:
        mock_get_connection.return_value = None

        result = await available_docker_model_runner_models()

        assert result is None


@pytest.mark.asyncio
async def test_available_docker_model_runner_models_no_models():
    """Test available_docker_model_runner_models when no models are available"""
    from app.desktop.studio_server.provider_api import (
        DockerModelRunnerConnection,
        available_docker_model_runner_models,
    )

    # Create mock connection with no models
    mock_connection = DockerModelRunnerConnection(
        message="Connected", supported_models=[], untested_models=[]
    )

    with (
        patch(
            "app.desktop.studio_server.provider_api.get_docker_model_runner_connection"
        ) as mock_get_connection,
        patch("app.desktop.studio_server.provider_api.built_in_models", []),
    ):
        mock_get_connection.return_value = mock_connection

        result = await available_docker_model_runner_models()

        assert result is None


@pytest.mark.asyncio
async def test_available_docker_model_runner_models_api_error():
    """Test available_docker_model_runner_models with API errors"""
    from app.desktop.studio_server.provider_api import (
        available_docker_model_runner_models,
    )

    with patch(
        "app.desktop.studio_server.provider_api.get_docker_model_runner_connection"
    ) as mock_get_connection:
        mock_get_connection.side_effect = openai.APIConnectionError(request=Mock())

        result = await available_docker_model_runner_models()

        assert result is None


@pytest.mark.asyncio
async def test_available_docker_model_runner_models_http_error():
    """Test available_docker_model_runner_models with HTTP errors"""
    from app.desktop.studio_server.provider_api import (
        available_docker_model_runner_models,
    )

    with patch(
        "app.desktop.studio_server.provider_api.get_docker_model_runner_connection"
    ) as mock_get_connection:
        mock_get_connection.side_effect = httpx.RequestError("Connection error")

        result = await available_docker_model_runner_models()

        assert result is None


@pytest.mark.asyncio
async def test_available_docker_model_runner_models_http_exception():
    """Test available_docker_model_runner_models with HTTPException"""
    from app.desktop.studio_server.provider_api import (
        available_docker_model_runner_models,
    )

    with patch(
        "app.desktop.studio_server.provider_api.get_docker_model_runner_connection"
    ) as mock_get_connection:
        mock_get_connection.side_effect = HTTPException(
            status_code=500, detail="Server error"
        )

        result = await available_docker_model_runner_models()

        assert result is None


def test_models_from_docker_model_runner_id():
    """Test models_from_docker_model_runner_id function"""
    from app.desktop.studio_server.provider_api import (
        models_from_docker_model_runner_id,
    )

    # Create test models
    test_models = [
        KilnModel(
            name="supported1",
            friendly_name="Supported 1",
            family="llama",
            providers=[
                KilnModelProvider(
                    name=ModelProviderName.docker_model_runner,
                    model_id="supported1",
                    supports_structured_output=True,
                )
            ],
        ),
        KilnModel(
            name="supported2",
            friendly_name="Supported 2",
            family="mistral",
            providers=[
                KilnModelProvider(
                    name=ModelProviderName.docker_model_runner,
                    model_id="supported2",
                    supports_structured_output=False,
                ),
                KilnModelProvider(
                    name=ModelProviderName.openai,
                    model_id="gpt-4",
                    supports_structured_output=True,
                ),
            ],
        ),
        KilnModel(
            name="openai_only_model",
            friendly_name="OpenAI Only Model",
            family="gpt",
            providers=[
                KilnModelProvider(
                    name=ModelProviderName.openai,
                    model_id="gpt-3.5-turbo",
                    supports_structured_output=True,
                )
            ],
        ),
    ]

    with patch("app.desktop.studio_server.provider_api.built_in_models", test_models):
        # Test matching Docker Model Runner ID
        results = models_from_docker_model_runner_id("supported1")
        assert len(results) == 1
        model, provider = results[0]
        assert model.name == "supported1"
        assert provider.name == ModelProviderName.docker_model_runner
        assert provider.model_id == "supported1"

        # Test matching Docker Model Runner ID with multiple providers
        results = models_from_docker_model_runner_id("supported2")
        assert len(results) == 1
        model, provider = results[0]
        assert model.name == "supported2"
        assert provider.name == ModelProviderName.docker_model_runner
        assert provider.model_id == "supported2"

        # Test non-matching ID
        results = models_from_docker_model_runner_id("non-existent-model")
        assert len(results) == 0

        # Test model without Docker Model Runner provider
        results = models_from_docker_model_runner_id("gpt-3.5-turbo")
        assert len(results) == 0


@pytest.mark.asyncio
async def test_get_available_models(app, client):
    # Mock Config.shared()
    mock_config = MagicMock()
    mock_config.get_value.return_value = "mock_key"

    # Mock provider_warnings
    mock_provider_warnings = {
        ModelProviderName.openai: MagicMock(required_config_keys=["key1"]),
        ModelProviderName.amazon_bedrock: MagicMock(required_config_keys=["key2"]),
    }

    # Mock built_in_models
    mock_built_in_models = [
        KilnModel(
            name="model1",
            friendly_name="Model 1",
            family="",
            providers=[
                KilnModelProvider(
                    name=ModelProviderName.openai,
                    model_id="oai1",
                    structured_output_mode="json_schema",
                )
            ],
        ),
        KilnModel(
            name="model2",
            friendly_name="Model 2",
            family="",
            providers=[
                KilnModelProvider(
                    name=ModelProviderName.amazon_bedrock,
                    model_id="bedrock1",
                    supports_structured_output=False,
                    supports_data_gen=False,
                    structured_output_mode="json_instructions",
                    suggested_for_evals=True,
                    uncensored=True,
                    suggested_for_uncensored_data_gen=True,
                ),
                KilnModelProvider(
                    name=ModelProviderName.ollama,
                    supports_structured_output=True,
                    model_id="ollama_model2",
                ),
                # Fine-tune only model should not appear in the list of available models
                KilnModelProvider(
                    name=ModelProviderName.together_ai,
                    provider_finetune_id="together_model2",
                    structured_output_mode="json_instructions",
                ),
            ],
        ),
    ]

    # Mock connect_ollama
    mock_ollama_connection = OllamaConnection(
        message="Connected", supported_models=["ollama_model1", "ollama_model2:latest"]
    )

    with (
        patch(
            "app.desktop.studio_server.provider_api.Config.shared",
            return_value=mock_config,
        ),
        patch(
            "app.desktop.studio_server.provider_api.provider_warnings",
            mock_provider_warnings,
        ),
        patch(
            "app.desktop.studio_server.provider_api.built_in_models",
            mock_built_in_models,
        ),
        patch(
            "app.desktop.studio_server.provider_api.connect_ollama",
            return_value=mock_ollama_connection,
        ),
    ):
        response = client.get("/api/available_models")

    assert response.status_code == 200
    assert response.json() == [
        {
            "provider_id": "ollama",
            "provider_name": "Ollama",
            "models": [
                {
                    "id": "model2",
                    "name": "Model 2",
                    "supports_structured_output": True,
                    "supports_data_gen": True,
                    "suggested_for_data_gen": False,
                    "suggested_for_evals": False,
                    "uncensored": False,
                    "suggested_for_uncensored_data_gen": False,
                    "supports_logprobs": False,
                    "structured_output_mode": "json_schema",
                    "task_filter": None,
                    "untested_model": False,
                    "supports_doc_extraction": False,
                    "multimodal_capable": False,
                    "multimodal_mime_types": None,
                }
            ],
        },
        {
            "provider_id": "openai",
            "provider_name": "OpenAI",
            "models": [
                {
                    "id": "model1",
                    "name": "Model 1",
                    "supports_structured_output": True,
                    "supports_data_gen": True,
                    "suggested_for_uncensored_data_gen": False,
                    "supports_logprobs": False,
                    "structured_output_mode": "json_schema",
                    "task_filter": None,
                    "untested_model": False,
                    "suggested_for_data_gen": False,
                    "suggested_for_evals": False,
                    "uncensored": False,
                    "supports_doc_extraction": False,
                    "multimodal_capable": False,
                    "multimodal_mime_types": None,
                },
            ],
        },
        {
            "provider_id": "amazon_bedrock",
            "provider_name": "Amazon Bedrock",
            "models": [
                {
                    "id": "model2",
                    "name": "Model 2",
                    "supports_structured_output": False,
                    "supports_data_gen": False,
                    "suggested_for_uncensored_data_gen": True,
                    "supports_logprobs": False,
                    "structured_output_mode": "json_instructions",
                    "task_filter": None,
                    "untested_model": False,
                    "suggested_for_data_gen": False,
                    "suggested_for_evals": True,
                    "uncensored": True,
                    "supports_doc_extraction": False,
                    "multimodal_capable": False,
                    "multimodal_mime_types": None,
                }
            ],
        },
    ]


@pytest.mark.asyncio
async def test_get_available_models_ollama_exception(app, client):
    # Mock Config.shared()
    mock_config = MagicMock()
    mock_config.get_value.return_value = "mock_key"

    # Mock provider_warnings
    mock_provider_warnings = {
        ModelProviderName.openai: MagicMock(required_config_keys=["key1"]),
    }

    # Mock built_in_models
    mock_built_in_models = [
        KilnModel(
            name="model1",
            family="",
            friendly_name="Model 1",
            providers=[
                KilnModelProvider(name=ModelProviderName.openai, model_id="123")
            ],
        ),
    ]

    # Mock connect_ollama to raise an HTTPException
    with (
        patch(
            "app.desktop.studio_server.provider_api.Config.shared",
            return_value=mock_config,
        ),
        patch(
            "app.desktop.studio_server.provider_api.provider_warnings",
            mock_provider_warnings,
        ),
        patch(
            "app.desktop.studio_server.provider_api.built_in_models",
            mock_built_in_models,
        ),
        patch(
            "app.desktop.studio_server.provider_api.connect_ollama",
            side_effect=HTTPException(status_code=500),
        ),
    ):
        response = client.get("/api/available_models")

    assert response.status_code == 200
    json = response.json()
    assert json == [
        {
            "provider_id": "openai",
            "provider_name": "OpenAI",
            "models": [
                {
                    "id": "model1",
                    "name": "Model 1",
                    "supports_structured_output": True,
                    "supports_data_gen": True,
                    "suggested_for_uncensored_data_gen": False,
                    "supports_logprobs": False,
                    "structured_output_mode": "default",
                    "task_filter": None,
                    "untested_model": False,
                    "suggested_for_data_gen": False,
                    "suggested_for_evals": False,
                    "uncensored": False,
                    "supports_doc_extraction": False,
                    "multimodal_capable": False,
                    "multimodal_mime_types": None,
                }
            ],
        },
    ]


def test_get_providers_models(client):
    response = client.get("/api/providers/models")
    assert response.status_code == 200

    data = response.json()
    assert "models" in data

    # Check if all built-in models are present in the response
    for model in built_in_models:
        assert model.name in data["models"]
        assert data["models"][model.name]["id"] == model.name
        assert data["models"][model.name]["name"] == model.friendly_name

    # Check if the number of models in the response matches the number of built-in models
    assert len(data["models"]) == len(built_in_models)

    if ModelName.llama_3_1_8b in data["models"]:
        assert data["models"][ModelName.llama_3_1_8b]["id"] == ModelName.llama_3_1_8b
        assert data["models"][ModelName.llama_3_1_8b]["name"] == "Llama 3.1 8B"


def test_model_from_ollama_tag():
    # Create test models
    test_models = [
        KilnModel(
            name="model1",
            friendly_name="Model 1",
            family="test",
            providers=[
                KilnModelProvider(
                    name=ModelProviderName.ollama,
                    model_id="llama2",
                    ollama_model_aliases=["llama-2", "llama2-chat"],
                )
            ],
        ),
        KilnModel(
            name="model2",
            friendly_name="Model 2",
            family="test",
            providers=[
                KilnModelProvider(name=ModelProviderName.ollama, model_id="mistral")
            ],
        ),
        KilnModel(
            name="model3",
            friendly_name="Model 3",
            family="test",
            providers=[
                KilnModelProvider(name=ModelProviderName.openai, model_id="gpt-4")
            ],
        ),
    ]

    with patch("app.desktop.studio_server.provider_api.built_in_models", test_models):
        # Test direct model match
        result, provider = models_from_ollama_tag("llama2")[0]
        assert result is not None
        assert result.name == "model1"
        assert provider.name == ModelProviderName.ollama

        # Test with :latest suffix
        result, provider = models_from_ollama_tag("mistral:latest")[0]
        assert result is not None
        assert result.name == "model2"
        assert provider.name == ModelProviderName.ollama

        # Test model alias match
        result, provider = models_from_ollama_tag("llama-2")[0]
        assert result is not None
        assert result.name == "model1"

        # Test model alias with :latest
        result, provider = models_from_ollama_tag("llama2-chat:latest")[0]
        assert result is not None
        assert result.name == "model1"
        assert provider.name == ModelProviderName.ollama

        # Test no match found
        results = models_from_ollama_tag("nonexistent-model")
        assert len(results) == 0

        # Test model without Ollama provider
        results = models_from_ollama_tag("gpt-4")
        assert len(results) == 0

        test_models.append(
            KilnModel(
                name="model1v2",
                friendly_name="Model 1v2",
                family="test",
                providers=[
                    KilnModelProvider(
                        name=ModelProviderName.ollama,
                        model_id="llama2",
                        ollama_model_aliases=["llama-2", "llama2-chat"],
                    )
                ],
            ),
        )

        # Test two models under one tag
        results = models_from_ollama_tag("llama-2")
        assert len(results) == 2
        model, provider = results[0]
        assert model.name == "model1"
        assert provider.name == ModelProviderName.ollama
        model, provider = results[1]
        assert model.name == "model1v2"
        assert provider.name == ModelProviderName.ollama


@pytest.mark.asyncio
async def test_available_ollama_models():
    # Create test models
    test_models = [
        KilnModel(
            name="model1",
            friendly_name="Model 1",
            family="test",
            providers=[
                KilnModelProvider(
                    name=ModelProviderName.ollama,
                    model_id="llama2",
                    ollama_model_aliases=["llama-2"],
                    supports_structured_output=True,
                )
            ],
        ),
        KilnModel(
            name="model2",
            friendly_name="Model 2",
            family="test",
            providers=[
                KilnModelProvider(
                    name=ModelProviderName.ollama,
                    model_id="mistral",
                    supports_structured_output=False,
                )
            ],
        ),
    ]

    # Test successful connection
    mock_ollama_connection = OllamaConnection(
        message="Connected",
        supported_models=["llama2", "mistral:latest"],
        untested_models=["scosman-net"],
    )

    with (
        patch("app.desktop.studio_server.provider_api.built_in_models", test_models),
        patch(
            "app.desktop.studio_server.provider_api.connect_ollama",
            return_value=mock_ollama_connection,
        ),
    ):
        result = await available_ollama_models()

        assert result is not None
        assert result.provider_name == "Ollama"
        assert result.provider_id == ModelProviderName.ollama
        assert len(result.models) == 3

        # Check first model
        assert result.models[0].id == "model1"
        assert result.models[0].name == "Model 1"
        assert result.models[0].supports_structured_output is True
        assert result.models[0].untested_model is False

        # Check second model
        assert result.models[1].id == "model2"
        assert result.models[1].name == "Model 2"
        assert result.models[1].supports_structured_output is False
        assert result.models[1].untested_model is False

        # Check third model
        assert result.models[2].id == "scosman-net"
        assert result.models[2].name == "scosman-net"
        assert result.models[2].supports_structured_output is False
        assert result.models[2].untested_model is True

    # Test when no models match
    mock_ollama_connection = OllamaConnection(
        message="Connected",
        supported_models=["unknown-model"],
        untested_models=[],
    )

    with (
        patch("app.desktop.studio_server.provider_api.built_in_models", test_models),
        patch(
            "app.desktop.studio_server.provider_api.connect_ollama",
            return_value=mock_ollama_connection,
        ),
    ):
        result = await available_ollama_models()
        assert result is None

    # Test when Ollama connection fails
    with patch(
        "app.desktop.studio_server.provider_api.connect_ollama",
        side_effect=HTTPException(status_code=417, detail="Failed to connect"),
    ):
        result = await available_ollama_models()
        assert result is None

    # Test with empty models list
    mock_ollama_connection = OllamaConnection(
        message="Connected", supported_models=[], untested_models=[]
    )

    with (
        patch("app.desktop.studio_server.provider_api.built_in_models", test_models),
        patch(
            "app.desktop.studio_server.provider_api.connect_ollama",
            return_value=mock_ollama_connection,
        ),
    ):
        result = await available_ollama_models()
        assert result is None


@patch("app.desktop.studio_server.provider_api.all_projects")
def test_all_fine_tuned_models(mock_all_projects):
    # Create mock projects, tasks, and fine-tunes
    mock_fine_tune1 = Mock()
    mock_fine_tune1.id = "ft1"
    mock_fine_tune1.name = "Fine Tune 1"
    mock_fine_tune1.fine_tune_model_id = "model1"
    mock_fine_tune1.provider = ModelProviderName.openai

    mock_fine_tune2 = Mock()
    mock_fine_tune2.id = "ft2"
    mock_fine_tune2.name = "Fine Tune 2"
    mock_fine_tune2.fine_tune_model_id = "model2"
    mock_fine_tune2.provider = ModelProviderName.openai

    mock_fine_tune3 = Mock()
    mock_fine_tune3.id = "ft3"
    mock_fine_tune3.name = "Incomplete Fine Tune"
    mock_fine_tune3.fine_tune_model_id = None  # Incomplete fine-tune
    mock_fine_tune3.provider = ModelProviderName.openai

    mock_task1 = Mock()
    mock_task1.id = "task1"
    mock_task1.finetunes.return_value = [mock_fine_tune1]

    mock_task2 = Mock()
    mock_task2.id = "task2"
    mock_task2.finetunes.return_value = [mock_fine_tune2, mock_fine_tune3]

    mock_project1 = Mock()
    mock_project1.id = "proj1"
    mock_project1.tasks.return_value = [mock_task1]

    mock_project2 = Mock()
    mock_project2.id = "proj2"
    mock_project2.tasks.return_value = [mock_task2]

    # Test case 1: Projects with fine-tuned models
    mock_all_projects.return_value = [mock_project1, mock_project2]

    result = all_fine_tuned_models()

    assert result is not None
    assert result.provider_name == "Fine Tuned Models"
    assert result.provider_id == "kiln_fine_tune"
    assert len(result.models) == 2  # Only completed fine-tunes should be included

    # Verify first model details
    assert result.models[0].id == "proj1::task1::ft1"
    assert result.models[0].name == "Fine Tune 1 (OpenAI)"
    assert result.models[0].supports_structured_output is True
    assert result.models[0].supports_data_gen is True
    assert result.models[0].task_filter == ["task1"]

    # Verify second model details
    assert result.models[1].id == "proj2::task2::ft2"
    assert result.models[1].name == "Fine Tune 2 (OpenAI)"
    assert result.models[1].supports_structured_output is True
    assert result.models[1].supports_data_gen is True
    assert result.models[1].task_filter == ["task2"]

    # Test case 2: No projects
    mock_all_projects.return_value = []

    result = all_fine_tuned_models()
    assert result is None

    # Test case 3: Projects with no fine-tuned models
    mock_task_empty = Mock()
    mock_task_empty.finetunes.return_value = []
    mock_project_empty = Mock()
    mock_project_empty.tasks.return_value = [mock_task_empty]
    mock_all_projects.return_value = [mock_project_empty]

    result = all_fine_tuned_models()
    assert result is None


@pytest.mark.asyncio
async def test_connect_ollama_rejects_invalid_url_format():
    with pytest.raises(HTTPException) as exc_info:
        await connect_ollama("invalid-url-no-protocol")
    assert exc_info.value.status_code == 400
    assert "Invalid Ollama URL" in exc_info.value.detail


@pytest.mark.asyncio
async def test_connect_ollama_uses_custom_url_when_provided():
    mock_tags_response = {"models": []}
    with (
        patch("requests.get") as mock_get,
        patch("app.desktop.studio_server.provider_api.parse_ollama_tags") as mock_parse,
        patch("app.desktop.studio_server.provider_api.Config.shared") as mock_config,
    ):
        mock_get.return_value.json.return_value = mock_tags_response
        mock_parse.return_value = OllamaConnection(
            message="Connected", supported_models=[]
        )
        mock_config.return_value.ollama_base_url = "http://default-url:11434"

        await connect_ollama("http://custom-url:11434")

        assert mock_get.call_count == 2
        assert mock_get.call_args_list[0][0][0] == "http://custom-url:11434/api/tags"
        assert mock_get.call_args_list[0][1] == {"timeout": 5}
        assert mock_get.call_args_list[1][0][0] == "http://custom-url:11434/api/version"


@pytest.mark.asyncio
async def test_connect_ollama_uses_default_url_when_no_custom_url():
    mock_tags_response = {"models": []}
    with (
        patch("requests.get") as mock_get,
        patch("app.desktop.studio_server.provider_api.parse_ollama_tags") as mock_parse,
        patch(
            "app.desktop.studio_server.provider_api.ollama_base_url"
        ) as mock_base_url,
    ):
        mock_get.return_value.json.return_value = mock_tags_response
        mock_parse.return_value = OllamaConnection(
            message="Connected", supported_models=[]
        )
        mock_base_url.return_value = "http://default-url:11434"

        await connect_ollama(None)

        assert mock_get.call_count == 2
        assert mock_get.call_args_list[0][0][0] == "http://default-url:11434/api/tags"
        assert mock_get.call_args_list[0][1] == {"timeout": 5}
        assert (
            mock_get.call_args_list[1][0][0] == "http://default-url:11434/api/version"
        )


@pytest.mark.asyncio
async def test_connect_ollama_saves_custom_url_on_success():
    mock_tags_response = {"models": []}
    with (
        patch("requests.get") as mock_get,
        patch("app.desktop.studio_server.provider_api.parse_ollama_tags") as mock_parse,
        patch("app.desktop.studio_server.provider_api.Config.shared") as mock_config,
    ):
        mock_get.return_value.json.return_value = mock_tags_response
        mock_parse.return_value = OllamaConnection(
            message="Connected", supported_models=[]
        )

        mock_config_instance = MagicMock()
        mock_config_instance.ollama_base_url = "http://old-url:11434"
        mock_config.return_value = mock_config_instance

        await connect_ollama("http://new-url:11434")

        mock_config_instance.save_setting.assert_called_once_with(
            "ollama_base_url", "http://new-url:11434"
        )


@pytest.mark.asyncio
async def test_connect_ollama_does_not_save_unchanged_url():
    mock_tags_response = {"models": []}
    with (
        patch("requests.get") as mock_get,
        patch("app.desktop.studio_server.provider_api.parse_ollama_tags") as mock_parse,
        patch("app.desktop.studio_server.provider_api.Config.shared") as mock_config,
    ):
        mock_get.return_value.json.return_value = mock_tags_response
        mock_parse.return_value = OllamaConnection(
            message="Connected", supported_models=[]
        )

        mock_config_instance = MagicMock()
        mock_config_instance.ollama_base_url = "http://same-url:11434"
        mock_config.return_value = mock_config_instance

        await connect_ollama("http://same-url:11434")

        mock_config_instance.save_setting.assert_not_called()


def test_custom_models():
    # Mock Config.shared().custom_models
    mock_custom_models = [
        "openai::model1",
        "groq::model2",
        "invalid_model_format",
        "openai::model::with::delimiters",
    ]

    with patch("app.desktop.studio_server.provider_api.Config.shared") as mock_config:
        mock_config_instance = MagicMock()
        mock_config_instance.custom_models = mock_custom_models
        mock_config.return_value = mock_config_instance

        result = custom_models()

        assert result is not None
        assert result.provider_name == "Custom Models"
        assert result.provider_id == ModelProviderName.kiln_custom_registry
        assert len(result.models) == 3  # Only valid models should be included

        # Verify first model details
        assert result.models[0].id == "openai::model1"
        assert result.models[0].name == "OpenAI: model1"
        assert result.models[0].supports_structured_output is False
        assert result.models[0].supports_data_gen is False
        assert result.models[0].untested_model is True

        # Verify second model details
        assert result.models[1].id == "groq::model2"
        assert result.models[1].name == "Groq: model2"
        assert result.models[1].supports_structured_output is False
        assert result.models[1].supports_data_gen is False
        assert result.models[1].untested_model is True

        # Verify third model details
        assert result.models[2].id == "openai::model::with::delimiters"
        assert result.models[2].name == "OpenAI: model::with::delimiters"
        assert result.models[2].supports_structured_output is False
        assert result.models[2].supports_data_gen is False
        assert result.models[2].untested_model is True

    # Test case: No custom models
    with patch("app.desktop.studio_server.provider_api.Config.shared") as mock_config:
        mock_config_instance = MagicMock()
        mock_config_instance.custom_models = []
        mock_config.return_value = mock_config_instance

        result = custom_models()
        assert result is None


@pytest.mark.asyncio
async def test_save_openai_compatible_providers(client):
    with patch("app.desktop.studio_server.provider_api.Config.shared") as mock_config:
        mock_config_instance = MagicMock()
        mock_config_instance.openai_compatible_providers = []
        mock_config.return_value = mock_config_instance

        response = client.post(
            "/api/provider/openai_compatible",
            params={
                "name": "test_provider",
                "base_url": "https://api.test.com",
                "api_key": "test_key",
            },
        )

        assert response.status_code == 200
        assert response.json() == {"message": "OpenAI compatible provider saved"}

        # Verify the provider was saved correctly
        mock_config_instance.openai_compatible_providers = [
            {
                "name": "test_provider",
                "base_url": "https://api.test.com",
                "api_key": "test_key",
            }
        ]


@pytest.mark.asyncio
async def test_save_openai_compatible_providers_duplicate_name(client):
    with patch("app.desktop.studio_server.provider_api.Config.shared") as mock_config:
        mock_config_instance = MagicMock()
        mock_config_instance.openai_compatible_providers = [
            {
                "name": "existing_provider",
                "base_url": "https://api.existing.com",
                "api_key": "existing_key",
            }
        ]
        mock_config.return_value = mock_config_instance

        response = client.post(
            "/api/provider/openai_compatible",
            params={
                "name": "existing_provider",
                "base_url": "https://api.test.com",
                "api_key": "test_key",
            },
        )

        assert response.status_code == 400
        assert response.json() == {"detail": "Provider with this name already exists"}


@pytest.mark.asyncio
async def test_save_openai_compatible_providers_new_array(client):
    with patch("app.desktop.studio_server.provider_api.Config.shared") as mock_config:
        mock_config_instance = MagicMock()
        mock_config_instance.openai_compatible_providers = (
            None  # Simulating no providers
        )
        mock_config.return_value = mock_config_instance

        response = client.post(
            "/api/provider/openai_compatible",
            params={
                "name": "first_provider",
                "base_url": "https://api.first.com",
                "api_key": "first_key",
            },
        )

        assert response.status_code == 200
        assert response.json() == {"message": "OpenAI compatible provider saved"}

        # Verify the provider was saved correctly
        mock_config_instance.openai_compatible_providers = [
            {
                "name": "first_provider",
                "base_url": "https://api.first.com",
                "api_key": "first_key",
            }
        ]


@pytest.mark.asyncio
async def test_save_openai_compatible_providers_add_to_existing_array(client):
    with patch("app.desktop.studio_server.provider_api.Config.shared") as mock_config:
        mock_config_instance = MagicMock()
        mock_config_instance.openai_compatible_providers = [
            {
                "name": "first_provider",
                "base_url": "https://api.first.com",
                "api_key": "first_key",
            }
        ]
        mock_config.return_value = mock_config_instance

        response = client.post(
            "/api/provider/openai_compatible",
            params={
                "name": "second_provider",
                "base_url": "https://api.second.com",
                "api_key": "second_key",
            },
        )

        assert response.status_code == 200
        assert response.json() == {"message": "OpenAI compatible provider saved"}

        # Verify both providers are in the list
        assert mock_config_instance.openai_compatible_providers == [
            {
                "name": "first_provider",
                "base_url": "https://api.first.com",
                "api_key": "first_key",
            },
            {
                "name": "second_provider",
                "base_url": "https://api.second.com",
                "api_key": "second_key",
            },
        ]


@pytest.mark.asyncio
async def test_delete_openai_compatible_providers(client):
    # Test successful deletion
    with patch("app.desktop.studio_server.provider_api.Config.shared") as mock_config:
        mock_config_instance = MagicMock()
        mock_config_instance.openai_compatible_providers = [
            {
                "name": "provider1",
                "base_url": "https://api.test1.com",
                "api_key": "key1",
            },
            {
                "name": "provider2",
                "base_url": "https://api.test2.com",
                "api_key": "key2",
            },
        ]
        mock_config.return_value = mock_config_instance

        response = client.delete(
            "/api/provider/openai_compatible",
            params={"name": "provider1"},
        )

        assert response.status_code == 200
        assert response.json() == {"message": "OpenAI compatible provider deleted"}

        # Verify the correct provider was removed
        assert mock_config_instance.openai_compatible_providers == [
            {
                "name": "provider2",
                "base_url": "https://api.test2.com",
                "api_key": "key2",
            }
        ]


@pytest.mark.asyncio
async def test_delete_openai_compatible_providers_empty_name(client):
    # Test deletion with empty name
    response = client.delete(
        "/api/provider/openai_compatible",
        params={"name": ""},
    )

    assert response.status_code == 400
    assert response.json() == {"message": "Name is required"}


@pytest.mark.asyncio
async def test_delete_openai_compatible_providers_nonexistent(client):
    # Test deletion of non-existent provider
    with patch("app.desktop.studio_server.provider_api.Config.shared") as mock_config:
        mock_config_instance = MagicMock()
        mock_config_instance.openai_compatible_providers = [
            {
                "name": "provider1",
                "base_url": "https://api.test1.com",
                "api_key": "key1",
            }
        ]
        mock_config.return_value = mock_config_instance

        response = client.delete(
            "/api/provider/openai_compatible",
            params={"name": "nonexistent_provider"},
        )

        assert response.status_code == 200
        assert response.json() == {"message": "OpenAI compatible provider deleted"}

        # Verify the original list remains unchanged
        assert mock_config_instance.openai_compatible_providers == [
            {
                "name": "provider1",
                "base_url": "https://api.test1.com",
                "api_key": "key1",
            }
        ]


@pytest.mark.asyncio
async def test_delete_openai_compatible_providers_empty_list(client):
    # Test deletion when providers list is empty
    with patch("app.desktop.studio_server.provider_api.Config.shared") as mock_config:
        mock_config_instance = MagicMock()
        mock_config_instance.openai_compatible_providers = None
        mock_config.return_value = mock_config_instance

        response = client.delete(
            "/api/provider/openai_compatible",
            params={"name": "any_provider"},
        )

        assert response.status_code == 200
        assert response.json() == {"message": "OpenAI compatible provider deleted"}

        # Verify empty list is set
        assert mock_config_instance.openai_compatible_providers == []


def test_openai_compatible_provider_cache_is_stale():
    # Test initial state
    cache = OpenAICompatibleProviderCache(providers=[])
    assert cache.is_stale() is True

    # Test within time window
    cache.last_updated = datetime.now()
    cache.openai_compat_config_when_cached = ["provider1"]
    with patch("app.desktop.studio_server.provider_api.Config.shared") as mock_config:
        mock_config.return_value.openai_compatible_providers = ["provider1"]
        assert cache.is_stale() is False

    # Test expired time window
    cache.last_updated = datetime.now() - timedelta(minutes=61)
    assert cache.is_stale() is True

    # Test config change
    cache.last_updated = datetime.now()
    cache.openai_compat_config_when_cached = ["provider1"]
    with patch("app.desktop.studio_server.provider_api.Config.shared") as mock_config:
        mock_config.return_value.openai_compatible_providers = ["provider2"]
        assert cache.is_stale() is True


def test_openai_compatible_providers():
    mock_provider_config = [
        {
            "name": "test_provider",
            "base_url": "https://api.test.com",
            "api_key": "test_key",
        }
    ]

    with (
        patch("app.desktop.studio_server.provider_api.Config.shared") as mock_config,
        patch(
            "app.desktop.studio_server.provider_api.openai_compatible_providers_load_cache"
        ) as mock_uncached,
    ):
        mock_config.return_value.openai_compatible_providers = mock_provider_config
        mock_uncached.return_value = OpenAICompatibleProviderCache(
            providers=[
                AvailableModels(
                    provider_id=ModelProviderName.openai_compatible,
                    provider_name="test_provider",
                    models=[
                        ModelDetails(
                            id="test_provider::model1",
                            name="model1",
                            supports_structured_output=False,
                            supports_data_gen=False,
                            supports_logprobs=False,
                            untested_model=True,
                            suggested_for_data_gen=False,
                            suggested_for_evals=False,
                            uncensored=False,
                            suggested_for_uncensored_data_gen=False,
                            structured_output_mode="json_instructions",
                            supports_doc_extraction=False,
                            multimodal_capable=False,
                            multimodal_mime_types=None,
                        )
                    ],
                ),
            ],
            last_updated=datetime.now(),
            openai_compat_config_when_cached=mock_provider_config,
        )

        # First call should create cache
        result1 = openai_compatible_providers()
        assert len(result1) == 1
        assert result1[0].provider_name == "test_provider"
        mock_uncached.assert_called_once()

        # Second call should use cache
        mock_uncached.reset_mock()
        result2 = openai_compatible_providers()
        assert len(result2) == 1
        assert result2[0].provider_name == "test_provider"
        mock_uncached.assert_not_called()

        # After config change, should refresh cache
        mock_config.return_value.openai_compatible_providers = [
            {
                "name": "new_provider",
                "base_url": "https://api.new.com",
                "api_key": "new_key",
            }
        ]
        openai_compatible_providers()
        mock_uncached.assert_called_once()


def test_openai_compatible_providers_uncached():
    mock_providers = [
        {
            "name": "test_provider",
            "base_url": "https://api.test.com",
            "api_key": "test_key",
        }
    ]

    # Mock OpenAI client and its models.list() method
    mock_model = MagicMock()
    mock_model.id = "gpt-4"
    mock_models_list = MagicMock()
    mock_models_list.return_value = [mock_model]
    mock_client = MagicMock()
    mock_client.models.list = mock_models_list

    with (
        patch("openai.OpenAI", return_value=mock_client),
        patch("app.desktop.studio_server.provider_api.Config.shared") as mock_config,
    ):
        mock_config.return_value.openai_compatible_providers = mock_providers
        result = openai_compatible_providers_load_cache().providers

        assert len(result) == 1
        assert result[0].provider_name == "test_provider"
        assert result[0].provider_id == ModelProviderName.openai_compatible
        assert len(result[0].models) == 1
        assert result[0].models[0].id == "test_provider::gpt-4"
        assert result[0].models[0].name == "gpt-4"
        assert result[0].models[0].untested_model is True


def test_openai_compatible_providers_uncached_empty_providers():
    with (
        patch("app.desktop.studio_server.provider_api.Config.shared") as mock_config,
    ):
        mock_config.return_value.openai_compatible_providers = []
        cached = openai_compatible_providers_load_cache()
        assert cached is None


def test_openai_compatible_providers_uncached_invalid_provider():
    invalid_providers = [
        {"name": "test", "base_url": "", "api_key": "key"},  # Missing base_url
        {
            "name": "",
            "base_url": "https://api.test.com",
            "api_key": "key",
        },  # Missing name
        {"base_url": "https://api.test.com", "api_key": "key"},  # No name
        {"name": "test", "api_key": "key"},  # No base_url
    ]

    with (
        patch("openai.OpenAI") as mock_openai,
        patch("app.desktop.studio_server.provider_api.Config.shared") as mock_config,
    ):
        mock_config.return_value.openai_compatible_providers = invalid_providers
        result = openai_compatible_providers_load_cache()
        assert result.providers == []
        mock_openai.assert_not_called()


def test_openai_compatible_providers_uncached_api_error():
    mock_providers = [
        {
            "name": "test_provider",
            "base_url": "https://api.test.com",
            "api_key": "test_key",
        }
    ]

    with (
        patch("openai.OpenAI") as mock_openai,
        patch("app.desktop.studio_server.provider_api.Config.shared") as mock_config,
    ):
        mock_config.return_value.openai_compatible_providers = mock_providers
        mock_openai.return_value.models.list.side_effect = Exception("API Error")
        result = openai_compatible_providers_load_cache()
        assert result.providers == []

        # Confirm the cache knows about the error and reports stale
        assert result.had_error
        assert result.is_stale()


@pytest.fixture
def mock_config_all_providers():
    mock_config = MagicMock()
    mock_config.open_ai_api_key = "test_key"
    mock_config.groq_api_key = "test_key"
    mock_config.open_router_api_key = "test_key"
    mock_config.fireworks_api_key = "test_key"
    mock_config.fireworks_account_id = "test_key"
    mock_config.bedrock_access_key = "test_key"
    mock_config.bedrock_secret_key = "test_key"
    mock_config.siliconflow_cn_api_key = "test_key"
    return mock_config


@pytest.mark.asyncio
async def test_disconnect_api_key_openai(client, mock_config_all_providers):
    with patch("app.desktop.studio_server.provider_api.Config.shared") as mock_config:
        mock_config.return_value = mock_config_all_providers

        response = client.post(
            "/api/provider/disconnect_api_key",
            params={"provider_id": "openai"},
        )

        assert response.status_code == 200
        assert response.json() == {"message": "Provider disconnected"}
        assert mock_config_all_providers.open_ai_api_key is None

        # Check it didn't unset the other providers
        assert mock_config_all_providers.groq_api_key is not None


@pytest.mark.asyncio
async def test_disconnect_api_key_siliconflow(client, mock_config_all_providers):
    with patch("app.desktop.studio_server.provider_api.Config.shared") as mock_config:
        mock_config.return_value = mock_config_all_providers

        response = client.post(
            "/api/provider/disconnect_api_key",
            params={"provider_id": "siliconflow_cn"},
        )

        assert response.status_code == 200
        assert response.json() == {"message": "Provider disconnected"}
        assert mock_config_all_providers.siliconflow_cn_api_key is None

        # Check it didn't unset the other providers
        assert mock_config_all_providers.open_ai_api_key is not None


@pytest.mark.asyncio
async def test_disconnect_api_key_groq(client, mock_config_all_providers):
    with patch("app.desktop.studio_server.provider_api.Config.shared") as mock_config:
        mock_config.return_value = mock_config_all_providers

        response = client.post(
            "/api/provider/disconnect_api_key",
            params={"provider_id": "groq"},
        )

        assert response.status_code == 200
        assert response.json() == {"message": "Provider disconnected"}
        assert mock_config_all_providers.groq_api_key is None

        # Check it didn't unset the other providers
        assert mock_config_all_providers.open_ai_api_key is not None


@pytest.mark.asyncio
async def test_disconnect_api_key_openrouter(client, mock_config_all_providers):
    with patch("app.desktop.studio_server.provider_api.Config.shared") as mock_config:
        mock_config.return_value = mock_config_all_providers

        response = client.post(
            "/api/provider/disconnect_api_key",
            params={"provider_id": "openrouter"},
        )

        assert response.status_code == 200
        assert response.json() == {"message": "Provider disconnected"}
        assert mock_config_all_providers.open_router_api_key is None

        # Check it didn't unset the other providers
        assert mock_config_all_providers.open_ai_api_key is not None


@pytest.mark.asyncio
async def test_disconnect_api_key_fireworks(client, mock_config_all_providers):
    with patch("app.desktop.studio_server.provider_api.Config.shared") as mock_config:
        mock_config.return_value = mock_config_all_providers

        response = client.post(
            "/api/provider/disconnect_api_key",
            params={"provider_id": "fireworks_ai"},
        )

        assert response.status_code == 200
        assert response.json() == {"message": "Provider disconnected"}
        assert mock_config_all_providers.fireworks_api_key is None
        assert mock_config_all_providers.fireworks_account_id is None

        # Check it didn't unset the other providers
        assert mock_config_all_providers.open_ai_api_key is not None


@pytest.mark.asyncio
async def test_disconnect_api_key_bedrock(client, mock_config_all_providers):
    with patch("app.desktop.studio_server.provider_api.Config.shared") as mock_config:
        mock_config.return_value = mock_config_all_providers

        response = client.post(
            "/api/provider/disconnect_api_key",
            params={"provider_id": "amazon_bedrock"},
        )

        assert response.status_code == 200
        assert response.json() == {"message": "Provider disconnected"}
        assert mock_config_all_providers.bedrock_access_key is None
        assert mock_config_all_providers.bedrock_secret_key is None

        # Check it didn't unset the other providers
        assert mock_config_all_providers.open_ai_api_key is not None


@pytest.mark.asyncio
async def test_disconnect_api_key_invalid_provider(client, mock_config_all_providers):
    response = client.post(
        "/api/provider/disconnect_api_key",
        params={"provider_id": "unsupported_provider"},
    )

    assert response.status_code == 400
    assert response.json() == {"message": "Invalid provider: unsupported_provider"}


@pytest.mark.parametrize(
    "provider_id",
    ["kiln_custom_registry", "kiln_fine_tune", "openai_compatible", "ollama"],
)
@pytest.mark.asyncio
async def test_disconnect_api_key_unsupported_provider(client, provider_id):
    response = client.post(
        "/api/provider/disconnect_api_key",
        params={"provider_id": provider_id},
    )

    assert response.status_code == 400
    assert response.json() == {"message": "Provider not supported"}


def test_parse_url():
    # Test successful case
    key_data = {"endpoint": "https://api.example.com/"}
    result = parse_url(key_data, "endpoint")
    assert result == "https://api.example.com"

    # Test with http
    key_data = {"endpoint": "http://localhost:8080/"}
    result = parse_url(key_data, "endpoint")
    assert result == "http://localhost:8080"

    # Test without trailing slash
    key_data = {"endpoint": "https://api.example.com"}
    result = parse_url(key_data, "endpoint")
    assert result == "https://api.example.com"

    # Test missing field
    key_data = {"wrong_field": "https://api.example.com"}
    with pytest.raises(HTTPException) as exc_info:
        parse_url(key_data, "endpoint")
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Endpoint URL not found"

    # Test empty string
    key_data = {"endpoint": ""}
    with pytest.raises(HTTPException) as exc_info:
        parse_url(key_data, "endpoint")
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Endpoint URL not found"

    # Test non-string value
    key_data = {"endpoint": 123}
    with pytest.raises(HTTPException) as exc_info:
        parse_url(key_data, "endpoint")
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Endpoint URL not found"

    # Test invalid URL scheme
    key_data = {"endpoint": "ftp://api.example.com"}
    with pytest.raises(HTTPException) as exc_info:
        parse_url(key_data, "endpoint")
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Endpoint URL must start with http or https"


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.requests.get")
@patch("app.desktop.studio_server.provider_api.Config.shared")
async def test_connect_gemini_success(mock_config_shared, mock_requests_get):
    # Setup
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '{"models": []}'
    mock_requests_get.return_value = mock_response

    mock_config = MagicMock()
    mock_config_shared.return_value = mock_config

    # Test
    result = await connect_gemini("test_api_key")

    # Verify
    assert result.status_code == 200
    assert result.body == b'{"message":"Connected to Gemini"}'
    mock_requests_get.assert_called_once_with(
        "https://generativelanguage.googleapis.com/v1beta/models?key=test_api_key",
    )
    assert mock_config.gemini_api_key == "test_api_key"


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.requests.get")
@patch("app.desktop.studio_server.provider_api.Config.shared")
async def test_connect_gemini_invalid_api_key(mock_config_shared, mock_requests_get):
    # Setup
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = "API_KEY_INVALID"
    mock_requests_get.return_value = mock_response

    mock_config = MagicMock()
    mock_config.gemini_api_key = None
    mock_config_shared.return_value = mock_config

    # Test
    result = await connect_gemini("invalid_key")

    # Verify
    assert result.status_code == 401
    assert result.body == b'{"message":"Failed to connect to Gemini. Invalid API key."}'
    assert mock_config.gemini_api_key is None


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.requests.get")
@patch("app.desktop.studio_server.provider_api.Config.shared")
async def test_connect_gemini_non_200_response(mock_config_shared, mock_requests_get):
    # Setup
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_requests_get.return_value = mock_response

    mock_config = MagicMock()
    mock_config.gemini_api_key = None
    mock_config_shared.return_value = mock_config

    # Test
    result = await connect_gemini("test_api_key")

    # Verify
    assert result.status_code == 400
    assert result.body == b'{"message":"Failed to connect to Gemini. Error: [500]"}'
    assert mock_config.gemini_api_key is None


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.requests.get")
@patch("app.desktop.studio_server.provider_api.Config.shared")
async def test_connect_gemini_request_exception(mock_config_shared, mock_requests_get):
    # Setup
    mock_requests_get.side_effect = Exception("Connection error")

    mock_config = MagicMock()
    mock_config.gemini_api_key = None
    mock_config_shared.return_value = mock_config

    # Test
    result = await connect_gemini("test_api_key")

    # Verify
    assert result.status_code == 400
    assert b"Failed to connect to Gemini. Error: Connection error" in result.body
    assert mock_config.gemini_api_key is None


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.requests.get")
@patch("app.desktop.studio_server.provider_api.Config.shared")
async def test_connect_anthropic_success(mock_config_shared, mock_requests_get):
    # Setup
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '{"models": []}'
    mock_requests_get.return_value = mock_response

    mock_config = MagicMock()
    mock_config_shared.return_value = mock_config

    # Test
    result = await connect_anthropic("test_api_key")

    # Verify
    assert result.status_code == 200
    assert result.body == b'{"message":"Connected to Anthropic"}'
    mock_requests_get.assert_called_once_with(
        "https://api.anthropic.com/v1/models",
        headers={
            "x-api-key": "test_api_key",
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        },
    )
    assert mock_config.anthropic_api_key == "test_api_key"


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.requests.get")
@patch("app.desktop.studio_server.provider_api.Config.shared")
async def test_connect_anthropic_invalid_api_key(mock_config_shared, mock_requests_get):
    # Setup
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = "Invalid API key"
    mock_requests_get.return_value = mock_response

    mock_config = MagicMock()
    mock_config.anthropic_api_key = None
    mock_config_shared.return_value = mock_config

    # Test
    result = await connect_anthropic("invalid_key")

    # Verify
    assert result.status_code == 401
    assert (
        result.body == b'{"message":"Failed to connect to Anthropic. Invalid API key."}'
    )
    assert mock_config.anthropic_api_key is None


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.requests.get")
@patch("app.desktop.studio_server.provider_api.Config.shared")
async def test_connect_anthropic_request_exception(
    mock_config_shared, mock_requests_get
):
    # Setup
    mock_requests_get.side_effect = Exception("Connection error")

    mock_config = MagicMock()
    mock_config.anthropic_api_key = None
    mock_config_shared.return_value = mock_config

    # Test
    result = await connect_anthropic("test_api_key")

    # Verify
    assert result.status_code == 400
    assert b"Failed to connect to Anthropic. Error: Connection error" in result.body
    assert mock_config.anthropic_api_key is None


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.requests.get")
@patch("app.desktop.studio_server.provider_api.Config.shared")
async def test_connect_azure_openai_success(mock_config_shared, mock_requests_get):
    # Setup
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '{"files": []}'
    mock_requests_get.return_value = mock_response

    mock_config = MagicMock()
    mock_config_shared.return_value = mock_config

    # Test
    result = await connect_azure_openai("test_api_key", "https://example.azure.com")

    # Verify
    assert result.status_code == 200
    assert result.body == b'{"message":"Connected to Azure OpenAI"}'
    mock_requests_get.assert_called_once_with(
        "https://example.azure.com/openai/files?api-version=2024-08-01-preview",
        headers={
            "api-key": "test_api_key",
            "Content-Type": "application/json",
        },
    )
    assert mock_config.azure_openai_api_key == "test_api_key"
    assert mock_config.azure_openai_endpoint == "https://example.azure.com"


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.requests.get")
@patch("app.desktop.studio_server.provider_api.Config.shared")
async def test_connect_azure_openai_invalid_api_key(
    mock_config_shared, mock_requests_get
):
    # Setup
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = "Invalid API key"
    mock_requests_get.return_value = mock_response

    mock_config = MagicMock()
    mock_config.azure_openai_api_key = None
    mock_config.azure_openai_endpoint = None
    mock_config_shared.return_value = mock_config

    # Test
    result = await connect_azure_openai("invalid_key", "https://example.azure.com")

    # Verify
    assert result.status_code == 401
    assert (
        result.body
        == b'{"message":"Failed to connect to Azure OpenAI. Invalid API key."}'
    )
    assert mock_config.azure_openai_api_key is None
    assert mock_config.azure_openai_endpoint is None


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.requests.get")
@patch("app.desktop.studio_server.provider_api.Config.shared")
async def test_connect_azure_openai_non_200_response(
    mock_config_shared, mock_requests_get
):
    # Setup
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_requests_get.return_value = mock_response

    mock_config = MagicMock()
    mock_config.azure_openai_api_key = None
    mock_config.azure_openai_endpoint = None
    mock_config_shared.return_value = mock_config

    # Test
    result = await connect_azure_openai("test_api_key", "https://example.azure.com")

    # Verify
    assert result.status_code == 400
    assert (
        result.body == b'{"message":"Failed to connect to Azure OpenAI. Error: [500]"}'
    )
    assert mock_config.azure_openai_api_key is None
    assert mock_config.azure_openai_endpoint is None


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.requests.get")
@patch("app.desktop.studio_server.provider_api.Config.shared")
async def test_connect_azure_openai_request_exception(
    mock_config_shared, mock_requests_get
):
    # Setup
    mock_requests_get.side_effect = Exception("Connection error")

    mock_config = MagicMock()
    mock_config.azure_openai_api_key = None
    mock_config.azure_openai_endpoint = None
    mock_config_shared.return_value = mock_config

    # Test
    result = await connect_azure_openai("test_api_key", "https://example.azure.com")

    # Verify
    assert result.status_code == 400
    assert b"Failed to connect to Azure OpenAI. Error: Connection error" in result.body
    assert mock_config.azure_openai_api_key is None
    assert mock_config.azure_openai_endpoint is None


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.requests.get")
@patch("app.desktop.studio_server.provider_api.Config.shared")
async def test_connect_huggingface_success(mock_config_shared, mock_requests_get):
    # Setup
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '{"data": "success"}'
    mock_requests_get.return_value = mock_response

    mock_config = MagicMock()
    mock_config_shared.return_value = mock_config

    # Execute
    result = await connect_huggingface("test_api_key")

    # Assert
    mock_requests_get.assert_called_once_with(
        "https://huggingface.co/api/organizations/fake_org_for_auth_test/resource-groups",
        headers={
            "Authorization": "Bearer test_api_key",
            "Content-Type": "application/json",
        },
    )
    assert mock_config.huggingface_api_key == "test_api_key"
    assert result.status_code == 200
    assert json.loads(result.body)["message"] == "Connected to Huggingface"


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.requests.get")
@patch("app.desktop.studio_server.provider_api.Config.shared")
async def test_connect_huggingface_invalid_api_key(
    mock_config_shared, mock_requests_get
):
    # Setup
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = '{"error": "Unauthorized"}'
    mock_requests_get.return_value = mock_response

    # Execute
    result = await connect_huggingface("invalid_api_key")

    # Assert
    mock_requests_get.assert_called_once_with(
        "https://huggingface.co/api/organizations/fake_org_for_auth_test/resource-groups",
        headers={
            "Authorization": "Bearer invalid_api_key",
            "Content-Type": "application/json",
        },
    )
    mock_config_shared.assert_not_called()
    assert result.status_code == 401
    assert (
        json.loads(result.body)["message"]
        == "Failed to connect to Huggingface. Invalid API key."
    )


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.requests.get")
@patch("app.desktop.studio_server.provider_api.Config.shared")
async def test_connect_huggingface_request_exception(
    mock_config_shared, mock_requests_get
):
    # Setup
    mock_requests_get.side_effect = Exception("Connection error")

    # Execute
    result = await connect_huggingface("test_api_key")

    # Assert
    mock_requests_get.assert_called_once_with(
        "https://huggingface.co/api/organizations/fake_org_for_auth_test/resource-groups",
        headers={
            "Authorization": "Bearer test_api_key",
            "Content-Type": "application/json",
        },
    )
    mock_config_shared.assert_not_called()
    assert result.status_code == 400
    assert (
        "Failed to connect to Huggingface. Error: Connection error"
        in json.loads(result.body)["message"]
    )


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.requests.get")
@patch("app.desktop.studio_server.provider_api.Config.shared")
async def test_connect_huggingface_non_401_response(
    mock_config_shared, mock_requests_get
):
    # Setup
    mock_response = MagicMock()
    mock_response.status_code = 404  # Any non-401 status code
    mock_response.text = '{"error": "Not found"}'
    mock_requests_get.return_value = mock_response

    mock_config = MagicMock()
    mock_config_shared.return_value = mock_config

    # Execute
    result = await connect_huggingface("test_api_key")

    # Assert
    mock_requests_get.assert_called_once_with(
        "https://huggingface.co/api/organizations/fake_org_for_auth_test/resource-groups",
        headers={
            "Authorization": "Bearer test_api_key",
            "Content-Type": "application/json",
        },
    )
    # Even with a 404, we should save the key as the function considers any non-401 as valid auth
    assert mock_config.huggingface_api_key == "test_api_key"
    assert result.status_code == 200
    assert json.loads(result.body)["message"] == "Connected to Huggingface"


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.litellm.acompletion")
@patch("app.desktop.studio_server.provider_api.Config.shared")
async def test_connect_vertex_success(mock_config_shared, mock_litellm_acompletion):
    # Setup
    mock_config = MagicMock()
    mock_config_shared.return_value = mock_config
    mock_litellm_acompletion.return_value = {
        "choices": [{"message": {"content": "Hello!"}}]
    }

    # Execute
    response = await connect_vertex("test-project-id", "us-central1")

    # Verify
    assert response.status_code == 200
    assert "Connected to Vertex" in response.body.decode()
    mock_litellm_acompletion.assert_called_once_with(
        model="vertex_ai/gemini-2.0-flash",
        messages=[{"content": "Hello, how are you?", "role": "user"}],
        vertex_project="test-project-id",
        vertex_location="us-central1",
    )
    assert mock_config.vertex_project_id == "test-project-id"


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.litellm.acompletion")
@patch("app.desktop.studio_server.provider_api.Config.shared")
async def test_connect_vertex_failure(mock_config_shared, mock_litellm_acompletion):
    # Setup
    mock_config = MagicMock()
    mock_config_shared.return_value = mock_config
    mock_litellm_acompletion.side_effect = Exception("Invalid project ID")

    # Execute
    response = await connect_vertex("invalid-project-id", "us-central1")

    # Verify
    assert response.status_code == 400
    assert "Failed to connect to Vertex" in response.body.decode()
    assert "Invalid project ID" in response.body.decode()
    mock_litellm_acompletion.assert_called_once_with(
        model="vertex_ai/gemini-2.0-flash",
        messages=[{"content": "Hello, how are you?", "role": "user"}],
        vertex_project="invalid-project-id",
        vertex_location="us-central1",
    )
    # Verify project ID was not saved
    assert (
        not hasattr(mock_config, "vertex_project_id")
        or mock_config.vertex_project_id != "invalid-project-id"
    )
    assert (
        not hasattr(mock_config, "vertex_location")
        or mock_config.vertex_location != "us-central1"
    )


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.requests.get")
@patch("app.desktop.studio_server.provider_api.Config.shared")
async def test_connect_together_success(mock_config_shared, mock_requests_get):
    # Setup
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '{"models": []}'
    mock_requests_get.return_value = mock_response

    mock_config = MagicMock()
    mock_config_shared.return_value = mock_config

    # Execute
    result = await connect_together("test_api_key")

    # Assert
    mock_requests_get.assert_called_once_with(
        "https://api.together.xyz/v1/models",
        headers={
            "Authorization": "Bearer test_api_key",
            "Content-Type": "application/json",
        },
    )
    assert mock_config.together_api_key == "test_api_key"
    assert result.status_code == 200
    assert result.body == b'{"message":"Connected to Together.ai"}'


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.requests.get")
@patch("app.desktop.studio_server.provider_api.Config.shared")
async def test_connect_together_invalid_api_key(mock_config_shared, mock_requests_get):
    # Setup
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = '{"error": "Invalid API key"}'
    mock_requests_get.return_value = mock_response

    # Execute
    result = await connect_together("invalid_api_key")

    # Assert
    mock_requests_get.assert_called_once_with(
        "https://api.together.xyz/v1/models",
        headers={
            "Authorization": "Bearer invalid_api_key",
            "Content-Type": "application/json",
        },
    )
    mock_config_shared.assert_not_called()  # Config should not be updated with invalid key
    assert result.status_code == 401
    assert (
        result.body
        == b'{"message":"Failed to connect to Together.ai. Invalid API key."}'
    )


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.requests.get")
@patch("app.desktop.studio_server.provider_api.Config.shared")
async def test_connect_together_request_exception(
    mock_config_shared, mock_requests_get
):
    # Setup
    mock_requests_get.side_effect = Exception("Connection error")

    # Execute
    result = await connect_together("test_api_key")

    # Assert
    mock_requests_get.assert_called_once()
    mock_config_shared.assert_not_called()  # Config should not be updated on error
    assert result.status_code == 400
    assert (
        result.body
        == b'{"message":"Failed to connect to Together.ai. Error: Connection error"}'
    )


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.requests.get")
@patch("app.desktop.studio_server.provider_api.Config.shared")
async def test_connect_together_non_401_response(mock_config_shared, mock_requests_get):
    # Setup
    mock_response = MagicMock()
    mock_response.status_code = 500  # Any non-401 status code
    mock_response.text = '{"error": "Server error"}'
    mock_requests_get.return_value = mock_response

    mock_config = MagicMock()
    mock_config_shared.return_value = mock_config

    # Execute
    result = await connect_together("test_api_key")

    # Assert
    mock_requests_get.assert_called_once()
    # Even with a 500 error, if it's not 401, we consider the key valid
    assert mock_config.together_api_key == "test_api_key"
    assert result.status_code == 200
    assert result.body == b'{"message":"Connected to Together.ai"}'


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.requests.get")
@patch("app.desktop.studio_server.provider_api.Config.shared")
async def test_connect_siliconflow_success(mock_config_shared, mock_requests_get):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '{"models": []}'
    mock_requests_get.return_value = mock_response

    mock_config = MagicMock()
    mock_config_shared.return_value = mock_config

    result = await connect_siliconflow("test_api_key")

    mock_requests_get.assert_called_once_with(
        "https://api.siliconflow.cn/v1/models",
        headers={
            "Authorization": "Bearer test_api_key",
            "Content-Type": "application/json",
        },
    )
    assert mock_config.siliconflow_cn_api_key == "test_api_key"
    assert result.status_code == 200
    assert result.body == b'{"message":"Connected to SiliconFlow"}'


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.requests.get")
@patch("app.desktop.studio_server.provider_api.Config.shared")
async def test_connect_siliconflow_invalid_api_key(
    mock_config_shared, mock_requests_get
):
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = '{"error": "Unauthorized"}'
    mock_requests_get.return_value = mock_response

    result = await connect_siliconflow("invalid_api_key")

    mock_requests_get.assert_called_once_with(
        "https://api.siliconflow.cn/v1/models",
        headers={
            "Authorization": "Bearer invalid_api_key",
            "Content-Type": "application/json",
        },
    )
    mock_config_shared.assert_not_called()
    assert result.status_code == 401
    assert (
        result.body
        == b'{"message":"Failed to connect to SiliconFlow. Invalid API key."}'
    )


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.requests.get")
@patch("app.desktop.studio_server.provider_api.Config.shared")
async def test_connect_siliconflow_request_exception(
    mock_config_shared, mock_requests_get
):
    mock_requests_get.side_effect = Exception("Connection error")

    result = await connect_siliconflow("test_api_key")

    mock_requests_get.assert_called_once()
    mock_config_shared.assert_not_called()
    assert result.status_code == 400
    assert (
        result.body
        == b'{"message":"Failed to connect to SiliconFlow. Error: Connection error"}'
    )


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.requests.get")
@patch("app.desktop.studio_server.provider_api.Config.shared")
async def test_connect_siliconflow_non_200_response(
    mock_config_shared, mock_requests_get
):
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_requests_get.return_value = mock_response

    result = await connect_siliconflow("test_api_key")

    mock_requests_get.assert_called_once()
    # Should NOT save key on non-200
    mock_config_shared.assert_not_called()
    assert result.status_code == 400
    assert (
        result.body
        == b'{"message":"Failed to connect to SiliconFlow. Error: [500] Internal Server Error"}'
    )


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.requests.post")
@patch("app.desktop.studio_server.provider_api.Config.shared")
async def test_connect_wandb_success(mock_config_shared, mock_requests_post):
    # Setup
    mock_config = MagicMock()
    mock_config_shared.return_value = mock_config

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": {"viewer": {"id": "test-user-id"}}}
    mock_requests_post.return_value = mock_response

    # Test
    result = await connect_wandb("test-api-key", None)

    # Assertions
    assert result.status_code == 200
    assert result.body == b'{"message":"Connected to Weights & Biases"}'

    # Verify API call
    mock_requests_post.assert_called_once_with(
        "https://api.wandb.ai/graphql",
        timeout=5,
        json={"query": "query { viewer { id } }"},
        headers={"Content-Type": "application/json"},
        auth=("api_key", "test-api-key"),
    )

    # Verify config values saved
    mock_config.wandb_api_key = "test-api-key"
    mock_config.wandb_base_url = None


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.requests.post")
@patch("app.desktop.studio_server.provider_api.Config.shared")
async def test_connect_wandb_custom_base_url(mock_config_shared, mock_requests_post):
    # Setup
    mock_config = MagicMock()
    mock_config_shared.return_value = mock_config

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": {"viewer": {"id": "test-user-id"}}}
    mock_requests_post.return_value = mock_response

    custom_url = "https://custom-wandb.example.com"

    # Test
    result = await connect_wandb("test-api-key", custom_url)

    # Assertions
    assert result.status_code == 200
    assert result.body == b'{"message":"Connected to Weights & Biases"}'

    # Verify API call with custom URL
    mock_requests_post.assert_called_once_with(
        f"{custom_url}/graphql",
        timeout=5,
        json={"query": "query { viewer { id } }"},
        headers={"Content-Type": "application/json"},
        auth=("api_key", "test-api-key"),
    )

    # Verify config values saved
    mock_config.wandb_api_key = "test-api-key"
    mock_config.wandb_base_url = custom_url


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.requests.post")
@patch("app.desktop.studio_server.provider_api.Config.shared")
async def test_connect_wandb_invalid_api_key(mock_config_shared, mock_requests_post):
    # Setup
    mock_config = MagicMock()
    mock_config_shared.return_value = mock_config

    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_requests_post.return_value = mock_response

    # Test
    result = await connect_wandb("invalid-api-key", None)

    # Assertions
    assert result.status_code == 401
    assert "Invalid API key" in result.body.decode()

    # Verify config values were not saved
    assert (
        not hasattr(mock_config, "wandb_api_key")
        or mock_config.wandb_api_key != "invalid-api-key"
    )


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.requests.post")
@patch("app.desktop.studio_server.provider_api.Config.shared")
async def test_connect_wandb_null_viewer(mock_config_shared, mock_requests_post):
    # Setup
    mock_config = MagicMock()
    mock_config_shared.return_value = mock_config

    # W&B API returns 200 but null viewer when API key is invalid -- normal failure case
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": {"viewer": None}}
    mock_requests_post.return_value = mock_response

    # Test
    result = await connect_wandb("invalid-api-key", None)

    # Assertions
    assert result.status_code == 401
    assert "Invalid API key" in result.body.decode()

    # Verify config values were not saved
    assert (
        not hasattr(mock_config, "wandb_api_key")
        or mock_config.wandb_api_key != "invalid-api-key"
    )


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.requests.post")
@patch("app.desktop.studio_server.provider_api.Config.shared")
async def test_connect_wandb_unexpected_response(
    mock_config_shared, mock_requests_post
):
    # Setup
    mock_config = MagicMock()
    mock_config_shared.return_value = mock_config

    # Response with unexpected format
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": {"unexpected": "format"}}
    mock_response.text = '{"data": {"unexpected": "format"}}'
    mock_requests_post.return_value = mock_response

    # Test
    result = await connect_wandb("test-api-key", None)

    # Assertions
    assert result.status_code == 400
    assert "Failed to connect to W&B" in result.body.decode()

    # Verify config values were not saved
    assert (
        not hasattr(mock_config, "wandb_api_key")
        or mock_config.wandb_api_key != "test-api-key"
    )


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.requests.post")
@patch("app.desktop.studio_server.provider_api.Config.shared")
async def test_connect_wandb_request_exception(mock_config_shared, mock_requests_post):
    # Setup
    mock_config = MagicMock()
    mock_config_shared.return_value = mock_config

    # Simulate a request exception
    mock_requests_post.side_effect = Exception("Network error")

    # Test
    result = await connect_wandb("test-api-key", None)

    # Assertions
    assert result.status_code == 400
    assert "Failed to connect to W&B" in result.body.decode()
    assert "Network error" in result.body.decode()

    # Verify config values were not saved
    assert (
        not hasattr(mock_config, "wandb_api_key")
        or mock_config.wandb_api_key != "test-api-key"
    )


@pytest.mark.asyncio
async def test_get_embedding_providers(app, client):
    # Mock Config.shared()
    mock_config = MagicMock()
    mock_config.get_value.return_value = "mock_key"

    # Mock provider_warnings
    mock_provider_warnings = {
        ModelProviderName.openai: MagicMock(required_config_keys=["key1"]),
        ModelProviderName.amazon_bedrock: MagicMock(required_config_keys=["key2"]),
        ModelProviderName.gemini_api: MagicMock(required_config_keys=["key3"]),
    }

    # Mock built_in_models
    mock_built_in_embedding_models = [
        KilnEmbeddingModel(
            name="model1",
            friendly_name="Model 1",
            family="",
            providers=[
                KilnEmbeddingModelProvider(
                    name=ModelProviderName.openai,
                    model_id="oai1",
                    n_dimensions=1536,
                    max_input_tokens=8192,
                    supports_custom_dimensions=True,
                )
            ],
        ),
        KilnEmbeddingModel(
            name="model2",
            friendly_name="Model 2",
            family="",
            providers=[
                KilnEmbeddingModelProvider(
                    name=ModelProviderName.amazon_bedrock,
                    model_id="bedrock1",
                    n_dimensions=1536,
                ),
                KilnEmbeddingModelProvider(
                    name=ModelProviderName.gemini_api,
                    model_id="gemini1",
                    n_dimensions=1536,
                    max_input_tokens=8192,
                ),
            ],
        ),
    ]

    with (
        patch(
            "app.desktop.studio_server.provider_api.Config.shared",
            return_value=mock_config,
        ),
        patch(
            "app.desktop.studio_server.provider_api.provider_warnings",
            mock_provider_warnings,
        ),
        patch(
            "app.desktop.studio_server.provider_api.built_in_embedding_models",
            mock_built_in_embedding_models,
        ),
    ):
        response = client.get("/api/available_embedding_models")

    assert response.status_code == 200
    assert response.json() == [
        {
            "provider_id": "openai",
            "provider_name": "OpenAI",
            "models": [
                {
                    "id": "model1",
                    "name": "Model 1",
                    "n_dimensions": 1536,
                    "max_input_tokens": 8192,
                    "supports_custom_dimensions": True,
                }
            ],
        },
        {
            "provider_id": "amazon_bedrock",
            "provider_name": "Amazon Bedrock",
            "models": [
                {
                    "id": "model2",
                    "name": "Model 2",
                    "n_dimensions": 1536,
                    "max_input_tokens": None,
                    "supports_custom_dimensions": False,
                }
            ],
        },
        {
            "provider_id": "gemini_api",
            "provider_name": "Gemini API",
            "models": [
                {
                    "id": "model2",
                    "name": "Model 2",
                    "n_dimensions": 1536,
                    "max_input_tokens": 8192,
                    "supports_custom_dimensions": False,
                }
            ],
        },
    ]


def test_get_providers_embedding_models(client):
    response = client.get("/api/providers/embedding_models")
    assert response.status_code == 200

    data = response.json()
    assert "models" in data

    # Check if all built-in embedding models are present in the response
    for model in built_in_embedding_models:
        assert model.name in data["models"]
        assert data["models"][model.name]["id"] == model.name
        assert data["models"][model.name]["name"] == model.friendly_name

    # Check if the number of models in the response matches the number of built-in embedding models
    assert len(data["models"]) == len(built_in_embedding_models)

    if EmbeddingModelName.openai_text_embedding_3_small in data["models"]:
        assert (
            data["models"][EmbeddingModelName.openai_text_embedding_3_small]["id"]
            == EmbeddingModelName.openai_text_embedding_3_small
        )
        assert (
            data["models"][EmbeddingModelName.openai_text_embedding_3_small]["name"]
            == "text-embedding-3-small"
        )
