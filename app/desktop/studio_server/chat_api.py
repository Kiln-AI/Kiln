import asyncio
import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx
from app.desktop.studio_server.api_client.kiln_server_client import (
    _get_base_url,
    _get_common_headers,
)
from app.desktop.studio_server.utils.copilot_utils import get_copilot_api_key
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from kiln_ai.adapters.model_adapters.stream_events import (
    AiSdkStreamEvent,
    FinishEvent,
    TextDeltaEvent,
    ToolInputAvailableEvent,
)
from kiln_ai.datamodel.tool_id import KilnBuiltInToolId
from kiln_ai.tools.tool_registry import tool_from_id
from kiln_server.utils.agent_checks.policy import DENY_AGENT
from pydantic import (
    BaseModel,
    ConfigDict,
    TypeAdapter,
    ValidationError,
    field_validator,
)

logger = logging.getLogger(__name__)

_CHAT_TIMEOUT = httpx.Timeout(timeout=300.0, connect=30.0)
_MAX_TOOL_ROUNDS = 25
_TOOL_APPROVAL_TIMEOUT_SEC = 600.0

SSE_TYPE_TOOL_APPROVAL_REQUIRED = "tool-approval-required"

_DENIED_TOOL_OUTPUT = json.dumps({"error": "The user did not accept the toolcall"})
_FUNCTION_NAME_TO_TOOL_ID: dict[str, str] = {
    "call_kiln_api": KilnBuiltInToolId.CALL_KILN_API,
}

KILN_SSE_CHAT_TRACE = "kiln_chat_trace"

_ai_sdk_stream_event_adapter = TypeAdapter(AiSdkStreamEvent)

_EXECUTOR_SERVER = "server"


class KilnToolInputMetadata(BaseModel):
    """Validated subset of ``kiln_metadata`` on tool-input-available events."""

    model_config = ConfigDict(extra="allow")

    executor: str | None = None
    requires_approval: bool | None = None
    permission: str | None = None
    approval_description: str | None = None

    @field_validator("requires_approval", mode="before")
    @classmethod
    def _requires_approval_must_be_bool_or_none(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, bool):
            return v
        raise ValueError("requires_approval must be a boolean or null")

    @field_validator("executor", "permission", "approval_description", mode="before")
    @classmethod
    def _optional_str_fields(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str):
            return v
        raise ValueError("must be a string or null")


def _parse_kiln_tool_metadata(raw: dict[str, Any]) -> KilnToolInputMetadata:
    try:
        return KilnToolInputMetadata.model_validate(dict(raw))
    except ValidationError:
        logger.debug("kiln_metadata validation failed, using narrowed fields: %s", raw)
        narrowed: dict[str, Any] = {}
        for key in ("executor", "permission", "approval_description"):
            v = raw.get(key)
            if isinstance(v, str):
                narrowed[key] = v
        ra = raw.get("requires_approval")
        if isinstance(ra, bool):
            narrowed["requires_approval"] = ra
        for k, v in raw.items():
            if k in narrowed or k == "requires_approval":
                continue
            narrowed[k] = v
        return KilnToolInputMetadata.model_validate(narrowed)


def _tool_input_executor_is_server(event: ToolInputAvailableEvent) -> bool:
    return _parse_kiln_tool_metadata(event.kiln_metadata).executor == _EXECUTOR_SERVER


def _tool_requires_user_approval(event: ToolInputAvailableEvent) -> bool:
    return _parse_kiln_tool_metadata(event.kiln_metadata).requires_approval is True


@dataclass
class PendingToolApproval:
    future: asyncio.Future[dict[str, bool]]
    required_tool_call_ids: frozenset[str]


class ToolApprovalRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: dict[str, PendingToolApproval] = {}

    async def register_wait(
        self, batch_id: str, required_tool_call_ids: frozenset[str]
    ) -> asyncio.Future[dict[str, bool]]:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, bool]] = loop.create_future()
        pending = PendingToolApproval(
            future=future, required_tool_call_ids=required_tool_call_ids
        )
        with self._lock:
            self._pending[batch_id] = pending
        return future

    def pop_pending(self, batch_id: str) -> PendingToolApproval | None:
        with self._lock:
            return self._pending.pop(batch_id, None)

    def submit_decisions(self, batch_id: str, decisions: dict[str, bool]) -> None:
        with self._lock:
            pending = self._pending.get(batch_id)
        if pending is None:
            raise HTTPException(
                status_code=404, detail="Timed out waiting for tool approval"
            )
        if pending.future.done():
            raise HTTPException(
                status_code=409, detail="Approval batch was already completed"
            )
        required = pending.required_tool_call_ids
        got = frozenset(decisions.keys())
        if got != required:
            raise HTTPException(
                status_code=400,
                detail="decisions must include exactly each toolCallId in the approval batch",
            )
        with self._lock:
            self._pending.pop(batch_id, None)
        pending.future.set_result(decisions)


_tool_approval_registry = ToolApprovalRegistry()


async def _register_tool_approval_wait(
    batch_id: str, required_tool_call_ids: frozenset[str]
) -> asyncio.Future[dict[str, bool]]:
    return await _tool_approval_registry.register_wait(batch_id, required_tool_call_ids)


def _pop_pending_tool_approval(batch_id: str) -> PendingToolApproval | None:
    return _tool_approval_registry.pop_pending(batch_id)


async def submit_tool_approval_decisions(
    batch_id: str, decisions: dict[str, bool]
) -> None:
    _tool_approval_registry.submit_decisions(batch_id, decisions)


def _format_tool_approval_required_sse(
    batch_id: str, items: list[dict[str, Any]]
) -> bytes:
    payload = {
        "type": SSE_TYPE_TOOL_APPROVAL_REQUIRED,
        "approvalBatchId": batch_id,
        "items": items,
    }
    return f"data: {json.dumps(payload)}\n\n".encode()


def _approval_item_from_event(event: ToolInputAvailableEvent) -> dict[str, Any]:
    meta = _parse_kiln_tool_metadata(event.kiln_metadata)
    item: dict[str, Any] = {
        "toolCallId": event.toolCallId,
        "toolName": event.toolName,
    }
    if meta.permission is not None:
        item["permission"] = meta.permission
    if meta.approval_description is not None:
        item["approvalDescription"] = meta.approval_description
    return item


async def _wait_for_tool_approval(
    batch_id: str,
    future: asyncio.Future[dict[str, bool]],
    _request: Request | None,
    timeout_sec: float,
) -> dict[str, bool] | Literal["timeout"]:
    try:
        return await asyncio.wait_for(future, timeout=timeout_sec)
    except asyncio.TimeoutError:
        _pop_pending_tool_approval(batch_id)
        if not future.done():
            future.cancel()
        return "timeout"
    except asyncio.CancelledError:
        _pop_pending_tool_approval(batch_id)
        if not future.done():
            future.cancel()
        raise


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
        request: Request | None = None,
    ) -> None:
        self._upstream_url = upstream_url
        self._headers = headers
        self._body = initial_body
        self._request = request

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
                client_events = [
                    e
                    for e in round_state.tool_input_events
                    if not _tool_input_executor_is_server(e)
                ]
                needs_approval = [
                    e for e in client_events if _tool_requires_user_approval(e)
                ]
                approval_decisions: dict[str, bool] | None = None
                if needs_approval:
                    required_ids = frozenset(e.toolCallId for e in needs_approval)
                    batch_id = str(uuid.uuid4())
                    approval_future = await _register_tool_approval_wait(
                        batch_id, required_ids
                    )
                    items = [_approval_item_from_event(e) for e in needs_approval]
                    yield _format_tool_approval_required_sse(batch_id, items)
                    wait_outcome = await _wait_for_tool_approval(
                        batch_id,
                        approval_future,
                        self._request,
                        _TOOL_APPROVAL_TIMEOUT_SEC,
                    )
                    if wait_outcome == "timeout":
                        err_tid = round_state.trace_id or str(uuid.uuid4())
                        yield (
                            f"data: {json.dumps({'type': 'error', 'message': 'Tool approval timed out.', 'trace_id': err_tid})}\n\n".encode()
                        )
                        return
                    approval_decisions = wait_outcome

                tool_results = await self._execute_client_tools(
                    round_state, approval_decisions
                )
                for tc_id, output in tool_results.items():
                    yield self._format_tool_output(tc_id, output)

                if not tool_results:
                    return

                self._body = _build_openai_tool_continuation(
                    self._body,
                    round_state.assistant_text,
                    round_state.tool_input_events,
                    tool_results,
                )
                continue

            return

    async def _execute_client_tools(
        self,
        round_state: RoundState,
        approval_decisions: dict[str, bool] | None,
    ) -> dict[str, str]:
        tool_results: dict[str, str] = {}
        for event in round_state.tool_input_events:
            if _tool_input_executor_is_server(event):
                logger.debug(
                    "Skipping local tool execution (executor=server): %s (call_id=%s)",
                    event.toolName,
                    event.toolCallId,
                )
                continue
            tc_id = event.toolCallId
            if _tool_requires_user_approval(event):
                if approval_decisions is None or not approval_decisions.get(tc_id):
                    tool_results[tc_id] = _DENIED_TOOL_OUTPUT
                    continue
            tool_name = event.toolName
            tool_args = event.input
            logger.info(
                "Executing server tool: %s (call_id=%s)",
                tool_name,
                tc_id,
            )
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

    Appends an ``assistant`` message with ``tool_calls`` (when there are local
    results) followed by one ``role: tool`` message per call that has an entry
    in *tool_results_by_call_id*, matching the OpenAI message schema the
    backend's ``convert_to_openai_messages`` expects.

    Only tool calls with a local result appear; upstream-only calls are omitted
    entirely rather than sent with empty ``content``.
    """
    local_events = [
        e for e in tool_input_events if e.toolCallId in tool_results_by_call_id
    ]

    tool_messages: list[dict[str, Any]] = []
    for event in local_events:
        tc_id = event.toolCallId
        tool_content = tool_results_by_call_id[tc_id]
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
        for event in local_events:
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
        }
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls
        new_messages = prior_messages + [assistant_msg] + tool_messages

    return {**original_body, "messages": new_messages}


class ToolApprovalRequestBody(BaseModel):
    approval_batch_id: str
    decisions: dict[str, bool]


def connect_chat_api(app: FastAPI) -> None:
    @app.post(
        "/api/chat/tool-approval",
        summary="Submit tool call approval decisions",
        tags=["Copilot"],
        openapi_extra=DENY_AGENT,
    )
    async def post_tool_approval(body: ToolApprovalRequestBody) -> JSONResponse:
        """Submit tool call approval decisions."""
        await submit_tool_approval_decisions(body.approval_batch_id, body.decisions)
        return JSONResponse({"ok": True})

    @app.post(
        "/api/chat",
        summary="Stream Chat",
        tags=["Copilot"],
        openapi_extra=DENY_AGENT,
    )
    async def chat(request: Request) -> StreamingResponse:
        """Forward chat to Kiln Copilot and stream AI SDK events as Server-Sent Events."""
        api_key = get_copilot_api_key()
        body_bytes = await request.body()
        body_json = json.loads(body_bytes)

        session = ChatStreamSession(
            upstream_url=f"{_get_base_url()}/v1/chat/",
            headers=_build_upstream_headers(api_key),
            initial_body=body_json,
            request=request,
        )
        return StreamingResponse(
            content=session.stream(),
            media_type="text/event-stream",
        )
