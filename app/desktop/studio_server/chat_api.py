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
from kiln_ai.adapters.model_adapters.stream_events import (
    AiSdkStreamEvent,
    FinishEvent,
    TextDeltaEvent,
    ToolInputAvailableEvent,
)
from kiln_ai.datamodel.tool_id import KilnBuiltInToolId
from kiln_ai.tools.tool_registry import tool_from_id
from pydantic import TypeAdapter, ValidationError

logger = logging.getLogger(__name__)

_CHAT_TIMEOUT = httpx.Timeout(timeout=300.0, connect=30.0)
_MAX_CLIENT_TOOL_ROUNDS = 25

KILN_SSE_CLIENT_TOOL_CALL = "client-tool-call"
KILN_SSE_CHAT_TRACE = "kiln_chat_trace"

_ai_sdk_stream_event_adapter = TypeAdapter(AiSdkStreamEvent)


def _try_parse_ai_sdk_event(data: dict[str, Any]) -> AiSdkStreamEvent | None:
    try:
        return _ai_sdk_stream_event_adapter.validate_python(data)
    except ValidationError:
        return None


FUNCTION_NAME_TO_TOOL_ID: dict[str, KilnBuiltInToolId] = {
    "call_kiln_api": KilnBuiltInToolId.CALL_KILN_API,
}


async def execute_tool(tool_name: str, args: dict[str, Any]) -> str:
    """Run a Kiln built-in tool by OpenAI function name; return its output string."""
    logger.info(
        "Executing server tool %s with args: %s",
        tool_name,
        json.dumps(args, default=str),
    )
    tool_id = FUNCTION_NAME_TO_TOOL_ID.get(tool_name)
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


def _parse_sse_events(
    raw: bytes,
    line_buffer: bytearray | None = None,
) -> tuple[
    list[bytes],
    dict[str, Any] | None,
    bool,
    list[ToolInputAvailableEvent],
    str,
    str | None,
]:
    """Parse raw SSE bytes into forwarding lines and extracted event data.

    Maintains a line buffer so that chunks split mid-line are handled correctly:
    bytes are appended to *line_buffer* and only complete lines (terminated by
    ``\\n``) are processed.  Pass the same ``bytearray`` instance across
    consecutive calls for a single upstream response; pass ``None`` (or omit)
    when processing a standalone, complete chunk (e.g. in unit tests).

    Each ``data:`` JSON object is deserialized with Pydantic
    :class:`~kiln_ai.adapters.model_adapters.stream_events.AiSdkStreamEvent`
    when possible; payloads that fail validation are still forwarded but do
    not contribute to extracted fields (except Kiln-only types below).

    Kiln extension types ``client-tool-call`` and ``kiln_chat_trace`` are not
    part of ``AiSdkStreamEvent`` and are handled separately from raw dicts.

    Returns:
        lines_to_forward: complete lines to stream back to the UI
        client_tool_event: the ``client-tool-call`` event dict, if present
            (suppressed from *lines_to_forward*)
        upstream_finish_tool_calls: True when a validated ``finish`` event has
            ``messageMetadata.finishReason == "tool-calls"``
        tool_input_events: validated ``tool-input-available`` events
        text_delta: concatenated ``text-delta`` content from validated events
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
    tool_input_events: list[ToolInputAvailableEvent] = []
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
                    else:
                        event_type = event.get("type")
                        if event_type == KILN_SSE_CLIENT_TOOL_CALL:
                            client_tool_event = event
                            continue
                        if event_type == KILN_SSE_CHAT_TRACE:
                            tid = event.get("trace_id")
                            if isinstance(tid, str) and tid:
                                chat_trace_id = tid
                        else:
                            parsed = _try_parse_ai_sdk_event(event)
                            if isinstance(parsed, FinishEvent):
                                meta = parsed.messageMetadata
                                if (
                                    meta is not None
                                    and meta.finishReason == "tool-calls"
                                ):
                                    upstream_finish_tool_calls = True
                            elif isinstance(parsed, TextDeltaEvent):
                                text_delta += parsed.delta
                            elif isinstance(parsed, ToolInputAvailableEvent):
                                tool_input_events.append(parsed)
                except (json.JSONDecodeError, TypeError):
                    logger.exception("Failed to parse AI SDK event", exc_info=True)
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
                tool_input_events_this_round: list[ToolInputAvailableEvent] = []
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

                # upstream send the trace_id that we need to send back in the next request to continue the trace
                if upstream_trace_id:
                    current_body = {
                        **current_body,
                        "trace_id": upstream_trace_id,
                        "messages": [],
                    }

                # AI SDK server-side tool round: the model stopped to call remote tools
                if upstream_finish_tool_calls:
                    deduped = tool_input_events_this_round
                    tool_results_by_call_id: dict[str, str] = {}
                    for event in deduped:
                        tc_id = event.toolCallId
                        tool_name = event.toolName
                        tool_args = event.input
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

                    # we ran the tools we needed to, continue on to sending back the results upstream
                    continue

                # stream is over but nothing to do here
                return

        return StreamingResponse(
            content=stream_with_client_tools(),
            media_type="text/event-stream",
        )


def _build_openai_tool_continuation(
    original_body: dict[str, Any],
    assistant_text: str,
    tool_input_events: list[ToolInputAvailableEvent],
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
        tc_id = event.toolCallId
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
            tc_id = event.toolCallId
            tool_name = event.toolName
            args_str = json.dumps(event.input)
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
