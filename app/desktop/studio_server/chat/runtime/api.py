"""``/api/conversations`` — the unified browser-facing conversation API.

Phase 2 shipped the CHILDREN SUBSET of the surface specified in the
functional spec §2 (list?parent= / get / events observer SSE / stop /
messages); phase 3 folds the AUTO-MODE surface in, replacing
``/api/chat/auto/*`` one-for-one. Phase 4 adds the interactive endpoints
(approvals / interactive create).

Old → new mapping (behavior preserved, vocabulary unified):

- ``GET  /api/chat/subagents?parent_trace_id=`` → ``GET /api/conversations?parent=``
- ``GET  /api/chat/subagents/events``           → ``GET /api/conversations/events``
- ``GET  /api/chat/subagents/{id}``             → ``GET /api/conversations/{sid}``
- ``GET  /api/chat/subagents/{id}/events``      → ``GET /api/conversations/{sid}/events``
- ``POST /api/chat/subagents/{id}/stop``        → ``POST /api/conversations/{sid}/stop``
- ``POST /api/chat/subagents/{id}/message``     → ``POST /api/conversations/{sid}/messages``
- ``POST /api/chat/auto/enable``                → ``POST /api/conversations`` (create/flip)
- ``POST /api/chat/auto/decline``               → ``POST /api/conversations/auto/decline``
- ``POST /api/chat/auto/{run}/stop``            → ``POST /api/conversations/{sid}/stop``
- ``POST /api/chat/auto/{run}/message``         → ``POST /api/conversations/{sid}/messages``
- ``GET  /api/chat/auto/{run}/events``          → ``GET /api/conversations/{sid}/events``
- ``GET  /api/chat/auto/resolve``               → ``GET /api/conversations/resolve``
- (new, functional spec §2) ``POST /api/conversations/{sid}/auto`` — flag
  flips on an EXISTING conversation.

and the per-kind lifecycle vocabularies (``kiln-subagent-status``,
``auto-mode-on/off/idle/state``) are replaced by the unified
``conversation-state`` event (runtime/sse.py) on both the observer stream
(as the on-subscribe marker and live lifecycle updates) and the
registry-level firehose. The AI-SDK content vocabulary on the observer
stream is untouched.

The desktop↔browser API has no version-skew constraint (they ship together),
so the old surfaces are deleted in the same phase that ports each kind.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any, AsyncGenerator

from fastapi import FastAPI, HTTPException, Path, Query, Response

from app.desktop.studio_server.chat.constants import DENIED_TOOL_OUTPUT
from app.desktop.studio_server.chat.stream_session import (
    ChatStreamSession,
    ToolCallInfo,
)
from app.desktop.studio_server.utils.copilot_utils import get_copilot_api_key

# Keepalive stays the shared jobs helper, exactly as the old auto/sub-agent
# APIs used it (its feeder-task design is what makes a quiet-window timeout
# safe for observer streams).
from app.desktop.studio_server.jobs.events import KeepalivePing, iter_with_keepalive
from kiln_server.cancellable_streaming_response import CancellableStreamingResponse
from kiln_server.git_sync_decorators import no_write_lock
from kiln_server.utils.agent_checks.policy import DENY_AGENT
from pydantic import BaseModel, Field

from .models import ConversationKind, ConversationRecord, RunState
from .sse import format_conversation_state
from .supervisor import ConversationCapError, conversation_supervisor


def _upstream_target() -> tuple[str, dict[str, str]]:
    """Upstream chat URL + auth headers for supervisor-owned runs.

    Lazy import of chat/routes.py (the canonical home of the URL/header
    builders — shared with the interactive proxy so they are built in
    exactly one place): routes.py imports this package's supervisor at
    module level, so a module-level import here would be a cycle.
    """
    from app.desktop.studio_server.chat.routes import (
        _build_upstream_headers,
        _upstream_chat_url,
    )

    return _upstream_chat_url(), _build_upstream_headers(get_copilot_api_key())


logger = logging.getLogger(__name__)

# Quiet-window keepalive for the SSE streams (same value as the old
# auto/sub-agent APIs).
KEEPALIVE_SECONDS = 15.0


class ConversationItem(BaseModel):
    """UI-facing view of one conversation record.

    Field notes:

    - ``state`` uses the unified ``RunState`` vocabulary; every value the old
      ``SubAgentStatus`` could produce keeps its exact string, so terminal
      checks port mechanically.
    - ``current_trace_id`` is the child's latest persisted upstream leaf. It
      exists ONLY so the browser can hydrate history via
      ``/api/chat/sessions/{leaf}`` (which is keyed by leaf trace ids until
      the backend adopts session ids); phase 5 removes it from this surface.
      It rides the REST responses but deliberately NOT the
      ``conversation-state`` event — observers re-fetch the item when they
      need a fresh leaf (see the conversation store's observe()).
    - ``final_report`` is included only when requested with
      ``include_report`` (same contract as the old API).
    """

    session_id: str
    kind: ConversationKind
    state: RunState
    name: str | None = None
    agent_type: str | None = None
    parent_session_id: str | None = None
    current_trace_id: str | None = None
    auto_flag: bool = False
    idle_reason: str | None = None
    rounds_used: int = 0
    report_available: bool = False
    report_delivered: bool = False
    final_report: str | None = None

    @classmethod
    def from_record(
        cls, record: ConversationRecord, include_report: bool = False
    ) -> "ConversationItem":
        return cls(
            session_id=record.session_id,
            kind=record.kind,
            state=record.state,
            name=record.name,
            agent_type=record.agent_type,
            parent_session_id=record.parent_session_id,
            current_trace_id=record.current_leaf_trace_id,
            auto_flag=record.auto_flag,
            idle_reason=record.idle_reason,
            rounds_used=record.rounds_used,
            report_available=record.final_report is not None,
            report_delivered=record.report_delivered,
            final_report=record.final_report if include_report else None,
        )


class SendConversationMessageRequest(BaseModel):
    content: str


class CreateConversationRequest(BaseModel):
    """``POST /api/conversations`` body — phase 3 scope: AUTO conversations
    (the old ``EnableAutoRequest`` = ``AutoChatSeed`` + reason, field
    semantics preserved verbatim). TODO(phase-4): grows a ``kind`` selector
    when interactive conversations are created here too (functional spec §2
    "create (optionally with first message)")."""

    # The conversation's current leaf trace id. Optional (Revision R2): a
    # brand-new conversation has no trace yet, so the seed carries only the
    # first user message in ``extra_messages`` and the backend starts a fresh
    # conversation, minting the first trace on the opening turn.
    trace_id: str | None = None
    # Resolve this enable_auto_mode call as "enabled" before the first round
    # (the consent-accept flow).
    enable_tool_call_id: str | None = None
    # Sibling client tools to auto-execute first (usually empty — the model
    # is instructed to call enable_auto_mode alone).
    pending_tool_calls: list[ToolCallInfo] = Field(default_factory=list)
    # Extra messages to prepend (e.g. the first user message on the
    # armed-first-send path).
    extra_messages: list[dict[str, Any]] = Field(default_factory=list)
    # Model-supplied reason from the enable_auto_mode call. The old world
    # stored it on AutoRunRecord.reason purely for the (deleted)
    # /api/chat/auto/sessions listing; it stays on the wire because the
    # consent flow still sends it and it is useful in logs.
    reason: str | None = None


class ConversationCreatedResponse(BaseModel):
    session_id: str


class DeclineAutoModeRequest(BaseModel):
    """Old ``DeclineAutoRequest`` verbatim (POST /api/chat/auto/decline)."""

    trace_id: str
    enable_tool_call_id: str
    # Other client tool calls from the same turn the backend is awaiting
    # results for. Normally empty (the model is instructed to call
    # enable_auto_mode alone); each is resolved as denied so the conversation
    # can continue interactively.
    siblings: list[ToolCallInfo] = Field(default_factory=list)


class SetAutoModeRequest(BaseModel):
    """``POST /api/conversations/{sid}/auto`` — flip the auto-mode flag on an
    EXISTING conversation (functional spec §2)."""

    enabled: bool


class ResolveConversationResponse(BaseModel):
    """Result of resolving a (possibly stale) trace id to a live auto
    conversation (old ``ResolveAutoResponse``, session-id vocabulary)."""

    session_id: str
    # The conversation's CURRENT leaf so the resyncing client can hydrate the
    # rounds completed while the tab was gone. Removed in phase 5 (browser
    # keys everything on session ids).
    current_trace_id: str
    # Replaces the old ``status`` (running | idle): lets the client choose
    # the right post-resync affordance — thinking indicator when running,
    # "· waiting for you" when idle — without waiting for the events stream.
    state: RunState
    auto_flag: bool


async def _observer_stream(session_id: str) -> AsyncGenerator[bytes, None]:
    """Pure-observer SSE over one conversation's bus: current-turn replay +
    conversation-state marker + live tail. Disconnecting only unsubscribes;
    the run keeps going (the core invariant both old observer streams had)."""
    async for item in iter_with_keepalive(
        conversation_supervisor.subscribe(session_id), KEEPALIVE_SECONDS
    ):
        if isinstance(item, KeepalivePing):
            yield b": ping\n\n"
        else:
            yield item


async def _state_firehose_stream() -> AsyncGenerator[bytes, None]:
    """Registry-level conversation-state firehose: an initial snapshot (one
    state event per known conversation) followed by live state events for
    every conversation. The UI store filters by parent client-side — same
    shape as the old sub-agent status firehose, so an interactive, idle
    parent still learns a child finished with no per-run stream open."""

    async def _with_snapshot() -> AsyncGenerator[bytes, None]:
        for record in conversation_supervisor.list_records():
            yield format_conversation_state(record)
        async for payload in conversation_supervisor.status_bus.subscribe():
            yield payload

    async for item in iter_with_keepalive(_with_snapshot(), KEEPALIVE_SECONDS):
        if isinstance(item, KeepalivePing):
            yield b": ping\n\n"
        else:
            yield item


def _resolve_parent_key(parent: str) -> str:
    """Resolve the ``parent`` query param to the key children are indexed by.

    The browser identifies the main conversation by its (possibly stale) leaf
    TRACE id until phase 5 keys everything on session ids, so resolution
    tries, in order:

    1. the old-loop interactive alias chain (``trace:<first-leaf>`` parent
       keys — any leaf the conversation ever had resolves; dies in phase 4
       with ``ParentConversationIndex``);
    2. the supervisor's whole-chain trace index, for parents that ARE
       supervisor records (auto since phase 3; interactive joins in phase 4):
       any leaf the conversation ever had resolves to its SESSION id, which
       is exactly what its children carry as ``parent_session_id``. Without
       this step an auto parent's children are invisible to the tab strip —
       the browser only ever holds trace ids, and the auto ``auto:<run_id>``
       alias chain that used to bridge this died with ``chat/auto/``.
       Guarded to non-subagent kinds: a CHILD session's own leaves are also
       indexed, and a child's leaf is never a parent handle (children can't
       have children — depth guard);
    3. the value itself, unresolved — which (a) yields the correct empty list
       for unknown traces and (b) already works for real parent session ids,
       so phases 4–5 need no route change to switch the browser to session
       ids.
    """
    from app.desktop.studio_server.chat.orchestration import parent_index

    alias = parent_index.alias_for_trace(parent)
    if alias is not None:
        return alias
    session_id = conversation_supervisor.session_for_trace(parent)
    if session_id is not None:
        record = conversation_supervisor.get(session_id)
        if record is not None and record.kind != "subagent":
            return session_id
    return parent


def connect_conversations_api(app: FastAPI) -> None:
    @app.get(
        "/api/conversations",
        summary="List conversations",
        tags=["Copilot"],
        openapi_extra=DENY_AGENT,
        response_model_exclude_none=True,
    )
    async def list_conversations(
        parent: Annotated[
            str | None,
            Query(
                description=(
                    "Filter to children of this conversation. Accepts the "
                    "parent's session id or (until phase 5 keys the browser "
                    "on session ids) any leaf trace id the parent "
                    "conversation has had — old-loop interactive parents and "
                    "supervisor-resident auto parents both resolve. Omit for "
                    "all live conversations."
                )
            ),
        ] = None,
    ) -> list[ConversationItem]:
        if parent is not None:
            records = conversation_supervisor.children_of(_resolve_parent_key(parent))
        else:
            records = conversation_supervisor.list_records()
        return [ConversationItem.from_record(record) for record in records]

    @app.post(
        "/api/conversations",
        summary="Create (or flip) an auto conversation",
        tags=["Copilot"],
        openapi_extra=DENY_AGENT,
    )
    @no_write_lock
    async def create_conversation(
        body: CreateConversationRequest,
    ) -> ConversationCreatedResponse:
        """Enable auto mode: create — or flip, if the trace already resolves
        to a live auto record — the conversation on the supervisor and start
        the first burst if the seed carries anything to run (old
        ``POST /api/chat/auto/enable``; see ``supervisor.enable_auto`` for the
        preserved entry shapes, including the ARMED-only manual enable that
        never POSTs an empty turn upstream). The run is supervised by the
        conversation supervisor and survives client disconnects."""
        upstream_url, headers = _upstream_target()
        try:
            record = await conversation_supervisor.enable_auto(
                trace_id=body.trace_id,
                enable_tool_call_id=body.enable_tool_call_id,
                pending_tool_calls=body.pending_tool_calls,
                extra_messages=body.extra_messages,
                upstream_url=upstream_url,
                headers=headers,
            )
        except ConversationCapError as exc:
            # Same cap surface as today: HTTP 429 with the preserved message.
            raise HTTPException(status_code=429, detail=str(exc))
        except RuntimeError as exc:
            # start_run refused because a run is already in flight for this
            # conversation (the old world silently spawned a duplicate
            # registry run here — a latent bug, not a contract).
            raise HTTPException(status_code=409, detail=str(exc))
        if body.reason:
            # The model's stated reason for requesting auto mode. The old
            # record.reason field died with /api/chat/auto/sessions; keep the
            # observability in the log line instead.
            logger.info(
                "Auto mode enabled for %s (reason: %s)",
                record.session_id,
                body.reason,
            )
        return ConversationCreatedResponse(session_id=record.session_id)

    @app.post(
        "/api/conversations/auto/decline",
        summary="Decline auto mode and resume interactive chat",
        tags=["Copilot"],
        openapi_extra=DENY_AGENT,
    )
    @no_write_lock
    async def decline_auto_mode(
        body: DeclineAutoModeRequest,
    ) -> CancellableStreamingResponse:
        """Resolve the pending ``enable_auto_mode`` call as declined and
        resume the normal interactive chat stream; sibling tool calls are
        resolved as denied. Byte-for-byte the old ``/api/chat/auto/decline``:
        the interactive conversation still lives on the OLD loop
        (``ChatStreamSession``), so declining is an interactive continuation,
        not a supervisor operation. TODO(phase-4): folds into
        ``POST /{{sid}}/auto`` (enabled=false + consent context) once
        interactive conversations own supervisor records and the parked
        enable call resolves through the interactive continuation there."""
        upstream_url, headers = _upstream_target()
        messages: list[dict[str, Any]] = [
            {
                "role": "tool",
                "tool_call_id": body.enable_tool_call_id,
                "content": json.dumps({"status": "declined"}, ensure_ascii=False),
            }
        ]
        for sibling in body.siblings:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": sibling.tool_call_id,
                    "content": DENIED_TOOL_OUTPUT,
                }
            )
        session = ChatStreamSession(
            upstream_url=upstream_url,
            headers=headers,
            initial_body={"trace_id": body.trace_id, "messages": messages},
        )
        return CancellableStreamingResponse(
            content=session.stream(),
            media_type="text/event-stream",
        )

    @app.get(
        "/api/conversations/resolve",
        summary="Resolve a trace id to a live auto conversation",
        tags=["Copilot"],
        openapi_extra=DENY_AGENT,
    )
    async def resolve_conversation(
        trace_id: Annotated[
            str,
            Query(description="A trace id from the conversation (may be stale)."),
        ],
    ) -> ResolveConversationResponse:
        """Resolve a (possibly stale) leaf trace id to the live auto
        conversation for its session (old ``GET /api/chat/auto/resolve``).

        Used by the web UI to resync after a hard refresh: the stored trace
        id is the leaf the tab last saw, but the desktop-owned run advances
        the leaf each round while the tab is gone. The supervisor's
        whole-chain trace index matches the stale id anyway, and the returned
        ``current_trace_id`` lets the client hydrate the rounds it missed
        before attaching to the live events stream. 404 if no live flag-on
        auto conversation owns the trace. Deleted in phase 5 when the
        browser keys conversations on session ids. NOTE: registered before
        the ``/{{session_id}}`` routes so the literal path wins."""
        record = conversation_supervisor.resolve_auto_for_trace(trace_id)
        if record is None or record.current_leaf_trace_id is None:
            raise HTTPException(
                status_code=404,
                detail=f"No active auto conversation for trace: {trace_id}",
            )
        return ResolveConversationResponse(
            session_id=record.session_id,
            current_trace_id=record.current_leaf_trace_id,
            state=record.state,
            auto_flag=record.auto_flag,
        )

    @app.get(
        "/api/conversations/events",
        summary="Stream conversation state events",
        tags=["Copilot"],
        openapi_extra=DENY_AGENT,
    )
    async def stream_conversation_state_events() -> CancellableStreamingResponse:
        """Registry-level firehose of ``conversation-state`` events (snapshot
        then live)."""
        return CancellableStreamingResponse(
            content=_state_firehose_stream(),
            media_type="text/event-stream",
        )

    @app.get(
        "/api/conversations/{session_id}",
        summary="Get a conversation",
        tags=["Copilot"],
        openapi_extra=DENY_AGENT,
        response_model_exclude_none=True,
    )
    async def get_conversation(
        session_id: Annotated[str, Path(description="The conversation session id.")],
        include_report: Annotated[
            bool,
            Query(description="Include the final report for terminal runs."),
        ] = False,
    ) -> ConversationItem:
        record = conversation_supervisor.get(session_id)
        if record is None:
            raise HTTPException(
                status_code=404, detail=f"Conversation not found: {session_id}"
            )
        return ConversationItem.from_record(record, include_report=include_report)

    @app.get(
        "/api/conversations/{session_id}/events",
        summary="Stream a conversation's chat events",
        tags=["Copilot"],
        openapi_extra=DENY_AGENT,
    )
    async def stream_conversation_events(
        session_id: Annotated[
            str, Path(description="The conversation session id to observe.")
        ],
    ) -> CancellableStreamingResponse:
        """Pure-observer SSE (buffer replay + state marker + live); 404 if
        unknown or GC'd. Any number of concurrent observers; disconnect never
        affects the run."""
        if conversation_supervisor.get(session_id) is None:
            raise HTTPException(
                status_code=404, detail=f"Conversation not found: {session_id}"
            )
        return CancellableStreamingResponse(
            content=_observer_stream(session_id),
            media_type="text/event-stream",
        )

    @app.post(
        "/api/conversations/{session_id}/stop",
        summary="Stop a conversation's run",
        tags=["Copilot"],
        status_code=202,
        openapi_extra=DENY_AGENT,
    )
    @no_write_lock
    async def stop_conversation(
        session_id: Annotated[
            str, Path(description="The conversation session id to stop.")
        ],
    ) -> Response:
        """Stop the run. Idempotent — stopping an unknown or terminal
        conversation is a no-op (a child's report, if any, is still delivered
        to the parent). Same 202-always contract as the old stop endpoint."""
        await conversation_supervisor.stop(session_id)
        return Response(status_code=202)

    @app.post(
        "/api/conversations/{session_id}/auto",
        summary="Flip a conversation's auto-mode flag",
        tags=["Copilot"],
        status_code=202,
        openapi_extra=DENY_AGENT,
    )
    @no_write_lock
    async def set_auto_mode(
        session_id: Annotated[str, Path(description="The conversation session id.")],
        body: SetAutoModeRequest,
    ) -> Response:
        """Flip the auto-mode flag on an EXISTING conversation (functional
        spec §2). ``enabled=false`` → today's disable semantics (old
        ``AutoChatRegistry.disable``: cancel a live burst, publish the off
        state with reason ``user_disabled``, TTL GC, cascade-stop sub-agent
        children); ``enabled=true`` → re-arm (ARMED-only: flag on, no
        upstream POST — the next message starts the burst). 404 unknown,
        409 for non-auto records (phase 3: interactive conversations aren't
        supervisor records yet, so only auto records are flippable —
        TODO(phase-4) lifts this), 429 when re-enabling would exceed the
        concurrency cap."""
        try:
            outcome = await conversation_supervisor.set_auto_flag(
                session_id, body.enabled
            )
        except ConversationCapError as exc:
            raise HTTPException(status_code=429, detail=str(exc))
        if outcome == "not_found":
            raise HTTPException(
                status_code=404, detail=f"Conversation not found: {session_id}"
            )
        if outcome == "invalid":
            raise HTTPException(
                status_code=409,
                detail=f"Conversation cannot flip auto mode: {session_id}",
            )
        return Response(status_code=202)

    @app.post(
        "/api/conversations/{session_id}/messages",
        summary="Send a user message into a conversation",
        tags=["Copilot"],
        status_code=202,
        openapi_extra=DENY_AGENT,
    )
    @no_write_lock
    async def send_conversation_message(
        session_id: Annotated[
            str, Path(description="The conversation session id to message.")
        ],
        body: SendConversationMessageRequest,
    ) -> Response:
        """Queue a user message (202). For a RUNNING child this is the steer
        path; for an auto conversation it is the inject/idle-re-arm path —
        drained at the next round boundary (or seeding a fresh burst),
        echoed to observers at enqueue time. 404 for unknown conversations,
        409 for terminal ones and for flag-OFF auto conversations (the old
        auto message endpoint's "no longer active" refusal — a send must
        never start an auto-approving burst without an active consent)."""
        record = conversation_supervisor.get(session_id)
        if record is None:
            raise HTTPException(
                status_code=404, detail=f"Conversation not found: {session_id}"
            )
        accepted = conversation_supervisor.send_message(session_id, body.content)
        if not accepted:
            detail = (
                f"Auto mode is no longer active: {session_id}"
                if record.kind == "auto" and not record.auto_flag
                else f"Conversation already finished: {session_id}"
            )
            raise HTTPException(status_code=409, detail=detail)
        return Response(status_code=202)
