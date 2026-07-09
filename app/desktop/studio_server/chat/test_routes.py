import json
from http import HTTPStatus
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.desktop.studio_server.api_client.kiln_ai_server_client.models import (
    ChatSnapshot,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.chat_session_list_item import (
    ChatSessionListItem as SdkChatSessionListItem,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.types import (
    Response as KilnResponse,
)
from app.desktop.studio_server.chat.routes import ChatSessionSnapshot
from kiln_server.error_codes import CHAT_CLIENT_VERSION_TOO_OLD


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
        {
            "id": "trace-1",
            "title": "Hi",
            "updated_at": "2025-06-15T12:30:00Z",
            "auto_active": False,
            "auto_run_id": None,
            "agent_type": None,
            "root_id": None,
            "parent_root_id": None,
            "is_subagent": False,
            "subagent_id": None,
            "subagent_status": None,
        }
    ]
    mock_asyncio_detailed.assert_called_once()
    call_kwargs = mock_asyncio_detailed.call_args[1]
    assert "client" in call_kwargs


@patch(
    "app.desktop.studio_server.chat.routes.list_sessions_v1_chat_sessions_get.asyncio_detailed",
    new_callable=AsyncMock,
)
def test_list_chat_sessions_auto_join_reads_supervisor(
    mock_asyncio_detailed, client, mock_api_key, monkeypatch
):
    # Phase 3: the auto_active/auto_run_id join reads the conversation
    # supervisor (the old AutoChatRegistry is gone). auto_run_id carries the
    # auto conversation's SESSION id, and the join keys on flag-on records —
    # the green dot persists while IDLE, disappears once stopped/disabled
    # (old AutoRunStatus.flag_on semantics).
    from app.desktop.studio_server.chat import routes as routes_module
    from app.desktop.studio_server.chat.runtime.supervisor import (
        ConversationSupervisor,
    )

    sup = ConversationSupervisor()
    monkeypatch.setattr(routes_module, "conversation_supervisor", sup)
    record = sup.create_conversation(
        "auto", upstream_url="https://example.test", headers={}
    )
    # Adopt the row's leaf like enable_auto does (whole-chain index).
    record.current_leaf_trace_id = "t1"
    record.seen_trace_ids.append("t1")
    sup._trace_index["t1"] = record.session_id

    parsed_item = SdkChatSessionListItem.from_dict(
        {
            "id": "t1",
            "title": "Active one",
            "updated_at": "2025-06-15T12:30:00+00:00",
            "task_run": _make_task_run_dict(),
        }
    )
    mock_asyncio_detailed.return_value = KilnResponse(
        status_code=HTTPStatus.OK,
        content=b"[]",
        headers={"content-type": "application/json"},
        parsed=[parsed_item],
    )

    r = client.get("/api/chat/sessions")
    assert r.status_code == 200
    body = r.json()
    assert body[0]["auto_active"] is True
    assert body[0]["auto_run_id"] == record.session_id

    # Flag off → the join drops it (no green dot after stop/disable).
    record.auto_flag = False
    r = client.get("/api/chat/sessions")
    assert r.json()[0]["auto_active"] is False
    assert r.json()[0]["auto_run_id"] is None


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
def test_get_chat_session_round_trips_context_usage(
    mock_asyncio_detailed, client, mock_api_key
):
    # Upstream now emits a top-level ``context_usage`` alongside ``id`` /
    # ``task_run``. The generated SDK model only declares id + task_run and
    # stashes extras in ``additional_properties``, which ``to_dict()`` re-emits,
    # so the field survives into ``ChatSessionSnapshot`` once the field exists.
    snapshot_dict = {
        "id": "trace-ctx",
        "task_run": _make_task_run_dict(trace=[{"role": "user", "content": "yo"}]),
        "context_usage": {
            "context_tokens": 1234,
            "context_limit": 150000,
            "context_percent": 0.0082,
            "compacted": True,
        },
    }
    parsed = ChatSnapshot.from_dict(snapshot_dict)
    mock_asyncio_detailed.return_value = KilnResponse(
        status_code=HTTPStatus.OK,
        content=b"{}",
        headers={"content-type": "application/json"},
        parsed=parsed,
    )

    r = client.get("/api/chat/sessions/trace-ctx")

    assert r.status_code == 200
    body = r.json()
    assert body["context_usage"] == {
        "context_tokens": 1234,
        "context_limit": 150000,
        "context_percent": 0.0082,
        "compacted": True,
    }


def test_chat_session_snapshot_drops_unknown_keys_invariant():
    # Pin the containment invariant at the model level, independent of the route
    # round-trip: a valid snapshot carrying the server-only ``compacted_trace``
    # validates successfully (no 500) AND the unknown key is dropped, so it can
    # never reach the client (functional_spec.md §7.3). This guards against a
    # maintainer "tightening" the config to ``extra="forbid"`` (which would raise
    # instead of drop) or relying on an unstated default.
    snapshot = ChatSessionSnapshot.model_validate(
        {
            "id": "trace-invariant",
            "task_run": {"trace": [{"role": "user", "content": "hi"}]},
            "context_usage": {
                "context_tokens": 1,
                "context_limit": 2,
                "context_percent": 0.5,
                "compacted": False,
            },
            "compacted_trace": [{"role": "system", "content": "secret"}],
        }
    )

    assert not hasattr(snapshot, "compacted_trace")
    assert "compacted_trace" not in snapshot.model_dump()
    assert snapshot.id == "trace-invariant"
    assert snapshot.context_usage is not None


@patch(
    "app.desktop.studio_server.chat.routes.get_session_v1_chat_sessions_session_id_get.asyncio_detailed",
    new_callable=AsyncMock,
)
def test_get_chat_session_drops_compacted_trace(
    mock_asyncio_detailed, client, mock_api_key
):
    # Defense in depth (functional_spec.md §7.3): even if a regressed upstream
    # leaked the server-only ``compacted_trace``, ``ChatSessionSnapshot``'s
    # ``extra="ignore"`` config must drop it at the client boundary. The full
    # ``task_run.trace`` and the gauge numbers still come through.
    snapshot_dict = {
        "id": "trace-leak",
        "task_run": _make_task_run_dict(trace=[{"role": "user", "content": "hi"}]),
        "compacted_trace": [{"role": "system", "content": "<compaction_summary>..."}],
        "context_usage": {
            "context_tokens": 99,
            "context_limit": 150000,
            "context_percent": 0.0007,
            "compacted": True,
        },
    }
    parsed = ChatSnapshot.from_dict(snapshot_dict)
    mock_asyncio_detailed.return_value = KilnResponse(
        status_code=HTTPStatus.OK,
        content=b"{}",
        headers={"content-type": "application/json"},
        parsed=parsed,
    )

    r = client.get("/api/chat/sessions/trace-leak")

    assert r.status_code == 200
    body = r.json()
    assert "compacted_trace" not in body
    assert body["task_run"]["trace"] == [{"role": "user", "content": "hi"}]
    assert body["context_usage"]["compacted"] is True


@patch(
    "app.desktop.studio_server.chat.routes.get_session_v1_chat_sessions_session_id_get.asyncio_detailed",
    new_callable=AsyncMock,
)
def test_get_chat_session_tolerates_missing_context_usage(
    mock_asyncio_detailed, client, mock_api_key
):
    # Backward compatibility: an older upstream that omits ``context_usage`` must
    # not 500 the proxy. ``response_model_exclude_none`` drops the absent field.
    snapshot_dict = {
        "id": "trace-old",
        "task_run": _make_task_run_dict(trace=[{"role": "user", "content": "yo"}]),
    }
    parsed = ChatSnapshot.from_dict(snapshot_dict)
    mock_asyncio_detailed.return_value = KilnResponse(
        status_code=HTTPStatus.OK,
        content=b"{}",
        headers={"content-type": "application/json"},
        parsed=parsed,
    )

    r = client.get("/api/chat/sessions/trace-old")

    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "trace-old"
    assert "context_usage" not in body


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


# ── Phase 5: conversation-key resolution on the history surface ───────────────
#
# The browser keys everything on session ids (functional spec §4); the
# upstream stays leaf-keyed until phase 6, so routes.py owns the mapping:
# rows carry the best key available (live sid → root id → legacy leaf) and
# GET/DELETE resolve any of those back to the current leaf.


def _fresh_supervisor(monkeypatch):
    from app.desktop.studio_server.chat import routes as routes_module
    from app.desktop.studio_server.chat.runtime.supervisor import (
        ConversationSupervisor,
    )

    sup = ConversationSupervisor()
    monkeypatch.setattr(routes_module, "conversation_supervisor", sup)
    return sup


def _seed_live_record(sup, leaf: str, kind: str = "interactive"):
    record = sup.create_conversation(
        kind, upstream_url="https://example.test", headers={}
    )
    record.current_leaf_trace_id = leaf
    record.seen_trace_ids.append(leaf)
    sup._trace_index[leaf] = record.session_id
    return record


@patch(
    "app.desktop.studio_server.chat.routes.list_sessions_v1_chat_sessions_get.asyncio_detailed",
    new_callable=AsyncMock,
)
def test_list_chat_sessions_rows_key_on_session_ids(
    mock_asyncio_detailed, client, mock_api_key, monkeypatch
):
    # Row id precedence: live record's session id (runtime-known, ANY kind —
    # parents and children) → upstream root_id (cold rows) → the leaf itself
    # (legacy sessions without session_meta). The browser treats all three as
    # one opaque conversation key.
    sup = _fresh_supervisor(monkeypatch)
    live = _seed_live_record(sup, "1111111111_live-leaf")
    rows = [
        {
            "id": "1111111111_live-leaf",
            "title": "Live",
            "updated_at": "2025-06-15T12:30:00+00:00",
            "task_run": _make_task_run_dict(),
            "root_id": "1111111112_live-root",
        },
        {
            "id": "1111111113_cold-leaf",
            "title": "Cold",
            "updated_at": "2025-06-15T12:00:00+00:00",
            "task_run": _make_task_run_dict(),
            "root_id": "1111111114_cold-root",
        },
        {
            "id": "1111111115_legacy-leaf",
            "title": "Legacy",
            "updated_at": "2025-06-15T11:00:00+00:00",
            "task_run": _make_task_run_dict(),
        },
    ]
    mock_asyncio_detailed.return_value = KilnResponse(
        status_code=HTTPStatus.OK,
        content=b"[]",
        headers={"content-type": "application/json"},
        parsed=[SdkChatSessionListItem.from_dict(row) for row in rows],
    )

    r = client.get("/api/chat/sessions")
    assert r.status_code == 200
    body = r.json()
    assert [row["id"] for row in body] == [
        live.session_id,
        "1111111114_cold-root",
        "1111111115_legacy-leaf",
    ]
    # root_id still rides every row that has one (grouping + the browser's
    # durable recovery key).
    assert body[0]["root_id"] == "1111111112_live-root"
    assert body[1]["root_id"] == "1111111114_cold-root"
    assert body[2]["root_id"] is None


@patch(
    "app.desktop.studio_server.chat.routes.get_session_v1_chat_sessions_session_id_get.asyncio_detailed",
    new_callable=AsyncMock,
)
def test_get_chat_session_resolves_live_session_key(
    mock_asyncio_detailed, client, mock_api_key, monkeypatch
):
    # A live conversation key resolves to the record's CURRENT leaf — the
    # replacement for the browser's deleted current_trace_id refresh (a
    # stale leaf of the same conversation resolves identically through the
    # whole-chain index).
    sup = _fresh_supervisor(monkeypatch)
    record = _seed_live_record(sup, "1111111111_stale-leaf")
    record.current_leaf_trace_id = "1111111110_current-leaf"
    record.seen_trace_ids.append("1111111110_current-leaf")
    sup._trace_index["1111111110_current-leaf"] = record.session_id

    parsed = ChatSnapshot.from_dict(
        {
            "id": "1111111110_current-leaf",
            "task_run": _make_task_run_dict(trace=[{"role": "user", "content": "yo"}]),
        }
    )
    mock_asyncio_detailed.return_value = KilnResponse(
        status_code=HTTPStatus.OK,
        content=b"{}",
        headers={"content-type": "application/json"},
        parsed=parsed,
    )

    for key in (record.session_id, "1111111111_stale-leaf"):
        r = client.get(f"/api/chat/sessions/{key}")
        assert r.status_code == 200, key
        assert (
            mock_asyncio_detailed.call_args[1]["session_id"]
            == "1111111110_current-leaf"
        )

    # A dead cv_ key (desktop restarted) has nothing to resolve to → 404
    # (a cv_ id is desktop-minted and never a valid upstream id).
    r = client.get("/api/chat/sessions/cv_dead")
    assert r.status_code == 404


@patch(
    "app.desktop.studio_server.chat.routes.get_session_v1_chat_sessions_session_id_get.asyncio_detailed",
    new_callable=AsyncMock,
)
@patch(
    "app.desktop.studio_server.chat.routes.list_sessions_v1_chat_sessions_get.asyncio_detailed",
    new_callable=AsyncMock,
)
def test_get_chat_session_resolves_cold_root_key_via_list_scan(
    mock_list, mock_get, client, mock_api_key, monkeypatch
):
    # A cold root key (no live record) resolves root→leaf via the upstream
    # sessions list — fetching the root DIRECTLY would return the stale
    # FIRST snapshot, so the scan must win. TODO(phase-6): collapses once
    # the upstream GET accepts either id kind.
    _fresh_supervisor(monkeypatch)
    mock_list.return_value = KilnResponse(
        status_code=HTTPStatus.OK,
        content=b"[]",
        headers={"content-type": "application/json"},
        parsed=[
            SdkChatSessionListItem.from_dict(
                {
                    "id": "1111111110_cur-leaf",
                    "title": "Cold",
                    "updated_at": "2025-06-15T12:00:00+00:00",
                    "task_run": _make_task_run_dict(),
                    "root_id": "1111111119_root",
                }
            )
        ],
    )
    mock_get.return_value = KilnResponse(
        status_code=HTTPStatus.OK,
        content=b"{}",
        headers={"content-type": "application/json"},
        parsed=ChatSnapshot.from_dict(
            {
                "id": "1111111110_cur-leaf",
                "task_run": _make_task_run_dict(
                    trace=[{"role": "user", "content": "yo"}]
                ),
            }
        ),
    )

    r = client.get("/api/chat/sessions/1111111119_root")
    assert r.status_code == 200
    assert mock_get.call_args[1]["session_id"] == "1111111110_cur-leaf"

    # A snapshot-shaped key matching NO root falls through to the legacy
    # leaf interpretation (sessions without session_meta resolve as today).
    r = client.get("/api/chat/sessions/1111111110_cur-leaf")
    assert r.status_code == 200
    assert mock_get.call_args[1]["session_id"] == "1111111110_cur-leaf"


@patch(
    "app.desktop.studio_server.chat.routes.list_sessions_v1_chat_sessions_get.asyncio_detailed",
    new_callable=AsyncMock,
)
async def test_leaf_for_root_id_pages_and_bounds(mock_list, mock_api_key):
    # The root→leaf scan pages the upstream list and stops at a short page —
    # bounded best-effort, mirroring architecture §8's trust model for the
    # backend's own pointer fallback.
    from app.desktop.studio_server.chat.routes import _leaf_for_root_id

    def _page(rows):
        return KilnResponse(
            status_code=HTTPStatus.OK,
            content=b"[]",
            headers={"content-type": "application/json"},
            parsed=[SdkChatSessionListItem.from_dict(r) for r in rows],
        )

    full_page = [
        {
            "id": f"1111111{i:03d}_leaf",
            "title": "x",
            "updated_at": "2025-06-15T12:00:00+00:00",
            "task_run": _make_task_run_dict(),
        }
        for i in range(100)
    ]
    match_page = [
        {
            "id": "1111111110_found-leaf",
            "title": "x",
            "updated_at": "2025-06-15T12:00:00+00:00",
            "task_run": _make_task_run_dict(),
            "root_id": "1111111119_root",
        }
    ]
    mock_list.side_effect = [_page(full_page), _page(match_page)]
    assert await _leaf_for_root_id("1111111119_root") == "1111111110_found-leaf"
    assert mock_list.call_count == 2
    assert mock_list.call_args_list[1][1]["offset"] == 100

    # A short page with no match COMPLETES the scan: None is the proven
    # "not a root id" outcome (the legacy-leaf fall-through, by design).
    mock_list.side_effect = [_page(match_page)]
    assert await _leaf_for_root_id("2222222222_other-root") is None


@patch(
    "app.desktop.studio_server.chat.routes.list_sessions_v1_chat_sessions_get.asyncio_detailed",
    new_callable=AsyncMock,
)
async def test_leaf_for_root_id_indeterminate_scan_raises(
    mock_list, mock_api_key, monkeypatch
):
    # Phase-5 CR MEDIUM 1 / LOW 4: transport failure, an upstream error
    # response, and page-bound exhaustion are all INDETERMINATE — they must
    # raise (never return the completed-no-match None), or callers would
    # fall through to the legacy-leaf interpretation and silently fork/stale
    # a root-keyed conversation.
    from app.desktop.studio_server.chat import routes as routes_module
    from app.desktop.studio_server.chat.routes import (
        UpstreamResolutionError,
        _leaf_for_root_id,
    )

    def _page(rows):
        return KilnResponse(
            status_code=HTTPStatus.OK,
            content=b"[]",
            headers={"content-type": "application/json"},
            parsed=[SdkChatSessionListItem.from_dict(r) for r in rows],
        )

    # Transport failure.
    mock_list.side_effect = httpx.ConnectError("boom")
    with pytest.raises(UpstreamResolutionError, match="unreachable"):
        await _leaf_for_root_id("1111111119_root")

    # Upstream error response.
    mock_list.side_effect = None
    mock_list.return_value = KilnResponse(
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        content=b"{}",
        headers={"content-type": "application/json"},
        parsed=None,
    )
    with pytest.raises(UpstreamResolutionError, match="500"):
        await _leaf_for_root_id("1111111119_root")

    # Page bound exhausted with (potentially) more pages remaining: a FULL
    # page at the bound means the scan never proved "no match" (LOW 4 —
    # failing open here would misread a beyond-bound root as a legacy leaf).
    monkeypatch.setattr(routes_module, "_ROOT_SCAN_MAX_PAGES", 1)
    full_page = [
        {
            "id": f"1111111{i:03d}_leaf",
            "title": "x",
            "updated_at": "2025-06-15T12:00:00+00:00",
            "task_run": _make_task_run_dict(),
        }
        for i in range(100)
    ]
    mock_list.return_value = None
    mock_list.side_effect = [_page(full_page)]
    with pytest.raises(UpstreamResolutionError, match="bound"):
        await _leaf_for_root_id("1111111119_root")


@patch(
    "app.desktop.studio_server.chat.routes.list_sessions_v1_chat_sessions_get.asyncio_detailed",
    new_callable=AsyncMock,
)
def test_get_and_delete_return_503_on_indeterminate_root_scan(
    mock_list, client, mock_api_key, monkeypatch
):
    # CR MEDIUM 1 (history side): a snapshot-shaped key whose root scan can't
    # complete must fail CLEAN with 503 — treating the key as a leaf could
    # serve (or delete) the stale FIRST snapshot of a root-keyed session.
    _fresh_supervisor(monkeypatch)
    mock_list.side_effect = httpx.ConnectError("boom")
    r = client.get("/api/chat/sessions/1111111119_root")
    assert r.status_code == 503

    r = client.delete("/api/chat/sessions/1111111119_root")
    assert r.status_code == 503


@patch(
    "app.desktop.studio_server.chat.routes.delete_session_v1_chat_sessions_session_id_delete.asyncio_detailed",
    new_callable=AsyncMock,
)
def test_delete_chat_session_resolves_key_and_cascades_by_leaf(
    mock_asyncio_detailed, client, mock_api_key, monkeypatch
):
    # DELETE accepts the same conversation keys; the upstream DELETE and the
    # orchestration cascade both run on the resolved CURRENT leaf (which the
    # trace index resolves back to the record for the cascade).
    sup = _fresh_supervisor(monkeypatch)
    record = _seed_live_record(sup, "1111111111_leaf")
    mock_asyncio_detailed.return_value = KilnResponse(
        status_code=HTTPStatus.NO_CONTENT,
        content=b"",
        headers={},
        parsed=None,
    )
    with patch(
        "app.desktop.studio_server.chat.routes.orchestration.handle_session_deleted",
        new_callable=AsyncMock,
    ) as cascade:
        r = client.delete(f"/api/chat/sessions/{record.session_id}")
    assert r.status_code == 204
    assert mock_asyncio_detailed.call_args[1]["session_id"] == "1111111111_leaf"
    cascade.assert_awaited_once_with("1111111111_leaf")


@patch(
    "app.desktop.studio_server.chat.routes.get_session_v1_chat_sessions_session_id_get.asyncio_detailed",
    new_callable=AsyncMock,
)
def test_get_chat_session_passes_through_root_id(
    mock_asyncio_detailed, client, mock_api_key
):
    # Phase 5: the snapshot's durable root_id rides the desktop proxy so the
    # browser can persist it as its restart-recovery key (a SESSION id — the
    # leaf-shaped ``id`` is no longer stored browser-side).
    snapshot_dict = {
        "id": "trace-abc",
        "task_run": _make_task_run_dict(trace=[{"role": "user", "content": "yo"}]),
        "root_id": "1111111119_root",
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
    assert r.json()["root_id"] == "1111111119_root"


@patch(
    "app.desktop.studio_server.chat.routes.list_sessions_v1_chat_sessions_get.asyncio_detailed",
    new_callable=AsyncMock,
)
def test_list_chat_sessions_passes_through_version_error_code(
    mock_asyncio_detailed, client, mock_api_key
):
    mock_asyncio_detailed.return_value = KilnResponse(
        status_code=HTTPStatus.BAD_REQUEST,
        content=json.dumps(
            {"message": "Update required", "code": CHAT_CLIENT_VERSION_TOO_OLD}
        ).encode(),
        headers={"content-type": "application/json"},
        parsed=None,
    )

    r = client.get("/api/chat/sessions")

    assert r.status_code == 400
    body = r.json()
    assert body["message"] == {
        "message": "Update required",
        "code": CHAT_CLIENT_VERSION_TOO_OLD,
    }


def _sse_event(data: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(data)}\n\n".encode()


def _parse_sse_events(content: bytes) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in content.decode().split("\n"):
        if not line.startswith("data: "):
            continue
        payload = line[6:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            ev = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(ev, dict):
            events.append(ev)
    return events


def _find_endpoint_by_path(app, path: str):
    """Locate the endpoint function for a route with exact path match."""
    for route in app.routes:
        if getattr(route, "path", None) == path:
            return route.endpoint  # type: ignore[attr-defined]
    raise AssertionError(f"Route with path {path} not found")


# --- GET /api/chat/version_policy proxy ---

PATCH_ROUTES_ASYNC_CLIENT = "app.desktop.studio_server.chat.routes.httpx.AsyncClient"


def _mock_version_policy_client(*, json_body=None, status_code=200):
    """Build a mock httpx.AsyncClient whose async .get() returns a fake response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    http_client = MagicMock()
    http_client.get = AsyncMock(return_value=resp)
    http_client.__aenter__ = AsyncMock(return_value=http_client)
    http_client.__aexit__ = AsyncMock(return_value=None)
    return MagicMock(return_value=http_client)


def test_version_policy_forwards_and_parses(client, mock_api_key):
    mock_class = _mock_version_policy_client(
        json_body={"required": False, "upgrade_nudge_version": "1.0.5"}
    )
    with patch(PATCH_ROUTES_ASYNC_CLIENT, mock_class):
        r = client.get("/api/chat/version_policy")
    assert r.status_code == 200
    assert r.json() == {"required": False, "upgrade_nudge_version": "1.0.5"}


def test_version_policy_degrades_on_non_200(client, mock_api_key):
    mock_class = _mock_version_policy_client(json_body={}, status_code=503)
    with patch(PATCH_ROUTES_ASYNC_CLIENT, mock_class):
        r = client.get("/api/chat/version_policy")
    assert r.status_code == 200
    assert r.json() == {"required": False, "upgrade_nudge_version": None}


def test_version_policy_degrades_on_invalid_upstream_body(client, mock_api_key):
    # Pydantic v2 ValidationError is not a ValueError; ensure it's caught and we
    # degrade to "no banner" rather than 500.
    mock_class = _mock_version_policy_client(json_body={"required": "not-a-bool"})
    with patch(PATCH_ROUTES_ASYNC_CLIENT, mock_class):
        r = client.get("/api/chat/version_policy")
    assert r.status_code == 200
    assert r.json() == {"required": False, "upgrade_nudge_version": None}


def test_version_policy_degrades_on_transport_error(client, mock_api_key):
    http_client = MagicMock()
    http_client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))
    http_client.__aenter__ = AsyncMock(return_value=http_client)
    http_client.__aexit__ = AsyncMock(return_value=None)
    with patch(PATCH_ROUTES_ASYNC_CLIENT, MagicMock(return_value=http_client)):
        r = client.get("/api/chat/version_policy")
    assert r.status_code == 200
    assert r.json() == {"required": False, "upgrade_nudge_version": None}


# ── Auto-mode interception on the interactive stream (port of the old
#    chat/auto/test_api.py /api/chat coverage; the interactive loop still
#    hosts these interceptions until phase 4). ─────────────────────────────────
