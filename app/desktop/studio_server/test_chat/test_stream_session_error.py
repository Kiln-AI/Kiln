import json
from unittest.mock import patch

import httpx
import pytest
from app.desktop.studio_server.chat.stream_session import ChatStreamSession
from kiln_server.error_codes import CHAT_CLIENT_VERSION_TOO_OLD


def _make_session():
    return ChatStreamSession(
        upstream_url="https://example.test/v1/chat",
        headers={},
        initial_body={"messages": []},
    )


class _FakeResponse:
    def __init__(self, status_code: int, body: bytes):
        self.status_code = status_code
        self._body = body

    async def aread(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class _FakeClient:
    def __init__(self, response: _FakeResponse):
        self._response = response

    def stream(self, *args, **kwargs):
        return self._response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


@pytest.mark.asyncio
async def test_stream_error_includes_code_field():
    error_body = json.dumps(
        {"message": "Update required", "code": CHAT_CLIENT_VERSION_TOO_OLD}
    ).encode()
    fake_resp = _FakeResponse(400, error_body)
    fake_client = _FakeClient(fake_resp)

    session = _make_session()

    with patch.object(httpx, "AsyncClient", return_value=fake_client):
        chunks = []
        async for chunk in session.stream():
            chunks.append(chunk)

    assert len(chunks) == 1
    payload = json.loads(chunks[0].decode().removeprefix("data: ").strip())
    assert payload["type"] == "error"
    assert payload["message"] == "Update required"
    assert payload["code"] == CHAT_CLIENT_VERSION_TOO_OLD


@pytest.mark.asyncio
async def test_stream_error_without_code_omits_code_field():
    error_body = json.dumps({"message": "Something failed"}).encode()
    fake_resp = _FakeResponse(500, error_body)
    fake_client = _FakeClient(fake_resp)

    session = _make_session()

    with patch.object(httpx, "AsyncClient", return_value=fake_client):
        chunks = []
        async for chunk in session.stream():
            chunks.append(chunk)

    assert len(chunks) == 1
    payload = json.loads(chunks[0].decode().removeprefix("data: ").strip())
    assert payload["type"] == "error"
    assert payload["message"] == "Something failed"
    assert "code" not in payload
