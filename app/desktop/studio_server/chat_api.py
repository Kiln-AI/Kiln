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
from kiln_ai.datamodel.tool_id import KilnBuiltInToolId
from kiln_ai.tools.tool_registry import tool_from_id
from kiln_ai.utils.config import Config

logger = logging.getLogger(__name__)

_CHAT_TIMEOUT = httpx.Timeout(timeout=300.0, connect=30.0)
_MAX_CLIENT_TOOL_ROUNDS = 5

_BUILTIN_FUNCTION_NAME_TO_TOOL_ID: dict[str, str] = {
    "add": KilnBuiltInToolId.ADD_NUMBERS.value,
    "subtract": KilnBuiltInToolId.SUBTRACT_NUMBERS.value,
    "multiply": KilnBuiltInToolId.MULTIPLY_NUMBERS.value,
    "divide": KilnBuiltInToolId.DIVIDE_NUMBERS.value,
    "call_kiln_api": KilnBuiltInToolId.CALL_KILN_API.value,
}


async def execute_tool(tool_name: str, args: dict[str, Any]) -> str:
    """Run a Kiln built-in tool by OpenAI function name; return its output string."""
    logger.info(
        "Executing server tool %s with args: %s",
        tool_name,
        json.dumps(args, default=str),
    )
    tool_id = _BUILTIN_FUNCTION_NAME_TO_TOOL_ID.get(tool_name)
    if tool_id is None:
        logger.warning("No local executor for server tool name: %s", tool_name)
        return json.dumps({"error": f"Unknown server tool: {tool_name}"})
    try:
        tool = tool_from_id(tool_id)
        result = await tool.run(**args)
        return result.output
    except Exception as e:
        logger.exception("Built-in tool %s failed", tool_name)
        return json.dumps({"error": str(e)})


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
) -> tuple[
    list[bytes],
    dict[str, Any] | None,
    bool,
    list[dict[str, Any]],
    str,
    str | None,
]:
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
        chat_trace_id: ``trace_id`` from the last ``kiln_chat_trace`` event in
            this chunk, if any (non-empty string only)
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
    chat_trace_id: str | None = None

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
                    elif event.get("type") == "kiln_chat_trace":
                        tid = event.get("trace_id")
                        if isinstance(tid, str) and tid:
                            chat_trace_id = tid
                except (json.JSONDecodeError, TypeError):
                    pass
        lines_to_forward.append(line)

    return (
        lines_to_forward,
        client_tool_event,
        upstream_finish_tool_calls,
        tool_input_events,
        text_delta,
        chat_trace_id,
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
                upstream_trace_id: str | None = None
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
                                    chunk_trace_id,
                                ) = _parse_sse_events(chunk, line_buffer)
                                if tool_event:
                                    client_tool_event = tool_event
                                if fin_tool_calls:
                                    upstream_finish_tool_calls = True
                                tool_input_events_this_round.extend(tool_inputs)
                                assistant_text_this_round += text_delta
                                if chunk_trace_id is not None:
                                    upstream_trace_id = chunk_trace_id
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

                if upstream_trace_id:
                    current_body = {
                        **current_body,
                        "trace_id": upstream_trace_id,
                        "messages": [],
                    }

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
                    tool_results_by_call_id: dict[str, str] = {}
                    for event in deduped:
                        tc_id = event.get("toolCallId", "")
                        tool_name = event.get("toolName", "")
                        raw_input = event.get("input", {})
                        tool_args = raw_input if isinstance(raw_input, dict) else {}
                        logger.info(
                            f"Executing server tool: {tool_name} (call_id={tc_id})"
                        )
                        tool_result = await execute_tool(tool_name, tool_args)
                        tool_results_by_call_id[tc_id] = tool_result
                        yield f"data: {json.dumps({'type': 'tool-output-available', 'toolCallId': tc_id, 'output': tool_result})}\n\n".encode()
                    current_body = _build_openai_tool_continuation(
                        current_body,
                        assistant_text_this_round,
                        deduped,
                        tool_results_by_call_id,
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
    tool_results_by_call_id: dict[str, str],
) -> dict[str, Any]:
    """Build the request body for continuing after server-side AI SDK tool calls.

    Appends an ``assistant`` message with ``tool_calls`` followed by one
    ``role: tool`` message per call (each carrying the matching execution
    result from *tool_results_by_call_id*), matching the OpenAI message schema
    the backend's ``convert_to_openai_messages`` expects.
    """
    tool_messages: list[dict[str, Any]] = []

    for event in tool_input_events:
        tc_id = event.get("toolCallId", "")
        tool_content = tool_results_by_call_id.get(tc_id, "")
        tool_messages.append(
            {
                "role": "tool",
                "tool_call_id": tc_id,
                "content": tool_content,
            }
        )

    prior_messages = list(original_body.get("messages", []))
    trace_only_continuation = bool(original_body.get("trace_id")) and not prior_messages

    if trace_only_continuation:
        new_messages = tool_messages
    else:
        tool_calls: list[dict[str, Any]] = []
        for event in tool_input_events:
            tc_id = event.get("toolCallId", "")
            tool_name = event.get("toolName", "")
            raw_input = event.get("input", {})
            if isinstance(raw_input, dict):
                args_str = json.dumps(raw_input)
            elif isinstance(raw_input, str):
                args_str = raw_input
            else:
                args_str = json.dumps(raw_input)
            tool_calls.append(
                {
                    "id": tc_id,
                    "type": "function",
                    "function": {"name": tool_name, "arguments": args_str},
                }
            )
        content: str | None = (
            assistant_text if assistant_text and assistant_text.strip() else None
        )
        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": content,
            "tool_calls": tool_calls,
        }
        new_messages = prior_messages + [assistant_msg] + tool_messages

    return {**original_body, "messages": new_messages}


def _build_continuation_body(
    original_body: dict[str, Any],
    tool_call_id: str,
    _tool_name: str,
    tool_input: Any,
    tool_result: str,
) -> dict[str, Any]:
    """Build the request body for continuing after a client tool call.

    Appends a single assistant message containing both the tool call and its
    result so the backend's convert_to_openai_messages produces the correct
    assistant(tool_calls) + tool(result) sequence.
    """
    messages = list(original_body.get("messages", []))
    parts: list[dict[str, Any]] = [
        {
            "toolCallId": tool_call_id,
            "state": "call",
            "input": tool_input,
        },
        {
            "toolCallId": tool_call_id,
            "state": "output-available",
            "output": tool_result,
        },
    ]
    assistant_msg = {"role": "assistant", "parts": parts}
    return {**original_body, "messages": messages + [assistant_msg]}
