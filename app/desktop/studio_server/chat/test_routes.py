import json
from http import HTTPStatus
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.desktop.studio_server.api_client.kiln_ai_server_client.models import (
    ChatSnapshot,
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


PATCH_ROUTES_HTTPX_CLIENT = "app.desktop.studio_server.chat.routes.httpx.AsyncClient"


def _mock_sessions_upstream(*, json_body=None, status_code=200, content=b""):
    """Mock httpx.AsyncClient whose async .get() serves the upstream session
    list. Returns (class mock to patch in, client mock to assert calls on)."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    resp.content = content
    http_client = MagicMock()
    http_client.get = AsyncMock(return_value=resp)
    http_client.__aenter__ = AsyncMock(return_value=http_client)
    http_client.__aexit__ = AsyncMock(return_value=None)
    return MagicMock(return_value=http_client), http_client


def test_list_chat_sessions_forwards_to_kiln(client, mock_api_key, monkeypatch):
    monkeypatch.delenv("KILN_DEV_MODE", raising=False)
    mock_class, http_client = _mock_sessions_upstream(
        json_body=[
            {
                "id": "trace-1",
                "title": "Hi",
                "updated_at": "2025-06-15T12:30:00+00:00",
            }
        ]
    )

    with patch(PATCH_ROUTES_HTTPX_CLIENT, mock_class):
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
    http_client.get.assert_called_once()
    call_kwargs = http_client.get.call_args[1]
    assert call_kwargs["params"] == {"limit": 50, "offset": 0}
    assert "Authorization" in call_kwargs["headers"]


def test_list_chat_sessions_auto_join_reads_supervisor(
    client, mock_api_key, monkeypatch
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

    mock_class, _http_client = _mock_sessions_upstream(
        json_body=[
            {
                "id": "t1",
                "title": "Active one",
                "updated_at": "2025-06-15T12:30:00+00:00",
            }
        ]
    )

    with patch(PATCH_ROUTES_HTTPX_CLIENT, mock_class):
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


# ── Phase 6: conversation-key resolution on the history surface ───────────────
#
# The browser keys everything on session ids (functional spec §4); rows carry
# the best key available (live sid → root id → legacy leaf). Resolution is
# purely LOCAL now: GET/DELETE substitute a live record's freshest upstream
# identity and forward any other key VERBATIM — the upstream resolves either
# id kind itself (architecture §8; the phase-5 desktop-side root→leaf list
# scan and its 503 indeterminate surface moved server-side with it).


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


def test_list_chat_sessions_rows_key_on_session_ids(client, mock_api_key, monkeypatch):
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
    mock_class, _http_client = _mock_sessions_upstream(json_body=rows)

    with patch(PATCH_ROUTES_HTTPX_CLIENT, mock_class):
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


def test_list_chat_sessions_joins_root_adopted_record_via_root_id(
    client, mock_api_key, monkeypatch
):
    # Phase 6: a record adopted by root key has NO leaf until its first
    # persist, so the row's leaf id can't find it in the trace index — the
    # join falls back to the row's root_id (which adopt indexed), so the row
    # keys on the live session id instead of minting a parallel identity.
    sup = _fresh_supervisor(monkeypatch)
    record = sup.create_conversation(
        "interactive", upstream_url="https://example.test", headers={}
    )
    record.resume_session_key = "1111111114_cold-root"
    record.seen_trace_ids.append("1111111114_cold-root")
    sup._trace_index["1111111114_cold-root"] = record.session_id

    mock_class, _http_client = _mock_sessions_upstream(
        json_body=[
            {
                "id": "1111111113_cold-leaf",
                "title": "Adopted",
                "updated_at": "2025-06-15T12:00:00+00:00",
                "root_id": "1111111114_cold-root",
            }
        ]
    )
    with patch(PATCH_ROUTES_HTTPX_CLIENT, mock_class):
        r = client.get("/api/chat/sessions")
    assert r.status_code == 200
    assert [row["id"] for row in r.json()] == [record.session_id]


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
def test_get_chat_session_forwards_cold_keys_verbatim(
    mock_get, client, mock_api_key, monkeypatch
):
    # Phase 6: a COLD key (root or legacy leaf — indistinguishable
    # desktop-side) is forwarded to the upstream AS-IS, with NO sessions-list
    # scan: the upstream resolves either id kind itself (root ids via its
    # pointer index) and returns the session's CURRENT leaf snapshot.
    _fresh_supervisor(monkeypatch)
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

    mock_list_class, list_http_client = _mock_sessions_upstream(json_body=[])
    with patch(PATCH_ROUTES_HTTPX_CLIENT, mock_list_class):
        for cold_key in ("1111111119_root", "1111111110_cur-leaf"):
            r = client.get(f"/api/chat/sessions/{cold_key}")
            assert r.status_code == 200, cold_key
            assert mock_get.call_args[1]["session_id"] == cold_key
    # The phase-5 root→leaf list scan is gone: resolution never touches the
    # upstream sessions list.
    list_http_client.get.assert_not_called()


@patch(
    "app.desktop.studio_server.chat.routes.get_session_v1_chat_sessions_session_id_get.asyncio_detailed",
    new_callable=AsyncMock,
)
def test_get_chat_session_key_adopted_record_forwards_resume_key(
    mock_get, client, mock_api_key, monkeypatch
):
    # A record adopted by cold key that hasn't persisted anything yet has no
    # leaf — the GET forwards its resume key (still resolvable upstream);
    # once a turn persists, the record's current leaf wins (freshest, O(1)).
    sup = _fresh_supervisor(monkeypatch)
    record = sup.create_conversation(
        "interactive", upstream_url="https://example.test", headers={}
    )
    record.resume_session_key = "1111111119_root"
    record.seen_trace_ids.append("1111111119_root")
    sup._trace_index["1111111119_root"] = record.session_id

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
    r = client.get(f"/api/chat/sessions/{record.session_id}")
    assert r.status_code == 200
    assert mock_get.call_args[1]["session_id"] == "1111111119_root"

    record.current_leaf_trace_id = "1111111110_cur-leaf"
    r = client.get(f"/api/chat/sessions/{record.session_id}")
    assert mock_get.call_args[1]["session_id"] == "1111111110_cur-leaf"


@patch(
    "app.desktop.studio_server.chat.routes.get_session_v1_chat_sessions_session_id_get.asyncio_detailed",
    new_callable=AsyncMock,
)
def test_get_chat_session_passes_through_upstream_503(
    mock_get, client, mock_api_key, monkeypatch
):
    # The indeterminate-resolution failure mode lives UPSTREAM now (the
    # backend's bounded pointer-fallback scan answers 503,
    # chat_session_resolution_incomplete); the proxy passes it through like
    # any other upstream error so the browser still sees a clean, retryable
    # failure instead of a silently stale transcript.
    _fresh_supervisor(monkeypatch)
    mock_get.return_value = KilnResponse(
        status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        content=b'{"detail":{"message":"Could not resolve the chat session."}}',
        headers={"content-type": "application/json"},
        parsed=None,
    )
    r = client.get("/api/chat/sessions/1111111119_root")
    assert r.status_code == 503


@patch(
    "app.desktop.studio_server.chat.routes.delete_session_v1_chat_sessions_session_id_delete.asyncio_detailed",
    new_callable=AsyncMock,
)
def test_delete_chat_session_resolves_key_and_cascades(
    mock_asyncio_detailed, client, mock_api_key, monkeypatch
):
    # DELETE accepts the same conversation keys; the upstream DELETE runs on
    # the record's freshest upstream identity (its current leaf) while the
    # orchestration cascade receives the browser's ORIGINAL key (phase 6:
    # handle_session_deleted resolves live sids directly and anything else
    # through the whole-chain index).
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
    cascade.assert_awaited_once_with(record.session_id)


@patch(
    "app.desktop.studio_server.chat.routes.delete_session_v1_chat_sessions_session_id_delete.asyncio_detailed",
    new_callable=AsyncMock,
)
def test_delete_chat_session_forwards_cold_keys_verbatim(
    mock_asyncio_detailed, client, mock_api_key, monkeypatch
):
    # A cold key deletes by-key upstream (the backend resolves a root to its
    # current leaf and cleans its pointer server-side); the cascade still
    # gets the original key — a no-op for a truly cold session.
    _fresh_supervisor(monkeypatch)
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
        r = client.delete("/api/chat/sessions/1111111119_root")
    assert r.status_code == 204
    assert mock_asyncio_detailed.call_args[1]["session_id"] == "1111111119_root"
    cascade.assert_awaited_once_with("1111111119_root")


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


def test_list_chat_sessions_passes_through_version_error_code(client, mock_api_key):
    mock_class, _http_client = _mock_sessions_upstream(
        status_code=400,
        content=json.dumps(
            {"message": "Update required", "code": CHAT_CLIENT_VERSION_TOO_OLD}
        ).encode(),
    )

    with patch(PATCH_ROUTES_HTTPX_CLIENT, mock_class):
        r = client.get("/api/chat/sessions")

    assert r.status_code == 400
    body = r.json()
    assert body["message"] == {
        "message": "Update required",
        "code": CHAT_CLIENT_VERSION_TOO_OLD,
    }


_SUBAGENT_LIST_ROWS = [
    {
        "id": "1111111111_parent-leaf",
        "title": "Parent",
        "updated_at": "2025-06-15T12:30:00+00:00",
        "root_id": "1111111112_parent-root",
    },
    {
        "id": "1111111113_child-leaf",
        "title": "Child task",
        "updated_at": "2025-06-15T12:31:00+00:00",
        "root_id": "1111111114_child-root",
        "parent_root_id": "1111111112_parent-root",
        "agent_type": "general",
        "is_subagent": True,
    },
]


def test_list_chat_sessions_hides_subagents_without_dev_mode(
    client, mock_api_key, monkeypatch
):
    # Sub-agent sessions are a developer affordance: outside dev mode the
    # proxy neither requests them upstream (no include_subagents param) nor
    # forwards any that an older upstream still returns.
    monkeypatch.delenv("KILN_DEV_MODE", raising=False)
    mock_class, http_client = _mock_sessions_upstream(json_body=_SUBAGENT_LIST_ROWS)

    with patch(PATCH_ROUTES_HTTPX_CLIENT, mock_class):
        r = client.get("/api/chat/sessions")

    assert r.status_code == 200
    assert [row["id"] for row in r.json()] == ["1111111112_parent-root"]
    params = http_client.get.call_args[1]["params"]
    assert "include_subagents" not in params


def test_list_chat_sessions_dev_mode_requests_and_keeps_subagents(
    client, mock_api_key, monkeypatch
):
    monkeypatch.setenv("KILN_DEV_MODE", "true")
    mock_class, http_client = _mock_sessions_upstream(json_body=_SUBAGENT_LIST_ROWS)

    with patch(PATCH_ROUTES_HTTPX_CLIENT, mock_class):
        r = client.get("/api/chat/sessions")

    assert r.status_code == 200
    body = r.json()
    assert [row["id"] for row in body] == [
        "1111111112_parent-root",
        "1111111114_child-root",
    ]
    assert body[1]["is_subagent"] is True
    assert body[1]["parent_root_id"] == "1111111112_parent-root"
    params = http_client.get.call_args[1]["params"]
    assert params["include_subagents"] == "true"


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
