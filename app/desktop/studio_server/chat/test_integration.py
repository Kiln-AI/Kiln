import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
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
from fastapi.testclient import TestClient
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


def _stream_chat(
    app: Any,
    body: dict[str, Any],
    api_key: str,
) -> StreamResult:
    client = TestClient(app)
    collected = bytearray()
    with patch.dict(os.environ, {"KILN_COPILOT_API_KEY": api_key}, clear=False):
        with client.stream(
            "POST",
            "/api/chat",
            json=body,
            timeout=httpx.Timeout(120.0, connect=30.0),
        ) as response:
            assert response.status_code == 200
            ctype = response.headers.get("content-type", "")
            assert ctype.startswith("text/event-stream")
            for line in response.iter_lines():
                text = line or ""
                collected.extend(text.encode("utf-8"))
                collected.extend(b"\n")
    r = _accumulate_stream_result(collected.decode("utf-8").splitlines())
    r.raw_bytes = bytes(collected)
    return r


def _stream_execute_tools(
    app: Any,
    body: dict[str, Any],
    api_key: str,
) -> StreamResult:
    client = TestClient(app)
    collected = bytearray()
    with patch.dict(os.environ, {"KILN_COPILOT_API_KEY": api_key}, clear=False):
        with client.stream(
            "POST",
            "/api/chat/execute-tools",
            json=body,
            timeout=httpx.Timeout(120.0, connect=30.0),
        ) as response:
            assert response.status_code == 200
            ctype = response.headers.get("content-type", "")
            assert ctype.startswith("text/event-stream")
            for line in response.iter_lines():
                text = line or ""
                collected.extend(text.encode("utf-8"))
                collected.extend(b"\n")
    r = _accumulate_stream_result(collected.decode("utf-8").splitlines())
    r.raw_bytes = bytes(collected)
    return r


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
def test_chat_api_integration(app):
    api_key = _require_copilot_api_key()
    client = TestClient(app)
    collected = bytearray()
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": (
                "hi - my name is bob. Can you compute 2 * 8 for me? "
                "Use the multiply tool if available."
            ),
        }
    ]

    with patch.dict(os.environ, {"KILN_COPILOT_API_KEY": api_key}, clear=False):
        for _round_i in range(_MAX_TOOL_ROUNDS_INTEGRATION):
            pending_tool_inputs: list[dict[str, Any]] = []
            assistant_chunks: list[str] = []
            stop_with_tool_calls = False

            with client.stream(
                "POST",
                "/api/chat",
                json={"messages": messages},
                timeout=httpx.Timeout(120.0, connect=30.0),
            ) as response:
                assert response.status_code == 200
                ctype = response.headers.get("content-type", "")
                assert ctype.startswith("text/event-stream")
                for line in response.iter_lines():
                    text = line or ""
                    logger.info(text)
                    collected.extend(text.encode("utf-8"))
                    collected.extend(b"\n")

                    ev = _sse_json_from_line(text)
                    if not ev:
                        continue
                    et = ev.get("type")
                    if et == "text-delta":
                        delta = ev.get("delta")
                        if isinstance(delta, str):
                            assistant_chunks.append(delta)
                    elif et == "tool-input-available":
                        pending_tool_inputs.append(ev)
                    elif et == "finish" and _finish_reason_is_tool_calls(ev):
                        stop_with_tool_calls = True

            if not stop_with_tool_calls:
                break

            assert pending_tool_inputs, (
                "finishReason tool-calls but no tool-input-available events"
            )
            continuation = _openai_assistant_and_tool_messages(
                "".join(assistant_chunks), pending_tool_inputs
            )
            messages = messages + continuation
        else:
            pytest.fail(
                f"Exceeded {_MAX_TOOL_ROUNDS_INTEGRATION} tool rounds without finishing"
            )

    content = bytes(collected)
    assert len(content) > 0
    assert b"data:" in content
    assert b"16" in content or b'"16"' in content


@pytest.mark.paid
def test_simple_text_chat_no_tools(app):
    api_key = _require_copilot_api_key()
    r = _stream_chat(
        app,
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Answer in one short sentence only: what is the capital of France? "
                        "Do not call any tools."
                    ),
                }
            ]
        },
        api_key,
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
def test_proxy_auto_executes_math_tools(app):
    api_key = _require_copilot_api_key()
    r = _stream_chat(
        app,
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "hi - my name is bob. Can you compute 2 * 8 for me? "
                        "Use the multiply tool if available."
                    ),
                }
            ]
        },
        api_key,
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
def test_multi_turn_trace_continuation(app):
    api_key = _require_copilot_api_key()
    first = _stream_chat(
        app,
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Remember this for our conversation: my display name is Bob. "
                        "Reply with one short acknowledgment sentence."
                    ),
                }
            ]
        },
        api_key,
    )
    tid = first.trace_id
    assert tid, "first turn should include kiln_chat_trace trace_id"

    second = _stream_chat(
        app,
        {
            "trace_id": tid,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "What display name did I ask you to remember? "
                        "Answer with the name only, one word if possible."
                    ),
                }
            ],
        },
        api_key,
    )
    assert second.trace_id
    combined = (
        second.text + second.raw_bytes.decode("utf-8", errors="replace")
    ).lower()
    assert "bob" in combined


@pytest.mark.paid
def test_execute_tools_with_approved_tool(app):
    api_key = _require_copilot_api_key()
    warm = _stream_chat(
        app,
        {"messages": [{"role": "user", "content": "Say hi in one word."}]},
        api_key,
    )
    trace_id = warm.trace_id
    assert trace_id
    tc_id = f"integ-approved-{uuid.uuid4().hex[:12]}"
    exec_r = _stream_execute_tools(
        app,
        {
            "trace_id": trace_id,
            "tool_calls": [
                {
                    "toolCallId": tc_id,
                    "toolName": "kiln_tool::add_numbers",
                    "input": {"a": 1, "b": 2},
                    "requiresApproval": True,
                }
            ],
            "decisions": {tc_id: True},
        },
        api_key,
    )
    _assert_event_ordering(exec_r.events)
    by_call = {o.get("toolCallId"): o.get("output") for o in exec_r.tool_outputs}
    assert by_call.get(tc_id) == "3"
    assert any(ev.get("type") == "finish" for ev in exec_r.events), (
        "execute-tools stream should continue with upstream finish"
    )


@pytest.mark.paid
def test_execute_tools_with_denied_tool(app):
    api_key = _require_copilot_api_key()
    warm = _stream_chat(
        app,
        {"messages": [{"role": "user", "content": "Say hello in one word."}]},
        api_key,
    )
    trace_id = warm.trace_id
    assert trace_id
    tc_id = f"integ-denied-{uuid.uuid4().hex[:12]}"
    exec_r = _stream_execute_tools(
        app,
        {
            "trace_id": trace_id,
            "tool_calls": [
                {
                    "toolCallId": tc_id,
                    "toolName": "kiln_tool::add_numbers",
                    "input": {"a": 10, "b": 20},
                    "requiresApproval": True,
                }
            ],
            "decisions": {tc_id: False},
        },
        api_key,
    )
    by_call = {o.get("toolCallId"): o.get("output") for o in exec_r.tool_outputs}
    assert by_call.get(tc_id) == DENIED_TOOL_OUTPUT


@pytest.mark.paid
def test_execute_tools_mixed_approved_and_denied(app):
    api_key = _require_copilot_api_key()
    warm = _stream_chat(
        app,
        {"messages": [{"role": "user", "content": "Acknowledge in one word."}]},
        api_key,
    )
    trace_id = warm.trace_id
    assert trace_id
    tc_add = f"integ-mix-add-{uuid.uuid4().hex[:10]}"
    tc_mul = f"integ-mix-mul-{uuid.uuid4().hex[:10]}"
    exec_r = _stream_execute_tools(
        app,
        {
            "trace_id": trace_id,
            "tool_calls": [
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
            "decisions": {tc_add: True, tc_mul: False},
        },
        api_key,
    )
    by_call = {o.get("toolCallId"): o.get("output") for o in exec_r.tool_outputs}
    assert by_call.get(tc_add) == "3"
    assert by_call.get(tc_mul) == DENIED_TOOL_OUTPUT


@pytest.mark.paid
def test_sse_events_match_frontend_expected_shapes(app):
    api_key = _require_copilot_api_key()
    warm = _stream_chat(
        app,
        {"messages": [{"role": "user", "content": "Say hi in one word."}]},
        api_key,
    )
    _assert_sse_events_match_frontend_expected_shapes(warm.events)
    trace_id = warm.trace_id
    assert trace_id
    tc_id = f"integ-sse-shapes-{uuid.uuid4().hex[:12]}"
    exec_r = _stream_execute_tools(
        app,
        {
            "trace_id": trace_id,
            "tool_calls": [
                {
                    "toolCallId": tc_id,
                    "toolName": "kiln_tool::multiply_numbers",
                    "input": {"a": 3, "b": 4},
                    "requiresApproval": True,
                }
            ],
            "decisions": {tc_id: True},
        },
        api_key,
    )
    _assert_sse_events_match_frontend_expected_shapes(exec_r.events)
    _assert_event_ordering(exec_r.events)
    assert any(ev.get("type") == "tool-output-available" for ev in exec_r.events)
    by_call = {o.get("toolCallId"): o.get("output") for o in exec_r.tool_outputs}
    assert _tool_output_matches_expected_number(by_call.get(tc_id), 12.0)
