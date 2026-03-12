from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.desktop.studio_server.chat_api import connect_chat_api
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_server.custom_errors import connect_custom_errors


@pytest.fixture
def app():
    app = FastAPI()
    connect_custom_errors(app)
    connect_chat_api(app)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def mock_api_key():
    with patch(
        "app.desktop.studio_server.utils.copilot_utils.Config.shared"
    ) as mock_config_shared:
        mock_config = mock_config_shared.return_value
        mock_config.kiln_copilot_api_key = "test_api_key"
        yield mock_config


def _make_httpx_mock(status_code: int = 200, chunks: list[bytes] | None = None):
    """Build a mock httpx.AsyncClient context-manager chain for chat_api tests."""
    if chunks is None:
        chunks = [b'data: {"type":"text-delta","delta":"hello"}\n\n']

    async def mock_aiter_bytes():
        for chunk in chunks:
            yield chunk

    mock_upstream = MagicMock()
    mock_upstream.status_code = status_code
    mock_upstream.aiter_bytes.return_value = mock_aiter_bytes()
    mock_upstream.aread = AsyncMock(
        return_value=b'{"message":"upstream error"}' if status_code != 200 else b""
    )
    mock_upstream.__aenter__ = AsyncMock(return_value=mock_upstream)
    mock_upstream.__aexit__ = AsyncMock(return_value=None)

    mock_client = MagicMock()
    mock_client.stream.return_value = mock_upstream
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    mock_async_client_class = MagicMock(return_value=mock_client)
    return mock_async_client_class, mock_client, mock_upstream


def test_chat_streams_chunks(client, mock_api_key):
    chunks = [
        b'data: {"type":"text-delta","delta":"hello"}\n\n',
        b'data: {"type":"finish"}\n\n',
    ]
    mock_class, mock_client, mock_upstream = _make_httpx_mock(chunks=chunks)

    with patch("app.desktop.studio_server.chat_api.httpx.AsyncClient", mock_class):
        response = client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert b"text-delta" in response.content
    assert b"finish" in response.content


def test_chat_forwards_auth_header(client, mock_api_key):
    mock_class, mock_client, mock_upstream = _make_httpx_mock()

    with patch("app.desktop.studio_server.chat_api.httpx.AsyncClient", mock_class):
        client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )

    call_kwargs = mock_client.stream.call_args
    headers = (
        call_kwargs.kwargs.get("headers") or call_kwargs.args[2]
        if len(call_kwargs.args) > 2
        else {}
    )
    if not headers:
        headers = call_kwargs.kwargs.get("headers", {})
    assert headers.get("Authorization") == "Bearer test_api_key"


def test_chat_forwards_request_body(client, mock_api_key):
    mock_class, mock_client, _ = _make_httpx_mock()
    request_body = {"messages": [{"role": "user", "content": "test message"}]}

    with patch("app.desktop.studio_server.chat_api.httpx.AsyncClient", mock_class):
        client.post("/api/chat", json=request_body)

    call_kwargs = mock_client.stream.call_args
    sent_content = call_kwargs.kwargs.get("content") or (
        call_kwargs.args[2] if len(call_kwargs.args) > 2 else None
    )
    if sent_content is None:
        sent_content = call_kwargs.kwargs.get("content")
    import json

    assert json.loads(sent_content) == request_body


def test_chat_returns_401_when_no_api_key(client):
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


def test_chat_handles_upstream_error(client, mock_api_key):
    mock_class, _, _ = _make_httpx_mock(status_code=500)

    with patch("app.desktop.studio_server.chat_api.httpx.AsyncClient", mock_class):
        response = client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 200
    assert b"error" in response.content
    assert b"upstream error" in response.content
