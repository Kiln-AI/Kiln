import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml
from app.desktop.studio_server.api_client.kiln_ai_server_client.api.health import (
    ping_ping_get,
)
from app.desktop.studio_server.api_client.kiln_server_client import (
    get_kiln_server_client,
)
from app.desktop.studio_server.chat.constants import (
    DENIED_TOOL_OUTPUT,
    KILN_SSE_CHAT_TRACE,
    SSE_TYPE_TOOL_CALLS_PENDING,
)
from kiln_ai.utils.config import Config

logger = logging.getLogger(__name__)

_MAX_TOOL_ROUNDS_INTEGRATION = 5


@dataclass
class StreamResult:
    events: list[dict[str, Any]] = field(default_factory=list)
    text: str = ""
    trace_id: str | None = None
    tool_inputs: list[dict[str, Any]] = field(default_factory=list)
    tool_outputs: list[dict[str, Any]] = field(default_factory=list)
    pending_items: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str | None = None
    raw_bytes: bytes = b""


def _sse_json_from_line(line: str) -> dict[str, Any] | None:
    if not line.startswith("data: "):
        return None
    payload = line[6:].strip()
    if not payload or payload == "[DONE]":
        return None
    try:
        out = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return out if isinstance(out, dict) else None


def _accumulate_stream_result(
    lines: Any,
) -> StreamResult:
    out = StreamResult()
    buf = bytearray()
    for line in lines:
        text = line or ""
        buf.extend(text.encode("utf-8"))
        buf.extend(b"\n")
        ev = _sse_json_from_line(text)
        if not ev:
            continue
        out.events.append(ev)
        et = ev.get("type")
        if et == "text-delta":
            delta = ev.get("delta")
            if isinstance(delta, str):
                out.text += delta
        elif et == "tool-input-available":
            out.tool_inputs.append(ev)
        elif et == "tool-output-available":
            out.tool_outputs.append(ev)
        elif et == SSE_TYPE_TOOL_CALLS_PENDING:
            items = ev.get("items")
            if isinstance(items, list):
                for it in items:
                    if isinstance(it, dict):
                        out.pending_items.append(it)
        elif et == KILN_SSE_CHAT_TRACE:
            tid = ev.get("trace_id")
            if isinstance(tid, str) and tid:
                out.trace_id = tid
        elif et == "finish":
            meta = ev.get("messageMetadata") or {}
            fr = meta.get("finishReason")
            if isinstance(fr, str):
                out.finish_reason = fr
    out.raw_bytes = bytes(buf)
    return out


async def _observe_and_run(
    sup,
    session_id: str,
    *,
    start,
    settle_timeout: float = 120.0,
) -> StreamResult:
    """Subscribe to the conversation's bus, run `start()` (send / decide),
    wait until the run settles (leaves RUNNING/AWAITING_APPROVAL), and return
    the accumulated stream — the phase-4 equivalent of consuming the old
    POST /api/chat response stream (observers see the same bytes)."""
    from app.desktop.studio_server.chat.runtime.models import RunState

    received: list[bytes] = []
    sub = sup.subscribe(session_id)

    async def _drain():
        async for payload in sub:
            received.append(payload)

    drain_task = asyncio.create_task(_drain())
    await asyncio.sleep(0.05)
    start()

    async def _poll():
        while True:
            record = sup.get(session_id)
            if record is not None and record.state not in (
                RunState.RUNNING,
                RunState.AWAITING_APPROVAL,
            ):
                return
            await asyncio.sleep(0.05)

    await asyncio.wait_for(_poll(), timeout=settle_timeout)
    await asyncio.sleep(0.1)  # let trailing bytes land on the queue
    drain_task.cancel()
    try:
        await drain_task
    except asyncio.CancelledError:
        pass
    await sub.aclose()
    collected = b"".join(received)
    r = _accumulate_stream_result(collected.decode("utf-8").splitlines())
    r.raw_bytes = collected
    return r


def _make_supervisor(api_key: str):
    """A fresh supervisor + the real upstream target (the same URL/header
    builders the routes use)."""
    from app.desktop.studio_server.chat.routes import (
        _build_upstream_headers,
        _upstream_chat_url,
    )
    from app.desktop.studio_server.chat.runtime.supervisor import (
        ConversationSupervisor,
    )

    with patch.dict(os.environ, {"KILN_COPILOT_API_KEY": api_key}, clear=False):
        return (
            ConversationSupervisor(),
            _upstream_chat_url(),
            _build_upstream_headers(api_key),
        )


def _chat_turn(
    sup, upstream_url: str, headers: dict[str, str], content: str, session_id=None
) -> tuple[StreamResult, str]:
    """Run one interactive turn (create the conversation on first use) and
    return (stream, session_id) — replaces the old _stream_chat driver."""

    async def _run() -> tuple[StreamResult, str]:
        sid = session_id
        if sid is None:
            record = await sup.adopt_interactive(
                None, upstream_url=upstream_url, headers=headers
            )
            sid = record.session_id
        result = await _observe_and_run(
            sup, sid, start=lambda: sup.send_message(sid, content)
        )
        return result, sid

    return asyncio.run(_run())


def _decide_staged_batch(
    sup,
    session_id: str,
    tool_calls: list[dict[str, Any]],
    decisions: dict[str, bool],
) -> StreamResult:
    """Stage a runless approval batch on the conversation and decide it —
    replaces the old _stream_execute_tools driver (same continuation body on
    the wire; the results stream on the observer channel)."""
    from kiln_ai.adapters.model_adapters.stream_events import (
        ToolInputAvailableEvent,
    )

    from app.desktop.studio_server.chat.runtime.models import (
        PendingApprovalBatch,
        RunState,
    )
    from app.desktop.studio_server.chat.stream_session import (
        _pending_item_from_event,
    )

    async def _run() -> StreamResult:
        conv = sup._conversations[session_id]
        events = [
            ToolInputAvailableEvent(
                toolCallId=tc["toolCallId"],
                toolName=tc["toolName"],
                input=tc["input"],
                kiln_metadata={"requires_approval": bool(tc["requiresApproval"])},
            )
            for tc in tool_calls
        ]
        batch = PendingApprovalBatch(
            items=[_pending_item_from_event(e) for e in events],
            body={"trace_id": conv.record.current_leaf_trace_id, "messages": []},
            assistant_text="",
            tool_input_events=events,
        )
        conv.pending_batch = batch
        conv.record.state = RunState.AWAITING_APPROVAL
        result = await _observe_and_run(
            sup,
            session_id,
            start=lambda: sup.decide(session_id, batch.batch_id, decisions),
        )
        return result

    return asyncio.run(_run())


def _require_copilot_api_key() -> str:
    api_key = _kiln_copilot_api_key_for_integration()
    if not api_key:
        pytest.skip(
            "No Kiln Copilot API key: set KILN_COPILOT_API_KEY or kiln_copilot_api_key "
            f"in {Path(Config.settings_dir(create=False)) / 'settings.yaml'}"
        )
    return api_key


def _finish_reason_is_tool_calls(event: dict[str, Any]) -> bool:
    meta = event.get("messageMetadata") or {}
    return meta.get("finishReason") == "tool-calls"


def _tool_output_matches_expected_number(value: Any, expected: float) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)) and float(value) == expected:
        return True
    s = str(value).strip()
    try:
        return float(s) == expected
    except ValueError:
        return False


def _assert_sse_events_match_frontend_expected_shapes(
    events: list[dict[str, Any]],
) -> None:
    for ev in events:
        et = ev.get("type")
        if not isinstance(et, str):
            continue
        if et == "text-delta":
            assert "delta" in ev
            assert isinstance(ev.get("delta"), str)
        elif et == "tool-input-available":
            assert isinstance(ev.get("toolCallId"), str)
            assert isinstance(ev.get("toolName"), str)
            assert "input" in ev
        elif et == "tool-output-available":
            assert isinstance(ev.get("toolCallId"), str)
            assert "output" in ev
        elif et == SSE_TYPE_TOOL_CALLS_PENDING:
            items = ev.get("items")
            assert isinstance(items, list) and len(items) > 0
            for it in items:
                assert isinstance(it, dict)
                assert isinstance(it.get("toolCallId"), str)
                assert isinstance(it.get("toolName"), str)
                assert "input" in it
        elif et == KILN_SSE_CHAT_TRACE:
            assert isinstance(ev.get("trace_id"), str)
            assert ev.get("trace_id")
        elif et == "finish":
            meta = ev.get("messageMetadata")
            assert meta is None or isinstance(meta, dict)
            if isinstance(meta, dict) and "finishReason" in meta:
                assert isinstance(meta.get("finishReason"), str)


def _assert_event_ordering(events: list[dict[str, Any]]) -> None:
    """Verify key SSE event ordering invariants."""
    type_list = [e.get("type") for e in events]
    for i, ev in enumerate(events):
        if ev.get("type") == "tool-output-available":
            tc_id = ev.get("toolCallId")
            input_indices = [
                j
                for j, e in enumerate(events)
                if e.get("type") == "tool-input-available"
                and e.get("toolCallId") == tc_id
            ]
            assert input_indices and input_indices[0] < i, (
                f"tool-output-available for {tc_id} at index {i} has no preceding tool-input-available"
            )
    if "finish" in type_list:
        finish_idx = type_list.index("finish")
        text_indices = [j for j, t in enumerate(type_list) if t == "text-delta"]
        for ti in text_indices:
            assert ti < finish_idx, "text-delta must come before finish"


def _execute_math_tool_for_integration(
    tool_name: str, arguments: dict[str, Any]
) -> str:
    """Mirror libs/core paid litellm streaming tests: built-in math tool names and {a,b} args."""
    base = tool_name.split("::")[-1]
    aliases = {
        "multiply_numbers": "multiply",
        "add_numbers": "add",
        "subtract_numbers": "subtract",
        "divide_numbers": "divide",
    }
    name = aliases.get(base, tool_name)
    a, b = float(arguments.get("a", 0)), float(arguments.get("b", 0))
    if name == "add":
        result = a + b
    elif name == "subtract":
        result = a - b
    elif name == "multiply":
        result = a * b
    elif name == "divide":
        result = a / b
    else:
        return json.dumps(
            {"error": f"integration test: unsupported tool {tool_name!r}"}
        )
    text = str(int(result)) if result == int(result) else str(result)
    return text


def _openai_assistant_and_tool_messages(
    assistant_text: str,
    tool_input_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    tool_calls: list[dict[str, Any]] = []
    tool_messages: list[dict[str, Any]] = []
    for ev in tool_input_events:
        tc_id = ev["toolCallId"]
        tname = ev["toolName"]
        inp = ev.get("input")
        if inp is None:
            inp = {}
        if isinstance(inp, str):
            arg_str = inp
            try:
                raw_args = json.loads(inp)
            except json.JSONDecodeError:
                raw_args = {}
        else:
            arg_str = json.dumps(inp)
            raw_args = inp if isinstance(inp, dict) else {}
        tool_calls.append(
            {
                "id": tc_id,
                "type": "function",
                "function": {"name": tname, "arguments": arg_str},
            }
        )
        if not isinstance(raw_args, dict):
            raw_args = {}
        result_str = _execute_math_tool_for_integration(tname, raw_args)
        tool_messages.append(
            {"role": "tool", "tool_call_id": tc_id, "content": result_str}
        )

    text = assistant_text.strip()
    assistant: dict[str, Any] = {
        "role": "assistant",
        "content": text if text else None,
        "tool_calls": tool_calls,
    }
    return [assistant, *tool_messages]


def _kiln_copilot_api_key_for_integration() -> str | None:
    """Resolve the Copilot API key for paid tests.

    Unit tests patch Config.settings_path to an empty temp file, so keys stored
    only in the real user settings.yaml are invisible to Config unless we read
    that file or the key is in the environment.
    """
    if key := os.environ.get("KILN_COPILOT_API_KEY"):
        return key.strip() or None
    settings_file = Path(Config.settings_dir(create=False)) / "settings.yaml"
    if not settings_file.is_file():
        return None
    data = yaml.safe_load(settings_file.read_text()) or {}
    raw = data.get("kiln_copilot_api_key")
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


@pytest.mark.paid
def test_api_integration():
    kiln_client = get_kiln_server_client()
    assert ping_ping_get.sync(client=kiln_client) == "pong"


@pytest.mark.paid
def test_chat_api_integration():
    # Old shape: the browser drove POST /api/chat rounds manually. New shape:
    # one send on an interactive conversation — the engine drives the rounds
    # (tool execution + continuation) server-side and observers see the same
    # event stream the old response carried.
    api_key = _require_copilot_api_key()
    sup, url, headers = _make_supervisor(api_key)
    r, _sid = _chat_turn(
        sup,
        url,
        headers,
        "hi - my name is bob. Can you compute 2 * 8 for me? "
        "Use the multiply tool if available.",
    )
    content = r.raw_bytes
    assert len(content) > 0
    assert b"data:" in content
    assert b"16" in content or b'"16"' in content


@pytest.mark.paid
def test_simple_text_chat_no_tools():
    api_key = _require_copilot_api_key()
    sup, url, headers = _make_supervisor(api_key)
    r, _sid = _chat_turn(
        sup,
        url,
        headers,
        "Answer in one short sentence only: what is the capital of France? "
        "Do not call any tools.",
    )
    assert len(r.raw_bytes) > 0
    assert b"data:" in r.raw_bytes
    assert r.trace_id, "kiln_chat_trace should issue trace_id"
    assert any(ev.get("type") == "text-delta" and ev.get("delta") for ev in r.events), (
        "expected non-empty text-delta"
    )
    assert not r.tool_inputs, "expected no tool-input-available for text-only prompt"
    assert not r.pending_items, "expected no tool-calls-pending"
    assert r.finish_reason != "tool-calls", (
        f"expected finish without tool-calls, got {r.finish_reason!r}"
    )


@pytest.mark.paid
def test_proxy_auto_executes_math_tools():
    api_key = _require_copilot_api_key()
    sup, url, headers = _make_supervisor(api_key)
    r, _sid = _chat_turn(
        sup,
        url,
        headers,
        "hi - my name is bob. Can you compute 2 * 8 for me? "
        "Use the multiply tool if available.",
    )
    assert len(r.raw_bytes) > 0
    assert "16" in r.text or b"16" in r.raw_bytes
    _assert_event_ordering(r.events)
    if r.tool_outputs:
        outputs_by_id = {o.get("toolCallId"): o.get("output") for o in r.tool_outputs}
        assert any(
            _tool_output_matches_expected_number(v, 16.0)
            for v in outputs_by_id.values()
        )


@pytest.mark.paid
def test_multi_turn_trace_continuation():
    # Continuation is the conversation record's own leaf now (the browser no
    # longer round-trips trace ids): two sends on the SAME session id must
    # continue the same upstream conversation.
    api_key = _require_copilot_api_key()
    sup, url, headers = _make_supervisor(api_key)
    first, sid = _chat_turn(
        sup,
        url,
        headers,
        "Remember this for our conversation: my display name is Bob. "
        "Reply with one short acknowledgment sentence.",
    )
    assert first.trace_id, "first turn should include kiln_chat_trace trace_id"

    second, _ = _chat_turn(
        sup,
        url,
        headers,
        "What display name did I ask you to remember? "
        "Answer with the name only, one word if possible.",
        session_id=sid,
    )
    assert second.trace_id
    combined = (
        second.text + second.raw_bytes.decode("utf-8", errors="replace")
    ).lower()
    assert "bob" in combined


@pytest.mark.paid
def test_approval_decisions_with_approved_tool():
    # Old test_execute_tools_with_approved_tool: the decisions flow now runs
    # through the parked-batch resume (same continuation body on the wire).
    api_key = _require_copilot_api_key()
    sup, url, headers = _make_supervisor(api_key)
    _warm, sid = _chat_turn(sup, url, headers, "Say hi in one word.")
    assert sup.get(sid).current_leaf_trace_id
    tc_id = f"integ-approved-{uuid.uuid4().hex[:12]}"
    exec_r = _decide_staged_batch(
        sup,
        sid,
        [
            {
                "toolCallId": tc_id,
                "toolName": "kiln_tool::add_numbers",
                "input": {"a": 1, "b": 2},
                "requiresApproval": True,
            }
        ],
        {tc_id: True},
    )
    _assert_event_ordering(exec_r.events)
    by_call = {o.get("toolCallId"): o.get("output") for o in exec_r.tool_outputs}
    assert by_call.get(tc_id) == "3"
    assert any(ev.get("type") == "finish" for ev in exec_r.events), (
        "the resume run should continue with upstream finish"
    )


@pytest.mark.paid
def test_approval_decisions_with_denied_tool():
    api_key = _require_copilot_api_key()
    sup, url, headers = _make_supervisor(api_key)
    _warm, sid = _chat_turn(sup, url, headers, "Say hello in one word.")
    tc_id = f"integ-denied-{uuid.uuid4().hex[:12]}"
    exec_r = _decide_staged_batch(
        sup,
        sid,
        [
            {
                "toolCallId": tc_id,
                "toolName": "kiln_tool::add_numbers",
                "input": {"a": 10, "b": 20},
                "requiresApproval": True,
            }
        ],
        {tc_id: False},
    )
    by_call = {o.get("toolCallId"): o.get("output") for o in exec_r.tool_outputs}
    assert by_call.get(tc_id) == DENIED_TOOL_OUTPUT


@pytest.mark.paid
def test_approval_decisions_mixed_approved_and_denied():
    api_key = _require_copilot_api_key()
    sup, url, headers = _make_supervisor(api_key)
    _warm, sid = _chat_turn(sup, url, headers, "Acknowledge in one word.")
    tc_add = f"integ-mix-add-{uuid.uuid4().hex[:10]}"
    tc_mul = f"integ-mix-mul-{uuid.uuid4().hex[:10]}"
    exec_r = _decide_staged_batch(
        sup,
        sid,
        [
            {
                "toolCallId": tc_add,
                "toolName": "kiln_tool::add_numbers",
                "input": {"a": 1, "b": 2},
                "requiresApproval": True,
            },
            {
                "toolCallId": tc_mul,
                "toolName": "kiln_tool::multiply_numbers",
                "input": {"a": 3, "b": 4},
                "requiresApproval": True,
            },
        ],
        {tc_add: True, tc_mul: False},
    )
    by_call = {o.get("toolCallId"): o.get("output") for o in exec_r.tool_outputs}
    assert by_call.get(tc_add) == "3"
    assert by_call.get(tc_mul) == DENIED_TOOL_OUTPUT


@pytest.mark.paid
def test_sse_events_match_frontend_expected_shapes():
    api_key = _require_copilot_api_key()
    sup, url, headers = _make_supervisor(api_key)
    warm, sid = _chat_turn(sup, url, headers, "Say hi in one word.")
    _assert_sse_events_match_frontend_expected_shapes(warm.events)
    tc_id = f"integ-sse-shapes-{uuid.uuid4().hex[:12]}"
    exec_r = _decide_staged_batch(
        sup,
        sid,
        [
            {
                "toolCallId": tc_id,
                "toolName": "kiln_tool::multiply_numbers",
                "input": {"a": 3, "b": 4},
                "requiresApproval": True,
            }
        ],
        {tc_id: True},
    )
    _assert_sse_events_match_frontend_expected_shapes(exec_r.events)
    _assert_event_ordering(exec_r.events)
    assert any(ev.get("type") == "tool-output-available" for ev in exec_r.events)
    by_call = {o.get("toolCallId"): o.get("output") for o in exec_r.tool_outputs}
    assert _tool_output_matches_expected_number(by_call.get(tc_id), 12.0)
