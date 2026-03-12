import json
import logging
from pathlib import Path
from typing import Any

import httpx
from app.desktop.studio_server.api_client.kiln_server_client import (
    _get_base_url,
    _get_common_headers,
)
from app.desktop.studio_server.utils.copilot_utils import get_copilot_api_key
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

_CHAT_TIMEOUT = httpx.Timeout(timeout=300.0, connect=30.0)
_MAX_CLIENT_TOOL_ROUNDS = 5


def _build_upstream_headers(api_key: str) -> dict[str, str]:
    return {
        **_get_common_headers(),
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _execute_client_tool(tool_name: str, arguments: dict[str, Any]) -> str:
    """Execute a client-side tool and return the result as a string."""
    if tool_name == "read_task_run":
        path = arguments.get("path", "")
        try:
            return Path(path).read_text()
        except Exception as e:
            return json.dumps({"error": f"Failed to read task run: {e}"})
    return json.dumps({"error": f"Unknown client tool: {tool_name}"})


def _parse_sse_events(
    raw: bytes,
) -> tuple[list[bytes], dict[str, Any] | None]:
    """Parse raw SSE bytes into passthrough lines and an optional client-tool-call event.

    Returns (lines_to_forward, client_tool_event_or_none).
    """
    lines_to_forward: list[bytes] = []
    client_tool_event: dict[str, Any] | None = None

    for line in raw.split(b"\n"):
        if line.startswith(b"data: "):
            payload = line[6:].strip()
            if payload and payload != b"[DONE]":
                try:
                    event = json.loads(payload)
                    if (
                        isinstance(event, dict)
                        and event.get("type") == "client-tool-call"
                    ):
                        client_tool_event = event
                        continue
                except (json.JSONDecodeError, TypeError):
                    pass
        lines_to_forward.append(line)

    return lines_to_forward, client_tool_event


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
                                lines, tool_event = _parse_sse_events(chunk)
                                if tool_event:
                                    client_tool_event = tool_event
                                forward_bytes = b"\n".join(lines)
                                if forward_bytes.strip():
                                    yield forward_bytes + b"\n"
                        except httpx.RemoteProtocolError:
                            if client_tool_event is not None:
                                logger.debug(
                                    "Connection closed after client tool call event (expected)"
                                )
                            else:
                                raise

                if client_tool_event is None:
                    return

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

        return StreamingResponse(
            content=stream_with_client_tools(),
            media_type="text/event-stream",
        )


def _build_continuation_body(
    original_body: dict[str, Any],
    tool_call_id: str,
    tool_name: str,
    tool_input: Any,
    tool_result: str,
) -> dict[str, Any]:
    """Build the request body for continuing after a client tool call.

    Appends an assistant message (with the tool call) and a tool result message
    so the backend can resume the conversation.
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
            ],
        }
    )

    messages.append(
        {
            "role": "assistant",
            "parts": [
                {
                    "type": f"tool-{tool_name}",
                    "toolCallId": tool_call_id,
                    "toolName": tool_name,
                    "input": tool_input,
                    "output": tool_result,
                    "state": "output-available",
                },
            ],
        }
    )

    return {**original_body, "messages": messages}
