import os
from importlib.metadata import version
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.desktop.studio_server.api_client.kiln_ai_server_client.api.health import (
    ping_ping_get,
)
from app.desktop.studio_server.api_client.kiln_server_client import (
    KilnServerClient,
    _get_desktop_app_version,
    get_kiln_server_client,
    server_client,
)

APP_VERSION = version("kiln-studio-desktop")


class TestGetKilnServerClient:
    """Tests for the get_kiln_server_client factory function."""

    def test_default_kiln_server(self):
        assert server_client is not None
        assert isinstance(server_client, KilnServerClient)

    def test_returns_client_with_correct_base_url_no_env_var(self):
        """Verify the client is configured with the correct base URL."""
        with patch.dict(os.environ, {}, clear=True):
            client = get_kiln_server_client()
            assert client._base_url == "https://api.kiln.tech"

    def test_returns_client_with_correct_base_url_with_env_var(self):
        """Verify the client is configured with the correct base URL."""
        with patch.dict(
            os.environ, {"KILN_SERVER_BASE_URL": "https://localhost:8000"}, clear=True
        ):
            client = get_kiln_server_client()
            assert client._base_url == "https://localhost:8000"

    def test_returns_client_with_correct_user_agent_header(self):
        """Verify the client has the correct User-Agent header set."""
        client = get_kiln_server_client()
        assert client._headers["User-Agent"] == f"KilnDesktopApp/{APP_VERSION}"
        assert client._headers["Kiln-Desktop-App-Version"] == APP_VERSION

    def test_client_creates_httpx_client_with_correct_headers(self):
        """Verify that when getting the httpx client, headers are properly passed."""
        client = get_kiln_server_client()
        httpx_client = client.get_httpx_client()

        assert httpx_client.headers["User-Agent"] == f"KilnDesktopApp/{APP_VERSION}"
        assert httpx_client.headers["Kiln-Desktop-App-Version"] == APP_VERSION

    def test_fetching_version_from_metadata(self):
        """Verify the client is configured with a valid version from metadata."""
        version = _get_desktop_app_version()
        assert APP_VERSION == version
        assert version != "unknown"
        assert "." in version
        for digits in version.split("."):
            assert digits.isdigit()


class TestMockedPingRequest:
    """Tests for ping request with mocked HTTP transport."""

    def test_ping_sync(self):
        """Verify ping request sends User-Agent header correctly."""
        client = get_kiln_server_client()

        mock_response = httpx.Response(
            status_code=200,
            content=b'"pong"',
            headers={"content-type": "application/json"},
        )

        mock_httpx_client = MagicMock(spec=httpx.Client)
        mock_httpx_client.request.return_value = mock_response

        client.set_httpx_client(mock_httpx_client)

        response = ping_ping_get.sync_detailed(client=client)

        mock_httpx_client.request.assert_called_once_with(method="get", url="/ping")
        assert response.status_code.value == 200
        assert response.parsed == '"pong"'

    def test_ping_returns_pong_using_sync_helper(self):
        """Verify the sync helper returns the parsed pong response."""
        client = get_kiln_server_client()

        mock_response = httpx.Response(
            status_code=200,
            content=b"pong",
            headers={"content-type": "text/plain"},
        )

        mock_httpx_client = MagicMock(spec=httpx.Client)
        mock_httpx_client.request.return_value = mock_response

        client.set_httpx_client(mock_httpx_client)

        result = ping_ping_get.sync(client=client)

        assert result == "pong"


@pytest.mark.paid
class TestRealPingRequest:
    """
    Tests for ping request against actual server.

    Will fail if the server is not running so marked as paid.
    """

    def test_real_ping_request(self):
        test_client = get_kiln_server_client()
        response = ping_ping_get.sync(client=test_client)
        assert response == "pong"

    async def test_real_async_ping_request(self):
        test_client = get_kiln_server_client()
        response = await ping_ping_get.asyncio(client=test_client)
        assert response == "pong"


class TestAsyncPingRequest:
    """Tests for async ping request."""

    @pytest.fixture
    def mock_async_transport(self):
        """Create a mock async transport that returns pong for /ping requests."""

        expected_user_agent = f"KilnDesktopApp/{APP_VERSION}"

        async def handle_request(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/ping":
                assert request.headers["User-Agent"] == expected_user_agent
                return httpx.Response(
                    status_code=200,
                    content=b"pong",
                    headers={"content-type": "text/plain"},
                )
            return httpx.Response(status_code=404)

        return httpx.MockTransport(handle_request)

    @pytest.mark.asyncio
    async def test_async_ping_request(self, mock_async_transport):
        """Test async ping request returns pong."""
        client = get_kiln_server_client()

        async_httpx_client = httpx.AsyncClient(
            base_url=client._base_url,
            headers=client._headers,
            transport=mock_async_transport,
        )
        client.set_async_httpx_client(async_httpx_client)

        result = await ping_ping_get.asyncio(client=client)

        assert result == "pong"
