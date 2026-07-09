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
from app.desktop.studio_server.chat import orchestration
from app.desktop.studio_server.chat.runtime.supervisor import conversation_supervisor
from app.desktop.studio_server.utils.copilot_utils import get_copilot_api_key
from fastapi import FastAPI, HTTPException, Path, Query
from kiln_server.utils.agent_checks.policy import DENY_AGENT
from pydantic import BaseModel, ConfigDict, ValidationError


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
    # Live auto-mode join from the in-memory conversation supervisor (phase 3
    # moved it off the deleted AutoChatRegistry). Wire names unchanged so the
    # history UI ports mechanically, but auto_run_id now carries the auto
    # CONVERSATION's session id (cv_…, addressable via /api/conversations) —
    # the same rename-by-value the phase-2 subagent_id join did. auto_active
    # stays flag-on semantics (RUNNING or IDLE — the green dot persists while
    # the run idles between bursts; old AutoRunStatus.flag_on).
    auto_active: bool = False
    auto_run_id: str | None = None
    # Sub-agent lineage. agent_type/root_id/parent_root_id come from the
    # upstream session meta (durable, survives app restarts); subagent_id/
    # subagent_status are joined from the in-memory conversation supervisor
    # (live runs only). The wire names are unchanged across the phase-2
    # migration so the history UI needs no changes, but the VALUES moved to
    # the unified vocabulary: subagent_id now carries the child's conversation
    # session id (cv_…, addressable via /api/conversations) and
    # subagent_status carries a RunState value (same strings as the old
    # SubAgentStatus for every reachable state).
    agent_type: str | None = None
    root_id: str | None = None
    parent_root_id: str | None = None
    is_subagent: bool = False
    subagent_id: str | None = None
    subagent_status: str | None = None


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


def connect_chat_api(app: FastAPI) -> None:
    """Register the surviving ``/api/chat/*`` routes.

    Phase 4 shrank this surface to exactly what the architecture (§1) says
    ``routes.py`` keeps: the HISTORY PROXIES (``/api/chat/sessions*`` —
    upstream session list/get/delete, joined with live supervisor state) and
    the VERSION POLICY proxy. The old interactive endpoints —
    ``POST /api/chat`` (the request-scoped chat loop) and
    ``POST /api/chat/execute-tools`` (the approval continuation) — are gone:
    interactive conversations run on the unified runtime behind
    ``/api/conversations`` (create/adopt + messages + approvals; see
    ``chat/runtime/api.py`` for the full old→new mapping).
    """

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
                # Server-side join against the in-memory conversation
                # supervisor so the UI gets a single, point-in-time view of
                # which sessions are actively running in auto mode (no
                # two-list correlation client side; old
                # auto_chat_registry.is_active_for_trace). auto_record_for_
                # trace resolves any leaf the conversation ever had and
                # filters to flag-ON auto records — the green dot persists
                # while idle between bursts, disappears once stopped/disabled.
                # A sub-ms race here is self-healing on the next refresh.
                auto_record = conversation_supervisor.auto_record_for_trace(item.id)
                auto_active = auto_record is not None
                auto_run_id = auto_record.session_id if auto_record else None
                # Durable lineage from the upstream session meta rides in the
                # generated SDK's additional_properties (the SDK model predates
                # these fields; regeneration isn't needed to read them).
                extra = item.additional_properties
                # Live-run join against the in-memory conversation supervisor:
                # resolve the row's leaf trace id (any leaf the child session
                # ever had is indexed) to a live sub-agent record. The kind
                # guard matters once phases 3–4 put parent conversations on
                # the same supervisor — a parent's leaf must never stamp its
                # own row as a sub-agent.
                child_sid = conversation_supervisor.session_for_trace(item.id)
                child_record = (
                    conversation_supervisor.get(child_sid) if child_sid else None
                )
                if child_record is not None and child_record.kind != "subagent":
                    child_record = None
                items.append(
                    ChatSessionListItem.model_validate(
                        {
                            "id": item.id,
                            "title": item.title,
                            "updated_at": item.updated_at,
                            "auto_active": auto_active,
                            "auto_run_id": auto_run_id,
                            "agent_type": extra.get("agent_type"),
                            "root_id": extra.get("root_id"),
                            "parent_root_id": extra.get("parent_root_id"),
                            "is_subagent": bool(extra.get("is_subagent")),
                            "subagent_id": (
                                child_record.session_id if child_record else None
                            ),
                            "subagent_status": (
                                child_record.state.value if child_record else None
                            ),
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
        # Cascade: stop children spawned by this session (and drop their pending
        # reports), or stop the sub-agent itself if a child session was deleted.
        await orchestration.handle_session_deleted(session_id)
