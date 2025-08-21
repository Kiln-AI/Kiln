from unittest.mock import AsyncMock, Mock, patch

import httpx
import openai
import pytest

from kiln_ai.adapters.docker_model_runner_tools import (
    DockerModelRunnerConnection,
    docker_model_runner_base_url,
    parse_docker_model_runner_models,
)
from kiln_ai.datamodel.datamodel_enums import ModelProviderName


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
    mock_models = [
        Mock(id="ai/llama3.2:3B-Q4_K_M"),
        Mock(id="ai/qwen3:8B-Q4_K_M"),
        Mock(id="ai/gemma3n:4B-Q4_K_M"),
        Mock(id="unsupported-model"),
    ]

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

        result = parse_docker_model_runner_models(mock_models)  # type: ignore

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


@pytest.mark.asyncio
async def test_get_docker_model_runner_connection_success():
    """Test get_docker_model_runner_connection with successful connection."""
    from kiln_ai.adapters.docker_model_runner_tools import (
        get_docker_model_runner_connection,
    )

    # Mock OpenAI client and models response
    mock_model = Mock()
    mock_model.id = "ai/llama3.2:3B-Q4_K_M"
    mock_models_response = [mock_model]

    with (
        patch(
            "kiln_ai.adapters.docker_model_runner_tools.openai.OpenAI"
        ) as mock_openai,
        patch(
            "kiln_ai.adapters.docker_model_runner_tools.parse_docker_model_runner_models"
        ) as mock_parse,
        patch(
            "kiln_ai.adapters.docker_model_runner_tools.docker_model_runner_base_url"
        ) as mock_base_url,
    ):
        mock_base_url.return_value = "http://localhost:12434/engines"
        mock_client = Mock()
        mock_client.models.list.return_value = mock_models_response
        mock_openai.return_value = mock_client

        expected_connection = DockerModelRunnerConnection(
            message="Connected",
            supported_models=["ai/llama3.2:3B-Q4_K_M"],
            untested_models=[],
        )
        mock_parse.return_value = expected_connection

        result = await get_docker_model_runner_connection()

        assert result == expected_connection
        mock_openai.assert_called_once_with(
            api_key="dummy",
            base_url="http://localhost:12434/engines/v1",
            max_retries=0,
        )
        mock_parse.assert_called_once_with(mock_models_response)


@pytest.mark.asyncio
async def test_get_docker_model_runner_connection_with_custom_url():
    """Test get_docker_model_runner_connection with custom URL."""
    from kiln_ai.adapters.docker_model_runner_tools import (
        get_docker_model_runner_connection,
    )

    # Mock OpenAI client and models response
    mock_model = Mock()
    mock_model.id = "ai/llama3.2:3B-Q4_K_M"
    mock_models_response = [mock_model]

    with (
        patch(
            "kiln_ai.adapters.docker_model_runner_tools.openai.OpenAI"
        ) as mock_openai,
        patch(
            "kiln_ai.adapters.docker_model_runner_tools.parse_docker_model_runner_models"
        ) as mock_parse,
    ):
        mock_client = Mock()
        mock_client.models.list.return_value = mock_models_response
        mock_openai.return_value = mock_client

        expected_connection = DockerModelRunnerConnection(
            message="Connected",
            supported_models=["ai/llama3.2:3B-Q4_K_M"],
            untested_models=[],
        )
        mock_parse.return_value = expected_connection

        custom_url = "http://custom:8080/engines/llama.cpp"
        result = await get_docker_model_runner_connection(custom_url)

        assert result == expected_connection
        mock_openai.assert_called_once_with(
            api_key="dummy",
            base_url=f"{custom_url}/v1",
            max_retries=0,
        )
        mock_parse.assert_called_once_with(mock_models_response)


@pytest.mark.asyncio
async def test_get_docker_model_runner_connection_api_error():
    """Test get_docker_model_runner_connection with API error."""
    from kiln_ai.adapters.docker_model_runner_tools import (
        get_docker_model_runner_connection,
    )

    with patch(
        "kiln_ai.adapters.docker_model_runner_tools.openai.OpenAI"
    ) as mock_openai:
        mock_client = Mock()
        mock_client.models.list.side_effect = openai.APIConnectionError(request=Mock())
        mock_openai.return_value = mock_client

        result = await get_docker_model_runner_connection()

        assert result is None


@pytest.mark.asyncio
async def test_get_docker_model_runner_connection_connection_error():
    """Test get_docker_model_runner_connection with connection error."""
    from kiln_ai.adapters.docker_model_runner_tools import (
        get_docker_model_runner_connection,
    )

    with patch(
        "kiln_ai.adapters.docker_model_runner_tools.openai.OpenAI"
    ) as mock_openai:
        mock_client = Mock()
        mock_client.models.list.side_effect = httpx.RequestError("Connection error")
        mock_openai.return_value = mock_client

        result = await get_docker_model_runner_connection()

        assert result is None


@pytest.mark.asyncio
async def test_get_docker_model_runner_connection_http_error():
    """Test get_docker_model_runner_connection with HTTP error."""
    from kiln_ai.adapters.docker_model_runner_tools import (
        get_docker_model_runner_connection,
    )

    with patch(
        "kiln_ai.adapters.docker_model_runner_tools.openai.OpenAI"
    ) as mock_openai:
        mock_client = Mock()
        mock_client.models.list.side_effect = httpx.RequestError("HTTP error")
        mock_openai.return_value = mock_client

        result = await get_docker_model_runner_connection()

        assert result is None


def test_docker_model_runner_model_installed_true():
    """Test docker_model_runner_model_installed returns True when model is installed."""
    from kiln_ai.adapters.docker_model_runner_tools import (
        docker_model_runner_model_installed,
    )

    connection = DockerModelRunnerConnection(
        message="Test",
        supported_models=["model1", "model2"],
        untested_models=["model3", "model4"],
    )

    # Test model in supported_models
    assert docker_model_runner_model_installed(connection, "model1") is True

    # Test model in untested_models
    assert docker_model_runner_model_installed(connection, "model3") is True


def test_docker_model_runner_model_installed_false():
    """Test docker_model_runner_model_installed returns False when model is not installed."""
    from kiln_ai.adapters.docker_model_runner_tools import (
        docker_model_runner_model_installed,
    )

    connection = DockerModelRunnerConnection(
        message="Test",
        supported_models=["model1", "model2"],
        untested_models=["model3", "model4"],
    )

    # Test model not in any list
    assert docker_model_runner_model_installed(connection, "nonexistent_model") is False
