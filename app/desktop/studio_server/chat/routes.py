import json
from dataclasses import dataclass
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
from app.desktop.studio_server.chat.runtime.models import ConversationRecord
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


# ── Phase 6: desktop-side conversation-key resolution ────────────────────────
#
# The browser keys everything on SESSION ids (functional spec §4: "Browser
# code never sees trace_id") and — since phase 6 — the UPSTREAM API resolves
# either id kind itself (``GET/DELETE /v1/chat/sessions/{id}`` and
# ``session_id`` continuation on ``POST /v1/chat/``, architecture §8). What
# remains desktop-side is purely LOCAL: mapping a key onto a live supervisor
# record when one exists. A key is one of:
#
# - a supervisor session id (``cv_…``) — the LIVE handle (history rows for
#   runtime-known conversations, the browser's attached conversation);
# - an upstream ``root_id`` (``session_meta.root_id``, the first persisted
#   snapshot's id) — the DURABLE handle (cold history rows, the browser's
#   restart-recovery key);
# - a bare upstream leaf id — LEGACY rows only (sessions without
#   ``session_meta`` expose no root; functional spec §4: "legacy sessions
#   resolve as today").
#
# The phase-5 root→leaf list scan (and its ``UpstreamResolutionError`` /
# 503 surface) is GONE: cold keys are forwarded to the upstream verbatim,
# where the pointer index resolves them in O(1) (with the backend's own
# bounded-scan fallback + loud 503 for the indeterminate case — the same
# trust model, now living where the data lives).


@dataclass(frozen=True)
class ResolvedConversationKey:
    """What a browser conversation key resolves to.

    ``record`` is set when the key names a LIVE supervisor conversation (by
    session id, or by any key its whole-chain trace index has seen).
    ``upstream_key`` is the id to hydrate/continue/delete with upstream — the
    backend accepts either id kind (phase 6), so it is: a live record's
    CURRENT leaf when known (strictly fresher than whatever the caller held,
    and an O(1) leaf-first lookup upstream), else the record's durable root /
    adopted resume key, else the browser's key verbatim (cold rows). Both
    fields are None only for a dead ``cv_`` handle (desktop restart/eviction)
    or a live record with nothing persisted yet — callers degrade exactly
    like the old world did with no stored trace.
    """

    record: ConversationRecord | None = None
    upstream_key: str | None = None


def resolve_conversation_key(key: str) -> ResolvedConversationKey:
    """Resolve a browser conversation key (see the section comment above).

    Resolution order (all LOCAL — no upstream I/O since phase 6):

    1. live record by session id — the primary key for runtime-known
       conversations;
    2. live record by the supervisor's whole-chain trace index — an
       upstream-shaped key naming a live conversation (any leaf it ever had,
       or the key it was adopted from) resolves to that record and its
       freshest upstream identity;
    3. ``cv_``-shaped but unknown → a dead desktop handle (the record died
       with a restart/eviction; a ``cv_`` id is desktop-minted and never a
       valid upstream id, so there is nothing to fall through to);
    4. anything else → the key itself, forwarded verbatim: the upstream
       resolves either id kind (root or leaf; garbage keys get the
       upstream's own 400/404, same as the pre-phase-5 world).
    """
    record = conversation_supervisor.get(key)
    if record is None:
        session_id = conversation_supervisor.session_for_trace(key)
        if session_id is not None:
            record = conversation_supervisor.get(session_id)
    if record is not None:
        return ResolvedConversationKey(
            record=record,
            # Preference order mirrors continuation_key_fields: the engine's
            # current leaf is the freshest handle (and O(1) upstream); a
            # key-adopted record with no persist yet falls back to its
            # durable root / adopted key.
            upstream_key=(
                record.current_leaf_trace_id
                or record.root_id
                or record.resume_session_key
            ),
        )
    if key.startswith("cv_"):
        return ResolvedConversationKey()
    return ResolvedConversationKey(upstream_key=key)


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

    # Phase 5: the row's PRIMARY key is a conversation key, never a raw leaf
    # trace id when anything better exists (functional spec §4 "history rows
    # key on session id"): the live record's session id for runtime-known
    # conversations, else the durable upstream root_id, else — legacy
    # sessions without session_meta only — the upstream leaf (opaque to the
    # browser; resolve_conversation_key handles all three on the way back
    # in). The old world keyed rows on the upstream leaf directly.
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
    # The session's durable id (``session_meta.root_id``), passed through
    # from the upstream response (phase 5): the browser persists it as its
    # restart-recovery key — a SESSION id, unlike the leaf-shaped ``id``
    # above, which the browser no longer stores. None for legacy sessions.
    root_id: str | None = None


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
                # resolve the row's leaf trace id (any leaf the session ever
                # had is indexed) to its live record — falling back to the
                # row's ROOT id, which is how a record adopted by root key
                # (phase 6: no leaf known until its first persist) still
                # joins its row. The subagent kind guard matters because
                # parents live on the same supervisor since phases 3–4 — a
                # parent's leaf must never stamp its own row as a sub-agent.
                extra_root = extra.get("root_id")
                live_sid = conversation_supervisor.session_for_trace(item.id) or (
                    conversation_supervisor.session_for_trace(extra_root)
                    if isinstance(extra_root, str)
                    else None
                )
                live_record = (
                    conversation_supervisor.get(live_sid) if live_sid else None
                )
                child_record = (
                    live_record
                    if live_record is not None and live_record.kind == "subagent"
                    else None
                )
                # Phase 5 row key (see ChatSessionListItem.id): the live
                # record's session id when the row's leaf resolves through
                # the supervisor (ANY kind — parents and children, terminal
                # children included, so a finished child's row stays
                # addressable while its record lives), else the durable
                # root_id, else the legacy leaf. resolve_conversation_key is
                # the exact inverse on GET/DELETE/adopt.
                row_id = (
                    live_record.session_id
                    if live_record is not None
                    else (extra.get("root_id") or item.id)
                )
                items.append(
                    ChatSessionListItem.model_validate(
                        {
                            "id": row_id,
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
            Path(
                description=(
                    "Conversation key: a live conversation's session id, an "
                    "upstream root id, or (legacy sessions only) a leaf id."
                )
            ),
        ],
    ) -> ChatSessionSnapshot:
        """Proxy to Kiln Copilot ``GET /v1/chat/sessions/{id}``.

        Phase 6: accepts any browser conversation key. For a LIVE
        conversation the desktop substitutes the record's freshest upstream
        identity (its current leaf — hydration is always fresh); any other
        key is forwarded VERBATIM, because the upstream now resolves either
        id kind itself (root ids via the pointer index, architecture §8 —
        the phase-5 desktop-side root→leaf scan and its 503 surface are
        gone; the upstream owns that failure mode now and this proxy passes
        its status through like any other error). 404 when the key yields
        nothing to forward: a dead ``cv_`` handle after a desktop restart,
        or a live record with nothing persisted yet.
        """
        resolved = resolve_conversation_key(session_id)
        if resolved.upstream_key is None:
            raise HTTPException(
                status_code=404, detail=f"Chat session not found: {session_id}"
            )
        api_key = get_copilot_api_key()
        client = get_authenticated_client(api_key)
        detailed = await get_session_v1_chat_sessions_session_id_get.asyncio_detailed(
            session_id=resolved.upstream_key,
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
        session_id: Annotated[
            str, Path(description="Conversation key of the session to delete.")
        ],
    ) -> None:
        """Proxy to Kiln Copilot ``DELETE /v1/chat/sessions/{id}``.

        Phase 6: accepts any browser conversation key; live records forward
        their freshest upstream identity, cold keys forward verbatim (the
        upstream deletes by either id kind — root ids resolve to the current
        leaf server-side, so the desktop no longer needs the leaf to delete a
        root-keyed session)."""
        resolved = resolve_conversation_key(session_id)
        if resolved.upstream_key is None:
            raise HTTPException(
                status_code=404, detail=f"Chat session not found: {session_id}"
            )
        api_key = get_copilot_api_key()
        client = get_authenticated_client(api_key)
        detailed = (
            await delete_session_v1_chat_sessions_session_id_delete.asyncio_detailed(
                session_id=resolved.upstream_key,
                client=client,
            )
        )
        if detailed.status_code != HTTPStatus.NO_CONTENT:
            _raise_upstream_error(detailed)
        # Cascade: stop children spawned by this session (and drop their pending
        # reports), or stop the sub-agent itself if a child session was deleted.
        # Keyed by the browser's ORIGINAL key: handle_session_deleted resolves
        # a live session id directly and anything else through the whole-chain
        # trace index (which also holds adopted resume keys). (Known corner:
        # the engine's pre-emit leaf stamp can briefly precede indexing if a
        # round then fails terminally before its boundary advance — a delete
        # in that instant misses the cascade for that one unindexed leaf;
        # accepted, self-heals next turn.)
        await orchestration.handle_session_deleted(session_id)
