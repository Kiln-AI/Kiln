import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import httpx
from app.desktop.studio_server.chat.constants import (
    CHAT_TIMEOUT,
    DENIED_TOOL_OUTPUT,
    FUNCTION_NAME_TO_TOOL_ID,
    MAX_TOOL_ROUNDS,
    SSE_TYPE_TOOL_CALLS_PENDING,
    SSE_TYPE_TOOL_EXEC_END,
    SSE_TYPE_TOOL_EXEC_START,
)
from app.desktop.studio_server.chat.sse_parser import EventParser
from app.desktop.studio_server.chat.tool_metadata import (
    _parse_kiln_tool_metadata,
    tool_input_executor_is_server,
    tool_requires_user_approval,
)
from kiln_ai.adapters.model_adapters.stream_events import ToolInputAvailableEvent
from kiln_ai.tools.tool_registry import tool_from_id
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


@dataclass
class RoundState:
    """Accumulated state from one upstream round.

    The first four fields are the public per-round outputs the caller reads.
    The trailing two carry the small amount of cross-round/error context that
    ``iter_upstream_round`` needs so it can own the non-200 / RemoteProtocolError
    handling that used to be inline in ``ChatStreamSession.stream()``:

    - ``trace_id_for_error``: the last trace id seen so far (seeded from the
      caller's known trace id), stamped onto error payloads so the UI can
      correlate. ``trace_id`` is the trace id observed *this* round.
    - ``seen_upstream_error``: whether an upstream ``error`` event was already
      forwarded, so a subsequent connection close isn't reported as a duplicate
      generic error.
    """

    finish_tool_calls: bool = False
    tool_input_events: list[ToolInputAvailableEvent] = field(default_factory=list)
    assistant_text: str = ""
    trace_id: str | None = None
    trace_id_for_error: str | None = None
    seen_upstream_error: bool = False
    # Set when iter_upstream_round itself yielded a terminal `error` SSE payload
    # (non-200 response, or a RemoteProtocolError with no finish boundary). The
    # caller uses this to stop the loop — distinct from a forwarded upstream
    # `error` event, which is non-terminal and leaves the loop free to continue.
    emitted_terminal_error: bool = False

    @property
    def is_terminal_upstream_error(self) -> bool:
        """Single source of truth for "this round ended on an upstream error and
        the loop must stop." Two distinct cases collapse here:

        - ``emitted_terminal_error``: iter_upstream_round already yielded a
          terminal error SSE (non-200, or RemoteProtocolError with no finish
          boundary) — nothing left to drive.
        - a forwarded upstream ``error`` event followed by a connection close
          with no tool-call finish boundary (``seen_upstream_error and not
          finish_tool_calls``): the duplicate generic error was suppressed and
          there is nothing more to continue from.

        Both the interactive ``ChatStreamSession.stream()`` and the auto-run
        ``AutoChatRunner`` consult this so the two paths can't drift.
        """
        return self.emitted_terminal_error or (
            self.seen_upstream_error and not self.finish_tool_calls
        )


class ToolCallInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tool_call_id: str = Field(alias="toolCallId")
    tool_name: str = Field(alias="toolName")
    input: dict[str, Any]
    requires_approval: bool = Field(alias="requiresApproval")


def _pending_item_from_event(event: ToolInputAvailableEvent) -> dict[str, Any]:
    meta = _parse_kiln_tool_metadata(event.kiln_metadata)
    item: dict[str, Any] = {
        "toolCallId": event.toolCallId,
        "toolName": event.toolName,
        "input": event.input,
        "requiresApproval": meta.requires_approval is True,
    }
    if meta.permission is not None:
        item["permission"] = meta.permission
    if meta.approval_description is not None:
        item["approvalDescription"] = meta.approval_description
    return item


def _format_tool_calls_pending_sse(events: list[ToolInputAvailableEvent]) -> bytes:
    items = [_pending_item_from_event(e) for e in events]
    payload = {"type": SSE_TYPE_TOOL_CALLS_PENDING, "items": items}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


async def iter_upstream_round(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    round_state: RoundState,
) -> AsyncIterator[bytes]:
    """POST one upstream round; yield forward-bytes as they stream; mutate
    ``round_state`` in place.

    Shared by the interactive ``ChatStreamSession.stream()`` and the auto-run
    ``AutoChatRunner``. It owns exactly the per-round upstream mechanics that
    used to be inline in ``stream()``: open the upstream POST, parse the SSE,
    forward the bytes, accumulate ``finish_tool_calls`` / ``tool_input_events`` /
    ``assistant_text`` / ``trace_id`` onto ``round_state``, and handle non-200
    responses and ``RemoteProtocolError`` by yielding the standard ``error`` SSE
    bytes and returning. It does NOT apply any post-round policy (approval gate,
    tool execution, continuation) — that stays caller-specific.

    ``round_state.trace_id_for_error`` should be seeded by the caller with the
    last known trace id before the first round; this generator updates it as new
    trace ids stream in and reads it when building error payloads.
    """
    parser = EventParser()

    async with client.stream(
        "POST",
        url,
        content=json.dumps(body, ensure_ascii=False).encode(),
        headers=headers,
    ) as upstream:
        if upstream.status_code != 200:
            error_body = await upstream.aread()
            detail = "Chat request failed."
            code: str | None = None
            if error_body.startswith(b"{"):
                try:
                    parsed = json.loads(error_body)
                    detail = parsed.get("message", detail) or detail
                    code = parsed.get("code")
                except json.JSONDecodeError:
                    pass
            error_payload: dict[str, Any] = {
                "type": "error",
                "message": detail,
            }
            if code:
                error_payload["code"] = code
            if round_state.trace_id_for_error:
                error_payload["trace_id"] = round_state.trace_id_for_error
            round_state.emitted_terminal_error = True
            yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n".encode()
            return

        try:
            async for chunk in upstream.aiter_bytes():
                result = parser.parse(chunk)
                if result.has_error_event:
                    round_state.seen_upstream_error = True
                if result.finish_tool_calls:
                    round_state.finish_tool_calls = True
                round_state.tool_input_events.extend(result.tool_input_events)
                round_state.assistant_text += result.text_delta
                if result.chat_trace_id is not None:
                    round_state.trace_id = result.chat_trace_id
                    round_state.trace_id_for_error = result.chat_trace_id
                if result.lines_to_forward:
                    yield b"\n".join(result.lines_to_forward) + b"\n"
        except httpx.RemoteProtocolError:
            if round_state.finish_tool_calls:
                logger.debug(
                    "Connection closed after streamed tool boundary "
                    "(AI SDK tool-calls finish; expected)"
                )
            elif round_state.seen_upstream_error:
                # we already passed on an error coming out of upstream server, the UI should be rendering it
                # we don't need to also tell it the stream was closed by the upstream server
                logger.debug(
                    "Connection closed after upstream error event; "
                    "suppressing duplicate error"
                )
            else:
                trace_id = round_state.trace_id_for_error or str(uuid.uuid4())
                error_payload = {
                    "type": "error",
                    "message": "Something went wrong.",
                    "trace_id": trace_id,
                }
                round_state.emitted_terminal_error = True
                yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n".encode()
                logger.exception(
                    "RemoteProtocolError during streaming (trace_id=%s)",
                    trace_id,
                )


async def execute_tool_batch(
    tool_calls: list[ToolCallInfo],
    decisions: dict[str, bool],
) -> dict[str, str]:
    results: dict[str, str] = {}
    for tc in tool_calls:
        if tc.requires_approval:
            approved = decisions.get(tc.tool_call_id)
            if approved is not True:
                results[tc.tool_call_id] = DENIED_TOOL_OUTPUT
                continue
        tool_result = await execute_tool(tc.tool_name, tc.input)
        results[tc.tool_call_id] = tool_result
    return results


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
        self._initial_trace_id: str | None = initial_body.get("trace_id")

    async def stream(self):
        """AsyncGenerator yielding SSE bytes to the client."""
        trace_id_for_error: str | None = self._initial_trace_id
        async with httpx.AsyncClient(timeout=CHAT_TIMEOUT) as client:
            for _ in range(MAX_TOOL_ROUNDS):
                round_state = RoundState(trace_id_for_error=trace_id_for_error)

                async for forward_bytes in iter_upstream_round(
                    client,
                    self._upstream_url,
                    self._headers,
                    self._body,
                    round_state,
                ):
                    yield forward_bytes

                trace_id_for_error = round_state.trace_id_for_error

                # A terminal upstream error (iter_upstream_round already emitted
                # the error SSE, or a forwarded upstream error followed by a
                # connection close with no finish boundary) means there's nothing
                # more to drive — end the stream, matching the pre-refactor
                # `return`s.
                if round_state.is_terminal_upstream_error:
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
                        if not tool_input_executor_is_server(e)
                    ]
                    needs_approval = [
                        e for e in client_events if tool_requires_user_approval(e)
                    ]
                    if needs_approval:
                        yield _format_tool_calls_pending_sse(client_events)
                        return

                    expected_tool_count = len(client_events)
                    yield self._format_tool_exec_start(expected_tool_count)
                    tool_results = await self._execute_client_tools(round_state, None)
                    for tc_id, output in tool_results.items():
                        yield self._format_tool_output(tc_id, output)
                    yield self._format_tool_exec_end(len(tool_results))

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

        # Loop exhausted all MAX_TOOL_ROUNDS without a natural exit
        error_payload = {
            "type": "error",
            "message": "Maximum tool rounds exceeded. Please start a new message.",
        }
        if trace_id_for_error:
            error_payload["trace_id"] = trace_id_for_error
        yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n".encode()

    async def _execute_client_tools(
        self,
        round_state: RoundState,
        approval_decisions: dict[str, bool] | None,
    ) -> dict[str, str]:
        tool_calls: list[ToolCallInfo] = []
        for event in round_state.tool_input_events:
            if tool_input_executor_is_server(event):
                logger.debug(
                    "Skipping local tool execution (executor=server): %s (call_id=%s)",
                    event.toolName,
                    event.toolCallId,
                )
                continue
            tool_calls.append(
                ToolCallInfo(
                    toolCallId=event.toolCallId,
                    toolName=event.toolName,
                    input=event.input,
                    requiresApproval=tool_requires_user_approval(event),
                )
            )
        return await execute_tool_batch(tool_calls, approval_decisions or {})

    @staticmethod
    def _format_tool_output(tc_id: str, output: str) -> bytes:
        return f"data: {json.dumps({'type': 'tool-output-available', 'toolCallId': tc_id, 'output': output}, ensure_ascii=False)}\n\n".encode()

    @staticmethod
    def _format_tool_exec_start(tool_count: int) -> bytes:
        payload = {"type": SSE_TYPE_TOOL_EXEC_START, "tool_count": tool_count}
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()

    @staticmethod
    def _format_tool_exec_end(tool_count: int) -> bytes:
        payload = {"type": SSE_TYPE_TOOL_EXEC_END, "tool_count": tool_count}
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


async def execute_tool(tool_name: str, args: dict[str, Any]) -> str:
    """Run a Kiln built-in tool by OpenAI function name; return its output string."""
    logger.info("Executing server tool %s", tool_name)
    args_str = json.dumps(args, default=str, ensure_ascii=False)
    logger.debug("Tool %s args: %.500s", tool_name, args_str)
    tool_id = FUNCTION_NAME_TO_TOOL_ID.get(tool_name)
    if tool_id is None:
        return json.dumps(
            {"error": f"Unknown tool name: {tool_name}"}, ensure_ascii=False
        )
    try:
        tool = tool_from_id(tool_id)
        result = await tool.run(**args)
        return result.output
    except Exception as e:
        logger.exception("Built-in tool %s failed", tool_name)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


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
            args_str = json.dumps(event.input, ensure_ascii=False)
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
