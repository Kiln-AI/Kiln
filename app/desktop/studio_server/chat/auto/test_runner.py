"""AutoChatRunner unit tests against a fake upstream."""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest

from .models import AutoChatSeed, AutoRunStatus
from .runner import MAX_TOOL_ROUNDS_MESSAGE, AutoChatRunner
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


def _runner(client: FakeUpstreamClient, seed: AutoChatSeed | None = None):
    emitted: list[bytes] = []
    traces: list[str] = []

    async def on_trace(tid: str) -> None:
        traces.append(tid)

    runner = AutoChatRunner(
        run_id="ar_test",
        seed=seed or AutoChatSeed(trace_id="tr-0", enable_tool_call_id="enable-1"),
        upstream_url="https://example.test/v1/chat",
        headers={},
        emit=emitted.append,
        on_trace=on_trace,
    )
    return runner, emitted, traces


def _decoded(emitted: list[bytes]) -> str:
    return b"".join(emitted).decode()


@pytest.mark.asyncio
async def test_text_only_round_finishes_done():
    # A plain text turn (no tool calls) finishes the run immediately as DONE.
    round1 = [text_delta("All done"), trace("tr-1"), finish("stop")]
    client = FakeUpstreamClient([FakeUpstreamResponse(chunks=round1)])
    runner, emitted, traces = _runner(client)

    with patch.object(httpx, "AsyncClient", return_value=client):
        await runner.run()

    assert runner.status == AutoRunStatus.DONE
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

    assert runner.status == AutoRunStatus.DONE
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

    assert runner.status == AutoRunStatus.DONE
    decoded = _decoded(emitted)
    assert '"type": "kiln-tool-execution-start"' in decoded
    assert '"output": "15"' in decoded
    assert '"type": "kiln-tool-execution-end"' in decoded
    # Continuation carried trace + tool result, no approval prompt.
    assert '"type": "tool-calls-pending"' not in decoded
    assert client.bodies[1]["trace_id"] == "tr-1"


@pytest.mark.asyncio
async def test_finish_with_text_only_is_asked_user():
    chunks = [text_delta("What should I do next?"), trace("tr-1"), finish("stop")]
    client = FakeUpstreamClient([FakeUpstreamResponse(chunks=chunks)])
    runner, emitted, _ = _runner(client)

    with patch.object(httpx, "AsyncClient", return_value=client):
        await runner.run()

    assert runner.status == AutoRunStatus.DONE
    assert runner.done_reason == "asked_user"


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
    assert runner.status == AutoRunStatus.DONE


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

    assert runner.status == AutoRunStatus.MAX_ROUNDS
    assert MAX_TOOL_ROUNDS_MESSAGE in _decoded(emitted)


@pytest.mark.asyncio
async def test_upstream_error_sets_error_status():
    client = FakeUpstreamClient(
        [FakeUpstreamResponse(status_code=500, body=b'{"message": "boom"}')]
    )
    runner, emitted, _ = _runner(client)

    with patch.object(httpx, "AsyncClient", return_value=client):
        await runner.run()

    assert runner.status == AutoRunStatus.ERROR
    assert "boom" in _decoded(emitted)


class TestSeedBody:
    @pytest.mark.asyncio
    async def test_enabled_seed_resolves_enable_tool_call(self):
        seed = AutoChatSeed(trace_id="tr-0", enable_tool_call_id="enable-1")
        runner, _, _ = _runner(FakeUpstreamClient([]), seed)
        body = await runner._build_seed_body()
        assert body["trace_id"] == "tr-0"
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
