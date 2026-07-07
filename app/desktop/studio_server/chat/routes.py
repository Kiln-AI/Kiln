import json
from datetime import datetime
from http import HTTPStatus
from typing import Annotated, Any, NoReturn

import httpx

from app.desktop.studio_server.api_client.kiln_ai_server_client.api.chat import (
    delete_session_v1_chat_sessions_session_id_delete,
    get_session_v1_chat_sessions_session_id_get,
    list_sessions_v1_chat_sessions_get,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.chat_session_list_item import (
    ChatSessionListItem as ApiSessionListItem,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.types import (
    Response as KilnResponse,
)
from app.desktop.studio_server.api_client.kiln_server_client import (
    _get_base_url,
    _get_common_headers,
    get_authenticated_client,
)
from app.desktop.studio_server.chat.auto.registry import auto_chat_registry
from app.desktop.studio_server.chat.stream_session import (
    ChatStreamSession,
    ToolCallInfo,
    execute_tool_batch,
)
from app.desktop.studio_server.utils.copilot_utils import get_copilot_api_key
from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.responses import StreamingResponse
from kiln_server.cancellable_streaming_response import CancellableStreamingResponse
from kiln_server.git_sync_decorators import no_write_lock
from kiln_ai.utils import spend_ledger
from kiln_server.utils.agent_checks.policy import ALLOW_AGENT, DENY_AGENT
from pydantic import BaseModel, ConfigDict, ValidationError


def _require_valid_conversation_id(conversation_id: str | None) -> None:
    """400 on a malformed client-supplied conversation_id before it is forwarded
    upstream / used to key the spend ledger — matching the budget endpoints, so a
    buggy client gets a clear error instead of silently untracked spend."""
    if conversation_id is not None and not spend_ledger.is_valid_conversation_id(
        conversation_id
    ):
        raise HTTPException(status_code=400, detail="Invalid conversation id")


def _build_upstream_headers(api_key: str) -> dict[str, str]:
    return {
        **_get_common_headers(),
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _upstream_chat_url() -> str:
    """Upstream Kiln Copilot ``/v1/chat/`` continuation URL.

    Shared by the interactive routes here and the auto-mode API so the path is
    built in exactly one place."""
    return f"{_get_base_url()}/v1/chat/"


def _raise_upstream_error(detailed: KilnResponse) -> NoReturn:
    try:
        body = json.loads(detailed.content) if detailed.content else None
    except (json.JSONDecodeError, TypeError):
        body = None
    if isinstance(body, dict):
        detail: Any = body.get("detail") or body.get("message") or body
        code = body.get("code")
        if code and isinstance(detail, str):
            detail = {"message": detail, "code": code}
    else:
        detail = body
    raise HTTPException(status_code=detailed.status_code.value, detail=detail)


class ChatSessionListItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    title: str | None = None
    updated_at: datetime | None = None
    auto_active: bool = False
    auto_run_id: str | None = None


class ClientVersionPolicy(BaseModel):
    model_config = ConfigDict(extra="ignore")

    required: bool = False
    upgrade_nudge_version: str | None = None


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


class ContextUsage(BaseModel):
    """Proxy mirror of the kiln_server ``ContextUsage`` value object.

    Carries only the gauge numbers and the ``compacted`` flag — never any trace
    content — so it is safe to surface to the web UI. Every field is optional so
    an older upstream that doesn't emit ``context_usage`` (or emits a partial
    object) never 500s the proxy; the web UI hides the gauge when it's absent.
    """

    model_config = ConfigDict(extra="ignore")

    context_tokens: int | None = None
    context_limit: int | None = None
    context_percent: float | None = None
    compacted: bool | None = None


class ChatSessionSnapshot(BaseModel):
    # ``extra="ignore"`` (explicit, matching Pydantic v2's default) is the
    # containment boundary (functional_spec.md §7.3): the upstream JSON is
    # re-emitted by the generated SDK's ``to_dict()`` and may carry the
    # server-only ``compacted_trace``; ``ignore`` silently DROPS that unknown key
    # so the full uncompacted ``task_run.trace`` is the only conversation the web
    # UI ever receives. Do NOT change to ``extra="forbid"`` — forbid does not
    # strip, it RAISES ValidationError, which would turn a leaked key into a 500.
    model_config = ConfigDict(extra="ignore")

    id: str
    task_run: TaskRunSnapshot
    context_usage: ContextUsage | None = None
    # Stable conversation identity persisted upstream; lets a client that lost
    # local state (new tab, history restore) re-learn it and re-bind the
    # conversation's spend budget.
    conversation_id: str | None = None


class ChatRequestMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: str
    content: str | list[dict[str, Any]] | None = None


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    messages: list[ChatRequestMessage]
    trace_id: str | None = None
    # Client-minted stable conversation identity (uuid4). Forwarded upstream
    # (the copilot backend persists it on snapshots) and used locally to key
    # the conversation's spend budget.
    conversation_id: str | None = None


class ExecuteToolsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    trace_id: str
    tool_calls: list[ToolCallInfo]
    decisions: dict[str, bool]
    conversation_id: str | None = None


class BudgetStatusResponse(BaseModel):
    """A conversation's spend-budget state, from the local spend ledger."""

    conversation_id: str
    budget_usd: float | None = None
    spent_usd: float = 0.0
    remaining_usd: float | None = None
    exhausted: bool = False
    # Model calls LiteLLM couldn't price (local/custom models); they debit
    # nothing, so when > 0 the budget is only partially tracked.
    unpriced_runs: int = 0
    unpriced_tokens: int = 0

    @classmethod
    def from_status(cls, status: spend_ledger.BudgetStatus) -> "BudgetStatusResponse":
        return cls(
            conversation_id=status.conversation_id,
            budget_usd=status.budget_usd,
            spent_usd=status.spent_usd,
            remaining_usd=status.remaining_usd,
            exhausted=status.exhausted,
            unpriced_runs=status.unpriced_runs,
            unpriced_tokens=status.unpriced_tokens,
        )


class SetBudgetRequest(BaseModel):
    # None clears the budget (spend tracking continues).
    budget_usd: float | None = None


def connect_chat_api(app: FastAPI) -> None:
    @app.post(
        "/api/chat/execute-tools",
        summary="Execute approved client tools and continue chat stream",
        tags=["Copilot"],
        openapi_extra=DENY_AGENT,
    )
    @no_write_lock
    async def post_execute_tools(body: ExecuteToolsRequest) -> StreamingResponse:
        """
        Tool calls that require user approval are streamed to the client for approval, along with the
        other toolcalls part of the same turn. The user must approve / reject all the approval-requiring
        toolcalls in the UI, then send back the decisions through this endpoint, which will execute
        the toolcalls and continue the chat stream.
        """
        _require_valid_conversation_id(body.conversation_id)
        api_key = get_copilot_api_key()
        tool_results = await execute_tool_batch(
            body.tool_calls, body.decisions, conversation_id=body.conversation_id
        )
        continuation_body: dict[str, Any] = {
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
        if body.conversation_id is not None:
            continuation_body["conversation_id"] = body.conversation_id
        session = ChatStreamSession(
            upstream_url=_upstream_chat_url(),
            headers=_build_upstream_headers(api_key),
            initial_body=continuation_body,
        )

        async def generate():
            yield ChatStreamSession._format_tool_exec_start(len(tool_results))
            for tc_id, output in tool_results.items():
                yield ChatStreamSession._format_tool_output(tc_id, output)
            yield ChatStreamSession._format_tool_exec_end(len(tool_results))
            async for chunk in session.stream():
                yield chunk

        return CancellableStreamingResponse(
            content=generate(),
            media_type="text/event-stream",
        )

    @app.get(
        "/api/chat/version_policy",
        summary="Client version policy",
        tags=["Copilot"],
        openapi_extra=DENY_AGENT,
    )
    async def chat_version_policy() -> ClientVersionPolicy:
        """Proxy to Kiln Copilot ``GET /v1/chat/version_policy``.

        Lets the assistant page show the upgrade banners on load. Forwards the
        desktop version header so the server can compute the verdict; on any
        upstream/transport failure we degrade to "no banner" rather than error.
        """
        api_key = get_copilot_api_key()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{_get_base_url()}/v1/chat/version_policy",
                    headers=_build_upstream_headers(api_key),
                )
        except httpx.HTTPError:
            return ClientVersionPolicy()
        if resp.status_code != HTTPStatus.OK:
            return ClientVersionPolicy()
        try:
            return ClientVersionPolicy.model_validate(resp.json())
        except (json.JSONDecodeError, ValidationError):
            # Pydantic v2 ValidationError is not a ValueError, so catch it
            # explicitly — a malformed upstream body degrades to "no banner".
            return ClientVersionPolicy()

    @app.get(
        "/api/chat/sessions",
        summary="List chat sessions",
        tags=["Copilot"],
        openapi_extra=DENY_AGENT,
    )
    async def list_chat_sessions(
        limit: Annotated[
            int, Query(description="Maximum number of sessions to return")
        ] = 50,
        offset: Annotated[int, Query(description="Number of sessions to skip")] = 0,
    ) -> list[ChatSessionListItem]:
        """Proxy to Kiln Copilot ``GET /v1/chat/sessions``."""
        api_key = get_copilot_api_key()
        client = get_authenticated_client(api_key)
        detailed = await list_sessions_v1_chat_sessions_get.asyncio_detailed(
            client=client,
            limit=limit,
            offset=offset,
        )
        if detailed.status_code == HTTPStatus.OK and isinstance(detailed.parsed, list):
            items: list[ChatSessionListItem] = []
            for item in detailed.parsed:
                if not isinstance(item, ApiSessionListItem):
                    continue
                # Server-side join against the in-memory auto-run registry so the
                # UI gets a single, point-in-time view of which sessions are
                # actively running in auto mode (no two-list correlation client
                # side). A sub-ms race here is self-healing on the next refresh.
                auto_active, auto_run_id = auto_chat_registry.is_active_for_trace(
                    item.id
                )
                items.append(
                    ChatSessionListItem.model_validate(
                        {
                            "id": item.id,
                            "title": item.title,
                            "updated_at": item.updated_at,
                            "auto_active": auto_active,
                            "auto_run_id": auto_run_id,
                        }
                    )
                )
            return items
        _raise_upstream_error(detailed)

    @app.get(
        "/api/chat/sessions/{session_id}",
        summary="Get chat session",
        tags=["Copilot"],
        openapi_extra=DENY_AGENT,
        response_model_exclude_none=True,
    )
    async def get_chat_session(
        session_id: Annotated[
            str,
            Path(description="Chat session id (same as trace id for continuation)."),
        ],
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
        session_id: Annotated[str, Path(description="Chat session id to delete.")],
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

    @app.get(
        "/api/chat/budget/{conversation_id}",
        summary="Get conversation spend budget",
        tags=["Copilot"],
        # Readable by the assistant so the model can check its remaining budget.
        openapi_extra=ALLOW_AGENT,
    )
    # Sync def (not async): the body does blocking ledger disk I/O and awaits
    # nothing, so FastAPI runs it in a threadpool instead of on the event loop.
    # (The conversation contextvar set by the middleware propagates into the
    # threadpool via contextvars context copy.)
    def get_chat_budget(
        conversation_id: Annotated[
            str, Path(description="Stable conversation id (uuid4).")
        ],
    ) -> BudgetStatusResponse | None:
        """The conversation's spend-budget status; null when nothing recorded."""
        _require_valid_conversation_id(conversation_id)
        # ALLOW_AGENT: the assistant can call this. Scope its reads to its own
        # conversation — when this request carries the conversation contextvar
        # (set by the budget middleware from the X-Kiln-Conversation-Id header an
        # assistant call_kiln_api stamps), reject a mismatched id so the model
        # can't read another conversation's spend. UI requests carry no header,
        # so the contextvar is unset and any conversation is readable.
        bound = spend_ledger.current_conversation_id.get()
        if bound is not None and bound != conversation_id:
            raise HTTPException(
                status_code=403,
                detail="conversation_id does not match the active conversation",
            )
        status = spend_ledger.get_status(conversation_id)
        if status is None:
            return None
        return BudgetStatusResponse.from_status(status)

    @app.post(
        "/api/chat/budget/{conversation_id}",
        summary="Set conversation spend budget",
        tags=["Copilot"],
        # The assistant must never raise its own budget — user-only endpoint.
        openapi_extra=DENY_AGENT,
    )
    # Sync def: blocking ledger disk I/O, no awaits — runs in FastAPI's threadpool.
    def set_chat_budget(
        conversation_id: Annotated[
            str, Path(description="Stable conversation id (uuid4).")
        ],
        body: SetBudgetRequest,
    ) -> BudgetStatusResponse:
        """Set or extend (absolute value) the conversation's USD spend budget."""
        _require_valid_conversation_id(conversation_id)
        try:
            status = spend_ledger.set_budget(conversation_id, body.budget_usd)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return BudgetStatusResponse.from_status(status)

    @app.post(
        "/api/chat",
        summary="Stream Chat",
        tags=["Copilot"],
        openapi_extra=DENY_AGENT,
    )
    @no_write_lock
    async def chat(body: ChatRequest) -> StreamingResponse:
        """Forward chat to Kiln Copilot and stream AI SDK events as Server-Sent Events."""
        _require_valid_conversation_id(body.conversation_id)
        api_key = get_copilot_api_key()

        session = ChatStreamSession(
            upstream_url=_upstream_chat_url(),
            headers=_build_upstream_headers(api_key),
            initial_body=body.model_dump(exclude_none=True),
        )
        return CancellableStreamingResponse(
            content=session.stream(),
            media_type="text/event-stream",
        )
