import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from kiln_ai.adapters.ml_model_list import (
    KilnModel,
    KilnModelProvider,
    ModelName,
    ModelProviderName,
    built_in_models,
)
from kiln_ai.utils.config import Config

from app.desktop.studio_server.provider_api import (
    OllamaConnection,
    connect_bedrock,
    connect_groq,
    connect_openrouter,
    connect_provider_api,
)


@pytest.fixture
def app():
    app = FastAPI()
    connect_provider_api(app)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_connect_api_key_invalid_payload(client):
    response = client.post(
        "/api/provider/connect_api_key",
        json={"provider": "openai", "key_data": "invalid"},
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
    with patch("app.desktop.studio_server.provider_api.os.environ", {}) as mock_env:
        yield mock_env


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.ChatBedrockConverse")
async def test_connect_bedrock_success(mock_chat_bedrock, mock_environ):
    mock_llm = MagicMock()
    mock_chat_bedrock.return_value = mock_llm
    mock_llm.invoke.side_effect = Exception("Some non-credential error")

    result = await connect_bedrock("test_access_key", "test_secret_key")

    assert isinstance(result, JSONResponse)
    assert result.status_code == 200
    assert result.body == b'{"message":"Connected to Bedrock"}'
    assert Config.shared().bedrock_access_key == "test_access_key"
    assert Config.shared().bedrock_secret_key == "test_secret_key"

    mock_chat_bedrock.assert_called_once_with(
        model="fake_model",
        region_name="us-west-2",
    )
    mock_llm.invoke.assert_called_once_with("Hello, how are you?")


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.ChatBedrockConverse")
async def test_connect_bedrock_invalid_credentials(mock_chat_bedrock, mock_environ):
    mock_llm = MagicMock()
    mock_chat_bedrock.return_value = mock_llm
    mock_llm.invoke.side_effect = Exception("UnrecognizedClientException")

    result = await connect_bedrock("invalid_access_key", "invalid_secret_key")

    assert isinstance(result, JSONResponse)
    assert result.status_code == 401
    assert (
        result.body
        == b'{"message":"Failed to connect to Bedrock. Invalid credentials."}'
    )

    assert "AWS_ACCESS_KEY_ID" not in mock_environ
    assert "AWS_SECRET_ACCESS_KEY" not in mock_environ


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.ChatBedrockConverse")
async def test_connect_bedrock_unknown_error(mock_chat_bedrock, mock_environ):
    mock_llm = MagicMock()
    mock_chat_bedrock.return_value = mock_llm
    mock_llm.invoke.side_effect = Exception("Some unexpected error")

    result = await connect_bedrock("test_access_key", "test_secret_key")

    assert isinstance(result, JSONResponse)
    assert result.status_code == 200
    assert result.body == b'{"message":"Connected to Bedrock"}'
    assert Config.shared().bedrock_access_key == "test_access_key"
    assert Config.shared().bedrock_secret_key == "test_secret_key"


@pytest.mark.asyncio
@patch("app.desktop.studio_server.provider_api.ChatBedrockConverse")
async def test_connect_bedrock_environment_variables(mock_chat_bedrock, mock_environ):
    mock_llm = MagicMock()
    mock_chat_bedrock.return_value = mock_llm
    mock_llm.invoke.side_effect = Exception("Some non-credential error")

    await connect_bedrock("test_access_key", "test_secret_key")

    assert "AWS_ACCESS_KEY_ID" not in mock_environ
    assert "AWS_SECRET_ACCESS_KEY" not in mock_environ

    mock_chat_bedrock.assert_called_once()


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
            providers=[KilnModelProvider(name=ModelProviderName.openai)],
        ),
        KilnModel(
            name="model2",
            friendly_name="Model 2",
            family="",
            providers=[
                KilnModelProvider(name=ModelProviderName.amazon_bedrock),
                KilnModelProvider(name=ModelProviderName.ollama),
            ],
        ),
    ]

    # Mock connect_ollama
    mock_ollama_connection = OllamaConnection(
        message="Connected", models=["ollama_model1", "ollama_model2"]
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
    r = response.json()
    assert response.json() == [
        {
            "provider_id": "ollama",
            "provider_name": "Ollama",
            "models": [
                {"id": "model2", "name": "Model 2"},
            ],
        },
        {
            "provider_id": "openai",
            "provider_name": "OpenAI",
            "models": [{"id": "model1", "name": "Model 1"}],
        },
        {
            "provider_id": "amazon_bedrock",
            "provider_name": "Amazon Bedrock",
            "models": [{"id": "model2", "name": "Model 2"}],
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
            providers=[KilnModelProvider(name=ModelProviderName.openai)],
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
    assert response.json() == [
        {
            "provider_id": "openai",
            "provider_name": "OpenAI",
            "models": [{"id": "model1", "name": "Model 1"}],
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
