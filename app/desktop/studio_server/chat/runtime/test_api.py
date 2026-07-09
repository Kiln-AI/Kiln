"""/api/conversations surface tests (FastAPI app over ASGI, no network).

Port of the old ``chat/subagents/test_api.py`` (deleted in phase 2) onto the
unified endpoints: same behaviors, unified vocabulary (session ids, RunState
strings, ``conversation-state`` events). Engines are patched to hang;
lifecycle is driven through the supervisor."""

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
from app.desktop.studio_server.chat import orchestration as orchestration_module
from app.desktop.studio_server.chat.orchestration import ParentConversationIndex
from app.desktop.studio_server.chat.runtime import api as conversations_api_module
from app.desktop.studio_server.chat.runtime.api import connect_conversations_api
from app.desktop.studio_server.chat.runtime.engine import ConversationEngine
from app.desktop.studio_server.chat.runtime.models import RunState, SubAgentSeed
from app.desktop.studio_server.chat.runtime.supervisor import ConversationSupervisor


@pytest.fixture
def supervisor(monkeypatch):
    sup = ConversationSupervisor()
    # The API module and the parent resolver both read module-level
    # singletons; point them at the fresh instances.
    monkeypatch.setattr(conversations_api_module, "conversation_supervisor", sup)
    monkeypatch.setattr(orchestration_module, "parent_index", ParentConversationIndex())
    return sup


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
    record = _spawn(supervisor)
    # Register the alias so the parent filter resolves a leaf trace id to the
    # children's parent key (the phase-2 bridge the browser relies on).
    orchestration_module.parent_index.parent_key_for_trace("leaf-1")

    r = await client.get("/api/conversations")
    assert r.status_code == 200
    assert [item["session_id"] for item in r.json()] == [record.session_id]
    assert r.json()[0]["kind"] == "subagent"

    r = await client.get("/api/conversations", params={"parent": "leaf-1"})
    assert [item["session_id"] for item in r.json()] == [record.session_id]

    # A parent key / session id works directly too (the phase-4/5 shape).
    r = await client.get("/api/conversations", params={"parent": "trace:leaf-1"})
    assert [item["session_id"] for item in r.json()] == [record.session_id]

    r = await client.get("/api/conversations", params={"parent": "other-leaf"})
    assert r.json() == []

    r = await client.get(f"/api/conversations/{record.session_id}")
    assert r.status_code == 200
    assert r.json()["state"] == "running"
    assert r.json()["name"] == "helper"

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
    conv = supervisor._conversations[record.session_id]
    assert [m.content for m in conv.inbox] == ["also check model B"]

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
