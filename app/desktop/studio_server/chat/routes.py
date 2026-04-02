import json

from app.desktop.studio_server.api_client.kiln_server_client import (
    _get_base_url,
    _get_common_headers,
)
from app.desktop.studio_server.utils.copilot_utils import get_copilot_api_key
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from kiln_server.utils.agent_checks.policy import DENY_AGENT
from pydantic import BaseModel

from app.desktop.studio_server.chat.stream_session import ChatStreamSession
from app.desktop.studio_server.chat.tool_approval import submit_tool_approval_decisions


def _build_upstream_headers(api_key: str) -> dict[str, str]:
    return {
        **_get_common_headers(),
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


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
