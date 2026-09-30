"""/api/conversations surface tests (FastAPI app over ASGI, no network).

Engines are patched to hang where lifecycle is driven through the
supervisor; the auto flows run against the shared fake upstream."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from kiln_server.custom_errors import connect_custom_errors

# Absolute imports so the patched module attributes are the same instances the
# app wiring resolves.
from app.desktop.studio_server.chat import routes as routes_module
from app.desktop.studio_server.chat.debug_log import ENV_VAR as DEBUG_LOG_ENV_VAR
from app.desktop.studio_server.chat.runtime import api as conversations_api_module
from app.desktop.studio_server.chat.runtime.api import connect_conversations_api
from app.desktop.studio_server.chat.runtime.engine import ConversationEngine
from app.desktop.studio_server.chat.runtime.models import RunState, auto_policy
from app.desktop.studio_server.chat.runtime.supervisor import ConversationSupervisor
from app.desktop.studio_server.chat.stream_session import _pending_item_from_event
from app.desktop.studio_server.chat.test_fakes import (
    FakeUpstreamClient,
    FakeUpstreamResponse,
    finish,
    text_delta,
    trace,
)


@pytest.fixture
def supervisor(monkeypatch):
    sup = ConversationSupervisor()
    # The API module reads a module-level singleton; point it at the fresh
    # instance. routes.py holds its own reference, consulted by the key
    # resolution the interactive create delegates to — patch both so the app
    # under test sees one supervisor, like production's shared singleton.
    monkeypatch.setattr(conversations_api_module, "conversation_supervisor", sup)
    monkeypatch.setattr(routes_module, "conversation_supervisor", sup)
    return sup


@pytest.fixture(autouse=True)
def no_rehydrate_network():
    # adopt_interactive's approval rehydration fetches the persisted snapshot
    # upstream; the API tests stage rehydration state explicitly instead, so
    # the default is "nothing persisted" (tests for the rehydration flow
    # patch this themselves with a scripted tail).
    with patch.object(
        ConversationSupervisor, "_fetch_persisted_trace", return_value=None
    ):
        yield


@pytest.fixture
def mock_api_key():
    # The auto endpoints build upstream headers via get_copilot_api_key.
    with patch(
        "app.desktop.studio_server.utils.copilot_utils.Config.shared"
    ) as mock_config_shared:
        mock_config = mock_config_shared.return_value
        mock_config.kiln_copilot_api_key = "test_api_key"
        yield mock_config


async def _wait_idle(supervisor: ConversationSupervisor, session_id: str) -> None:
    """Wait until the auto burst settles (record leaves RUNNING)."""

    async def _poll():
        while True:
            record = supervisor.get(session_id)
            if record is not None and record.state != RunState.RUNNING:
                return
            await asyncio.sleep(0.01)

    await asyncio.wait_for(_poll(), timeout=3.0)


@pytest.fixture
def hang_engine():
    async def _hang(self, record, policy, io, initial_body=None) -> None:
        await asyncio.Event().wait()

    with patch.object(ConversationEngine, "run", _hang):
        yield


@pytest.fixture
def app(supervisor):
    app = FastAPI()
    connect_custom_errors(app)
    connect_conversations_api(app)
    return app


@pytest_asyncio.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as http_client:
        yield http_client


def _seeded_interactive(supervisor: ConversationSupervisor, leaf: str):
    """A live interactive conversation already holding a persisted leaf — the
    state the browser's ensure() produces before it enables auto mode."""
    record = supervisor.create_conversation(
        "interactive", upstream_url="https://example.test", headers={}
    )
    record.current_leaf_trace_id = leaf
    record.seen_trace_ids.append(leaf)
    supervisor._trace_index[leaf] = record.session_id
    return record


def _running_interactive(supervisor: ConversationSupervisor):
    record = supervisor.create_conversation(
        "interactive", upstream_url="https://example.test", headers={}
    )
    supervisor.start_run(
        record.session_id, {"messages": [{"role": "user", "content": "go"}]}
    )
    return record


@pytest.mark.parametrize(
    ("value", "expected"), [(None, False), ("0", False), ("1", True)]
)
async def test_chat_debug_status(client, monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv(DEBUG_LOG_ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(DEBUG_LOG_ENV_VAR, value)
    r = await client.get("/api/chat/debug_status")
    assert r.status_code == 200
    assert r.json() == {"debug_log_enabled": expected}


async def test_get_conversation(supervisor, hang_engine, client):
    record = _running_interactive(supervisor)

    r = await client.get(f"/api/conversations/{record.session_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == record.session_id
    assert body["state"] == "running"
    assert body["kind"] == "interactive"
    assert body["auto_flag"] is False
    # Trace ids never ride the browser surface (functional spec §4).
    assert "current_trace_id" not in body
    assert "current_leaf_trace_id" not in body

    r = await client.get("/api/conversations/cv_missing")
    assert r.status_code == 404
    await supervisor.stop(record.session_id)


async def test_stop_endpoint_idempotent(supervisor, hang_engine, client):
    record = _running_interactive(supervisor)
    r = await client.post(f"/api/conversations/{record.session_id}/stop")
    assert r.status_code == 202
    assert supervisor.get(record.session_id).state == RunState.IDLE
    assert supervisor._conversations[record.session_id].task is None
    # Idempotent, including unknown ids.
    assert (
        await client.post(f"/api/conversations/{record.session_id}/stop")
    ).status_code == 202
    assert (await client.post("/api/conversations/cv_missing/stop")).status_code == 202


async def test_messages_endpoint(supervisor, hang_engine, client):
    record = _running_interactive(supervisor)
    r = await client.post(
        f"/api/conversations/{record.session_id}/messages",
        json={"content": "also check model B"},
    )
    assert r.status_code == 202
    # The accepted message's stable id rides the 202 body so the sending tab
    # can dedupe its own echo.
    conv = supervisor._conversations[record.session_id]
    assert [m.content for m in conv.inbox] == ["also check model B"]
    assert r.json()["message_id"] == conv.inbox[0].id
    await supervisor.stop(record.session_id)

    # The narrow disable window (flag off, auto policy still attached) refuses
    # a send with 409 rather than auto-approving without consent.
    conv.policy = auto_policy()
    conv.record.auto_flag = False
    r = await client.post(
        f"/api/conversations/{record.session_id}/messages",
        json={"content": "too late"},
    )
    assert r.status_code == 409

    r = await client.post(
        "/api/conversations/cv_missing/messages", json={"content": "x"}
    )
    assert r.status_code == 404


async def test_observer_stream_opens_with_state_marker(supervisor, hang_engine, client):
    # The observer stream never ends for a live conversation, and httpx's ASGI
    # transport drives the app to completion (no client-disconnect signal), so
    # the stream GENERATOR is exercised directly; the route wrapper adds
    # nothing beyond it.
    record = _running_interactive(supervisor)
    stream = conversations_api_module._observer_stream(record.session_id)
    try:
        first = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
    finally:
        await stream.aclose()
    state = json.loads(first.decode().removeprefix("data: "))
    assert state["type"] == "conversation-state"
    assert state["session_id"] == record.session_id
    assert state["state"] == "running"
    await supervisor.stop(record.session_id)

    r = await client.get("/api/conversations/cv_missing/events")
    assert r.status_code == 404


# ── Auto-mode surface ─────────────────────────────────────────────────────────


async def test_create_auto_starts_burst_and_returns_session_id(
    supervisor, client, mock_api_key
):
    # Consent accept: keyed by the LIVE conversation's session id — the
    # consent event arrives on the observer of an existing record, so a sid
    # is always in hand.
    seeded = _seeded_interactive(supervisor, "t1")
    round1 = [text_delta("on it"), trace("t1"), finish("stop")]
    fake = FakeUpstreamClient([FakeUpstreamResponse(chunks=round1)])

    with patch.object(httpx, "AsyncClient", return_value=fake):
        r = await client.post(
            "/api/conversations",
            json={
                "session_id": seeded.session_id,
                "enable_tool_call_id": "tc_enable",
                "reason": "running the eval",
            },
        )
        assert r.status_code == 200
        session_id = r.json()["session_id"]
        assert session_id == seeded.session_id
        await _wait_idle(supervisor, session_id)

    # The seed body resolved the enable call as enabled and continued from
    # the RECORD's own leaf with the auto_mode flag (also pinned by the
    # auto_seed_and_tool_round golden fixture).
    seed_body = fake.bodies[0]
    assert seed_body["trace_id"] == "t1"
    assert seed_body["auto_mode"] is True
    assert seed_body["messages"][0]["tool_call_id"] == "tc_enable"
    assert json.loads(seed_body["messages"][0]["content"]) == {"status": "enabled"}
    record = supervisor.get(session_id)
    assert record.kind == "auto" and record.auto_flag is True


async def test_create_auto_unknown_session_returns_404(
    supervisor, client, mock_api_key
):
    # The named conversation died with a restart/eviction — so did the
    # consent dialog's context; never silently fork a parallel record.
    r = await client.post(
        "/api/conversations",
        json={"session_id": "cv_missing", "enable_tool_call_id": "tc_enable"},
    )
    assert r.status_code == 404


async def test_create_auto_cap_returns_429(supervisor, client, mock_api_key):
    seeded = _seeded_interactive(supervisor, "t1")
    supervisor._auto_max_concurrent = 0  # cap reached: any enable is rejected
    r = await client.post(
        "/api/conversations",
        json={"session_id": seeded.session_id, "enable_tool_call_id": "tc_enable"},
    )
    assert r.status_code == 429
    assert "concurrent" in r.json()["message"].lower()


async def test_create_auto_armed_only_never_posts_upstream(
    supervisor, client, mock_api_key
):
    # Manual enable (ARMED-only): the record flips to IDLE("armed") with NO
    # upstream POST (an empty POST would be rejected by the backend).
    seeded = _seeded_interactive(supervisor, "t1")
    fake = FakeUpstreamClient([])  # any POST would blow up the fake
    with patch.object(httpx, "AsyncClient", return_value=fake):
        r = await client.post(
            "/api/conversations", json={"session_id": seeded.session_id}
        )
    assert r.status_code == 200
    record = supervisor.get(r.json()["session_id"])
    assert record is seeded
    assert record.state == RunState.IDLE
    assert record.idle_reason == "armed"
    assert record.auto_flag is True
    assert fake.bodies == []


async def test_decline_via_sid_auto_streams_on_observer(
    supervisor, client, mock_api_key
):
    # POST /{sid}/auto (enabled=false + decline ctx): the enable call
    # resolves as declined + denied siblings via an interactive turn on the
    # SAME conversation, whose reply streams on the observer channel. The
    # record HOLDS a leaf (a decline follows a live turn that persisted the
    # enable call), so the continuation rides trace_id.
    record = _seeded_interactive(supervisor, "t1")
    continuation = [text_delta("continuing interactively"), trace("t2"), finish("stop")]
    fake = FakeUpstreamClient([FakeUpstreamResponse(chunks=continuation)])

    with patch.object(httpx, "AsyncClient", return_value=fake):
        r = await client.post(
            f"/api/conversations/{record.session_id}/auto",
            json={
                "enabled": False,
                "decline": {
                    "gating_tool_call_id": "tc_enable",
                    "siblings": [
                        {
                            "toolCallId": "tc_sib",
                            "toolName": "kiln_tool::add_numbers",
                            "input": {"a": 1, "b": 2},
                            "requiresApproval": True,
                        }
                    ],
                },
            },
        )
        assert r.status_code == 202
        await _wait_idle(supervisor, record.session_id)

    sent_body = fake.bodies[0]
    assert sent_body["trace_id"] == "t1"
    messages = {m["tool_call_id"]: m["content"] for m in sent_body["messages"]}
    assert json.loads(messages["tc_enable"]) == {"status": "declined"}
    assert json.loads(messages["tc_sib"]) == {
        "error": "The user did not accept the toolcall"
    }
    # Declining never enables anything; the conversation stays interactive.
    assert record.auto_flag is False and record.kind == "interactive"

    # Unknown conversation → 404.
    r = await client.post(
        "/api/conversations/cv_missing/auto",
        json={"enabled": False, "decline": {"gating_tool_call_id": "tc"}},
    )
    assert r.status_code == 404


async def test_set_auto_flag_endpoint(supervisor, hang_engine, client, mock_api_key):
    auto = supervisor.create_conversation(
        "auto", upstream_url="https://example.test", headers={}
    )

    # Disable: flag off, reason user_disabled, and the swap back to the
    # interactive life.
    r = await client.post(
        f"/api/conversations/{auto.session_id}/auto", json={"enabled": False}
    )
    assert r.status_code == 202
    assert auto.auto_flag is False and auto.idle_reason == "user_disabled"
    assert auto.kind == "interactive"

    # Re-enable: the policy flip on the same record — ARMED-only re-arm.
    r = await client.post(
        f"/api/conversations/{auto.session_id}/auto", json={"enabled": True}
    )
    assert r.status_code == 202
    assert auto.auto_flag is True and auto.idle_reason == "armed"
    assert auto.kind == "auto"

    # Unknown → 404.
    r = await client.post("/api/conversations/cv_missing/auto", json={"enabled": True})
    assert r.status_code == 404


async def test_message_idle_auto_starts_burst_then_interactive_after_stop(
    supervisor, client, mock_api_key
):
    burst1 = [text_delta("first"), trace("t1"), finish("stop")]
    burst2 = [text_delta("second"), trace("t2"), finish("stop")]
    turn3 = [text_delta("manual again"), trace("t3"), finish("stop")]
    fake = FakeUpstreamClient(
        [
            FakeUpstreamResponse(chunks=burst1),
            FakeUpstreamResponse(chunks=burst2),
            FakeUpstreamResponse(chunks=turn3),
        ]
    )
    seeded = _seeded_interactive(supervisor, "t1")
    with patch.object(httpx, "AsyncClient", return_value=fake):
        session_id = (
            await client.post(
                "/api/conversations",
                json={
                    "session_id": seeded.session_id,
                    "enable_tool_call_id": "tc_enable",
                },
            )
        ).json()["session_id"]
        await _wait_idle(supervisor, session_id)

        # Idle re-arm: the message seeds a fresh burst (side-note framing is
        # for MID-burst drains only — the re-arm message rides unframed).
        r = await client.post(
            f"/api/conversations/{session_id}/messages", json={"content": "do more"}
        )
        assert r.status_code == 202
        await _wait_idle(supervisor, session_id)

        assert fake.bodies[1]["messages"] == [{"role": "user", "content": "do more"}]
        assert fake.bodies[1]["auto_mode"] is True

        # Stop clears the flag AND swaps the record back to its interactive
        # life: the next send runs a plain gated turn, no auto_mode.
        await supervisor.stop(session_id)
        record = supervisor.get(session_id)
        assert record.kind == "interactive" and record.auto_flag is False
        r = await client.post(
            f"/api/conversations/{session_id}/messages",
            json={"content": "keep going manually"},
        )
        assert r.status_code == 202
        await _wait_idle(supervisor, session_id)

    assert fake.bodies[2]["messages"] == [
        {"role": "user", "content": "keep going manually"}
    ]
    assert "auto_mode" not in fake.bodies[2]
    assert fake.bodies[2]["trace_id"] == "t2"


async def test_stop_auto_conversation_clears_flag(supervisor, client, mock_api_key):
    auto = supervisor.create_conversation(
        "auto", upstream_url="https://example.test", headers={}
    )
    r = await client.post(f"/api/conversations/{auto.session_id}/stop")
    assert r.status_code == 202
    assert auto.auto_flag is False
    assert auto.idle_reason == "user_stopped"
    # Idempotent (202 always).
    assert (
        await client.post(f"/api/conversations/{auto.session_id}/stop")
    ).status_code == 202


@pytest.mark.parametrize(
    "path,method",
    [
        ("/api/conversations", "POST"),
        ("/api/conversations/{session_id}/auto", "POST"),
        ("/api/conversations/{session_id}/stop", "POST"),
        ("/api/conversations/{session_id}/messages", "POST"),
        ("/api/conversations/{session_id}/approvals/decisions", "POST"),
    ],
)
def test_mutating_conversation_endpoints_have_no_write_lock(app, path, method):
    # Mutating endpoints must be @no_write_lock so GitSyncMiddleware doesn't
    # break SSE disconnect cancellation.
    for route in app.routes:
        if getattr(route, "path", None) == path and method in getattr(
            route, "methods", set()
        ):
            assert getattr(route.endpoint, "_git_sync_no_write_lock", False), (
                f"{method} {path} must be @no_write_lock"
            )
            return
    raise AssertionError(f"{method} {path} route not found")


# ── Interactive create/adopt + approvals endpoints ───────────────────────────


async def test_create_interactive_creates_and_adopts(supervisor, client, mock_api_key):
    # kind="interactive": create-or-adopt keyed by the browser's opaque
    # conversation key (session id / root id / legacy leaf — never a trace the
    # browser tracked itself), idempotent.
    r = await client.post("/api/conversations", json={"kind": "interactive"})
    assert r.status_code == 200
    fresh_sid = r.json()["session_id"]
    assert supervisor.get(fresh_sid).kind == "interactive"
    assert supervisor.get(fresh_sid).state == RunState.IDLE

    # A cold upstream-shaped key is adopted VERBATIM as the resume key (no
    # desktop-side key→leaf resolution — the record's first turn continues by
    # session_id and the backend resolves the leaf).
    r = await client.post(
        "/api/conversations", json={"kind": "interactive", "session_id": "leaf-9"}
    )
    adopted_sid = r.json()["session_id"]
    assert supervisor.get(adopted_sid).resume_session_key == "leaf-9"
    assert supervisor.get(adopted_sid).current_leaf_trace_id is None
    # Idempotent: the same key returns the SAME conversation — including its
    # own session id (the live handle the browser normally sends).
    r = await client.post(
        "/api/conversations", json={"kind": "interactive", "session_id": "leaf-9"}
    )
    assert r.json()["session_id"] == adopted_sid
    r = await client.post(
        "/api/conversations", json={"kind": "interactive", "session_id": adopted_sid}
    )
    assert r.json()["session_id"] == adopted_sid


async def test_create_interactive_by_root_key_and_dead_cv_key(
    supervisor, client, mock_api_key
):
    # A COLD root key (history row after a desktop restart) is adopted
    # VERBATIM as the record's resume key (the backend resolves either id
    # kind on the first session_id continuation). The key is deliberately NOT
    # stamped into root_id: roots and legacy leaves are indistinguishable
    # desktop-side, and root_id must stay the TRUE durable handle (it is
    # backfilled from the rehydration fetch / first persist instead).
    root_key = "1234567890_root-42"
    r = await client.post(
        "/api/conversations",
        json={"kind": "interactive", "session_id": root_key},
    )
    assert r.status_code == 200
    record = supervisor.get(r.json()["session_id"])
    assert record.resume_session_key == root_key
    assert record.current_leaf_trace_id is None
    assert record.root_id is None

    # A dead cv_ key (the record died with a restart, no durable fallback):
    # a fresh EMPTY record (a cv_ id is desktop-minted and never a valid
    # upstream id, so there is nothing else it could mean).
    r = await client.post(
        "/api/conversations", json={"kind": "interactive", "session_id": "cv_dead"}
    )
    assert r.status_code == 200
    fresh = supervisor.get(r.json()["session_id"])
    assert fresh.current_leaf_trace_id is None
    assert fresh.resume_session_key is None
    assert fresh.root_id is None


async def test_create_interactive_resume_turn_continues_by_session_id(
    supervisor, client, mock_api_key
):
    # The resume flow end-to-end: adopt by cold key, first send →
    # the upstream body carries session_id=<key> (the backend resolves the
    # current leaf); after the turn persists, the engine holds the real leaf
    # and the NEXT send continues by trace_id — the normal in-process flow.
    root_key = "1234567890_root-77"
    r = await client.post(
        "/api/conversations",
        json={"kind": "interactive", "session_id": root_key},
    )
    sid = r.json()["session_id"]

    fake = FakeUpstreamClient(
        [
            FakeUpstreamResponse(
                chunks=[text_delta("resumed"), trace("leaf-77b"), finish("stop")]
            ),
            FakeUpstreamResponse(
                chunks=[text_delta("again"), trace("leaf-77c"), finish("stop")]
            ),
        ]
    )
    with patch.object(httpx, "AsyncClient", return_value=fake):
        r = await client.post(
            f"/api/conversations/{sid}/messages", json={"content": "hello again"}
        )
        assert r.status_code == 202
        await _wait_idle(supervisor, sid)
        r = await client.post(
            f"/api/conversations/{sid}/messages", json={"content": "and more"}
        )
        assert r.status_code == 202
        await _wait_idle(supervisor, sid)

    first, second = fake.bodies
    assert first["session_id"] == root_key
    assert "trace_id" not in first
    assert second["trace_id"] == "leaf-77b"
    assert "session_id" not in second
    # The engine never mistakes a continuation leaf for the durable root of
    # an adopted (mid-chain) conversation.
    record = supervisor.get(sid)
    assert record.current_leaf_trace_id == "leaf-77c"
    assert record.root_id is None


def _stage_runless_batch(supervisor, session_id: str):
    """Stage a rehydrated-shape (runless) batch on an idle conversation."""
    from kiln_ai.adapters.model_adapters.stream_events import ToolInputAvailableEvent

    from app.desktop.studio_server.chat.runtime.models import PendingApprovalBatch

    conv = supervisor._conversations[session_id]
    events = [
        ToolInputAvailableEvent(
            toolCallId="tc_open",
            toolName="add",
            input={"a": 2, "b": 3},
            kiln_metadata={"requires_approval": True},
        )
    ]
    batch = PendingApprovalBatch(
        items=[_pending_item_from_event(e) for e in events],
        body={"trace_id": "leaf-1", "messages": []},
        assistant_text="",
        tool_input_events=events,
    )
    conv.pending_batch = batch
    conv.record.state = RunState.AWAITING_APPROVAL
    return batch


async def test_approvals_get_and_decide_flow(supervisor, client, mock_api_key):
    record = await supervisor.adopt_interactive(
        "leaf-1", upstream_url="https://example.test", headers={}
    )
    # Nothing pending (and nothing rehydratable — the autouse fixture returns
    # no persisted tail) → 404.
    r = await client.get(f"/api/conversations/{record.session_id}/approvals")
    assert r.status_code == 404
    r = await client.get("/api/conversations/cv_missing/approvals")
    assert r.status_code == 404

    batch = _stage_runless_batch(supervisor, record.session_id)
    r = await client.get(f"/api/conversations/{record.session_id}/approvals")
    assert r.status_code == 200
    assert r.json()["batch_id"] == batch.batch_id
    # Items keep the exact tool-calls-pending wire shape.
    assert r.json()["items"] == [
        {
            "toolCallId": "tc_open",
            "toolName": "add",
            "input": {"a": 2, "b": 3},
            "requiresApproval": True,
        }
    ]

    # Wrong batch id → 404 (validated), before any decision lands.
    r = await client.post(
        f"/api/conversations/{record.session_id}/approvals/decisions",
        json={"batch_id": "ab_wrong", "decisions": {"tc_open": True}},
    )
    assert r.status_code == 404

    continuation = [text_delta("sum is 5"), trace("t2"), finish("stop")]
    fake = FakeUpstreamClient([FakeUpstreamResponse(chunks=continuation)])
    with patch.object(httpx, "AsyncClient", return_value=fake):
        r = await client.post(
            f"/api/conversations/{record.session_id}/approvals/decisions",
            json={"batch_id": batch.batch_id, "decisions": {"tc_open": True}},
        )
        assert r.status_code == 202
        # Two tabs deciding the same batch: first wins, second gets 409
        # (functional spec §5).
        r = await client.post(
            f"/api/conversations/{record.session_id}/approvals/decisions",
            json={"batch_id": batch.batch_id, "decisions": {"tc_open": False}},
        )
        assert r.status_code == 409
        await _wait_idle(supervisor, record.session_id)

    # The resume run POSTed a role:tool continuation.
    (body,) = fake.bodies
    assert body["trace_id"] == "leaf-1"
    assert body["messages"][0]["role"] == "tool"
    assert body["messages"][0]["tool_call_id"] == "tc_open"


async def test_approvals_get_rehydrates_from_trace_tail(
    supervisor, client, mock_api_key
):
    # GET /approvals attempts trace-tail rehydration when nothing is in
    # memory — the graceful-stop / desktop-restart recovery entry (functional
    # spec §5).
    record = await supervisor.adopt_interactive(
        "leaf-1", upstream_url="https://example.test", headers={}
    )
    tail = [
        {"role": "user", "content": "please add"},
        {
            "role": "assistant",
            "content": "need approval",
            "tool_calls": [
                {
                    "id": "tc_open",
                    "type": "function",
                    "function": {"name": "add", "arguments": '{"a": 2, "b": 3}'},
                }
            ],
        },
    ]
    with patch.object(
        ConversationSupervisor, "_fetch_persisted_trace", return_value=tail
    ):
        r = await client.get(f"/api/conversations/{record.session_id}/approvals")
    assert r.status_code == 200
    assert r.json()["items"][0]["toolCallId"] == "tc_open"
    # Rebuilt calls are conservatively gated (metadata not persisted).
    assert r.json()["items"][0]["requiresApproval"] is True
    assert record.state == RunState.AWAITING_APPROVAL
