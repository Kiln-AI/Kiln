import json

from app.desktop.studio_server.api_client.kiln_server_client import (
    _get_base_url,
    _get_common_headers,
)
from app.desktop.studio_server.chat.stream_session import (
    ChatStreamSession,
    ToolCallInfo,
    execute_tool_batch,
)
from app.desktop.studio_server.utils.copilot_utils import get_copilot_api_key
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from kiln_server.utils.agent_checks.policy import DENY_AGENT
from pydantic import BaseModel, ConfigDict


def _build_upstream_headers(api_key: str) -> dict[str, str]:
    return {
        **_get_common_headers(),
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


class ExecuteToolsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    trace_id: str
    tool_calls: list[ToolCallInfo]
    decisions: dict[str, bool]


def connect_chat_api(app: FastAPI) -> None:
    @app.post(
        "/api/chat/execute-tools",
        summary="Execute approved client tools and continue chat stream",
        tags=["Copilot"],
        openapi_extra=DENY_AGENT,
    )
    async def post_execute_tools(body: ExecuteToolsRequest) -> StreamingResponse:
        """
        Tool calls that require user approval are streamed to the client for approval, along with the
        other toolcalls part of the same turn. The user must approve / reject all the approval-requiring
        toolcalls in the UI, then send back the decisions through this endpoint, which will execute
        the toolcalls and continue the chat stream.
        """
        api_key = get_copilot_api_key()
        tool_results = await execute_tool_batch(body.tool_calls, body.decisions)
        continuation_body: dict = {
            "trace_id": body.trace_id,
            "messages": [
                {
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": output,
                }
                for tc_id, output in tool_results.items()
            ],
        }
        session = ChatStreamSession(
            upstream_url=f"{_get_base_url()}/v1/chat/",
            headers=_build_upstream_headers(api_key),
            initial_body=continuation_body,
        )

        async def generate():
            for tc_id, output in tool_results.items():
                yield ChatStreamSession._format_tool_output(tc_id, output)
            async for chunk in session.stream():
                yield chunk

        return StreamingResponse(
            content=generate(),
            media_type="text/event-stream",
        )

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
        )
        return StreamingResponse(
            content=session.stream(),
            media_type="text/event-stream",
        )
