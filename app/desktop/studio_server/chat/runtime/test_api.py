"""/api/conversations surface tests (FastAPI app over ASGI, no network).

Port of the old ``chat/subagents/test_api.py`` (deleted in phase 2) PLUS the
old ``chat/auto/test_api.py`` endpoint suite (deleted in phase 3) onto the
unified endpoints: same behaviors, unified vocabulary (session ids, RunState
strings, ``conversation-state`` events). Engines are patched to hang where
lifecycle is driven through the supervisor; the auto flows run against the
shared fake upstream."""

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
# app wiring resolves (see the note in chat/test_orchestration.py).
from app.desktop.studio_server.chat.runtime import api as conversations_api_module
from app.desktop.studio_server.chat.runtime.api import connect_conversations_api
from app.desktop.studio_server.chat.runtime.engine import ConversationEngine
from app.desktop.studio_server.chat.runtime.models import RunState, SubAgentSeed
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
    # instance (the phase-2/3 parent_index singleton died with the old loop).
    monkeypatch.setattr(conversations_api_module, "conversation_supervisor", sup)
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
    # The auto endpoints build upstream headers via get_copilot_api_key (the
    # old auto/test_api.py fixture, verbatim).
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


def _spawn(supervisor: ConversationSupervisor, parent_key: str = "trace:leaf-1"):
    return supervisor.spawn_subagent(
        SubAgentSeed(
            agent_type="general",
            name="helper",
            prompt="Briefing.",
            parent_trace_id="leaf-1",
        ),
        parent_session_id=parent_key,
        upstream_url="https://example.test",
        headers={},
    )


async def test_list_and_get(supervisor, hang_engine, client):
    # The parent is a real interactive supervisor record since phase 4; its
    # leaf resolves through the whole-chain trace index (the old
    # ParentConversationIndex alias chain died with the old loop).
    parent = await supervisor.adopt_interactive(
        "leaf-1", upstream_url="https://example.test", headers={}
    )
    record = _spawn(supervisor, parent_key=parent.session_id)

    r = await client.get("/api/conversations")
    assert r.status_code == 200
    assert {item["session_id"] for item in r.json()} == {
        parent.session_id,
        record.session_id,
    }

    # The browser's parent handle is the (possibly stale) leaf trace id until
    # phase 5 — it resolves to the parent's children.
    r = await client.get("/api/conversations", params={"parent": "leaf-1"})
    assert [item["session_id"] for item in r.json()] == [record.session_id]

    # The parent session id works directly too (the phase-5 shape).
    r = await client.get("/api/conversations", params={"parent": parent.session_id})
    assert [item["session_id"] for item in r.json()] == [record.session_id]

    r = await client.get("/api/conversations", params={"parent": "other-leaf"})
    assert r.json() == []

    r = await client.get(f"/api/conversations/{record.session_id}")
    assert r.status_code == 200
    assert r.json()["state"] == "running"
    assert r.json()["name"] == "helper"
    assert r.json()["kind"] == "subagent"

    r = await client.get("/api/conversations/cv_missing")
    assert r.status_code == 404
    await supervisor.stop(record.session_id)


async def test_get_include_report(supervisor, hang_engine, client):
    record = _spawn(supervisor)
    await supervisor.stop(record.session_id)
    r = await client.get(
        f"/api/conversations/{record.session_id}",
        params={"include_report": "true"},
    )
    body = r.json()
    assert body["state"] == "stopped"
    # The stopped run's report is synthesized with a status note (old
    # _final_report_for behavior, now the supervisor's settle path).
    assert "STOPPED" in body["final_report"]
    # Without include_report the report stays out of the payload.
    r = await client.get(f"/api/conversations/{record.session_id}")
    assert "final_report" not in r.json()


async def test_stop_endpoint_idempotent(supervisor, hang_engine, client):
    record = _spawn(supervisor)
    r = await client.post(f"/api/conversations/{record.session_id}/stop")
    assert r.status_code == 202
    assert supervisor.get(record.session_id).state == RunState.STOPPED
    # Idempotent, including unknown ids.
    assert (
        await client.post(f"/api/conversations/{record.session_id}/stop")
    ).status_code == 202
    assert (await client.post("/api/conversations/cv_missing/stop")).status_code == 202


async def test_messages_endpoint(supervisor, hang_engine, client):
    record = _spawn(supervisor)
    r = await client.post(
        f"/api/conversations/{record.session_id}/messages",
        json={"content": "also check model B"},
    )
    assert r.status_code == 202
    # Phase 4: the accepted message's stable id rides the 202 body so the
    # sending tab can dedupe its own echo.
    conv = supervisor._conversations[record.session_id]
    assert [m.content for m in conv.inbox] == ["also check model B"]
    assert r.json()["message_id"] == conv.inbox[0].id

    await supervisor.stop(record.session_id)
    r = await client.post(
        f"/api/conversations/{record.session_id}/messages",
        json={"content": "too late"},
    )
    assert r.status_code == 409

    r = await client.post(
        "/api/conversations/cv_missing/messages", json={"content": "x"}
    )
    assert r.status_code == 404


async def test_observer_events_replay_and_terminal(supervisor, hang_engine, client):
    record = _spawn(supervisor)
    await supervisor.stop(record.session_id)

    # A late observer of a terminal run gets the conversation-state marker
    # and EOF (the old status-marker contract, unified vocabulary).
    async with client.stream(
        "GET", f"/api/conversations/{record.session_id}/events"
    ) as response:
        assert response.status_code == 200
        collected = b""
        async for chunk in response.aiter_bytes():
            collected += chunk
            if b'"stopped"' in collected:
                break
    assert b"conversation-state" in collected
    payloads = [
        json.loads(line[6:])
        for line in collected.decode().split("\n")
        if line.startswith("data: ")
    ]
    states = [p for p in payloads if p.get("type") == "conversation-state"]
    assert states and states[-1]["session_id"] == record.session_id
    assert states[-1]["state"] == "stopped"
    assert states[-1]["kind"] == "subagent"
    assert states[-1]["report_available"] is True

    r = await client.get("/api/conversations/cv_missing/events")
    assert r.status_code == 404


async def test_state_firehose_snapshot_then_live(supervisor, hang_engine):
    # The firehose opens with one conversation-state event per known record
    # (the old status firehose's snapshot contract) before going live.
    #
    # Exercised on the route's stream GENERATOR, not over ASGITransport: the
    # firehose never ends by design, and httpx's ASGI transport drives the app
    # to completion (no client-disconnect signal), so an HTTP-level test would
    # hang forever — the exact reason the old API suites only ever streamed
    # TERMINAL runs. The route wrapper adds nothing beyond this generator.
    record = _spawn(supervisor)
    stream = conversations_api_module._state_firehose_stream()
    try:
        snapshot = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
        assert b"conversation-state" in snapshot
        assert record.session_id.encode() in snapshot
        assert b'"running"' in snapshot

        # Live tail: a state change publishes to attached firehose observers.
        stop_task = asyncio.create_task(supervisor.stop(record.session_id))
        live = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
        await stop_task
        assert record.session_id.encode() in live
        assert b'"stopped"' in live
    finally:
        await stream.aclose()


# ── Auto-mode surface (port of the old chat/auto/test_api.py endpoint suite) ──


async def test_create_auto_starts_burst_and_returns_session_id(
    supervisor, client, mock_api_key
):
    round1 = [text_delta("on it"), trace("t1"), finish("stop")]
    fake = FakeUpstreamClient([FakeUpstreamResponse(chunks=round1)])

    with patch.object(httpx, "AsyncClient", return_value=fake):
        r = await client.post(
            "/api/conversations",
            json={
                "trace_id": "t1",
                "enable_tool_call_id": "tc_enable",
                "reason": "running the eval",
            },
        )
        assert r.status_code == 200
        session_id = r.json()["session_id"]
        assert session_id.startswith("cv_")
        assert supervisor.get(session_id) is not None
        await _wait_idle(supervisor, session_id)

    # The seed body resolved the enable call as enabled and continued from the
    # caller's trace with the auto_mode flag (old enable seed contract, also
    # pinned by the auto_seed_and_tool_round golden fixture).
    seed_body = fake.bodies[0]
    assert seed_body["trace_id"] == "t1"
    assert seed_body["auto_mode"] is True
    assert seed_body["messages"][0]["tool_call_id"] == "tc_enable"
    assert json.loads(seed_body["messages"][0]["content"]) == {"status": "enabled"}
    record = supervisor.get(session_id)
    assert record.kind == "auto" and record.auto_flag is True


async def test_list_children_of_auto_parent_by_stale_leaf(
    supervisor, client, mock_api_key
):
    # CRITICAL regression guard (the pre-refactor "invisible tabs" bug
    # shape): the browser's REAL parent handle is the main transcript's
    # (possibly stale) leaf trace id — chat.svelte calls
    # syncForConversation(currentLeafTraceId). An auto parent's children are
    # keyed by its SESSION id, so ?parent=<leaf> must resolve through the
    # supervisor's whole-chain trace index (the old auto:<run_id> alias
    # chain that bridged this died with chat/auto/).
    round1 = [trace("t2"), text_delta("hi"), finish("stop")]
    fake = FakeUpstreamClient([FakeUpstreamResponse(chunks=round1)])
    with patch.object(httpx, "AsyncClient", return_value=fake):
        session_id = (
            await client.post(
                "/api/conversations",
                json={"trace_id": "t1", "enable_tool_call_id": "tc_enable"},
            )
        ).json()["session_id"]
        await _wait_idle(supervisor, session_id)

    child = supervisor.create_conversation(
        "subagent",
        upstream_url="https://example.test",
        headers={},
        parent_session_id=session_id,
        seed=SubAgentSeed(
            agent_type="general",
            name="helper",
            prompt="Briefing.",
            parent_trace_id="t2",
        ),
    )

    # Every handle the browser can hold resolves to the same children list:
    # the seed leaf (stale after the burst advanced to t2), the current
    # leaf, and the session id itself (the phase-4/5 shape).
    for handle in ("t1", "t2", session_id):
        r = await client.get("/api/conversations", params={"parent": handle})
        assert [i["session_id"] for i in r.json()] == [child.session_id], handle

    # A child's own leaf is never a parent handle (children can't have
    # children — the resolver's kind guard), and unknown traces yield the
    # correct empty list.
    supervisor._trace_index["child-leaf"] = child.session_id
    r = await client.get("/api/conversations", params={"parent": "child-leaf"})
    assert r.json() == []
    r = await client.get("/api/conversations", params={"parent": "never-seen"})
    assert r.json() == []


async def test_create_auto_cap_returns_429(supervisor, client, mock_api_key):
    supervisor._auto_max_concurrent = 0  # cap reached: any enable is rejected
    r = await client.post(
        "/api/conversations",
        json={"trace_id": "t1", "enable_tool_call_id": "tc_enable"},
    )
    assert r.status_code == 429
    assert "concurrent" in r.json()["message"].lower()


async def test_create_auto_armed_only_never_posts_upstream(
    supervisor, client, mock_api_key
):
    # Manual enable (ARMED-only): the record is created IDLE("armed") with NO
    # upstream POST — the old is_armed_only branch (an empty POST would be
    # rejected by the backend).
    fake = FakeUpstreamClient([])  # any POST would blow up the fake
    with patch.object(httpx, "AsyncClient", return_value=fake):
        r = await client.post("/api/conversations", json={"trace_id": "t1"})
    assert r.status_code == 200
    record = supervisor.get(r.json()["session_id"])
    assert record.state == RunState.IDLE
    assert record.idle_reason == "armed"
    assert record.auto_flag is True
    assert fake.bodies == []


async def test_decline_via_sid_auto_streams_on_observer(
    supervisor, client, mock_api_key
):
    # The old /api/chat/auto/decline, folded into POST /{sid}/auto
    # (enabled=false + decline ctx): the enable call resolves as declined +
    # denied siblings via an interactive turn on the SAME conversation, whose
    # reply streams on the observer channel instead of the request response.
    record = await supervisor.adopt_interactive(
        "t1", upstream_url="https://example.test", headers={}
    )
    continuation = [text_delta("continuing interactively"), trace("t2"), finish("stop")]
    fake = FakeUpstreamClient([FakeUpstreamResponse(chunks=continuation)])

    with patch.object(httpx, "AsyncClient", return_value=fake):
        r = await client.post(
            f"/api/conversations/{record.session_id}/auto",
            json={
                "enabled": False,
                "decline": {
                    "enable_tool_call_id": "tc_enable",
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

    # Byte-for-byte the old decline continuation body.
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
        json={"enabled": False, "decline": {"enable_tool_call_id": "tc"}},
    )
    assert r.status_code == 404


async def test_set_auto_flag_endpoint(supervisor, hang_engine, client, mock_api_key):
    auto = supervisor.create_conversation(
        "auto", upstream_url="https://example.test", headers={}
    )
    child = _spawn(supervisor)

    # Disable: today's semantics (flag off, reason user_disabled) + the
    # phase-4 swap back to the interactive life.
    r = await client.post(
        f"/api/conversations/{auto.session_id}/auto", json={"enabled": False}
    )
    assert r.status_code == 202
    assert auto.auto_flag is False and auto.idle_reason == "user_disabled"
    assert auto.kind == "interactive"

    # Re-enable: the true policy flip (interactive records ARE flippable in
    # phase 4) — ARMED-only re-arm.
    r = await client.post(
        f"/api/conversations/{auto.session_id}/auto", json={"enabled": True}
    )
    assert r.status_code == 202
    assert auto.auto_flag is True and auto.idle_reason == "armed"
    assert auto.kind == "auto"

    # Unknown → 404; sub-agent records are never flippable → 409.
    r = await client.post("/api/conversations/cv_missing/auto", json={"enabled": True})
    assert r.status_code == 404
    r = await client.post(
        f"/api/conversations/{child.session_id}/auto", json={"enabled": True}
    )
    assert r.status_code == 409
    await supervisor.stop(child.session_id)


async def test_resolve_matches_stale_leaf(supervisor, client, mock_api_key):
    # The stored leaf is stale after the run advances; resolve matches it via
    # the whole-chain index and returns the CURRENT leaf + state so the
    # hard-refresh client hydrates the rounds it missed (old
    # /api/chat/auto/resolve contract, session-id vocabulary).
    round1 = [trace("t2"), text_delta("hi"), finish("stop")]
    fake = FakeUpstreamClient([FakeUpstreamResponse(chunks=round1)])
    with patch.object(httpx, "AsyncClient", return_value=fake):
        session_id = (
            await client.post(
                "/api/conversations",
                json={"trace_id": "t1", "enable_tool_call_id": "tc_enable"},
            )
        ).json()["session_id"]
        await _wait_idle(supervisor, session_id)

        r = await client.get("/api/conversations/resolve", params={"trace_id": "t1"})
        assert r.status_code == 200
        assert r.json() == {
            "session_id": session_id,
            "current_trace_id": "t2",
            "state": "idle",
            "auto_flag": True,
        }

    r = await client.get(
        "/api/conversations/resolve", params={"trace_id": "never-seen"}
    )
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
    with patch.object(httpx, "AsyncClient", return_value=fake):
        session_id = (
            await client.post(
                "/api/conversations",
                json={"trace_id": "t1", "enable_tool_call_id": "tc_enable"},
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
        # life (phase 4 — the old "no longer active" 409 refusal is lifted by
        # construction): the next send runs a plain gated turn, no auto_mode.
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
    # Idempotent (old 202-always contract).
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
    # Same pin the old auto API suite kept: mutating endpoints must be
    # @no_write_lock so GitSyncMiddleware doesn't break SSE disconnect
    # cancellation.
    for route in app.routes:
        if getattr(route, "path", None) == path and method in getattr(
            route, "methods", set()
        ):
            assert getattr(route.endpoint, "_git_sync_no_write_lock", False), (
                f"{method} {path} must be @no_write_lock"
            )
            return
    raise AssertionError(f"{method} {path} route not found")


# ── Phase 4: interactive create/adopt + approvals endpoints ───────────────────


async def test_create_interactive_creates_and_adopts(supervisor, client, mock_api_key):
    # kind="interactive" replaces the old POST /api/chat conversation model:
    # create-or-adopt keyed by trace id, idempotent.
    r = await client.post("/api/conversations", json={"kind": "interactive"})
    assert r.status_code == 200
    fresh_sid = r.json()["session_id"]
    assert supervisor.get(fresh_sid).kind == "interactive"
    assert supervisor.get(fresh_sid).state == RunState.IDLE

    r = await client.post(
        "/api/conversations", json={"kind": "interactive", "trace_id": "leaf-9"}
    )
    adopted_sid = r.json()["session_id"]
    assert supervisor.get(adopted_sid).current_leaf_trace_id == "leaf-9"
    # Idempotent: the same trace returns the SAME conversation.
    r = await client.post(
        "/api/conversations", json={"kind": "interactive", "trace_id": "leaf-9"}
    )
    assert r.json()["session_id"] == adopted_sid


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

    # The resume run POSTed the old execute-tools continuation shape.
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
