from http import HTTPStatus
from unittest.mock import AsyncMock, patch

from app.desktop.studio_server.api_client.kiln_ai_server_client.models import (
    ChatSnapshot,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.chat_session_list_item import (
    ChatSessionListItem as SdkChatSessionListItem,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.types import (
    Response as KilnResponse,
)


def _make_task_run_dict(**overrides):
    base = {
        "input": "",
        "output": {"output": "", "model_type": "test_model"},
        "model_type": "test_model",
    }
    base.update(overrides)
    return base


@patch(
    "app.desktop.studio_server.chat.routes.list_sessions_v1_chat_sessions_get.asyncio_detailed",
    new_callable=AsyncMock,
)
def test_list_chat_sessions_forwards_to_kiln(
    mock_asyncio_detailed, client, mock_api_key
):
    list_item_dict = {
        "id": "trace-1",
        "title": "Hi",
        "updated_at": "2025-06-15T12:30:00+00:00",
        "task_run": _make_task_run_dict(),
    }
    parsed_item = SdkChatSessionListItem.from_dict(list_item_dict)
    mock_asyncio_detailed.return_value = KilnResponse(
        status_code=HTTPStatus.OK,
        content=b"[]",
        headers={"content-type": "application/json"},
        parsed=[parsed_item],
    )

    r = client.get("/api/chat/sessions")

    assert r.status_code == 200
    assert r.json() == [
        {"id": "trace-1", "title": "Hi", "updated_at": "2025-06-15T12:30:00Z"}
    ]
    mock_asyncio_detailed.assert_called_once()
    call_kwargs = mock_asyncio_detailed.call_args[1]
    assert "client" in call_kwargs


@patch(
    "app.desktop.studio_server.chat.routes.get_session_v1_chat_sessions_session_id_get.asyncio_detailed",
    new_callable=AsyncMock,
)
def test_get_chat_session_forwards_to_kiln(mock_asyncio_detailed, client, mock_api_key):
    snapshot_dict = {
        "id": "trace-abc",
        "task_run": _make_task_run_dict(
            trace=[{"role": "user", "content": "yo"}],
        ),
    }
    parsed = ChatSnapshot.from_dict(snapshot_dict)
    mock_asyncio_detailed.return_value = KilnResponse(
        status_code=HTTPStatus.OK,
        content=b"{}",
        headers={"content-type": "application/json"},
        parsed=parsed,
    )

    r = client.get("/api/chat/sessions/trace-abc")

    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "trace-abc"
    assert body["task_run"]["trace"] == [{"role": "user", "content": "yo"}]
    mock_asyncio_detailed.assert_called_once()
    call_kwargs = mock_asyncio_detailed.call_args[1]
    assert call_kwargs["session_id"] == "trace-abc"
    assert "client" in call_kwargs


@patch(
    "app.desktop.studio_server.chat.routes.get_session_v1_chat_sessions_session_id_get.asyncio_detailed",
    new_callable=AsyncMock,
)
def test_get_chat_session_passes_through_error_status(
    mock_asyncio_detailed, client, mock_api_key
):
    mock_asyncio_detailed.return_value = KilnResponse(
        status_code=HTTPStatus.NOT_FOUND,
        content=b'{"detail":"not found"}',
        headers={"content-type": "application/json"},
        parsed=None,
    )

    r = client.get("/api/chat/sessions/missing")

    assert r.status_code == 404
    assert r.json()["message"] == "not found"


@patch(
    "app.desktop.studio_server.chat.routes.delete_session_v1_chat_sessions_session_id_delete.asyncio_detailed",
    new_callable=AsyncMock,
)
def test_delete_chat_session_returns_204(mock_asyncio_detailed, client, mock_api_key):
    mock_asyncio_detailed.return_value = KilnResponse(
        status_code=HTTPStatus.NO_CONTENT,
        content=b"",
        headers={},
        parsed=None,
    )

    r = client.delete("/api/chat/sessions/trace-xyz")

    assert r.status_code == 204
    mock_asyncio_detailed.assert_called_once()
    call_kwargs = mock_asyncio_detailed.call_args[1]
    assert call_kwargs["session_id"] == "trace-xyz"
    assert "client" in call_kwargs


@patch(
    "app.desktop.studio_server.chat.routes.delete_session_v1_chat_sessions_session_id_delete.asyncio_detailed",
    new_callable=AsyncMock,
)
def test_delete_chat_session_passes_through_error(
    mock_asyncio_detailed, client, mock_api_key
):
    mock_asyncio_detailed.return_value = KilnResponse(
        status_code=HTTPStatus.NOT_FOUND,
        content=b'{"detail":"session not found"}',
        headers={"content-type": "application/json"},
        parsed=None,
    )

    r = client.delete("/api/chat/sessions/missing")

    assert r.status_code == 404
    assert r.json()["message"] == "session not found"


@patch(
    "app.desktop.studio_server.chat.routes.list_sessions_v1_chat_sessions_get.asyncio_detailed",
    new_callable=AsyncMock,
)
def test_list_chat_sessions_passes_through_version_error_code(
    mock_asyncio_detailed, client, mock_api_key
):
    mock_asyncio_detailed.return_value = KilnResponse(
        status_code=HTTPStatus.BAD_REQUEST,
        content=b'{"message":"Update required","code":"chat_client_version_too_old"}',
        headers={"content-type": "application/json"},
        parsed=None,
    )

    r = client.get("/api/chat/sessions")

    assert r.status_code == 400
    body = r.json()
    assert body["message"] == "Update required"
    assert body["code"] == "chat_client_version_too_old"
