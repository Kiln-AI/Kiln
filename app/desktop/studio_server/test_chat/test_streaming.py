from unittest.mock import patch

from app.desktop.studio_server.test_chat.helpers import (
    PATCH_ASYNC_CLIENT,
    make_httpx_mock,
    sse_text_delta,
)


class TestChatStreaming:
    def test_streams_chunks(self, client, mock_api_key):
        chunks = [
            sse_text_delta("hello"),
            b'data: {"type":"finish"}\n\n',
        ]
        mock_class, _, _ = make_httpx_mock(chunks=chunks)

        with patch(PATCH_ASYNC_CLIENT, mock_class):
            response = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert b"text-delta" in response.content

    def test_forwards_auth_header(self, client, mock_api_key):
        mock_class, mock_client, _ = make_httpx_mock()

        with patch(PATCH_ASYNC_CLIENT, mock_class):
            response = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )
            _ = response.content

        call_kwargs = mock_client.stream.call_args
        headers = call_kwargs.kwargs.get("headers", {})
        assert headers.get("Authorization") == "Bearer test_api_key"

    def test_returns_401_when_no_api_key(self, client):
        with patch(
            "app.desktop.studio_server.utils.copilot_utils.Config.shared"
        ) as mock_config_shared:
            mock_config = mock_config_shared.return_value
            mock_config.kiln_copilot_api_key = None

            response = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )

        assert response.status_code == 401

    def test_handles_upstream_error(self, client, mock_api_key):
        mock_class, _, _ = make_httpx_mock(status_code=500)

        with patch(PATCH_ASYNC_CLIENT, mock_class):
            response = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )

        assert response.status_code == 200
        assert b"error" in response.content
