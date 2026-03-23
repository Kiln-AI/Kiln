import asyncio
import json
import logging
from typing import Any

import httpx
from app.desktop.studio_server.api_client.kiln_server_client import (
    _get_base_url,
    _get_common_headers,
)
from app.desktop.studio_server.utils.copilot_utils import get_copilot_api_key
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from kiln_ai.datamodel import Project, TaskRun
from kiln_ai.utils.config import Config

logger = logging.getLogger(__name__)

_CHAT_TIMEOUT = httpx.Timeout(timeout=300.0, connect=30.0)
_MAX_CLIENT_TOOL_ROUNDS = 5

# Canned result returned for every server-side (remote) tool call.
# None means "execute all tools with this constant answer"; a frozenset would
# restrict which tool names are auto-handled (reserved for future use).
_REMOTE_TOOL_AUTO_EXECUTE: frozenset[str] | None = None
_CANNED_TOOL_RESULT = "The result is 58"
_TOOL_SIMULATION_DELAY_SEC = 5.0


async def execute_tool(tool_name: str, args: dict[str, Any]) -> str:
    """Simulate remote tool execution (delay + canned result) for UX testing."""
    await asyncio.sleep(_TOOL_SIMULATION_DELAY_SEC)
    _ = tool_name, args
    return _CANNED_TOOL_RESULT


def _build_upstream_headers(api_key: str) -> dict[str, str]:
    return {
        **_get_common_headers(),
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _find_task_run_by_id(task_run_id: str) -> TaskRun | None:
    """Search all projects and tasks for a task run with the given ID."""
    project_paths = Config.shared().projects or []
    for project_path in project_paths:
        try:
            project = Project.load_from_file(project_path)
        except Exception:
            continue
        for task in project.tasks():
            run = TaskRun.from_id_and_parent_path(task_run_id, task.path)
            if run is not None:
                return run
    return None


def _execute_client_tool(tool_name: str, arguments: dict[str, Any]) -> str:
    """Execute a client-side tool and return the result as a string."""
    if tool_name == "read_task_run":
        task_run_id = arguments.get("task_run_id", "")
        if not task_run_id:
            return json.dumps({"error": "task_run_id is required"})
        try:
            run = _find_task_run_by_id(task_run_id)
            if run is None:
                return json.dumps({"error": f"Task run not found: {task_run_id}"})
            return run.model_dump_json(indent=2)
        except Exception as e:
            return json.dumps({"error": f"Failed to read task run: {e}"})
    return json.dumps({"error": f"Unknown client tool: {tool_name}"})


def _parse_sse_events(
    raw: bytes,
    line_buffer: bytearray | None = None,
) -> tuple[list[bytes], dict[str, Any] | None, bool, list[dict[str, Any]], str]:
    """Parse raw SSE bytes into forwarding lines and extracted event data.

    Maintains a line buffer so that chunks split mid-line are handled correctly:
    bytes are appended to *line_buffer* and only complete lines (terminated by
    ``\\n``) are processed.  Pass the same ``bytearray`` instance across
    consecutive calls for a single upstream response; pass ``None`` (or omit)
    when processing a standalone, complete chunk (e.g. in unit tests).

    Returns:
        lines_to_forward: complete lines to stream back to the UI
        client_tool_event: the ``client-tool-call`` event dict, if present
            (suppressed from *lines_to_forward*)
        upstream_finish_tool_calls: True when a ``finish`` event carries
            ``messageMetadata.finishReason == "tool-calls"``
        tool_input_events: list of ``tool-input-available`` event dicts
        text_delta: concatenated ``text-delta`` content from this chunk
    """
    if line_buffer is None:
        line_buffer = bytearray()

    line_buffer.extend(raw)

    # Split on newlines; the last element is an incomplete line that stays in
    # the buffer until the next chunk arrives.
    parts = bytes(line_buffer).split(b"\n")
    line_buffer.clear()
    line_buffer.extend(parts[-1])
    complete_lines = parts[:-1]

    lines_to_forward: list[bytes] = []
    client_tool_event: dict[str, Any] | None = None
    upstream_finish_tool_calls = False
    tool_input_events: list[dict[str, Any]] = []
    text_delta = ""

    for line in complete_lines:
        if line.startswith(b"data: "):
            payload = line[6:].strip()
            if payload and payload != b"[DONE]":
                try:
                    event = json.loads(payload)
                    if not isinstance(event, dict):
                        pass
                    elif event.get("type") == "client-tool-call":
                        client_tool_event = event
                        continue  # strip from forwarded stream
                    elif event.get("type") == "finish":
                        meta = event.get("messageMetadata") or {}
                        if meta.get("finishReason") == "tool-calls":
                            upstream_finish_tool_calls = True
                    elif event.get("type") == "tool-input-available":
                        tool_input_events.append(event)
                    elif event.get("type") == "text-delta":
                        delta = event.get("delta")
                        if isinstance(delta, str):
                            text_delta += delta
                except (json.JSONDecodeError, TypeError):
                    pass
        lines_to_forward.append(line)

    return (
        lines_to_forward,
        client_tool_event,
        upstream_finish_tool_calls,
        tool_input_events,
        text_delta,
    )


def _dedupe_tool_inputs(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate tool-input-available events by toolCallId; last entry wins."""
    seen: dict[str, dict[str, Any]] = {}
    for ev in events:
        seen[ev.get("toolCallId", "")] = ev
    return list(seen.values())


def connect_chat_api(app: FastAPI) -> None:
    @app.post("/api/chat")
    async def chat(request: Request) -> StreamingResponse:
        api_key = get_copilot_api_key()
        body_bytes = await request.body()
        body_json = json.loads(body_bytes)

        upstream_url = f"{_get_base_url()}/v1/chat/"
        headers = _build_upstream_headers(api_key)

        async def stream_with_client_tools():
            current_body = body_json
            rounds = 0

            while rounds < _MAX_CLIENT_TOOL_ROUNDS:
                rounds += 1
                client_tool_event = None
                upstream_finish_tool_calls = False
                tool_input_events_this_round: list[dict[str, Any]] = []
                assistant_text_this_round = ""
                line_buffer = bytearray()

                async with httpx.AsyncClient(timeout=_CHAT_TIMEOUT) as client:
                    async with client.stream(
                        "POST",
                        upstream_url,
                        content=json.dumps(current_body).encode(),
                        headers=headers,
                    ) as upstream:
                        if upstream.status_code != 200:
                            error_body = await upstream.aread()
                            detail = "Chat request failed."
                            if error_body.startswith(b"{"):
                                try:
                                    detail = (
                                        json.loads(error_body).get("message", detail)
                                        or detail
                                    )
                                except json.JSONDecodeError:
                                    pass
                            yield f"data: {json.dumps({'type': 'error', 'message': detail})}\n\n".encode()
                            return

                        try:
                            async for chunk in upstream.aiter_bytes():
                                (
                                    lines,
                                    tool_event,
                                    fin_tool_calls,
                                    tool_inputs,
                                    text_delta,
                                ) = _parse_sse_events(chunk, line_buffer)
                                if tool_event:
                                    client_tool_event = tool_event
                                if fin_tool_calls:
                                    upstream_finish_tool_calls = True
                                tool_input_events_this_round.extend(tool_inputs)
                                assistant_text_this_round += text_delta
                                forward_bytes = b"\n".join(lines)
                                if forward_bytes.strip():
                                    yield forward_bytes + b"\n"
                        except httpx.RemoteProtocolError:
                            if (
                                client_tool_event is not None
                                or upstream_finish_tool_calls
                            ):
                                logger.debug(
                                    "Connection closed after streamed tool boundary "
                                    "(client-tool-call or AI SDK tool-calls finish; expected)"
                                )
                            else:
                                raise

                # client-tool-call takes precedence when both appear in one round
                if client_tool_event is not None:
                    tool_name = client_tool_event.get("toolName", "")
                    tool_call_id = client_tool_event.get("toolCallId", "")
                    tool_input = client_tool_event.get("input", {})

                    logger.info(
                        f"Executing client tool: {tool_name} (call_id={tool_call_id})"
                    )

                    yield f"data: {json.dumps({'type': 'tool-output-available', 'toolCallId': tool_call_id, 'output': '(executing locally...)'})}\n\n".encode()

                    tool_result = _execute_client_tool(tool_name, tool_input)

                    yield f"data: {json.dumps({'type': 'tool-output-available', 'toolCallId': tool_call_id, 'output': tool_result})}\n\n".encode()

                    current_body = _build_continuation_body(
                        current_body, tool_call_id, tool_name, tool_input, tool_result
                    )
                    continue

                # AI SDK server-side tool round: the model stopped to call remote tools
                if upstream_finish_tool_calls and tool_input_events_this_round:
                    deduped = _dedupe_tool_inputs(tool_input_events_this_round)
                    for event in deduped:
                        tc_id = event.get("toolCallId", "")
                        tool_name = event.get("toolName", "")
                        raw_input = event.get("input", {})
                        tool_args = raw_input if isinstance(raw_input, dict) else {}
                        logger.info(
                            f"Simulating remote tool: {tool_name} (call_id={tc_id})"
                        )
                        tool_result = await execute_tool(tool_name, tool_args)
                        yield f"data: {json.dumps({'type': 'tool-output-available', 'toolCallId': tc_id, 'output': tool_result})}\n\n".encode()
                    current_body = _build_openai_tool_continuation(
                        current_body, assistant_text_this_round, deduped
                    )
                    continue

                return

        return StreamingResponse(
            content=stream_with_client_tools(),
            media_type="text/event-stream",
        )


def _build_openai_tool_continuation(
    original_body: dict[str, Any],
    assistant_text: str,
    tool_input_events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the request body for continuing after server-side AI SDK tool calls.

    Appends an ``assistant`` message with ``tool_calls`` followed by one
    ``role: tool`` message per call (each carrying the canned result), matching
    the OpenAI message schema the backend's ``convert_to_openai_messages``
    expects.
    """
    tool_calls: list[dict[str, Any]] = []
    tool_messages: list[dict[str, Any]] = []

    for event in tool_input_events:
        tc_id = event.get("toolCallId", "")
        tool_name = event.get("toolName", "")
        inp = event.get("input", {})
        arg_str = inp if isinstance(inp, str) else json.dumps(inp)

        tool_calls.append(
            {
                "id": tc_id,
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": arg_str,
                },
            }
        )
        tool_messages.append(
            {
                "role": "tool",
                "tool_call_id": tc_id,
                "content": _CANNED_TOOL_RESULT,
            }
        )

    messages = list(original_body.get("messages", []))
    assistant_content = assistant_text.strip() or None
    messages.append(
        {
            "role": "assistant",
            "content": assistant_content,
            "tool_calls": tool_calls,
        }
    )
    messages.extend(tool_messages)

    return {**original_body, "messages": messages}


def _build_continuation_body(
    original_body: dict[str, Any],
    tool_call_id: str,
    tool_name: str,
    tool_input: Any,
    tool_result: str,
) -> dict[str, Any]:
    """Build the request body for continuing after a client tool call.

    Appends a single assistant message containing both the tool call and its
    result so the backend's convert_to_openai_messages produces the correct
    assistant(tool_calls) + tool(result) sequence.
    """
    messages = list(original_body.get("messages", []))

    messages.append(
        {
            "role": "assistant",
            "parts": [
                {
                    "type": f"tool-{tool_name}",
                    "toolCallId": tool_call_id,
                    "toolName": tool_name,
                    "input": tool_input,
                    "state": "call",
                },
                {
                    "type": f"tool-{tool_name}",
                    "toolCallId": tool_call_id,
                    "toolName": tool_name,
                    "output": tool_result,
                    "state": "output-available",
                },
            ],
        }
    )

    return {**original_body, "messages": messages}
