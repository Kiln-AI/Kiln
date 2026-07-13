"""AutoChatRunner unit tests against a fake upstream."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from .models import AutoChatSeed, AutoRunStatus, InboundMessage
from app.desktop.studio_server.chat.stream_session import MAX_CHAT_RETRIES

from .runner import (
    MAX_TOOL_ROUNDS_MESSAGE,
    AutoChatRunner,
    _side_note_message,
)
from .test_fakes import (
    FakeUpstreamClient,
    FakeUpstreamResponse,
    finish,
    finish_tool_calls,
    text_delta,
    tool_input_available,
    trace,
)

SERVER_META = {"executor": "server"}


def _runner(
    client: FakeUpstreamClient,
    seed: AutoChatSeed | None = None,
    inbound: list | None = None,
):
    emitted: list[bytes] = []
    traces: list[str] = []

    async def on_trace(tid: str) -> None:
        traces.append(tid)

    # Mirror AutoChatRun.drain_inbound: atomically take and clear the queue.
    queue = inbound if inbound is not None else []

    def drain_inbound():
        nonlocal queue
        taken = queue
        queue = []
        return taken

    runner = AutoChatRunner(
        run_id="ar_test",
        seed=seed or AutoChatSeed(trace_id="tr-0", enable_tool_call_id="enable-1"),
        upstream_url="https://example.test/v1/chat",
        headers={},
        emit=emitted.append,
        on_trace=on_trace,
        drain_inbound=drain_inbound,
    )
    return runner, emitted, traces


def _decoded(emitted: list[bytes]) -> str:
    return b"".join(emitted).decode()


def _events(emitted: list[bytes]) -> list[dict]:
    events: list[dict] = []
    for line in _decoded(emitted).split("\n"):
        if line.startswith("data: "):
            payload = line[6:].strip()
            if payload and payload != "[DONE]":
                events.append(json.loads(payload))
    return events


@pytest.mark.asyncio
async def test_text_only_round_settles_idle():
    # Revision R1: a plain text turn (no tool calls) settles the burst to IDLE —
    # the conversation flag stays on, the runner does not go terminal.
    round1 = [text_delta("All done"), trace("tr-1"), finish("stop")]
    client = FakeUpstreamClient([FakeUpstreamResponse(chunks=round1)])
    runner, emitted, traces = _runner(client)

    with patch.object(httpx, "AsyncClient", return_value=client):
        await runner.run()

    assert runner.status == AutoRunStatus.IDLE
    decoded = _decoded(emitted)
    assert '"type": "auto-mode-on"' in decoded
    assert "All done" in decoded
    assert traces == ["tr-1"]


@pytest.mark.asyncio
async def test_server_tool_only_round_finishes_done():
    # When a finish=tool-calls round contains only server-executed tools, the
    # app server has nothing to execute (execute_tool_batch([]) → {}) and the
    # run ends DONE that round — same as the interactive path.
    round1 = [
        tool_input_available("s1", "server_tool", {}, kiln_metadata=SERVER_META),
        trace("tr-1"),
        finish_tool_calls(),
    ]
    client = FakeUpstreamClient([FakeUpstreamResponse(chunks=round1)])
    runner, emitted, _ = _runner(client)

    with patch.object(httpx, "AsyncClient", return_value=client):
        await runner.run()

    assert runner.status == AutoRunStatus.IDLE
    decoded = _decoded(emitted)
    # exec start/end with zero client tools, no pending approval prompt.
    assert '"tool_count": 0' in decoded
    assert '"type": "tool-calls-pending"' not in decoded


@pytest.mark.asyncio
async def test_multi_round_auto_executes_client_tool():
    round1 = [
        text_delta("computing"),
        tool_input_available("tc1", "add", {"a": 10, "b": 5}),
        trace("tr-1"),
        finish_tool_calls(),
    ]
    round2 = [text_delta("Result is 15"), trace("tr-2"), finish("stop")]
    client = FakeUpstreamClient(
        [FakeUpstreamResponse(chunks=round1), FakeUpstreamResponse(chunks=round2)]
    )
    runner, emitted, _ = _runner(client)

    with patch.object(httpx, "AsyncClient", return_value=client):
        await runner.run()

    assert runner.status == AutoRunStatus.IDLE
    decoded = _decoded(emitted)
    assert '"type": "kiln-tool-execution-start"' in decoded
    assert '"output": "15"' in decoded
    assert '"type": "kiln-tool-execution-end"' in decoded
    # Continuation carried trace + tool result, no approval prompt.
    assert '"type": "tool-calls-pending"' not in decoded
    assert client.bodies[1]["trace_id"] == "tr-1"


@pytest.mark.asyncio
async def test_no_trace_seed_first_round_posts_message_and_gets_trace():
    # Revision R2: a no-trace seed (brand-new conversation) POSTs the first user
    # message with NO trace_id; the backend mints the first trace on that round,
    # which on_trace records. The first turn thus runs in auto mode from the start.
    chunks = [text_delta("On it"), trace("tr-new-1"), finish("stop")]
    client = FakeUpstreamClient([FakeUpstreamResponse(chunks=chunks)])
    seed = AutoChatSeed(
        trace_id=None,
        extra_messages=[{"role": "user", "content": "do the thing"}],
    )
    runner, _, traces = _runner(client, seed)

    with patch.object(httpx, "AsyncClient", return_value=client):
        await runner.run()

    assert runner.status == AutoRunStatus.IDLE
    # The opening POST carried the user message and NO trace_id (fresh conv).
    assert "trace_id" not in client.bodies[0]
    assert client.bodies[0]["messages"] == [{"role": "user", "content": "do the thing"}]
    # The backend minted the first trace, surfaced to on_trace.
    assert traces == ["tr-new-1"]


@pytest.mark.asyncio
async def test_finish_with_text_only_is_asked_user():
    chunks = [text_delta("What should I do next?"), trace("tr-1"), finish("stop")]
    client = FakeUpstreamClient([FakeUpstreamResponse(chunks=chunks)])
    runner, emitted, _ = _runner(client)

    with patch.object(httpx, "AsyncClient", return_value=client):
        await runner.run()

    assert runner.status == AutoRunStatus.IDLE
    assert runner.idle_reason == "asked_user"


@pytest.mark.asyncio
async def test_auto_approve_executes_tool_requiring_approval_with_no_pending_event():
    # A client tool that *would* require approval interactively runs unattended
    # in auto mode — no tool-calls-pending event is ever emitted.
    round1 = [
        tool_input_available(
            "tc1",
            "multiply",
            {"a": 6, "b": 7},
            kiln_metadata={"requires_approval": True},
        ),
        trace("tr-1"),
        finish_tool_calls(),
    ]
    round2 = [text_delta("42"), trace("tr-2"), finish("stop")]
    client = FakeUpstreamClient(
        [FakeUpstreamResponse(chunks=round1), FakeUpstreamResponse(chunks=round2)]
    )
    runner, emitted, _ = _runner(client)

    with patch.object(httpx, "AsyncClient", return_value=client):
        await runner.run()

    decoded = _decoded(emitted)
    assert '"type": "tool-calls-pending"' not in decoded
    assert '"output": "42"' in decoded
    assert runner.status == AutoRunStatus.IDLE


@pytest.mark.asyncio
async def test_max_rounds_backstop_emits_error():
    # A client tool that keeps producing continuations never finishes → the
    # runner exhausts MAX_TOOL_ROUNDS and hits the backstop. (A server-only tool
    # batch yields no results and would return DONE instead.)
    def looping_round(i: int):
        return FakeUpstreamResponse(
            chunks=[
                tool_input_available(f"tc{i}", "add", {"a": 1, "b": 1}),
                trace(f"tr-{i}"),
                finish_tool_calls(),
            ]
        )

    from app.desktop.studio_server.chat.constants import MAX_TOOL_ROUNDS

    client = FakeUpstreamClient([looping_round(i) for i in range(MAX_TOOL_ROUNDS)])
    runner, emitted, _ = _runner(client)

    with patch.object(httpx, "AsyncClient", return_value=client):
        await runner.run()

    # Revision R1: the backstop ends the burst but the flag stays on (IDLE,
    # reason "max_rounds").
    assert runner.status == AutoRunStatus.IDLE
    assert runner.idle_reason == "max_rounds"
    assert MAX_TOOL_ROUNDS_MESSAGE in _decoded(emitted)


@pytest.mark.asyncio
async def test_non_retryable_upstream_error_sets_error_status_without_retry():
    # A 4xx (here 400) is non-retryable: the burst ends immediately, flag stays on
    # (IDLE, reason "error"), and no retry is attempted.
    client = FakeUpstreamClient(
        [FakeUpstreamResponse(status_code=400, body=b'{"message": "boom"}')]
    )
    runner, emitted, _ = _runner(client)

    with patch.object(httpx, "AsyncClient", return_value=client):
        await runner.run()

    assert runner.status == AutoRunStatus.IDLE
    assert runner.idle_reason == "error"
    assert "boom" in _decoded(emitted)
    # No retry attempted for a non-retryable status, and only one upstream request.
    assert '"type": "kiln-chat-retry"' not in _decoded(emitted)
    assert len(client.bodies) == 1


@pytest.mark.asyncio
async def test_retryable_upstream_error_retries_then_succeeds():
    # Two transient 503s, then a normal round. The runner retries with backoff,
    # emits a retry event per attempt, recovers, and never surfaces the error.
    round_ok = [text_delta("done"), trace("tr-1"), finish("stop")]
    client = FakeUpstreamClient(
        [
            FakeUpstreamResponse(status_code=503, body=b'{"message": "rate limited"}'),
            FakeUpstreamResponse(status_code=503, body=b'{"message": "rate limited"}'),
            FakeUpstreamResponse(chunks=round_ok),
        ]
    )
    runner, emitted, _ = _runner(client)

    with (
        patch.object(httpx, "AsyncClient", return_value=client),
        patch(
            "app.desktop.studio_server.chat.stream_session.asyncio.sleep",
            new_callable=AsyncMock,
        ) as sleep_mock,
    ):
        await runner.run()

    # Parse structurally: a retry event per failed attempt, numbered 1, 2.
    retry_events = [e for e in _events(emitted) if e["type"] == "kiln-chat-retry"]
    assert [e["attempt"] for e in retry_events] == [1, 2]
    assert all(e["max_attempts"] == MAX_CHAT_RETRIES for e in retry_events)
    assert all(e["status_code"] == 503 for e in retry_events)
    # Backoff actually ran between attempts (not a tight spin).
    assert sleep_mock.await_count == 2
    # Recovered: the transient error was never surfaced; the burst settled on the
    # successful round (text-only → asked_user).
    assert "rate limited" not in _decoded(emitted)
    assert runner.idle_reason == "asked_user"
    assert len(client.bodies) == 3


@pytest.mark.asyncio
async def test_retryable_upstream_error_exhausts_retries_then_idle_error():
    client = FakeUpstreamClient(
        [
            FakeUpstreamResponse(status_code=500, body=b'{"message": "boom"}')
            for _ in range(MAX_CHAT_RETRIES + 1)
        ]
    )
    runner, emitted, _ = _runner(client)

    with (
        patch.object(httpx, "AsyncClient", return_value=client),
        patch(
            "app.desktop.studio_server.chat.stream_session.asyncio.sleep",
            new=AsyncMock(),
        ),
    ):
        await runner.run()

    decoded = _decoded(emitted)
    # One retry event per attempt up to the cap, then give up.
    assert decoded.count('"type": "kiln-chat-retry"') == MAX_CHAT_RETRIES
    # On give-up the held-back error is finally surfaced.
    assert "boom" in decoded
    assert runner.status == AutoRunStatus.IDLE
    assert runner.idle_reason == "error"
    assert len(client.bodies) == MAX_CHAT_RETRIES + 1


@pytest.mark.asyncio
async def test_connection_error_retries_then_succeeds():
    # A pre-response connection failure (no status code) is retried just like a
    # transient 5xx, as long as nothing was streamed.
    round_ok = [text_delta("done"), trace("tr-1"), finish("stop")]
    client = FakeUpstreamClient(
        [
            FakeUpstreamResponse(raise_connect_error=True),
            FakeUpstreamResponse(chunks=round_ok),
        ]
    )
    runner, emitted, _ = _runner(client)

    with (
        patch.object(httpx, "AsyncClient", return_value=client),
        patch(
            "app.desktop.studio_server.chat.stream_session.asyncio.sleep",
            new=AsyncMock(),
        ),
    ):
        await runner.run()

    decoded = _decoded(emitted)
    assert decoded.count('"type": "kiln-chat-retry"') == 1
    assert runner.idle_reason == "asked_user"
    assert len(client.bodies) == 2


@pytest.mark.asyncio
async def test_mid_stream_transport_error_after_content_is_not_retried():
    # The central anti-duplication guard: a transport failure that strikes AFTER
    # bytes were already forwarded must NOT be retried (a re-POST would duplicate
    # the streamed output). Here a text delta streams, then the stream drops with
    # a non-RemoteProtocolError transport error.
    client = FakeUpstreamClient(
        [
            FakeUpstreamResponse(
                chunks=[text_delta("partial answer")],
                raise_transport_error_after_chunks=True,
            ),
            # A second response is queued to prove it is never requested.
            FakeUpstreamResponse(
                chunks=[text_delta("dupe"), trace("tr-x"), finish("stop")]
            ),
        ]
    )
    runner, emitted, _ = _runner(client)

    with (
        patch.object(httpx, "AsyncClient", return_value=client),
        patch(
            "app.desktop.studio_server.chat.stream_session.asyncio.sleep",
            new_callable=AsyncMock,
        ) as sleep_mock,
    ):
        await runner.run()

    decoded = _decoded(emitted)
    # No retry, no backoff, exactly one upstream request — the guard held.
    assert '"type": "kiln-chat-retry"' not in decoded
    assert sleep_mock.await_count == 0
    assert len(client.bodies) == 1
    # The already-streamed content appears exactly once (never duplicated).
    assert decoded.count("partial answer") == 1
    assert "dupe" not in decoded
    # A single generic error is surfaced and the burst settles IDLE("error").
    assert runner.status == AutoRunStatus.IDLE
    assert runner.idle_reason == "error"


@pytest.mark.asyncio
async def test_stop_requested_during_retry_settles_user_stopped():
    # Stop pressed *while actively retrying* a persistent transient failure must
    # honor the graceful-stop contract: settle USER_STOPPED (so the supervisor
    # publishes auto-mode-off), not IDLE("error") with the flag left on.
    client = FakeUpstreamClient(
        [
            FakeUpstreamResponse(status_code=503, body=b'{"message": "rate limited"}'),
            FakeUpstreamResponse(status_code=503, body=b'{"message": "rate limited"}'),
        ]
    )
    runner, emitted, _ = _runner(client)

    # Request Stop from inside the backoff sleep, so one retry has already been
    # emitted and the run is genuinely mid-retry when the stop lands — exercising
    # the in-retry transition (not the pre-run stop path).
    async def _stop_mid_backoff(*args, **kwargs):
        runner.stop_requested = True

    with (
        patch.object(httpx, "AsyncClient", return_value=client),
        patch(
            "app.desktop.studio_server.chat.stream_session.asyncio.sleep",
            new=AsyncMock(side_effect=_stop_mid_backoff),
        ),
    ):
        await runner.run()

    decoded = _decoded(emitted)
    # It DID enter the retry branch (one retry emitted) before the stop landed,
    # then settled USER_STOPPED without surfacing the transient error.
    assert decoded.count('"type": "kiln-chat-retry"') == 1
    assert "rate limited" not in decoded
    assert runner.status == AutoRunStatus.USER_STOPPED
    # The stop landed during the backoff sleep, so the retry is abandoned BEFORE
    # re-POSTing — only the initial request was made (no extra round streamed).
    assert len(client.bodies) == 1


class TestSeedBody:
    @pytest.mark.asyncio
    async def test_enabled_seed_resolves_enable_tool_call(self):
        seed = AutoChatSeed(trace_id="tr-0", enable_tool_call_id="enable-1")
        runner, _, _ = _runner(FakeUpstreamClient([]), seed)
        body = await runner._build_seed_body()
        assert body["trace_id"] == "tr-0"
        # auto_mode rides the seed so the upstream orchestrator phrases the
        # auto-round-cap reminder for an absent user.
        assert body["auto_mode"] is True
        assert body["messages"] == [
            {
                "role": "tool",
                "tool_call_id": "enable-1",
                "content": json.dumps({"status": "enabled"}),
            }
        ]

    @pytest.mark.asyncio
    async def test_extra_messages_only_seed(self):
        seed = AutoChatSeed(
            trace_id="tr-0",
            extra_messages=[{"role": "user", "content": "go"}],
        )
        runner, _, _ = _runner(FakeUpstreamClient([]), seed)
        body = await runner._build_seed_body()
        assert body["messages"] == [{"role": "user", "content": "go"}]

    @pytest.mark.asyncio
    async def test_no_trace_seed_omits_trace_id(self):
        # Revision R2: a brand-new conversation has no trace yet, so the seed
        # carries only the first user message and the body omits trace_id (the
        # backend starts a fresh conversation and mints the first trace).
        seed = AutoChatSeed(
            trace_id=None,
            extra_messages=[{"role": "user", "content": "first message"}],
        )
        runner, _, _ = _runner(FakeUpstreamClient([]), seed)
        body = await runner._build_seed_body()
        assert "trace_id" not in body
        assert body["auto_mode"] is True
        assert body["messages"] == [{"role": "user", "content": "first message"}]

    @pytest.mark.asyncio
    async def test_pending_sibling_tool_calls_are_executed(self):
        from app.desktop.studio_server.chat.stream_session import ToolCallInfo

        seed = AutoChatSeed(
            trace_id="tr-0",
            enable_tool_call_id="enable-1",
            pending_tool_calls=[
                ToolCallInfo(
                    toolCallId="sib1",
                    toolName="add",
                    input={"a": 1, "b": 2},
                    requiresApproval=True,
                )
            ],
        )
        runner, _, _ = _runner(FakeUpstreamClient([]), seed)
        body = await runner._build_seed_body()
        # enable tool resolved + sibling executed (auto-approved → "3").
        roles = [(m["tool_call_id"], m["content"]) for m in body["messages"]]
        assert ("enable-1", json.dumps({"status": "enabled"})) in roles
        assert ("sib1", "3") in roles


def test_side_note_message_frames_content_to_continue_working():
    # A drained mid-burst message is wrapped so the model answers inline and keeps
    # working (does not stop just to reply), but the original text is preserved.
    msg = InboundMessage(content="also handle edge case Y")
    wrapped = _side_note_message(msg)
    assert wrapped["role"] == "user"
    assert "also handle edge case Y" in wrapped["content"]
    assert "<system-reminder>" in wrapped["content"]
    assert "side note" in wrapped["content"].lower()
    assert "do not end your turn just to reply" in wrapped["content"]


# ── Revision R1: message injection ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_injected_message_appended_to_continuation():
    # A message queued while a tool round is in flight is drained at the next
    # round boundary and appended (role:"user") to the continuation body — the
    # backend sees the tool result AND the new user input on the next turn.
    inbound = [InboundMessage(content="also do X")]
    round1 = [
        tool_input_available("tc1", "add", {"a": 1, "b": 1}),
        trace("tr-1"),
        finish_tool_calls(),
    ]
    round2 = [text_delta("ok"), trace("tr-2"), finish("stop")]
    client = FakeUpstreamClient(
        [FakeUpstreamResponse(chunks=round1), FakeUpstreamResponse(chunks=round2)]
    )
    runner, emitted, _ = _runner(client, inbound=inbound)

    with patch.object(httpx, "AsyncClient", return_value=client):
        await runner.run()

    # The second upstream body carries the tool result then the injected user
    # message (appended last).
    second_body = client.bodies[1]
    assert second_body["trace_id"] == "tr-1"
    # auto_mode set once on the seed propagates through every {**body} continuation.
    assert second_body["auto_mode"] is True
    user_messages = [m for m in second_body["messages"] if m.get("role") == "user"]
    # Mid-burst injected messages are framed as a side note so the model answers
    # inline and keeps working instead of halting on a text-only reply.
    assert len(user_messages) == 1
    assert "also do X" in user_messages[0]["content"]
    assert "<system-reminder>" in user_messages[0]["content"]
    # The runner does NOT echo on drain — the registry already echoed the message
    # onto the bus/buffer at enqueue time (CR Moderate 1). Double-echo would
    # render the message twice; the combined registry+runner echo-once behaviour
    # is asserted in test_registry.py.
    assert '"type": "user-message"' not in _decoded(emitted)


@pytest.mark.asyncio
async def test_drain_before_idle_continues_with_queued_message():
    # A message queued exactly as the burst would settle (a plain-text handoff
    # with no tool calls) must not be dropped — the runner continues with it as a
    # fresh user turn instead of going idle.
    inbound = [InboundMessage(content="keep going")]
    round1 = [text_delta("Anything else?"), trace("tr-1"), finish("stop")]
    round2 = [text_delta("done now"), trace("tr-2"), finish("stop")]
    client = FakeUpstreamClient(
        [FakeUpstreamResponse(chunks=round1), FakeUpstreamResponse(chunks=round2)]
    )
    runner, emitted, _ = _runner(client, inbound=inbound)

    with patch.object(httpx, "AsyncClient", return_value=client):
        await runner.run()

    # It did NOT stop after round1 — a second upstream round ran, seeded with the
    # queued user message as a fresh turn.
    assert len(client.bodies) == 2
    assert len(client.bodies[1]["messages"]) == 1
    queued_msg = client.bodies[1]["messages"][0]
    assert queued_msg["role"] == "user"
    assert "keep going" in queued_msg["content"]
    assert "<system-reminder>" in queued_msg["content"]
    # Eventually settled IDLE once the queue was empty.
    assert runner.status == AutoRunStatus.IDLE


@pytest.mark.asyncio
async def test_no_queued_message_settles_idle():
    # Control: with an empty queue, a plain-text handoff settles IDLE (one round).
    round1 = [text_delta("Anything else?"), trace("tr-1"), finish("stop")]
    client = FakeUpstreamClient([FakeUpstreamResponse(chunks=round1)])
    runner, _, _ = _runner(client, inbound=[])

    with patch.object(httpx, "AsyncClient", return_value=client):
        await runner.run()

    assert runner.status == AutoRunStatus.IDLE
    assert len(client.bodies) == 1


# ── Revision R1: disable_auto_mode interception ───────────────────────────────


@pytest.mark.asyncio
async def test_disable_auto_mode_intercepted_not_executed():
    # The model calls disable_auto_mode mid-burst → the runner intercepts it
    # (never executes), records USER_DISABLED, resolves the call as disabled, and
    # ends the burst.
    round1 = [
        text_delta("turning off auto mode"),
        tool_input_available("tc_disable", "disable_auto_mode", input={}),
        trace("tr-1"),
        finish_tool_calls(),
    ]
    # The runner resolves the disable call back to the backend (CR Moderate 3),
    # so a final continuation round runs and the backend persists a clean
    # snapshot (no dangling tool call).
    round2 = [text_delta("okay, auto mode off"), trace("tr-2"), finish("stop")]
    client = FakeUpstreamClient(
        [FakeUpstreamResponse(chunks=round1), FakeUpstreamResponse(chunks=round2)]
    )
    runner, emitted, _ = _runner(client)

    with patch(
        "app.desktop.studio_server.chat.stream_session.execute_tool"
    ) as execute_tool_mock:
        with patch.object(httpx, "AsyncClient", return_value=client):
            await runner.run()

    assert runner.status == AutoRunStatus.USER_DISABLED
    # Never executed as a tool.
    execute_tool_mock.assert_not_called()
    # The disabled result is resolved onto the stream (as a tool-output event
    # whose JSON-string output is {"status":"disabled"}).
    outputs = [
        json.loads(e["output"])
        for e in _events(emitted)
        if e.get("type") == "tool-output-available"
    ]
    assert {"status": "disabled"} in outputs


@pytest.mark.asyncio
async def test_disable_auto_mode_resolves_tool_result_to_backend():
    # CR Moderate 3: the intercepted disable_auto_mode call must be resolved back
    # to the backend so the persisted trace has no dangling tool call. Assert a
    # second (continuation) upstream body is sent carrying the disable
    # tool_call_id resolved as {"status":"disabled"}.
    round1 = [
        text_delta("turning off auto mode"),
        tool_input_available("tc_disable", "disable_auto_mode", input={}),
        trace("tr-1"),
        finish_tool_calls(),
    ]
    round2 = [text_delta("okay, auto mode off"), trace("tr-2"), finish("stop")]
    client = FakeUpstreamClient(
        [FakeUpstreamResponse(chunks=round1), FakeUpstreamResponse(chunks=round2)]
    )
    runner, _, traces = _runner(client)

    with patch.object(httpx, "AsyncClient", return_value=client):
        await runner.run()

    # A continuation was sent to the backend (two upstream bodies).
    assert len(client.bodies) == 2
    continuation = client.bodies[1]
    # It continues from the trace the disable turn was persisted on.
    assert continuation["trace_id"] == "tr-1"
    # It resolves the disable tool call as {"status":"disabled"}.
    disable_tool_msgs = [
        m
        for m in continuation["messages"]
        if m.get("role") == "tool" and m.get("tool_call_id") == "tc_disable"
    ]
    assert len(disable_tool_msgs) == 1
    assert json.loads(disable_tool_msgs[0]["content"]) == {"status": "disabled"}
    # The trace from the clean snapshot is observed/indexed.
    assert runner.disable_trace_id == "tr-2"
    assert "tr-2" in traces


# ── enable_auto_mode no-op while already on ──────────────────────────────────


@pytest.mark.asyncio
async def test_enable_auto_mode_while_on_resolves_already_enabled_and_continues():
    # The model calls enable_auto_mode while auto mode is already on. It's a
    # signal, never executed — the runner resolves it as "already enabled" (NOT
    # an "Unknown tool name" error) and the burst continues normally.
    round1 = [
        text_delta("enabling auto mode"),
        tool_input_available("tc_enable", "enable_auto_mode", input={}),
        trace("tr-1"),
        finish_tool_calls(),
    ]
    round2 = [text_delta("carrying on"), trace("tr-2"), finish("stop")]
    client = FakeUpstreamClient(
        [FakeUpstreamResponse(chunks=round1), FakeUpstreamResponse(chunks=round2)]
    )
    runner, emitted, _ = _runner(client)

    with patch(
        "app.desktop.studio_server.chat.stream_session.execute_tool"
    ) as execute_tool_mock:
        with patch.object(httpx, "AsyncClient", return_value=client):
            await runner.run()

    # Burst continues — not disabled, not errored.
    assert runner.status == AutoRunStatus.IDLE
    # Never executed as a tool (no "Unknown tool name" path).
    execute_tool_mock.assert_not_called()
    # The enable call is resolved as already-enabled on the stream.
    outputs = [
        json.loads(e["output"])
        for e in _events(emitted)
        if e.get("type") == "tool-output-available"
    ]
    assert {"status": "enabled", "detail": "Auto mode is already enabled."} in outputs
    # A continuation was sent to the backend resolving the enable tool_call_id, so
    # the persisted trace has no dangling tool call.
    assert len(client.bodies) == 2
    enable_tool_msgs = [
        m
        for m in client.bodies[1]["messages"]
        if m.get("role") == "tool" and m.get("tool_call_id") == "tc_enable"
    ]
    assert len(enable_tool_msgs) == 1
    assert json.loads(enable_tool_msgs[0]["content"]) == {
        "status": "enabled",
        "detail": "Auto mode is already enabled.",
    }


@pytest.mark.asyncio
async def test_enable_auto_mode_resolved_alongside_executable_sibling():
    # Defensive: if enable_auto_mode arrives with a sibling tool call, the sibling
    # still executes (auto-approved) and the enable call resolves as a no-op.
    round1 = [
        text_delta("enabling and computing"),
        tool_input_available("tc_enable", "enable_auto_mode", input={}),
        tool_input_available("tc_add", "add", {"a": 2, "b": 3}),
        trace("tr-1"),
        finish_tool_calls(),
    ]
    round2 = [text_delta("done"), trace("tr-2"), finish("stop")]
    client = FakeUpstreamClient(
        [FakeUpstreamResponse(chunks=round1), FakeUpstreamResponse(chunks=round2)]
    )
    runner, emitted, _ = _runner(client)

    with patch.object(httpx, "AsyncClient", return_value=client):
        await runner.run()

    assert runner.status == AutoRunStatus.IDLE
    raw_outputs = [
        e["output"]
        for e in _events(emitted)
        if e.get("type") == "tool-output-available"
    ]
    # The sibling executed (add → "5") and the enable call resolved as a no-op.
    assert "5" in raw_outputs
    assert (
        json.dumps(
            {"status": "enabled", "detail": "Auto mode is already enabled."},
            ensure_ascii=False,
        )
        in raw_outputs
    )


# ── Graceful stop (functional spec §4.4(1)) ──────────────────────────────────


@pytest.mark.asyncio
async def test_graceful_stop_surfaces_tool_calls_for_approval_not_executed():
    # The in-flight round finishes streaming (no cut-off); then at the round
    # boundary, because stop was requested, the round's client tool calls are
    # surfaced via tool-calls-pending for normal approval instead of being
    # auto-executed. The burst ends USER_STOPPED and no continuation is sent.
    round1 = [
        text_delta("on it"),
        tool_input_available("tc1", "add", {"a": 1, "b": 2}),
        trace("tr-1"),
        finish_tool_calls(),
    ]
    client = FakeUpstreamClient([FakeUpstreamResponse(chunks=round1)])
    runner, emitted, _ = _runner(client)
    runner.stop_requested = True

    with patch.object(httpx, "AsyncClient", return_value=client):
        await runner.run()

    assert runner.status == AutoRunStatus.USER_STOPPED
    decoded = _decoded(emitted)
    # The current turn's output was delivered (not cut off).
    assert "on it" in decoded
    # The tool calls were surfaced for approval, NOT auto-executed.
    assert '"type": "tool-calls-pending"' in decoded
    assert '"output": "3"' not in decoded
    assert '"type": "kiln-tool-execution-start"' not in decoded
    # No second upstream round was started.
    assert len(client.bodies) == 1


@pytest.mark.asyncio
async def test_graceful_stop_plain_text_final_round_just_disables():
    # A plain-text final round on graceful stop: finish what was streamed, then
    # disable — nothing to approve, no tool-calls-pending.
    round1 = [text_delta("Here is the summary."), trace("tr-1"), finish("stop")]
    client = FakeUpstreamClient([FakeUpstreamResponse(chunks=round1)])
    runner, emitted, _ = _runner(client)
    runner.stop_requested = True

    with patch.object(httpx, "AsyncClient", return_value=client):
        await runner.run()

    assert runner.status == AutoRunStatus.USER_STOPPED
    decoded = _decoded(emitted)
    assert "Here is the summary." in decoded
    assert '"type": "tool-calls-pending"' not in decoded
    assert len(client.bodies) == 1


@pytest.mark.asyncio
async def test_graceful_stop_drops_queued_inbound_on_plain_text():
    # Stop must not start a new burst: a queued inbound message is dropped (we do
    # NOT continue with it) when stop is requested on a plain-text boundary.
    inbound = [InboundMessage(content="keep going")]
    round1 = [text_delta("Anything else?"), trace("tr-1"), finish("stop")]
    client = FakeUpstreamClient([FakeUpstreamResponse(chunks=round1)])
    runner, _, _ = _runner(client, inbound=inbound)
    runner.stop_requested = True

    with patch.object(httpx, "AsyncClient", return_value=client):
        await runner.run()

    assert runner.status == AutoRunStatus.USER_STOPPED
    # No second round despite the queued message.
    assert len(client.bodies) == 1
