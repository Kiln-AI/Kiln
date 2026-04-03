import json
from datetime import datetime
from http import HTTPStatus
from typing import Any, NoReturn

from app.desktop.studio_server.api_client.kiln_ai_server_client.api.chat import (
    delete_session_v1_chat_sessions_session_id_delete,
    get_session_v1_chat_sessions_session_id_get,
    list_sessions_v1_chat_sessions_get,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.types import (
    Response as KilnResponse,
)
from app.desktop.studio_server.api_client.kiln_server_client import (
    _get_base_url,
    _get_common_headers,
    get_authenticated_client,
)
from app.desktop.studio_server.chat.stream_session import (
    ChatStreamSession,
    ToolCallInfo,
    execute_tool_batch,
)
from app.desktop.studio_server.utils.copilot_utils import get_copilot_api_key
from fastapi import FastAPI, HTTPException, Path, Request
from fastapi.responses import StreamingResponse
from kiln_server.utils.agent_checks.policy import DENY_AGENT
from pydantic import BaseModel, ConfigDict


def _build_upstream_headers(api_key: str) -> dict[str, str]:
    return {
        **_get_common_headers(),
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _raise_upstream_error(detailed: KilnResponse) -> NoReturn:
    try:
        body = json.loads(detailed.content) if detailed.content else None
    except (json.JSONDecodeError, TypeError):
        body = None
    detail = body.get("detail", body) if isinstance(body, dict) else body
    raise HTTPException(status_code=detailed.status_code.value, detail=detail)


class ChatSessionListItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    title: str | None = None
    updated_at: datetime | None = None


class TraceToolCallFunction(BaseModel):
    name: str
    arguments: str


class TraceToolCall(BaseModel):
    id: str
    type: str = "function"
    function: TraceToolCallFunction


class TraceMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: str
    content: str | list[dict[str, Any]] | None = None
    tool_calls: list[TraceToolCall] | None = None
    tool_call_id: str | None = None
    reasoning_content: str | None = None


class TaskRunSnapshot(BaseModel):
    model_config = ConfigDict(extra="allow")

    trace: list[TraceMessage] | None = None


class ChatSessionSnapshot(BaseModel):
    id: str
    task_run: TaskRunSnapshot


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

    @app.get(
        "/api/chat/sessions",
        summary="List chat sessions",
        tags=["Copilot"],
        openapi_extra=DENY_AGENT,
    )
    async def list_chat_sessions() -> list[ChatSessionListItem]:
        """Proxy to Kiln Copilot ``GET /v1/chat/sessions``."""
        api_key = get_copilot_api_key()
        client = get_authenticated_client(api_key)
        detailed = await list_sessions_v1_chat_sessions_get.asyncio_detailed(
            client=client,
        )
        if detailed.status_code == HTTPStatus.OK and detailed.parsed is not None:
            return [
                ChatSessionListItem.model_validate(item.to_dict())
                for item in detailed.parsed
            ]
        _raise_upstream_error(detailed)

    @app.get(
        "/api/chat/sessions/{session_id}",
        summary="Get chat session",
        tags=["Copilot"],
        openapi_extra=DENY_AGENT,
        response_model_exclude_none=True,
    )
    async def get_chat_session(
        session_id: str = Path(
            ...,
            description="Chat session id (same as trace id for continuation).",
        ),
    ) -> ChatSessionSnapshot:
        """Proxy to Kiln Copilot ``GET /v1/chat/sessions/{session_id}``."""
        api_key = get_copilot_api_key()
        client = get_authenticated_client(api_key)
        detailed = await get_session_v1_chat_sessions_session_id_get.asyncio_detailed(
            session_id=str(session_id),
            client=client,
        )
        if detailed.status_code == HTTPStatus.OK and detailed.parsed is not None:
            return ChatSessionSnapshot.model_validate(detailed.parsed.to_dict())
        _raise_upstream_error(detailed)

    @app.delete(
        "/api/chat/sessions/{session_id}",
        summary="Delete chat session",
        tags=["Copilot"],
        openapi_extra=DENY_AGENT,
        status_code=204,
    )
    async def delete_chat_session(
        session_id: str = Path(..., description="Chat session id to delete."),
    ) -> None:
        """Proxy to Kiln Copilot ``DELETE /v1/chat/sessions/{session_id}``."""
        api_key = get_copilot_api_key()
        client = get_authenticated_client(api_key)
        detailed = (
            await delete_session_v1_chat_sessions_session_id_delete.asyncio_detailed(
                session_id=session_id,
                client=client,
            )
        )
        if detailed.status_code != HTTPStatus.NO_CONTENT:
            _raise_upstream_error(detailed)

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
