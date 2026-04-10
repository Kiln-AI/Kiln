import json
from unittest.mock import AsyncMock, MagicMock

PATCH_ASYNC_CLIENT = "app.desktop.studio_server.chat.stream_session.httpx.AsyncClient"
PATCH_EXECUTE_TOOL = "app.desktop.studio_server.chat.stream_session.execute_tool"


def sse_text_delta(delta: str, text_id: str = "text-test") -> bytes:
    payload = {
        "type": "text-delta",
        "id": text_id,
        "delta": delta,
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


def make_httpx_mock(status_code: int = 200, chunks: list[bytes] | None = None):
    if chunks is None:
        chunks = [sse_text_delta("hello")]

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
