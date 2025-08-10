from typing import cast
from unittest.mock import AsyncMock, Mock, patch

import httpx
import openai
import pytest

from kiln_ai.adapters.docker_model_runner_tools import (
    DockerModelRunnerConnection,
    docker_model_runner_base_url,
    parse_docker_model_runner_models,
)
from libs.core.kiln_ai.datamodel.datamodel_enums import ModelProviderName


def test_docker_model_runner_base_url_default():
    """Test that the default base URL is returned when no config is set."""
    with patch("kiln_ai.adapters.docker_model_runner_tools.Config") as mock_config:
        mock_config.shared().docker_model_runner_base_url = None
        result = docker_model_runner_base_url()
        assert result == "http://localhost:12434/engines/llama.cpp"


def test_docker_model_runner_base_url_from_config():
    """Test that the configured base URL is returned when set."""
    with patch("kiln_ai.adapters.docker_model_runner_tools.Config") as mock_config:
        mock_config.shared().docker_model_runner_base_url = (
            "http://custom:8080/engines/llama.cpp"
        )
        result = docker_model_runner_base_url()
        assert result == "http://custom:8080/engines/llama.cpp"


def test_parse_docker_model_runner_models_with_supported_models():
    """Test parsing Docker Model Runner models response with supported models."""
    # Create mock OpenAI Model objects
    mock_models = cast(
        list[openai.types.Model],
        [
            Mock(id="ai/llama3.2:3B-Q4_K_M"),
            Mock(id="ai/qwen3:8B-Q4_K_M"),
            Mock(id="ai/gemma3n:4B-Q4_K_M"),
            Mock(id="unsupported-model"),
        ],
    )

    with patch(
        "kiln_ai.adapters.docker_model_runner_tools.built_in_models"
    ) as mock_built_in_models:
        # Mock built-in models with Docker Model Runner providers
        mock_model = Mock()
        mock_provider = Mock()
        mock_provider.name = ModelProviderName.docker_model_runner
        mock_provider.model_id = "ai/llama3.2:3B-Q4_K_M"
        mock_model.providers = [mock_provider]
        mock_built_in_models.__iter__ = Mock(return_value=iter([mock_model]))

        result = parse_docker_model_runner_models(mock_models)

        assert result is not None
        assert result.message == "Docker Model Runner connected"
        assert "ai/llama3.2:3B-Q4_K_M" in result.supported_models
        assert "unsupported-model" in result.untested_models


def test_parse_docker_model_runner_models_no_models():
    """Test parsing Docker Model Runner models response with no models."""
    mock_models = []

    result = parse_docker_model_runner_models(mock_models)

    assert result is not None
    assert "no supported models are available" in result.message
    assert len(result.supported_models) == 0
    assert len(result.untested_models) == 0


def test_docker_model_runner_connection_all_models():
    """Test that DockerModelRunnerConnection.all_models() returns both supported and untested models."""
    connection = DockerModelRunnerConnection(
        message="Test",
        supported_models=["model1", "model2"],
        untested_models=["model3", "model4"],
    )

    all_models = connection.all_models()
    assert all_models == ["model1", "model2", "model3", "model4"]


@pytest.mark.asyncio
async def test_docker_model_runner_online_success():
    """Test that docker_model_runner_online returns True when service is available."""
    with patch(
        "kiln_ai.adapters.docker_model_runner_tools.httpx.AsyncClient"
    ) as mock_client_class:
        mock_client = Mock()
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_class.return_value.__aenter__.return_value = mock_client

        from kiln_ai.adapters.docker_model_runner_tools import (
            docker_model_runner_online,
        )

        result = await docker_model_runner_online()

        assert result is True
        mock_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_docker_model_runner_online_failure():
    """Test that docker_model_runner_online returns False when service is unavailable."""
    with patch(
        "kiln_ai.adapters.docker_model_runner_tools.httpx.AsyncClient"
    ) as mock_client_class:
        mock_client = Mock()
        mock_client.get = AsyncMock(side_effect=httpx.RequestError("Connection error"))
        mock_client_class.return_value.__aenter__.return_value = mock_client

        from kiln_ai.adapters.docker_model_runner_tools import (
            docker_model_runner_online,
        )

        result = await docker_model_runner_online()

        assert result is False
