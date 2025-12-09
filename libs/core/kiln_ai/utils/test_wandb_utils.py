from unittest.mock import AsyncMock, patch

import httpx
import pytest

from kiln_ai.utils.wandb_utils import AuthenticationError, get_wandb_default_entity


class TestGetWandbDefaultEntity:
    """Test suite for get_wandb_default_entity function."""

    @pytest.fixture
    def mock_response(self):
        """Create a mock HTTP response."""
        response = AsyncMock(spec=httpx.Response)
        return response

    @pytest.fixture
    def valid_api_key(self):
        """Valid API key for testing."""
        return "test_api_key_12345"

    @pytest.fixture
    def base_url(self):
        """Base URL for testing."""
        return "https://api.wandb.ai"

    @pytest.fixture
    def custom_base_url(self):
        """Custom base URL for testing."""
        return "https://custom.wandb.ai"

    @pytest.mark.asyncio
    async def test_successful_entity_retrieval(
        self, mock_response, valid_api_key, base_url
    ):
        """Test successful retrieval of default entity."""
        # Setup mock response
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "viewer": {
                    "id": "user123",
                    "username": "testuser",
                    "defaultEntity": {"id": "entity123", "name": "test-entity"},
                }
            }
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await get_wandb_default_entity(valid_api_key, base_url)

            assert result == "test-entity"

            # Verify the API call was made correctly
            mock_client.post.assert_called_once_with(
                f"{base_url}/graphql",
                timeout=5.0,
                json={
                    "query": "query { viewer { id, username, defaultEntity { id, name } } }"
                },
                headers={"Content-Type": "application/json"},
                auth=("api_key", valid_api_key),
            )

    @pytest.mark.asyncio
    async def test_successful_entity_retrieval_custom_url(
        self, mock_response, valid_api_key, custom_base_url
    ):
        """Test successful retrieval with custom base URL."""
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "viewer": {
                    "id": "user123",
                    "username": "testuser",
                    "defaultEntity": {"id": "entity123", "name": "custom-entity"},
                }
            }
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await get_wandb_default_entity(valid_api_key, custom_base_url)

            assert result == "custom-entity"
            mock_client.post.assert_called_once_with(
                f"{custom_base_url}/graphql",
                timeout=5.0,
                json={
                    "query": "query { viewer { id, username, defaultEntity { id, name } } }"
                },
                headers={"Content-Type": "application/json"},
                auth=("api_key", valid_api_key),
            )

    @pytest.mark.asyncio
    async def test_default_base_url_when_none(self, mock_response, valid_api_key):
        """Test that default base URL is used when None is provided."""
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "viewer": {
                    "id": "user123",
                    "username": "testuser",
                    "defaultEntity": {"id": "entity123", "name": "default-entity"},
                }
            }
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await get_wandb_default_entity(valid_api_key, None)

            assert result == "default-entity"
            mock_client.post.assert_called_once_with(
                "https://api.wandb.ai/graphql",
                timeout=5.0,
                json={
                    "query": "query { viewer { id, username, defaultEntity { id, name } } }"
                },
                headers={"Content-Type": "application/json"},
                auth=("api_key", valid_api_key),
            )

    @pytest.mark.asyncio
    async def test_no_default_entity_returns_none(
        self, mock_response, valid_api_key, base_url
    ):
        """Test that None is returned when user has no default entity."""
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "viewer": {
                    "id": "user123",
                    "username": "testuser",
                    "defaultEntity": None,
                }
            }
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await get_wandb_default_entity(valid_api_key, base_url)

            assert result is None

    @pytest.mark.asyncio
    async def test_invalid_api_key_401_error(self, mock_response, base_url):
        """Test handling of 401 unauthorized error."""
        mock_response.status_code = 401

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await get_wandb_default_entity("invalid_key", base_url)

            assert isinstance(result, AuthenticationError)
            assert "Failed to connect to W&B. Invalid API key (401)." in str(result)

    @pytest.mark.asyncio
    async def test_null_viewer_authentication_error(
        self, mock_response, valid_api_key, base_url
    ):
        """Test handling of null viewer in response."""
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"viewer": None}}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await get_wandb_default_entity(valid_api_key, base_url)

            assert isinstance(result, AuthenticationError)
            assert "Failed to connect to W&B. Invalid API key (no viewer)." in str(
                result
            )

    @pytest.mark.asyncio
    async def test_missing_data_field_returns_none(
        self, mock_response, valid_api_key, base_url
    ):
        """Test handling of response missing data field."""
        mock_response.status_code = 200
        mock_response.json.return_value = {"errors": ["Some GraphQL error"]}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await get_wandb_default_entity(valid_api_key, base_url)

            assert result is None

    @pytest.mark.asyncio
    async def test_missing_viewer_field_returns_none(
        self, mock_response, valid_api_key, base_url
    ):
        """Test handling of response missing viewer field."""
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {}}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await get_wandb_default_entity(valid_api_key, base_url)

            assert result is None

    @pytest.mark.asyncio
    async def test_network_timeout_error(self, valid_api_key, base_url):
        """Test handling of network timeout."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.side_effect = httpx.TimeoutException("Request timed out")

            result = await get_wandb_default_entity(valid_api_key, base_url)

            assert isinstance(result, AuthenticationError)
            assert (
                "Failed to connect to W&B. Unexpected error: Request timed out"
                in str(result)
            )

    @pytest.mark.asyncio
    async def test_connection_error(self, valid_api_key, base_url):
        """Test handling of connection error."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.side_effect = httpx.ConnectError("Connection failed")

            result = await get_wandb_default_entity(valid_api_key, base_url)

            assert isinstance(result, AuthenticationError)
            assert (
                "Failed to connect to W&B. Unexpected error: Connection failed"
                in str(result)
            )

    @pytest.mark.asyncio
    async def test_json_decode_error(self, mock_response, valid_api_key, base_url):
        """Test handling of JSON decode error."""
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await get_wandb_default_entity(valid_api_key, base_url)

            assert isinstance(result, AuthenticationError)
            assert "Failed to connect to W&B. Unexpected error: Invalid JSON" in str(
                result
            )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status_code", [400, 403, 404, 500, 502, 503])
    async def test_various_http_error_codes(
        self, mock_response, valid_api_key, base_url, status_code
    ):
        """Test handling of various HTTP error status codes."""
        mock_response.status_code = status_code
        mock_response.json.return_value = {"error": "Some API error"}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await get_wandb_default_entity(valid_api_key, base_url)

            # For non-401 errors, the function should return None (no explicit handling)
            assert result is None

    @pytest.mark.asyncio
    async def test_empty_entity_name_returns_empty_string(
        self, mock_response, valid_api_key, base_url
    ):
        """Test handling of empty entity name."""
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "viewer": {
                    "id": "user123",
                    "username": "testuser",
                    "defaultEntity": {"id": "entity123", "name": ""},
                }
            }
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await get_wandb_default_entity(valid_api_key, base_url)

            # The code only checks 'is not None', so empty string is returned as-is
            assert result == ""

    @pytest.mark.asyncio
    async def test_malformed_response_structure(
        self, mock_response, valid_api_key, base_url
    ):
        """Test handling of malformed response structure."""
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "viewer": {
                    "id": "user123",
                    "username": "testuser",
                    "defaultEntity": {
                        "id": "entity123"
                        # Missing 'name' field
                    },
                }
            }
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await get_wandb_default_entity(valid_api_key, base_url)

            # Missing 'name' field causes KeyError, which gets caught and wrapped
            assert isinstance(result, AuthenticationError)
            assert "'name'" in str(result)


class TestAuthenticationError:
    """Test suite for AuthenticationError exception."""

    def test_authentication_error_creation(self):
        """Test that AuthenticationError can be created and has correct message."""
        message = "Test authentication error"
        error = AuthenticationError(message)

        assert isinstance(error, Exception)
        assert str(error) == message

    def test_authentication_error_inheritance(self):
        """Test that AuthenticationError inherits from Exception."""
        error = AuthenticationError("Test")
        assert isinstance(error, Exception)
