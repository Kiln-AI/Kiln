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
# stream_session resolves the singleton lazily off the registry module (to break
# a circular import), so the disable-interception path reads it from here.
_MODULE_REGISTRY = "app.desktop.studio_server.chat.auto.registry.auto_chat_registry"
_KEEPALIVE = "app.desktop.studio_server.chat.auto.api.KEEPALIVE_SECONDS"


@pytest.fixture
def registry(monkeypatch):
    """Fresh registry patched over the singleton the endpoints + routes use."""
    reg = AutoChatRegistry()
    monkeypatch.setattr(_API_REGISTRY, reg)
    monkeypatch.setattr(_ROUTES_REGISTRY, reg)
    monkeypatch.setattr(_MODULE_REGISTRY, reg)
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


class _GatedResponse:
    """One round that streams a trace, blocks until released, then a plain-text
    finish — lets a test observe a RUNNING burst before it settles."""

    def __init__(self, release: asyncio.Event) -> None:
        self.status_code = 200
        self._release = release

    async def aread(self) -> bytes:
        return b""

    async def aiter_bytes(self):
        yield trace("t1")
        await self._release.wait()
        yield text_delta("settled")
        yield finish("stop")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class _GatedClient:
    def __init__(self, release: asyncio.Event) -> None:
        self._release = release
        self.bodies: list = []

    def stream(self, method, url, *, content, headers):
        self.bodies.append(json.loads(content.decode()))
        return _GatedResponse(self._release)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


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


async def _wait_settled(
    registry: AutoChatRegistry, run_id: str, timeout: float = 3.0
) -> None:
    """Wait until a burst settles — the run leaves RUNNING (→ IDLE or off)."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        run = registry.get(run_id)
        if run is None or run.record.status != AutoRunStatus.RUNNING:
            return
        await asyncio.sleep(0.01)
    run = registry.get(run_id)
    actual = run.record.status if run else "missing"
    raise AssertionError(f"Auto run {run_id} did not settle; was {actual}")


# Back-compat alias: legacy tests wait for the burst to settle (IDLE under R1).
_wait_terminal = _wait_settled


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


@pytest.mark.asyncio
async def test_stop_clears_flag_with_user_stopped(client, registry, mock_api_key):
    # /stop is graceful (functional spec §4.4(1)): it returns 202 promptly and
    # sets a stop intent WITHOUT cutting off the in-flight round. The flag clears
    # (USER_STOPPED) + auto-mode-off(user_stopped) is published only once the
    # current round finishes.
    release = asyncio.Event()
    gated = _GatedClient(release)
    with patch.object(httpx, "AsyncClient", return_value=gated):
        run_id = (
            await client.post(
                "/api/chat/auto/enable",
                json={"trace_id": "t1", "enable_tool_call_id": "tc_enable"},
            )
        ).json()["run_id"]
        await asyncio.sleep(0.05)
        run = registry.get(run_id)
        received: list[bytes] = []

        async def _drain():
            async for b in run.bus.subscribe():
                received.append(b)

        drain_task = asyncio.create_task(_drain())
        await asyncio.sleep(0.02)
        r = await client.post(f"/api/chat/auto/{run_id}/stop")
        assert r.status_code == 202
        # Not cut off: still RUNNING until the in-flight round finishes.
        await asyncio.sleep(0.02)
        assert run.record.status == AutoRunStatus.RUNNING
        # Let the round finish; the burst now winds down to off.
        release.set()
        await _wait_terminal(registry, run_id)
        await asyncio.sleep(0.02)
        drain_task.cancel()

    assert run.record.status == AutoRunStatus.USER_STOPPED
    decoded = b"".join(received).decode()
    assert '"type": "auto-mode-off"' in decoded
    assert '"reason": "user_stopped"' in decoded


# ── events ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_events_404_unknown_run(client, registry, mock_api_key):
    r = await client.get("/api/chat/auto/ar_unknown/events")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_idle_run_not_evicted_and_remains_attachable(
    client, registry, mock_api_key
):
    # Revision R1: a settled burst goes IDLE (flag on) and the entry is NOT
    # evicted — the run stays registered (so /events can re-attach, 404 only once
    # GC'd). The idle-vs-off marker the bus emits on subscribe is unit-tested at
    # the registry level; the infinite idle SSE stream is not exercised over
    # ASGITransport (it never terminates).
    round1 = [text_delta("hello from auto"), trace("t1"), finish("stop")]
    fake = FakeUpstreamClient([FakeUpstreamResponse(chunks=round1)])

    with patch.object(httpx, "AsyncClient", return_value=fake):
        run_id = (
            await client.post(
                "/api/chat/auto/enable",
                json={"trace_id": "t1", "enable_tool_call_id": "tc_enable"},
            )
        ).json()["run_id"]
        await _wait_settled(registry, run_id)

    run = registry.get(run_id)
    assert run is not None
    assert run.record.status == AutoRunStatus.IDLE
    # Still active for the session-list join (green dot persists while idle).
    active, rid = registry.is_active_for_trace("t1")
    assert active and rid == run_id


@pytest.mark.asyncio
async def test_events_streams_off_marker_after_stop(
    client, registry, mock_api_key, fast_keepalive
):
    # An explicitly stopped run is off (terminal) — a late attach gets exactly
    # the off marker and the stream ends.
    round1 = [text_delta("hello from auto"), trace("t1"), finish("stop")]
    fake = FakeUpstreamClient([FakeUpstreamResponse(chunks=round1)])

    with patch.object(httpx, "AsyncClient", return_value=fake):
        run_id = (
            await client.post(
                "/api/chat/auto/enable",
                json={"trace_id": "t1", "enable_tool_call_id": "tc_enable"},
            )
        ).json()["run_id"]
        await _wait_settled(registry, run_id)
        await client.post(f"/api/chat/auto/{run_id}/stop")

        r = await client.get(f"/api/chat/auto/{run_id}/events")

    assert r.status_code == 200
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


@pytest.mark.asyncio
async def test_resolve_active_returns_run_and_current_trace(
    client, registry, mock_api_key
):
    """A live run resolves its seed (stale) leaf to {run_id, current_trace_id}."""
    release = asyncio.Event()
    upstream = _GatedClient(release)
    with patch.object(httpx, "AsyncClient", return_value=upstream):
        enable = await client.post(
            "/api/chat/auto/enable",
            json={"trace_id": "t1", "enable_tool_call_id": "tc_enable"},
        )
        assert enable.status_code == 200
        run_id = enable.json()["run_id"]

        r = await client.get("/api/chat/auto/resolve", params={"trace_id": "t1"})
        assert r.status_code == 200
        assert r.json() == {"run_id": run_id, "current_trace_id": "t1"}

        release.set()
        await _wait_settled(registry, run_id)


@pytest.mark.asyncio
async def test_resolve_stale_trace_in_chain_returns_current_leaf(
    client, registry, mock_api_key
):
    """The seed leaf is stale after the run advances; resolve still matches it via
    the whole-chain index and returns the run's CURRENT leaf (so the hard-refresh
    client hydrates the rounds it missed)."""
    round1 = [trace("t2"), text_delta("hi"), finish("stop")]
    upstream = FakeUpstreamClient([FakeUpstreamResponse(chunks=round1)])
    with patch.object(httpx, "AsyncClient", return_value=upstream):
        enable = await client.post(
            "/api/chat/auto/enable",
            json={"trace_id": "t1", "enable_tool_call_id": "tc_enable"},
        )
        run_id = enable.json()["run_id"]
        await _wait_settled(registry, run_id)

        # Stale seed leaf t1 resolves to the run, current leaf is now t2.
        r = await client.get("/api/chat/auto/resolve", params={"trace_id": "t1"})
        assert r.status_code == 200
        assert r.json() == {"run_id": run_id, "current_trace_id": "t2"}


@pytest.mark.asyncio
async def test_resolve_unknown_trace_returns_404(client, registry, mock_api_key):
    r = await client.get("/api/chat/auto/resolve", params={"trace_id": "never-seen"})
    assert r.status_code == HTTPStatus.NOT_FOUND


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


# ── disable_auto_mode interception (interactive /api/chat) ────────────────────


@pytest.mark.asyncio
async def test_disable_auto_mode_intercepted_and_continues_interactively(
    client, registry, mock_api_key
):
    # The model calls disable_auto_mode on the interactive stream → it is
    # intercepted (never executed), the conversation flag is cleared with
    # auto-mode-off(user_disabled), the call is resolved {"status":"disabled"},
    # and the stream continues interactively (a second upstream round runs).
    round1 = [
        trace("t1"),
        text_delta("turning auto mode off"),
        tool_input_available("tc_disable", "disable_auto_mode", input={}),
        finish_tool_calls(),
    ]
    round2 = [text_delta("back to interactive"), finish("stop")]
    fake = FakeUpstreamClient(
        [FakeUpstreamResponse(chunks=round1), FakeUpstreamResponse(chunks=round2)]
    )

    # Seed a live IDLE run indexed under t1 so disable_for_trace has a flag to
    # clear and an observer bus to publish auto-mode-off onto.
    record = AutoRunRecord(
        run_id="ar_live",
        status=AutoRunStatus.IDLE,
        current_trace_id="t1",
        seen_trace_ids=["t1"],
    )
    real_run = _make_idle_run(record)
    registry._runs["ar_live"] = real_run
    registry._trace_index["t1"] = "ar_live"

    execute_tool_mock = AsyncMock()
    with patch.object(httpx, "AsyncClient", return_value=fake):
        with patch(
            "app.desktop.studio_server.chat.stream_session.execute_tool",
            execute_tool_mock,
        ):
            r = await client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "stop auto mode"}]},
            )

    assert r.status_code == 200
    events = _parse_sse_events(r.content)
    # disable_auto_mode is never executed.
    execute_tool_mock.assert_not_called()
    # The flag was cleared on the live run.
    assert real_run.record.status == AutoRunStatus.USER_DISABLED
    # The interactive stream resolved the call as disabled (tool-output event).
    disabled_outputs = [
        json.loads(e["output"])
        for e in events
        if e.get("type") == "tool-output-available"
        and e.get("toolCallId") == "tc_disable"
    ]
    assert disabled_outputs == [{"status": "disabled"}]
    # ...and continued interactively.
    assert any(
        e.get("type") == "text-delta" and e.get("delta") == "back to interactive"
        for e in events
    )
    # Two upstream rounds: the continuation carried the resolved tool result.
    assert len(fake.bodies) == 2
    continuation_msgs = fake.bodies[1]["messages"]
    disabled = [
        m
        for m in continuation_msgs
        if m.get("role") == "tool" and m.get("tool_call_id") == "tc_disable"
    ]
    assert disabled and json.loads(disabled[0]["content"]) == {"status": "disabled"}


@pytest.mark.asyncio
async def test_disable_auto_mode_interactive_sibling_requiring_approval_is_denied(
    client, registry, mock_api_key
):
    # CR Mild: on the INTERACTIVE disable path, a sibling bundled in the same turn
    # as disable_auto_mode must go through the normal approval gate, NOT be
    # auto-approved. A sibling that requires approval (with no decision available
    # on this path) is therefore denied — its tool execution never runs and the
    # resolved result is DENIED_TOOL_OUTPUT. (Auto-approval is the runner's job.)
    from app.desktop.studio_server.chat.constants import DENIED_TOOL_OUTPUT

    round1 = [
        trace("t1"),
        tool_input_available("tc_disable", "disable_auto_mode", input={}),
        tool_input_available(
            "tc_sibling",
            "call_kiln_api",
            input={"x": 1},
            kiln_metadata={"requires_approval": True},
        ),
        finish_tool_calls(),
    ]
    round2 = [text_delta("back to interactive"), finish("stop")]
    fake = FakeUpstreamClient(
        [FakeUpstreamResponse(chunks=round1), FakeUpstreamResponse(chunks=round2)]
    )

    record = AutoRunRecord(
        run_id="ar_live",
        status=AutoRunStatus.IDLE,
        current_trace_id="t1",
        seen_trace_ids=["t1"],
    )
    real_run = _make_idle_run(record)
    registry._runs["ar_live"] = real_run
    registry._trace_index["t1"] = "ar_live"

    execute_tool_mock = AsyncMock()
    with patch.object(httpx, "AsyncClient", return_value=fake):
        with patch(
            "app.desktop.studio_server.chat.stream_session.execute_tool",
            execute_tool_mock,
        ):
            r = await client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "stop auto mode"}]},
            )

    assert r.status_code == 200
    events = _parse_sse_events(r.content)
    # The approval-gated sibling was NOT executed (denied, not auto-approved).
    execute_tool_mock.assert_not_called()
    sibling_outputs = [
        e["output"]
        for e in events
        if e.get("type") == "tool-output-available"
        and e.get("toolCallId") == "tc_sibling"
    ]
    assert sibling_outputs == [DENIED_TOOL_OUTPUT]
    # The disable call itself is still resolved as disabled.
    disabled_outputs = [
        json.loads(e["output"])
        for e in events
        if e.get("type") == "tool-output-available"
        and e.get("toolCallId") == "tc_disable"
    ]
    assert disabled_outputs == [{"status": "disabled"}]


def _make_idle_run(record: AutoRunRecord):
    """Build a real AutoChatRun (with bus + buffer) parked at IDLE for the
    disable-interception test, without a supervising task."""
    from app.desktop.studio_server.chat.auto.models import AutoChatSeed
    from app.desktop.studio_server.chat.auto.registry import AutoChatRun

    return AutoChatRun(
        record=record,
        seed=AutoChatSeed(trace_id=record.current_trace_id),
        upstream_url="https://example.test/v1/chat",
        headers={},
        on_trace=None,
    )


# ── message injection endpoint (Revision R1) ──────────────────────────────────


@pytest.mark.asyncio
async def test_message_endpoint_404_when_unknown(client, registry, mock_api_key):
    r = await client.post("/api/chat/auto/ar_unknown/message", json={"content": "hi"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_message_endpoint_starts_new_burst_when_idle(
    client, registry, mock_api_key
):
    burst1 = [text_delta("first"), trace("t1"), finish("stop")]
    burst2 = [text_delta("second"), trace("t2"), finish("stop")]
    fake = FakeUpstreamClient(
        [FakeUpstreamResponse(chunks=burst1), FakeUpstreamResponse(chunks=burst2)]
    )
    with patch.object(httpx, "AsyncClient", return_value=fake):
        run_id = (
            await client.post(
                "/api/chat/auto/enable",
                json={"trace_id": "t1", "enable_tool_call_id": "tc_enable"},
            )
        ).json()["run_id"]
        await _wait_settled(registry, run_id)
        assert registry.get(run_id).record.status == AutoRunStatus.IDLE

        r = await client.post(
            f"/api/chat/auto/{run_id}/message",
            json={"content": "do more", "trace_id": "t1"},
        )
        assert r.status_code == 202
        await _wait_settled(registry, run_id)

    # The second upstream body was seeded with the injected user message.
    assert fake.bodies[1]["messages"] == [{"role": "user", "content": "do more"}]


@pytest.mark.asyncio
async def test_message_endpoint_enqueues_into_active_burst(
    client, registry, mock_api_key
):
    # While a burst is RUNNING, /message enqueues the user message (drained by
    # the runner at the next round boundary) and echoes it onto the bus — it does
    # NOT start a new burst. Deterministic via a gated client that holds the
    # first round open.
    release = asyncio.Event()
    gated = _GatedClient(release)
    with patch.object(httpx, "AsyncClient", return_value=gated):
        run_id = (
            await client.post(
                "/api/chat/auto/enable",
                json={"trace_id": "t1", "enable_tool_call_id": "tc_enable"},
            )
        ).json()["run_id"]
        await asyncio.sleep(0.05)  # let the burst reach RUNNING
        assert registry.get(run_id).record.status == AutoRunStatus.RUNNING

        r = await client.post(
            f"/api/chat/auto/{run_id}/message",
            json={"content": "inject"},
        )
        assert r.status_code == 202

        run = registry.get(run_id)
        # Queued for drain at the next boundary; echoed for observers.
        assert [m.content for m in run.inbound] == ["inject"]
        assert b"inject" in b"".join(run.buffer)

        release.set()
        await _wait_settled(registry, run_id)


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
        ("/api/chat/auto/{run_id}/message", "POST"),
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
