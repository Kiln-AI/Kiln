import json
import logging
import os
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
from fastapi.testclient import TestClient
from kiln_ai.utils.config import Config

logger = logging.getLogger(__name__)

_MAX_TOOL_ROUNDS_INTEGRATION = 5


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


def _finish_reason_is_tool_calls(event: dict[str, Any]) -> bool:
    meta = event.get("messageMetadata") or {}
    return meta.get("finishReason") == "tool-calls"


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
    api_key = _kiln_copilot_api_key_for_integration()
    if not api_key:
        pytest.skip(
            "No Kiln Copilot API key: set KILN_COPILOT_API_KEY or kiln_copilot_api_key "
            f"in {Path(Config.settings_dir(create=False)) / 'settings.yaml'}"
        )
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
        for round_i in range(_MAX_TOOL_ROUNDS_INTEGRATION):
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
