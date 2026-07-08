"""SubAgentRunner unit tests against the shared fake upstream."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.desktop.studio_server.chat.auto.models import InboundMessage
from app.desktop.studio_server.chat.auto.test_fakes import (
    FakeUpstreamClient,
    FakeUpstreamResponse,
    finish,
    finish_tool_calls,
    text_delta,
    tool_input_available,
    trace,
)

from .models import SubAgentSeed, SubAgentStatus
from .runner import (
    AUTO_MODE_NOOP_RESULT,
    DEPTH_LIMIT_RESULT,
    SubAgentRunner,
)

ORCHESTRATION_NAMES = frozenset({"spawn_subagent", "stop_subagent"})


def _runner(
    client: FakeUpstreamClient,
    inbound: list[InboundMessage] | None = None,
    max_rounds: int | None = None,
):
    emitted: list[bytes] = []
    traces: list[str] = []

    async def on_trace(tid: str) -> None:
        traces.append(tid)

    queue = inbound if inbound is not None else []

    def drain_inbound():
        nonlocal queue
        taken = queue
        queue = []
        return taken

    runner = SubAgentRunner(
        subagent_id="sa_test",
        seed=SubAgentSeed(
            agent_type="general",
            name="eval-helper",
            prompt="Briefing: do the thing.",
            parent_key="trace:parent-leaf-1",
            parent_trace_id="parent-leaf-1",
        ),
        upstream_url="https://example.test/v1/chat",
        headers={},
        emit=emitted.append,
        on_trace=on_trace,
        drain_inbound=drain_inbound,
        orchestration_tool_names=ORCHESTRATION_NAMES,
        max_rounds=max_rounds,
    )
    return runner, emitted, traces


async def test_seed_body_carries_agent_block_and_kickoff():
    client = FakeUpstreamClient(
        [FakeUpstreamResponse([text_delta("done"), trace("tr-1"), finish()])]
    )
    runner, _, traces = _runner(client)
    with patch.object(httpx, "AsyncClient", return_value=client):
        await runner.run()

    body = client.bodies[0]
    assert body["agent"] == {
        "agent_type": "general",
        "seed_prompt": "Briefing: do the thing.",
        "parent_trace_id": "parent-leaf-1",
    }
    assert body["auto_mode"] is True
    assert "eval-helper" in body["messages"][0]["content"]
    assert "trace_id" not in body
    assert runner.status == SubAgentStatus.COMPLETED
    assert runner.final_report == "done"
    assert traces == ["tr-1"]


async def test_agent_block_dropped_after_first_trace():
    client = FakeUpstreamClient(
        [
            FakeUpstreamResponse(
                [
                    tool_input_available("tc-1", "call_kiln_api", {"x": 1}),
                    trace("tr-1"),
                    finish_tool_calls(),
                ]
            ),
            FakeUpstreamResponse(
                [text_delta("final report"), trace("tr-2"), finish()]
            ),
        ]
    )
    runner, _, _ = _runner(client)
    with (
        patch.object(httpx, "AsyncClient", return_value=client),
        patch(
            "app.desktop.studio_server.chat.stream_session.execute_tool",
            new=AsyncMock(return_value='{"ok": true}'),
        ),
    ):
        await runner.run()

    continuation = client.bodies[1]
    assert "agent" not in continuation
    assert continuation["trace_id"] == "tr-1"
    assert continuation["auto_mode"] is True
    # The tool result rides the continuation.
    assert any(m.get("role") == "tool" for m in continuation["messages"])
    assert runner.status == SubAgentStatus.COMPLETED
    assert runner.final_report == "final report"


async def test_orchestration_and_auto_mode_calls_intercepted():
    client = FakeUpstreamClient(
        [
            FakeUpstreamResponse(
                [
                    tool_input_available("tc-spawn", "spawn_subagent", {}),
                    tool_input_available("tc-auto", "enable_auto_mode", {}),
                    trace("tr-1"),
                    finish_tool_calls(),
                ]
            ),
            FakeUpstreamResponse([text_delta("ok"), trace("tr-2"), finish()]),
        ]
    )
    runner, _, _ = _runner(client)
    with patch.object(httpx, "AsyncClient", return_value=client):
        await runner.run()

    continuation = client.bodies[1]
    tool_msgs = {
        m["tool_call_id"]: m["content"]
        for m in continuation["messages"]
        if m.get("role") == "tool"
    }
    assert tool_msgs["tc-spawn"] == DEPTH_LIMIT_RESULT
    assert tool_msgs["tc-auto"] == AUTO_MODE_NOOP_RESULT
    assert runner.status == SubAgentStatus.COMPLETED


async def test_max_rounds_times_out():
    responses = [
        FakeUpstreamResponse(
            [
                tool_input_available(f"tc-{i}", "call_kiln_api", {}),
                trace(f"tr-{i}"),
                finish_tool_calls(),
            ]
        )
        for i in range(2)
    ]
    client = FakeUpstreamClient(responses)
    runner, emitted, _ = _runner(client, max_rounds=2)
    with (
        patch.object(httpx, "AsyncClient", return_value=client),
        patch(
            "app.desktop.studio_server.chat.stream_session.execute_tool",
            new=AsyncMock(return_value='{"ok": true}'),
        ),
    ):
        await runner.run()

    assert runner.status == SubAgentStatus.TIMEOUT
    assert runner.rounds_used == 2


async def test_steer_message_drained_before_finish_continues_run():
    inbound = [InboundMessage(content="also check model B")]
    client = FakeUpstreamClient(
        [
            FakeUpstreamResponse(
                [text_delta("thought I was done"), trace("tr-1"), finish()]
            ),
            FakeUpstreamResponse([text_delta("real report"), trace("tr-2"), finish()]),
        ]
    )
    runner, _, _ = _runner(client, inbound=inbound)
    with patch.object(httpx, "AsyncClient", return_value=client):
        await runner.run()

    steer_body = client.bodies[1]
    contents = [m.get("content", "") for m in steer_body["messages"]]
    assert any("also check model B" in c for c in contents)
    assert any("system-reminder" in c for c in contents)
    assert runner.status == SubAgentStatus.COMPLETED
    assert runner.final_report == "real report"


async def test_upstream_failure_marks_failed():
    client = FakeUpstreamClient(
        [FakeUpstreamResponse(status_code=400, body=b'{"message": "bad"}')]
    )
    runner, emitted, _ = _runner(client)
    with patch.object(httpx, "AsyncClient", return_value=client):
        await runner.run()

    assert runner.status == SubAgentStatus.FAILED
    decoded = b"".join(emitted).decode()
    assert json.loads(decoded.split("data: ")[1].strip())["type"] == "error"
