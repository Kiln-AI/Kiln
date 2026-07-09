"""``/api/conversations`` — the unified browser-facing conversation API.

Phase 2 ships the CHILDREN SUBSET of the surface specified in the functional
spec §2 (list?parent= / get / events observer SSE / stop / messages), which is
everything the sub-agent UI needs; it replaces ``/api/chat/subagents/*``
one-for-one. Phases 3–4 fold the auto and interactive endpoints
(create / approvals / auto flag) into the same routes.

Old → new mapping (behavior preserved, vocabulary unified):

- ``GET  /api/chat/subagents?parent_trace_id=`` → ``GET /api/conversations?parent=``
- ``GET  /api/chat/subagents/events``           → ``GET /api/conversations/events``
- ``GET  /api/chat/subagents/{id}``             → ``GET /api/conversations/{sid}``
- ``GET  /api/chat/subagents/{id}/events``      → ``GET /api/conversations/{sid}/events``
- ``POST /api/chat/subagents/{id}/stop``        → ``POST /api/conversations/{sid}/stop``
- ``POST /api/chat/subagents/{id}/message``     → ``POST /api/conversations/{sid}/messages``

and the ``kiln-subagent-status`` control event is replaced by the unified
``conversation-state`` event (runtime/sse.py) on both the observer stream (as
the on-subscribe marker and live lifecycle updates) and the registry-level
firehose. The AI-SDK content vocabulary on the observer stream is untouched.

The desktop↔browser API has no version-skew constraint (they ship together),
so the old surface is deleted in this same phase.
"""

from __future__ import annotations

from typing import Annotated, AsyncGenerator

from fastapi import FastAPI, HTTPException, Path, Query, Response

# Keepalive stays the shared jobs helper, exactly as the old auto/sub-agent
# APIs used it (its feeder-task design is what makes a quiet-window timeout
# safe for observer streams).
from app.desktop.studio_server.jobs.events import KeepalivePing, iter_with_keepalive
from kiln_server.cancellable_streaming_response import CancellableStreamingResponse
from kiln_server.git_sync_decorators import no_write_lock
from kiln_server.utils.agent_checks.policy import DENY_AGENT
from pydantic import BaseModel

from .models import ConversationKind, ConversationRecord, RunState
from .sse import format_conversation_state
from .supervisor import conversation_supervisor

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

    Phase-2 bridge: the browser identifies the main conversation by its leaf
    TRACE id (parents still run on the old loops and have no session id), so
    try the alias chain first — any leaf the conversation ever had resolves.
    An unresolved value falls through unchanged, which (a) yields the correct
    empty list for unknown traces and (b) already works for real parent
    session ids, so phases 4–5 need no route change to switch the browser to
    session ids."""
    from app.desktop.studio_server.chat.orchestration import parent_index

    return parent_index.alias_for_trace(parent) or parent


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
                    "parent's session id or (while parents run on the legacy "
                    "loops) any leaf trace id the parent conversation has "
                    "had. Omit for all live conversations."
                )
            ),
        ] = None,
    ) -> list[ConversationItem]:
        if parent is not None:
            records = conversation_supervisor.children_of(_resolve_parent_key(parent))
        else:
            records = conversation_supervisor.list_records()
        return [ConversationItem.from_record(record) for record in records]

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
        path — drained at the next round boundary, echoed to observers at
        enqueue time. 404 for unknown conversations, 409 for terminal ones
        (same statuses the old message endpoint returned)."""
        if conversation_supervisor.get(session_id) is None:
            raise HTTPException(
                status_code=404, detail=f"Conversation not found: {session_id}"
            )
        accepted = conversation_supervisor.send_message(session_id, body.content)
        if not accepted:
            raise HTTPException(
                status_code=409,
                detail=f"Conversation already finished: {session_id}",
            )
        return Response(status_code=202)
