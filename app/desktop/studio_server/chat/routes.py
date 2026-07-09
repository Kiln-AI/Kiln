import json
import re
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


# ── Phase 5: desktop-side conversation-key resolution ────────────────────────
#
# The browser keys everything on SESSION ids now (functional spec §4:
# "Browser code never sees trace_id") while the UPSTREAM chat API stays
# trace-keyed until phase 6 — so the desktop owns the mapping from the
# browser's opaque conversation key to the upstream leaf. A key is one of:
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
# TODO(phase-6): the root→leaf list scan collapses once the backend accepts
# session ids on ``GET/DELETE /v1/chat/sessions/{id}`` and ``POST /v1/chat/``
# (implementation plan phase 6) — resolution then forwards the key verbatim.

# Bounds for the root→leaf scan: the upstream list is the only root-keyed
# source until phase 6 (each row carries BOTH ids), so resolution pages
# through it. Mirrors the "bounded leaf scan" trust model architecture §8
# specifies for the backend's own pointer fallback.
#
# Accepted cost (phase-5 CR LOW 4): a legacy leaf-shaped key pays one list
# page per resolution (it can never match a root, but only a completed scan
# can prove that). Deliberately NOT cached — history opens fetched the same
# list moments earlier and the common case is a single page; phase 6 makes
# the whole scan moot (the backend resolves either id kind itself).
_ROOT_SCAN_PAGE_SIZE = 100
_ROOT_SCAN_MAX_PAGES = 10


class UpstreamResolutionError(Exception):
    """Root→leaf resolution could not be COMPLETED (phase-5 CR MEDIUM 1 /
    LOW 4).

    Raised when the upstream sessions list is unreachable / errors, or when
    the page bound is exhausted with pages remaining — in both cases "is
    this key a root id?" is INDETERMINATE, which must never be conflated
    with the completed-scan-no-match result (None, the by-design legacy-leaf
    fall-through): falling through on an indeterminate scan would treat the
    ROOT snapshot as the current leaf — a silent conversation fork from
    turn 1 on create/adopt, or a stale first-turn transcript on GET. Callers
    map this to a loud 503 instead.
    """


# Upstream snapshot ids (roots AND leaves — a root IS the first snapshot's
# id) start with a 10-digit reverse-timestamp prefix (the backend's
# ``ChatSnapshot.validate_id`` contract). Keys without that shape can never
# match a ``root_id``, so the scan is skipped for them — a garbage or dead
# key must not cost an upstream list walk.
_SNAPSHOT_ID_PREFIX_RE = re.compile(r"^\d{10}_")


@dataclass(frozen=True)
class ResolvedConversationKey:
    """What a browser conversation key resolves to.

    ``record`` is set when the key names a LIVE supervisor conversation (by
    session id, or by any leaf its whole-chain trace index has seen).
    ``leaf_trace_id`` is the upstream id to hydrate/continue from — for live
    records the record's CURRENT leaf (strictly fresher than whatever the
    caller held; this replaces the deleted ``current_trace_id`` refresh the
    browser used to do). ``root_id`` rides along when resolution learned it.
    All three are None for a dead ``cv_`` handle (desktop restart/eviction) —
    callers degrade exactly like the old world did with no stored trace.
    """

    record: ConversationRecord | None = None
    leaf_trace_id: str | None = None
    root_id: str | None = None


async def _leaf_for_root_id(root_id: str) -> str | None:
    """Resolve an upstream ``root_id`` to the session's CURRENT leaf via the
    upstream sessions list (each row carries ``id`` = leaf AND ``root_id``).

    Kept desktop-side deliberately (phase 5 scope note): cold history rows
    (no live record) must still open, and fetching the FIRST snapshot by its
    id directly would hydrate a truncated first-turn transcript — only the
    list knows the current leaf.

    Three outcomes (phase-5 CR MEDIUM 1 / LOW 4 — the distinction is
    load-bearing):

    - a leaf: the key IS a root id and this is its session's current leaf;
    - ``None``: the FULL list was scanned (a short page ended it) and no row
      matches — the key is not a root id, so the caller's legacy-leaf
      fall-through is correct by construction;
    - ``UpstreamResolutionError``: transport failure, upstream error, or the
      page bound exhausted with pages remaining — indeterminate, never
      fall-through material.
    """
    api_key = get_copilot_api_key()
    client = get_authenticated_client(api_key)
    offset = 0
    for _ in range(_ROOT_SCAN_MAX_PAGES):
        try:
            detailed = await list_sessions_v1_chat_sessions_get.asyncio_detailed(
                client=client,
                limit=_ROOT_SCAN_PAGE_SIZE,
                offset=offset,
            )
        except httpx.HTTPError as exc:
            raise UpstreamResolutionError(
                f"Upstream sessions list unreachable while resolving {root_id}"
            ) from exc
        if detailed.status_code != HTTPStatus.OK or not isinstance(
            detailed.parsed, list
        ):
            raise UpstreamResolutionError(
                f"Upstream sessions list returned {detailed.status_code} "
                f"while resolving {root_id}"
            )
        for item in detailed.parsed:
            if not isinstance(item, ApiSessionListItem):
                continue
            if item.additional_properties.get("root_id") == root_id:
                return item.id
        if len(detailed.parsed) < _ROOT_SCAN_PAGE_SIZE:
            # Short page ⇒ the list is exhausted: a COMPLETED scan with no
            # match — the only case where "not a root id" is proven.
            return None
        offset += _ROOT_SCAN_PAGE_SIZE
    # Page bound hit with pages remaining: indeterminate (LOW 4 — failing
    # open here would misread a beyond-bound root as a legacy leaf).
    raise UpstreamResolutionError(
        f"Root scan bound ({_ROOT_SCAN_MAX_PAGES} pages) exhausted while "
        f"resolving {root_id}"
    )


async def resolve_conversation_key(key: str) -> ResolvedConversationKey:
    """Resolve a browser conversation key (see the section comment above).

    Resolution order:

    1. live record by session id — the primary key for runtime-known
       conversations;
    2. live record by the supervisor's whole-chain trace index — a legacy
       leaf-shaped key naming a live conversation resolves to that record
       (and its CURRENT leaf, which may be many rounds fresher);
    3. ``cv_``-shaped but unknown → a dead desktop handle (the record died
       with a restart/eviction; a ``cv_`` id is desktop-minted and never a
       valid upstream id, so there is nothing to fall through to);
    4. upstream root→leaf scan (cold history rows);
    5. the key itself as a leaf (legacy rows) — reached only when step 4
       COMPLETED with no match (or was skipped for a non-snapshot-shaped
       key).

    Raises ``UpstreamResolutionError`` when step 4 could not complete
    (CR MEDIUM 1): an indeterminate scan must never degrade into the leaf
    interpretation — callers answer 503 so the browser retries instead of
    silently forking/staling the conversation.
    """
    record = conversation_supervisor.get(key)
    if record is None:
        session_id = conversation_supervisor.session_for_trace(key)
        if session_id is not None:
            record = conversation_supervisor.get(session_id)
    if record is not None:
        return ResolvedConversationKey(
            record=record,
            leaf_trace_id=record.current_leaf_trace_id,
            root_id=record.root_id,
        )
    if key.startswith("cv_"):
        return ResolvedConversationKey()
    if _SNAPSHOT_ID_PREFIX_RE.match(key):
        # Only snapshot-shaped keys can be upstream root ids; fetching a ROOT
        # directly would return the FIRST (stale) snapshot, so the scan must
        # run before the leaf interpretation.
        leaf = await _leaf_for_root_id(key)
        if leaf is not None:
            return ResolvedConversationKey(leaf_trace_id=leaf, root_id=key)
    return ResolvedConversationKey(leaf_trace_id=key)


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
                # had is indexed) to its live record. The subagent kind guard
                # matters because parents live on the same supervisor since
                # phases 3–4 — a parent's leaf must never stamp its own row
                # as a sub-agent.
                live_sid = conversation_supervisor.session_for_trace(item.id)
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
        """Proxy to Kiln Copilot ``GET /v1/chat/sessions/{leaf}``.

        Phase 5: accepts any browser conversation key and resolves the
        upstream leaf DESKTOP-side (``resolve_conversation_key``) — for a
        live conversation that is the record's CURRENT leaf, so hydration is
        always fresh (the browser used to refresh a ``current_trace_id``
        itself; that field is gone). 404 when the key yields no leaf: a dead
        ``cv_`` handle after a desktop restart, or a live record with nothing
        persisted yet. 503 when the root→leaf scan couldn't COMPLETE
        (CR MEDIUM 1 / LOW 4): serving the key-as-leaf on an indeterminate
        scan could return the stale FIRST snapshot of a root-keyed session —
        fail clean and let the client retry (only a completed-no-match scan
        falls through, which is the by-design legacy-leaf path).
        """
        try:
            resolved = await resolve_conversation_key(session_id)
        except UpstreamResolutionError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        if resolved.leaf_trace_id is None:
            raise HTTPException(
                status_code=404, detail=f"Chat session not found: {session_id}"
            )
        api_key = get_copilot_api_key()
        client = get_authenticated_client(api_key)
        detailed = await get_session_v1_chat_sessions_session_id_get.asyncio_detailed(
            session_id=resolved.leaf_trace_id,
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
        """Proxy to Kiln Copilot ``DELETE /v1/chat/sessions/{leaf}``.

        Phase 5: accepts any browser conversation key; the upstream DELETE is
        leaf-keyed until phase 6, so the leaf is resolved desktop-side like
        the GET above — including the 503 on an indeterminate root scan
        (deleting the key-as-leaf could delete the WRONG snapshot of a
        root-keyed session)."""
        try:
            resolved = await resolve_conversation_key(session_id)
        except UpstreamResolutionError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        if resolved.leaf_trace_id is None:
            raise HTTPException(
                status_code=404, detail=f"Chat session not found: {session_id}"
            )
        api_key = get_copilot_api_key()
        client = get_authenticated_client(api_key)
        detailed = (
            await delete_session_v1_chat_sessions_session_id_delete.asyncio_detailed(
                session_id=resolved.leaf_trace_id,
                client=client,
            )
        )
        if detailed.status_code != HTTPStatus.NO_CONTENT:
            _raise_upstream_error(detailed)
        # Cascade: stop children spawned by this session (and drop their pending
        # reports), or stop the sub-agent itself if a child session was deleted.
        # Keyed by the resolved LEAF: handle_session_deleted resolves it back
        # through the whole-chain trace index, and a live record's current
        # leaf is always indexed. (Known corner: the engine's pre-emit leaf
        # stamp can briefly precede indexing if a round then fails terminally
        # before its boundary advance — a delete in that instant misses the
        # cascade for that one unindexed leaf; accepted, self-heals next turn.)
        await orchestration.handle_session_deleted(resolved.leaf_trace_id)
