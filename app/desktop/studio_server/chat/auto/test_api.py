"""Auto-mode API surface tests (FastAPI app over ASGI, fake upstream).

Covers the enable/decline/stop/events/sessions endpoints, the enable_auto_mode
interception on the interactive stream, and the session-list auto_active join.

No real network: the upstream httpx client the handlers/runner open is replaced
with the Phase-2 fakes. Tests run over an httpx ASGI client (not TestClient) so
the registry's background supervising tasks share the test's event loop and
progress while we await — the same pattern as jobs/test_api.py. Each test runs
against a fresh AutoChatRegistry patched over the module singleton.
"""

from __future__ import annotations

import asyncio
import json
from http import HTTPStatus
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.chat_session_list_item import (
    ChatSessionListItem as SdkChatSessionListItem,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.types import (
    Response as KilnResponse,
)
from app.desktop.studio_server.chat import connect_chat_api, connect_chat_auto_api
from app.desktop.studio_server.chat.auto.models import AutoRunRecord, AutoRunStatus
from app.desktop.studio_server.chat.auto.registry import AutoChatRegistry
from app.desktop.studio_server.chat.auto.test_fakes import (
    FakeUpstreamClient,
    FakeUpstreamResponse,
    finish,
    finish_tool_calls,
    text_delta,
    tool_input_available,
    trace,
)
from app.desktop.studio_server.chat.helpers import sse_text_delta
from fastapi import FastAPI
from kiln_server.custom_errors import connect_custom_errors

# Pytest's rootdir import can give a file two module identities (e.g. both
# ``chat.auto.api`` and ``app.desktop.studio_server.chat.auto.api``). The app is
# wired from the fully-qualified package, so patch the singletons via the
# fully-qualified dotted paths the endpoints actually resolve against.
_API_REGISTRY = "app.desktop.studio_server.chat.auto.api.auto_chat_registry"
_ROUTES_REGISTRY = "app.desktop.studio_server.chat.routes.auto_chat_registry"
_KEEPALIVE = "app.desktop.studio_server.chat.auto.api.KEEPALIVE_SECONDS"


@pytest.fixture
def registry(monkeypatch):
    """Fresh registry patched over the singleton the endpoints + routes use."""
    reg = AutoChatRegistry()
    monkeypatch.setattr(_API_REGISTRY, reg)
    monkeypatch.setattr(_ROUTES_REGISTRY, reg)
    return reg


@pytest.fixture
def fast_keepalive(monkeypatch):
    # ASGITransport batches the SSE generator's output and only flushes buffered
    # lines once the next chunk forces a flush. A short keepalive makes that
    # prompt in tests. Production keeps the 15s default.
    monkeypatch.setattr(_KEEPALIVE, 0.05)


@pytest.fixture
def app(registry):
    app = FastAPI()
    connect_custom_errors(app)
    connect_chat_api(app)
    connect_chat_auto_api(app)
    return app


@pytest_asyncio.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as http_client:
        yield http_client


@pytest.fixture
def mock_api_key():
    with patch(
        "app.desktop.studio_server.utils.copilot_utils.Config.shared"
    ) as mock_config_shared:
        mock_config = mock_config_shared.return_value
        mock_config.kiln_copilot_api_key = "test_api_key"
        yield mock_config


def _parse_sse_events(content: bytes) -> list[dict]:
    events: list[dict] = []
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


async def _wait_terminal(
    registry: AutoChatRegistry, run_id: str, timeout: float = 3.0
) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        run = registry.get(run_id)
        if run is not None and run.record.status.is_terminal:
            return
        await asyncio.sleep(0.01)
    run = registry.get(run_id)
    actual = run.record.status if run else "missing"
    raise AssertionError(
        f"Auto run {run_id} did not reach a terminal status; was {actual}"
    )


# ── enable ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enable_starts_run_returns_run_id(client, registry, mock_api_key):
    round1 = [text_delta("on it"), trace("t1"), finish("stop")]
    fake = FakeUpstreamClient([FakeUpstreamResponse(chunks=round1)])

    with patch.object(httpx, "AsyncClient", return_value=fake):
        r = await client.post(
            "/api/chat/auto/enable",
            json={
                "trace_id": "t1",
                "enable_tool_call_id": "tc_enable",
                "reason": "running the eval",
            },
        )
        assert r.status_code == 200
        run_id = r.json()["run_id"]
        assert run_id.startswith("ar_")
        assert registry.get(run_id) is not None
        await _wait_terminal(registry, run_id)

    assert registry.get(run_id).record.reason == "running the eval"


@pytest.mark.asyncio
async def test_enable_cap_returns_429(client, registry, mock_api_key):
    registry._max_concurrent = 0  # cap reached: any start is rejected
    r = await client.post(
        "/api/chat/auto/enable",
        json={"trace_id": "t1", "enable_tool_call_id": "tc_enable"},
    )
    assert r.status_code == 429
    assert "concurrent" in r.json()["message"].lower()


@pytest.mark.asyncio
async def test_enable_resolves_enable_call_in_seed_body(client, registry, mock_api_key):
    round1 = [text_delta("done"), trace("t1"), finish("stop")]
    fake = FakeUpstreamClient([FakeUpstreamResponse(chunks=round1)])

    with patch.object(httpx, "AsyncClient", return_value=fake):
        run_id = (
            await client.post(
                "/api/chat/auto/enable",
                json={"trace_id": "t1", "enable_tool_call_id": "tc_enable"},
            )
        ).json()["run_id"]
        await _wait_terminal(registry, run_id)

    seed_body = fake.bodies[0]
    assert seed_body["trace_id"] == "t1"
    assert seed_body["messages"][0]["tool_call_id"] == "tc_enable"
    assert json.loads(seed_body["messages"][0]["content"]) == {"status": "enabled"}


# ── decline ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_decline_resumes_interactive_stream(client, registry, mock_api_key):
    continuation = [sse_text_delta("continuing interactively"), finish("stop")]
    fake = FakeUpstreamClient([FakeUpstreamResponse(chunks=continuation)])

    with patch.object(httpx, "AsyncClient", return_value=fake):
        r = await client.post(
            "/api/chat/auto/decline",
            json={
                "trace_id": "t1",
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
        )

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert b"continuing interactively" in r.content

    sent_body = fake.bodies[0]
    assert sent_body["trace_id"] == "t1"
    messages = {m["tool_call_id"]: m["content"] for m in sent_body["messages"]}
    assert json.loads(messages["tc_enable"]) == {"status": "declined"}
    assert json.loads(messages["tc_sib"]) == {
        "error": "The user did not accept the toolcall"
    }


# ── stop ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stop_returns_202_and_is_idempotent(client, registry, mock_api_key):
    round1 = [text_delta("done"), trace("t1"), finish("stop")]
    fake = FakeUpstreamClient([FakeUpstreamResponse(chunks=round1)])
    with patch.object(httpx, "AsyncClient", return_value=fake):
        run_id = (
            await client.post(
                "/api/chat/auto/enable",
                json={"trace_id": "t1", "enable_tool_call_id": "tc_enable"},
            )
        ).json()["run_id"]

        stop1 = await client.post(f"/api/chat/auto/{run_id}/stop")
        assert stop1.status_code == 202
        # Stopping again (now terminal) is still a no-op 202.
        stop2 = await client.post(f"/api/chat/auto/{run_id}/stop")
        assert stop2.status_code == 202

    # Unknown id is a no-op, still 202.
    stop_unknown = await client.post("/api/chat/auto/ar_doesnotexist/stop")
    assert stop_unknown.status_code == 202


# ── events ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_events_404_unknown_run(client, registry, mock_api_key):
    r = await client.get("/api/chat/auto/ar_unknown/events")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_events_streams_terminal_off_marker(
    client, registry, mock_api_key, fast_keepalive
):
    round1 = [text_delta("hello from auto"), trace("t1"), finish("stop")]
    fake = FakeUpstreamClient([FakeUpstreamResponse(chunks=round1)])

    with patch.object(httpx, "AsyncClient", return_value=fake):
        run_id = (
            await client.post(
                "/api/chat/auto/enable",
                json={"trace_id": "t1", "enable_tool_call_id": "tc_enable"},
            )
        ).json()["run_id"]
        # Let the run finish so attaching gets the terminal marker and ends.
        await _wait_terminal(registry, run_id)

        r = await client.get(f"/api/chat/auto/{run_id}/events")

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    types = [e.get("type") for e in _parse_sse_events(r.content)]
    assert "auto-mode-off" in types


# ── sessions ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sessions_lists_active_runs(client, registry, mock_api_key):
    record = MagicMock()
    record.run_id = "ar_fixed"
    record.current_trace_id = "t1"
    record.status = AutoRunStatus.RUNNING
    record.reason = "doing work"
    with patch.object(registry, "list_active", return_value=[record]):
        r = await client.get("/api/chat/auto/sessions")

    assert r.status_code == 200
    assert r.json() == [
        {
            "run_id": "ar_fixed",
            "current_trace_id": "t1",
            "status": "running",
            "reason": "doing work",
        }
    ]


# ── interception (interactive /api/chat) ──────────────────────────────────────


@pytest.mark.asyncio
async def test_enable_auto_mode_emits_consent_required(client, registry, mock_api_key):
    chunks = [
        trace("t1"),
        text_delta("I can run this for you"),
        tool_input_available(
            "tc_enable",
            "enable_auto_mode",
            input={"reason": "run the full eval"},
        ),
        finish_tool_calls(),
    ]
    fake = FakeUpstreamClient([FakeUpstreamResponse(chunks=chunks)])
    execute_tool_mock = AsyncMock()

    with patch.object(httpx, "AsyncClient", return_value=fake):
        with patch(
            "app.desktop.studio_server.chat.stream_session.execute_tool",
            execute_tool_mock,
        ):
            r = await client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "run my eval"}]},
            )

    assert r.status_code == 200
    consent = [
        e
        for e in _parse_sse_events(r.content)
        if e.get("type") == "auto-mode-consent-required"
    ]
    assert len(consent) == 1
    assert consent[0]["enable_tool_call_id"] == "tc_enable"
    assert consent[0]["trace_id"] == "t1"
    assert consent[0]["reason"] == "run the full eval"
    assert consent[0]["sibling_tool_calls"] == []

    # enable_auto_mode is never executed and the loop returns (single round only).
    execute_tool_mock.assert_not_called()
    assert len(fake.bodies) == 1


@pytest.mark.asyncio
async def test_enable_auto_mode_carries_sibling_tool_calls(
    client, registry, mock_api_key
):
    chunks = [
        text_delta("here we go"),
        tool_input_available("tc_enable", "enable_auto_mode", input={}),
        tool_input_available(
            "tc_sib", "kiln_tool::add_numbers", input={"a": 1, "b": 2}
        ),
        finish_tool_calls(),
    ]
    fake = FakeUpstreamClient([FakeUpstreamResponse(chunks=chunks)])

    with patch.object(httpx, "AsyncClient", return_value=fake):
        r = await client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "go"}]},
        )

    assert r.status_code == 200
    consent = [
        e
        for e in _parse_sse_events(r.content)
        if e.get("type") == "auto-mode-consent-required"
    ]
    assert len(consent) == 1
    assert consent[0]["reason"] is None
    sibling_ids = {s["toolCallId"] for s in consent[0]["sibling_tool_calls"]}
    assert sibling_ids == {"tc_sib"}


# ── session-list join ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch(
    "app.desktop.studio_server.chat.routes.list_sessions_v1_chat_sessions_get.asyncio_detailed",
    new_callable=AsyncMock,
)
async def test_session_list_auto_active_join(
    mock_asyncio_detailed, client, registry, mock_api_key
):
    parsed_item = SdkChatSessionListItem.from_dict(
        {
            "id": "t1",
            "title": "Active one",
            "updated_at": "2025-06-15T12:30:00+00:00",
            "task_run": {
                "input": "",
                "output": {"output": "", "model_type": "test"},
                "model_type": "test",
            },
        }
    )
    mock_asyncio_detailed.return_value = KilnResponse(
        status_code=HTTPStatus.OK,
        content=b"[]",
        headers={"content-type": "application/json"},
        parsed=[parsed_item],
    )

    # Seed a real RUNNING run indexed under the row's leaf id ("t1") so the
    # join exercises the actual lookup path: routes.py keys is_active_for_trace
    # on item.id, which must resolve through _trace_index to the live run.
    record = AutoRunRecord(
        run_id="ar_live",
        status=AutoRunStatus.RUNNING,
        current_trace_id="t1",
        seen_trace_ids=["t1"],
    )
    registry._runs["ar_live"] = SimpleNamespace(record=record)
    registry._trace_index["t1"] = "ar_live"

    r = await client.get("/api/chat/sessions")

    assert r.status_code == 200
    body = r.json()
    assert body[0]["auto_active"] is True
    assert body[0]["auto_run_id"] == "ar_live"


# ── no_write_lock ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "path,method",
    [
        ("/api/chat/auto/enable", "POST"),
        ("/api/chat/auto/decline", "POST"),
        ("/api/chat/auto/{run_id}/stop", "POST"),
    ],
)
def test_mutating_auto_endpoints_have_no_write_lock(app, path, method):
    for route in app.routes:
        if getattr(route, "path", None) == path and method in getattr(
            route, "methods", set()
        ):
            assert getattr(route.endpoint, "_git_sync_no_write_lock", False), (
                f"{method} {path} must be @no_write_lock so GitSyncMiddleware "
                "does not break SSE disconnect cancellation"
            )
            return
    raise AssertionError(f"{method} {path} route not found")
