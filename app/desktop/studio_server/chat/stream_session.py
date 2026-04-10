import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

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
    """Accumulated state from one upstream round."""

    finish_tool_calls: bool = False
    tool_input_events: list[ToolInputAvailableEvent] = field(default_factory=list)
    assistant_text: str = ""
    trace_id: str | None = None


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
        "requiresApproval": tool_requires_user_approval(event),
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

    async def stream(self):
        """AsyncGenerator yielding SSE bytes to the client."""
        for _ in range(MAX_TOOL_ROUNDS):
            round_state = RoundState()
            parser = EventParser()
            trace_id_for_error: str | None = None

            async with httpx.AsyncClient(timeout=CHAT_TIMEOUT) as client:
                async with client.stream(
                    "POST",
                    self._upstream_url,
                    content=json.dumps(self._body, ensure_ascii=False).encode(),
                    headers=self._headers,
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
                        if trace_id_for_error:
                            error_payload["trace_id"] = trace_id_for_error
                        yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n".encode()
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
                                "message": "Something went wrong.",
                                "trace_id": trace_id,
                            }
                            yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n".encode()
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
                    if not tool_input_executor_is_server(e)
                ]
                needs_approval = [
                    e for e in client_events if tool_requires_user_approval(e)
                ]
                if needs_approval:
                    # some toolcalls in the batch require approval, so stream them to the client for approval
                    # and client will send the decisions through /api/chat/execute-tools endpoint to continue
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

    async def _execute_client_tools(
        self,
        round_state: RoundState,
        approval_decisions: dict[str, bool] | None,
    ) -> dict[str, str]:
        tool_results: dict[str, str] = {}
        for event in round_state.tool_input_events:
            if tool_input_executor_is_server(event):
                logger.debug(
                    "Skipping local tool execution (executor=server): %s (call_id=%s)",
                    event.toolName,
                    event.toolCallId,
                )
                continue
            tc_id = event.toolCallId
            if tool_requires_user_approval(event):
                if approval_decisions is None or not approval_decisions.get(tc_id):
                    tool_results[tc_id] = DENIED_TOOL_OUTPUT
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
    logger.info(
        "Executing server tool %s with args: %s",
        tool_name,
        json.dumps(args, default=str, ensure_ascii=False),
    )
    tool_id = FUNCTION_NAME_TO_TOOL_ID.get(tool_name)
    if tool_id is None:
        raise ValueError(f"Unknown tool name: {tool_name}")
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
