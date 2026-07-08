"""Sub-agents API surface tests (FastAPI app over ASGI, no network).

Runners are patched to hang; lifecycle is driven through the registry. The
fully-qualified module paths are patched (the app is wired from the
``app.desktop...`` package even when tests import relatively)."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio
from app.desktop.studio_server.chat.subagents import api as subagents_api_module
from app.desktop.studio_server.chat.subagents.api import connect_chat_subagents_api
from app.desktop.studio_server.chat.subagents.models import (
    SubAgentSeed,
    SubAgentStatus,
)
from app.desktop.studio_server.chat.subagents.registry import SubAgentRegistry
from app.desktop.studio_server.chat.subagents.runner import SubAgentRunner
from fastapi import FastAPI
from kiln_server.custom_errors import connect_custom_errors


@pytest.fixture
def registry(monkeypatch):
    reg = SubAgentRegistry()
    monkeypatch.setattr(subagents_api_module, "subagent_registry", reg)
    return reg


@pytest.fixture
def hang_runner():
    async def _hang(self) -> None:
        await asyncio.Event().wait()

    with patch.object(SubAgentRunner, "run", _hang):
        yield


@pytest.fixture
def app(registry):
    app = FastAPI()
    connect_custom_errors(app)
    connect_chat_subagents_api(app)
    return app


@pytest_asyncio.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as http_client:
        yield http_client


def _spawn(registry: SubAgentRegistry, parent_key: str = "trace:leaf-1"):
    return registry.spawn(
        SubAgentSeed(
            agent_type="general",
            name="helper",
            prompt="Briefing.",
            parent_key=parent_key,
            parent_trace_id="leaf-1",
        ),
        upstream_url="https://example.test",
        headers={},
    )


async def test_list_and_get(registry, hang_runner, client):
    record = _spawn(registry)
    # Register the alias so the parent filter resolves.
    registry.parent_key_for_trace("leaf-1")

    r = await client.get("/api/chat/subagents")
    assert r.status_code == 200
    assert [item["subagent_id"] for item in r.json()] == [record.subagent_id]

    r = await client.get(
        "/api/chat/subagents", params={"parent_trace_id": "leaf-1"}
    )
    assert [item["subagent_id"] for item in r.json()] == [record.subagent_id]

    r = await client.get(
        "/api/chat/subagents", params={"parent_trace_id": "other-leaf"}
    )
    assert r.json() == []

    r = await client.get(f"/api/chat/subagents/{record.subagent_id}")
    assert r.status_code == 200
    assert r.json()["status"] == "running"

    r = await client.get("/api/chat/subagents/sa_missing")
    assert r.status_code == 404
    await registry.stop(record.subagent_id)


async def test_get_include_report(registry, hang_runner, client):
    record = _spawn(registry)
    await registry.stop(record.subagent_id)
    r = await client.get(
        f"/api/chat/subagents/{record.subagent_id}",
        params={"include_report": "true"},
    )
    body = r.json()
    assert body["status"] == "stopped"
    assert "STOPPED" in body["final_report"]


async def test_stop_endpoint_idempotent(registry, hang_runner, client):
    record = _spawn(registry)
    r = await client.post(f"/api/chat/subagents/{record.subagent_id}/stop")
    assert r.status_code == 202
    assert registry.get(record.subagent_id).record.status == SubAgentStatus.STOPPED
    # Idempotent, including unknown ids.
    assert (
        await client.post(f"/api/chat/subagents/{record.subagent_id}/stop")
    ).status_code == 202
    assert (await client.post("/api/chat/subagents/sa_missing/stop")).status_code == 202


async def test_message_endpoint(registry, hang_runner, client):
    record = _spawn(registry)
    r = await client.post(
        f"/api/chat/subagents/{record.subagent_id}/message",
        json={"content": "also check model B"},
    )
    assert r.status_code == 202
    run = registry.get(record.subagent_id)
    assert [m.content for m in run.inbound] == ["also check model B"]

    await registry.stop(record.subagent_id)
    r = await client.post(
        f"/api/chat/subagents/{record.subagent_id}/message",
        json={"content": "too late"},
    )
    assert r.status_code == 409

    r = await client.post(
        "/api/chat/subagents/sa_missing/message", json={"content": "x"}
    )
    assert r.status_code == 404


async def test_observer_events_replay_and_terminal(registry, hang_runner, client):
    record = _spawn(registry)
    await registry.stop(record.subagent_id)

    async with client.stream(
        "GET", f"/api/chat/subagents/{record.subagent_id}/events"
    ) as response:
        assert response.status_code == 200
        collected = b""
        async for chunk in response.aiter_bytes():
            collected += chunk
            if b'"status": "stopped"' in collected or b'"stopped"' in collected:
                break
    assert b"kiln-subagent-status" in collected
