import json
import logging
import uuid
from dataclasses import dataclass, field
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
_MAX_TOOL_ROUNDS = 25
_FUNCTION_NAME_TO_TOOL_ID: dict[str, str] = {
    "call_kiln_api": KilnBuiltInToolId.CALL_KILN_API,
}

KILN_SSE_CHAT_TRACE = "kiln_chat_trace"

_ai_sdk_stream_event_adapter = TypeAdapter(AiSdkStreamEvent)


def _try_parse_ai_sdk_event(data: dict[str, Any]) -> AiSdkStreamEvent | None:
    try:
        return _ai_sdk_stream_event_adapter.validate_python(data)
    except ValidationError:
        return None


@dataclass
class ParseResult:
    lines_to_forward: list[bytes] = field(default_factory=list)
    finish_tool_calls: bool = False
    tool_input_events: list[ToolInputAvailableEvent] = field(default_factory=list)
    text_delta: str = ""
    chat_trace_id: str | None = None


class EventParser:
    """Stateful SSE parser that accumulates a line buffer across chunks."""

    def __init__(self) -> None:
        self._line_buffer = bytearray()

    def parse(self, raw: bytes) -> ParseResult:
        self._line_buffer.extend(raw)

        parts = bytes(self._line_buffer).split(b"\n")
        self._line_buffer.clear()
        self._line_buffer.extend(parts[-1])
        complete_lines = parts[:-1]

        result = ParseResult(lines_to_forward=list(complete_lines))

        i = 0
        while i < len(result.lines_to_forward):
            line = result.lines_to_forward[i]
            if line.startswith(b"data: "):
                payload = line[6:].strip()
                if payload and payload != b"[DONE]":
                    self._process_payload(payload, result)
            i += 1

        return result

    def _process_payload(self, payload: bytes, result: ParseResult) -> None:
        try:
            event = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            logger.debug("Failed to parse SSE payload as JSON: %s", payload[:120])
            return

        if not isinstance(event, dict):
            return

        event_type = event.get("type")

        if event_type == KILN_SSE_CHAT_TRACE:
            tid = event.get("trace_id")
            if isinstance(tid, str) and tid:
                result.chat_trace_id = tid
            return

        parsed = _try_parse_ai_sdk_event(event)
        if isinstance(parsed, FinishEvent):
            meta = parsed.messageMetadata
            if meta is not None and meta.finishReason == "tool-calls":
                result.finish_tool_calls = True
        elif isinstance(parsed, TextDeltaEvent):
            result.text_delta += parsed.delta
        elif isinstance(parsed, ToolInputAvailableEvent):
            result.tool_input_events.append(parsed)


@dataclass
class RoundState:
    """Accumulated state from one upstream round."""

    finish_tool_calls: bool = False
    tool_input_events: list[ToolInputAvailableEvent] = field(default_factory=list)
    assistant_text: str = ""
    trace_id: str | None = None


class ChatStreamSession:
    """Owns the multi-round streaming loop for a single chat request."""

    def __init__(
        self,
        upstream_url: str,
        headers: dict[str, str],
        initial_body: dict[str, Any],
    ) -> None:
        self._upstream_url = upstream_url
        self._headers = headers
        self._body = initial_body

    async def stream(self):
        """AsyncGenerator yielding SSE bytes to the client."""
        for _ in range(_MAX_TOOL_ROUNDS):
            round_state = RoundState()
            parser = EventParser()
            trace_id_for_error: str | None = None

            async with httpx.AsyncClient(timeout=_CHAT_TIMEOUT) as client:
                async with client.stream(
                    "POST",
                    self._upstream_url,
                    content=json.dumps(self._body).encode(),
                    headers=self._headers,
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
                        error_payload: dict[str, Any] = {
                            "type": "error",
                            "message": detail,
                        }
                        if trace_id_for_error:
                            error_payload["trace_id"] = trace_id_for_error
                        yield f"data: {json.dumps(error_payload)}\n\n".encode()
                        return

                    try:
                        async for chunk in upstream.aiter_bytes():
                            result = parser.parse(chunk)
                            if result.finish_tool_calls:
                                round_state.finish_tool_calls = True
                            round_state.tool_input_events.extend(
                                result.tool_input_events
                            )
                            round_state.assistant_text += result.text_delta
                            if result.chat_trace_id is not None:
                                round_state.trace_id = result.chat_trace_id
                                trace_id_for_error = result.chat_trace_id
                            forward_bytes = b"\n".join(result.lines_to_forward)
                            if forward_bytes.strip():
                                yield forward_bytes + b"\n"
                    except httpx.RemoteProtocolError:
                        if round_state.finish_tool_calls:
                            logger.debug(
                                "Connection closed after streamed tool boundary "
                                "(AI SDK tool-calls finish; expected)"
                            )
                        else:
                            trace_id = trace_id_for_error or str(uuid.uuid4())
                            error_payload = {
                                "type": "error",
                                "message": "Connection to upstream server was lost.",
                                "trace_id": trace_id,
                            }
                            yield f"data: {json.dumps(error_payload)}\n\n".encode()
                            logger.exception(
                                "RemoteProtocolError during streaming (trace_id=%s)",
                                trace_id,
                            )
                            return

            if round_state.trace_id:
                self._body = {
                    **self._body,
                    "trace_id": round_state.trace_id,
                    "messages": [],
                }

            if round_state.finish_tool_calls:
                tool_results = await self._execute_client_tools(round_state)
                for tc_id, output in tool_results.items():
                    yield self._format_tool_output(tc_id, output)

                self._body = _build_openai_tool_continuation(
                    self._body,
                    round_state.assistant_text,
                    round_state.tool_input_events,
                    tool_results,
                )
                continue

            return

    async def _execute_client_tools(self, round_state: RoundState) -> dict[str, str]:
        tool_results: dict[str, str] = {}
        for event in round_state.tool_input_events:
            tc_id = event.toolCallId
            tool_name = event.toolName
            tool_args = event.input
            logger.info(
                "Executing server tool: %s (call_id=%s)",
                tool_name,
                tc_id,
            )

            print("========================")
            print(f"tool_name: {tool_name}")
            print(f"tool_args: {tool_args}")

            # may be a passive visible event from the remote server executing the tool
            # and we don't have it here, we should not run it
            tool_id = _FUNCTION_NAME_TO_TOOL_ID.get(tool_name, tool_name)
            if not tool_id:
                print("No tool id found -> continuing")
                continue
            else:
                print(f"Tool id found -> executing tool: {tool_id}")

            tool_result = await execute_tool(tool_name, tool_args)
            tool_results[tc_id] = tool_result
        return tool_results

    @staticmethod
    def _format_tool_output(tc_id: str, output: str) -> bytes:
        return f"data: {json.dumps({'type': 'tool-output-available', 'toolCallId': tc_id, 'output': output})}\n\n".encode()


async def execute_tool(tool_name: str, args: dict[str, Any]) -> str:
    """Run a Kiln built-in tool by OpenAI function name; return its output string."""
    logger.info(
        "Executing server tool %s with args: %s",
        tool_name,
        json.dumps(args, default=str),
    )
    tool_id = _FUNCTION_NAME_TO_TOOL_ID.get(tool_name, tool_name)
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


def connect_chat_api(app: FastAPI) -> None:
    @app.post("/api/chat")
    async def chat(request: Request) -> StreamingResponse:
        api_key = get_copilot_api_key()
        body_bytes = await request.body()
        body_json = json.loads(body_bytes)

        session = ChatStreamSession(
            upstream_url=f"{_get_base_url()}/v1/chat/",
            headers=_build_upstream_headers(api_key),
            initial_body=body_json,
        )
        return StreamingResponse(
            content=session.stream(),
            media_type="text/event-stream",
        )
