import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
from fastapi import Request
from kiln_ai.adapters.model_adapters.stream_events import ToolInputAvailableEvent
from kiln_ai.tools.tool_registry import tool_from_id

from app.desktop.studio_server.chat.constants import (
    _CHAT_TIMEOUT,
    _DENIED_TOOL_OUTPUT,
    _FUNCTION_NAME_TO_TOOL_ID,
    _MAX_TOOL_ROUNDS,
    _TOOL_APPROVAL_TIMEOUT_SEC,
)
from app.desktop.studio_server.chat.sse_parser import EventParser
from app.desktop.studio_server.chat.tool_approval import (
    _approval_item_from_event,
    _format_tool_approval_required_sse,
    _register_tool_approval_wait,
    _wait_for_tool_approval,
)
from app.desktop.studio_server.chat.tool_metadata import (
    _tool_input_executor_is_server,
    _tool_requires_user_approval,
)

logger = logging.getLogger(__name__)


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
