"""``/api/conversations`` — the unified browser-facing conversation API.

Replaces the request-scoped interactive chat surface (``POST /api/chat`` +
``POST /api/chat/execute-tools``, where the stream ENDED at a
``tool-calls-pending`` event and the browser POSTed the decisions to
continue) with supervised conversations the browser observes:

- ``GET /api/conversations?parent=`` — the live conversations, or the
  sub-agent children of one parent (by the parent's session id);
- ``GET /api/conversations/events`` — the registry-level
  ``conversation-state`` firehose (snapshot + live);
- ``POST /api/conversations`` — create/adopt an interactive conversation
  (``kind="interactive"``), or enable auto mode (``kind="auto"``: flip the
  named conversation, or create one for the armed-first-send seed);
- ``GET /api/conversations/{sid}`` — the record;
- ``GET /api/conversations/{sid}/events`` — observer SSE (current-turn
  replay + ``conversation-state`` marker + live);
- ``POST /api/conversations/{sid}/messages`` — send (an idle send starts the
  turn; a send while running is injected at the next round boundary);
- ``GET /api/conversations/{sid}/approvals`` +
  ``POST /api/conversations/{sid}/approvals/decisions`` — the run PARKS on
  approvals instead of ending the stream (same wire bodies upstream);
- ``POST /api/conversations/{sid}/auto`` — flip the auto-mode flag on an
  EXISTING conversation, or decline a pending consent request;
- ``POST /api/conversations/{sid}/stop`` — stop the in-flight turn/burst.

``GET /api/conversations/{sid}`` takes ``include_report`` to add a finished
child's final report. The consent decline on ``/{sid}/auto`` covers both
gating calls: ``enable_auto_mode`` and the FR2 spawn-consent
``spawn_subagent``. ``/{sid}/stop`` takes ``cascade=true`` to stop every
running sub-agent child first.

Lifecycle is reported by the unified ``conversation-state`` event
(runtime/sse.py) on both the observer stream (as the on-subscribe marker and
live lifecycle updates) and the registry-level firehose. The AI-SDK content
vocabulary on the observer stream is the upstream's.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, AsyncGenerator, Literal

from fastapi import FastAPI, HTTPException, Path, Query, Response
from kiln_server.cancellable_streaming_response import CancellableStreamingResponse
from kiln_server.git_sync_decorators import no_write_lock
from kiln_server.utils.agent_checks.policy import DENY_AGENT
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.desktop.studio_server.chat.stream_session import ToolCallInfo

# The shared keepalive helper: its feeder-task design is what makes a
# quiet-window timeout safe for observer streams.
from app.desktop.studio_server.jobs.events import KeepalivePing, iter_with_keepalive
from app.desktop.studio_server.utils.copilot_utils import get_copilot_api_key

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

# Quiet-window keepalive for the SSE streams.
KEEPALIVE_SECONDS = 15.0


class ConversationItem(BaseModel):
    """UI-facing view of one conversation record.

    - ``state`` uses the ``RunState`` vocabulary.
    - Browsers never see trace ids (functional spec §4). History hydration
      goes through ``GET /api/chat/sessions/{session_id}`` and the DESKTOP
      resolves the record's current leaf (``routes.resolve_conversation_key``).
    - ``root_id`` is the upstream session's DURABLE id (``session_meta.
      root_id``) when the desktop has learned it — exposed so the browser can
      persist a restart-proof recovery key (the in-memory ``session_id`` dies
      with the desktop process; the recovery key resumes via the backend's
      own session-id resolution).
    - ``final_report`` is included only when requested with
      ``include_report``.
    """

    session_id: str
    kind: ConversationKind
    state: RunState
    name: str | None = None
    agent_type: str | None = None
    parent_session_id: str | None = None
    root_id: str | None = None
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
            root_id=record.root_id,
            auto_flag=record.auto_flag,
            idle_reason=record.idle_reason,
            rounds_used=record.rounds_used,
            report_available=record.final_report is not None,
            report_delivered=record.report_delivered,
            final_report=record.final_report if include_report else None,
        )


class SendConversationMessageRequest(BaseModel):
    content: str


class ConversationMessageAccepted(BaseModel):
    """202 body for ``POST /{sid}/messages``: the accepted message's stable
    server-minted id. The sending tab renders the typed
    text locally and uses this id to dedupe the run's ``user-message`` echo
    (whose content carries the app-context header only OTHER observers
    should render, stripped)."""

    message_id: str


class CreateConversationRequest(BaseModel):
    """``POST /api/conversations`` body.

    ``kind`` selects the flow:

    - ``"auto"`` (default — the enable flow): flips the named conversation —
      or creates one when ``session_id`` is absent (armed-first-send).
    - ``"interactive"``: create-or-adopt the conversation for ``session_id``
      (functional spec §2 "create"; idempotent — a key resolving to a live
      record returns that record's session id). The first message goes
      through ``POST /{sid}/messages`` like every other message.
    """

    kind: Literal["interactive", "auto"] = "auto"
    # The conversation key. For kind="interactive": any key the browser can
    # hold — a live session id, a history row id (live sid / upstream root
    # id / legacy leaf), or the persisted recovery key; None creates a fresh
    # empty record (first send opens it). For kind="auto": the LIVE
    # conversation's session id (consent accept / manual enable — the
    # consent event arrives on the observer of a live record, so a sid is
    # always in hand); None is the armed-first-send create (the seed carries
    # the first user message in ``extra_messages`` and the backend mints the
    # conversation).
    session_id: str | None = None
    # Resolve this enable_auto_mode call as "enabled" before the first round
    # (the enable-triggered consent accept). None for the FR2 spawn-consent
    # accept, where the gating spawn rides pending_tool_calls instead. Auto
    # kind only.
    enable_tool_call_id: str | None = None
    # Client tool calls to auto-execute first, their results seeding the
    # burst. Usually empty for the enable trigger (the model is instructed to
    # call enable_auto_mode alone); the spawn-consent accept sends the gating
    # spawn_subagent call FIRST here (+ any siblings), so accepting actually
    # spawns the child. Auto kind only.
    pending_tool_calls: list[ToolCallInfo] = Field(default_factory=list)
    # Extra messages to prepend (e.g. the first user message on the
    # armed-first-send path). Auto kind only.
    extra_messages: list[dict[str, Any]] = Field(default_factory=list)
    # Model-supplied reason from the enable_auto_mode call, logged when auto
    # mode turns on.
    reason: str | None = None


class ConversationCreatedResponse(BaseModel):
    session_id: str


class DeclineAutoModeContext(BaseModel):
    """Consent-decline context riding ``POST /{sid}/auto`` with
    ``enabled=false``. The conversation record's own leaf is authoritative,
    so no trace id rides here."""

    model_config = ConfigDict(populate_by_name=True)

    # The call that surfaced the consent flow: the enable_auto_mode call, or
    # (FR2) the spawn_subagent call that required auto mode. Resolved as
    # {"status": "declined"}. The ``enable_tool_call_id`` spelling is also
    # accepted, for an open browser tab whose bundle still sends that name.
    gating_tool_call_id: str = Field(
        validation_alias=AliasChoices("gating_tool_call_id", "enable_tool_call_id")
    )
    # Other client tool calls from the same turn the backend is awaiting
    # results for. Normally empty (the model is instructed to call
    # enable_auto_mode alone); each is resolved as denied so the
    # conversation can continue interactively.
    siblings: list[ToolCallInfo] = Field(default_factory=list)


class SetAutoModeRequest(BaseModel):
    """``POST /api/conversations/{sid}/auto`` — flip the auto-mode flag on an
    EXISTING conversation (functional spec §2). With ``enabled=false`` and a
    ``decline`` context this is the consent-decline flow: the pending
    ``enable_auto_mode`` call resolves as declined + denied siblings through
    an interactive continuation turn streaming on the observer channel."""

    enabled: bool
    # Present = the consent-DECLINE flow (enable- or spawn-triggered): the
    # gating call resolves as declined + denied siblings instead of a plain
    # flag flip.
    decline: DeclineAutoModeContext | None = None


class PendingApprovalsResponse(BaseModel):
    """``GET /{sid}/approvals`` — the parked batch awaiting decisions.

    ``items`` is the exact wire shape of the ``tool-calls-pending`` event
    items (toolCallId/toolName/input/requiresApproval[/permission/
    approvalDescription]) so the approval box consumes either source
    identically; ``batch_id`` is what ``POST decisions`` must echo back
    (validated — a stale batch id 404s, an already-decided batch 409s)."""

    batch_id: str
    items: list[dict[str, Any]]


class ApprovalDecisionsRequest(BaseModel):
    """``POST /{sid}/approvals/decisions`` — one decision set for the whole
    batch (partial decisions are not allowed; matches today's UI, functional
    spec §2). Keys are tool_call_ids; True = run, False/absent = deny."""

    batch_id: str
    decisions: dict[str, bool]


async def _observer_stream(session_id: str) -> AsyncGenerator[bytes, None]:
    """Pure-observer SSE over one conversation's bus: current-turn replay +
    conversation-state marker + live tail. Disconnecting only unsubscribes;
    the run keeps going."""
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
    every conversation. The UI store filters by parent client-side, so an
    interactive, idle parent still learns a child finished with no per-run
    stream open."""

    def _snapshot() -> list[bytes]:
        # Built INSIDE subscribe(), AFTER the firehose subscriber is already
        # registered on the status bus (see BroadcastBus.subscribe): a
        # conversation spawned while we read/format list_records() has its
        # live conversation-state event QUEUED for this subscriber rather than
        # lost in a read-snapshot-then-subscribe gap (a running child missing
        # from the store). Materialize eagerly so the whole read is one
        # synchronous step with no await for an event to slip through.
        return [
            format_conversation_state(record)
            for record in conversation_supervisor.list_records()
        ]

    async def _with_snapshot() -> AsyncGenerator[bytes, None]:
        async for payload in conversation_supervisor.status_bus.subscribe(
            snapshot=_snapshot
        ):
            yield payload

    async for item in iter_with_keepalive(_with_snapshot(), KEEPALIVE_SECONDS):
        if isinstance(item, KeepalivePing):
            yield b": ping\n\n"
        else:
            yield item


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
                    "Filter to children of this conversation, by the "
                    "parent's session id. Omit for all live conversations."
                )
            ),
        ] = None,
    ) -> list[ConversationItem]:
        # ``parent`` is a session id — children carry their parent's
        # ``parent_session_id`` verbatim, so no resolution is needed (an
        # unknown value yields the correct empty list).
        if parent is not None:
            records = conversation_supervisor.children_of(parent)
        else:
            records = conversation_supervisor.list_records()
        return [ConversationItem.from_record(record) for record in records]

    @app.post(
        "/api/conversations",
        summary="Create (or adopt/flip) a conversation",
        tags=["Copilot"],
        openapi_extra=DENY_AGENT,
    )
    @no_write_lock
    async def create_conversation(
        body: CreateConversationRequest,
    ) -> ConversationCreatedResponse:
        """Create a conversation, by kind (functional spec §2 — see
        ``CreateConversationRequest``):

        - ``kind="interactive"``: create-or-adopt the conversation for the
          given key. Idempotent: a key resolving to a live record (any kind)
          returns that record's session id; a TERMINAL record's key (a
          finished sub-agent reopened from history) continues its trace on a
          fresh interactive record; a cold key (upstream root id / legacy
          leaf) is adopted VERBATIM — the backend resolves it on the first
          turn — and rehydrates pending approvals from the persisted trace
          tail (functional spec §5 restart recovery); a dead ``cv_`` key —
          the record died with a desktop restart — creates a fresh empty
          record.
        - ``kind="auto"`` (default): enable auto mode — flip the named
          conversation, or create one for the armed-first-send seed (see
          ``supervisor.enable_auto`` for the entry shapes, including the
          ARMED-only manual enable that never POSTs an empty turn upstream).

        Runs are supervised by the conversation supervisor and survive client
        disconnects."""
        upstream_url, headers = _upstream_target()
        if body.kind == "interactive":
            # Lazy import for the same routes.py cycle _upstream_target
            # documents. Resolution is purely LOCAL (live-record lookup); a
            # cold key is adopted AS-IS and the record's first turn continues
            # upstream by session_id — the backend resolves the session's
            # current leaf itself (architecture §8).
            from app.desktop.studio_server.chat.routes import (
                resolve_conversation_key,
            )

            session_key: str | None = None
            if body.session_id is not None:
                resolved = resolve_conversation_key(body.session_id)
                if (
                    resolved.record is not None
                    and not resolved.record.state.is_terminal
                ):
                    # Idempotent adopt: the key names a live conversation.
                    return ConversationCreatedResponse(
                        session_id=resolved.record.session_id
                    )
                # A terminal record's key (a finished sub-agent reopened from
                # history) resolves to its current leaf so the fresh
                # interactive record continues that trace; a cold key rides
                # verbatim; a dead cv_ key yields None (fresh empty record).
                session_key = resolved.upstream_key
            record = await conversation_supervisor.adopt_interactive(
                session_key,
                upstream_url=upstream_url,
                headers=headers,
            )
            return ConversationCreatedResponse(session_id=record.session_id)
        try:
            record = await conversation_supervisor.enable_auto(
                session_id=body.session_id,
                enable_tool_call_id=body.enable_tool_call_id,
                pending_tool_calls=body.pending_tool_calls,
                extra_messages=body.extra_messages,
                upstream_url=upstream_url,
                headers=headers,
            )
        except KeyError:
            # The named conversation died with a restart/eviction — and so
            # did the consent dialog's context.
            raise HTTPException(
                status_code=404,
                detail=f"Conversation not found: {body.session_id}",
            )
        except ValueError as exc:
            # Sub-agent/terminal records can't enable auto mode (mirrors
            # set_auto_flag's "invalid" outcome).
            raise HTTPException(status_code=409, detail=str(exc))
        except ConversationCapError as exc:
            raise HTTPException(status_code=429, detail=str(exc))
        except RuntimeError as exc:
            # A run is already in flight for this conversation.
            raise HTTPException(status_code=409, detail=str(exc))
        if body.reason:
            # The model's stated reason for requesting auto mode.
            logger.info(
                "Auto mode enabled for %s (reason: %s)",
                record.session_id,
                body.reason,
            )
        return ConversationCreatedResponse(session_id=record.session_id)

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
        unknown or evicted. Any number of concurrent observers; disconnect
        never affects the run."""
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
        cascade: Annotated[
            bool,
            Query(
                description="Also stop every running sub-agent child (kill the"
                " whole tree). Without it an interactive stop only cancels the"
                " in-flight turn; auto/sub-agent stops cascade regardless."
            ),
        ] = False,
    ) -> Response:
        """Stop the run. Idempotent — stopping an unknown or terminal
        conversation is a no-op (a child's report, if any, is still delivered
        to the parent); always 202. ``cascade=true`` stops the children
        FIRST (their reports are suppressed — the parent is being torn down,
        same order as session deletion) and then the conversation itself."""
        if cascade:
            await conversation_supervisor.stop_children(session_id)
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
        spec §2). ``enabled=false`` → disable: cancel a live burst, publish
        the off state with reason ``user_disabled`` and cascade-stop sub-agent
        children; the record then swaps back to its interactive life.
        ``enabled=false`` + ``decline`` → the consent-decline flow: resolve
        the pending gating call — ``enable_auto_mode``, or the FR2
        spawn-consent ``spawn_subagent`` — as declined + denied siblings via
        an interactive continuation turn that streams on the observer channel.
        ``enabled=true`` → enable/re-arm: the record flips to the auto policy
        (ARMED-only: flag on, no upstream POST — the next message starts the
        burst). 404 unknown, 409 for sub-agent records / a decline racing an
        in-flight run, 429 when enabling would exceed the concurrency cap."""
        if not body.enabled and body.decline is not None:
            outcome = conversation_supervisor.decline_auto(
                session_id,
                gating_tool_call_id=body.decline.gating_tool_call_id,
                siblings=body.decline.siblings,
            )
            if outcome == "not_found":
                raise HTTPException(
                    status_code=404, detail=f"Conversation not found: {session_id}"
                )
            if outcome == "invalid":
                raise HTTPException(
                    status_code=409,
                    detail=f"Conversation cannot decline auto mode: {session_id}",
                )
            if outcome == "busy":
                raise HTTPException(
                    status_code=409,
                    detail=f"Conversation already has a run in flight: {session_id}",
                )
            return Response(status_code=202)
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

    @app.get(
        "/api/conversations/{session_id}/approvals",
        summary="Get the conversation's pending approval batch",
        tags=["Copilot"],
        openapi_extra=DENY_AGENT,
    )
    async def get_pending_approvals(
        session_id: Annotated[str, Path(description="The conversation session id.")],
    ) -> PendingApprovalsResponse:
        """The parked approval batch awaiting decisions (functional spec §2).

        The run PARKS and the browser fetches the batch here — keyed off the
        ``tool-calls-pending`` event / the AWAITING_APPROVAL state — then
        answers via ``POST /{sid}/approvals/decisions``. When no batch is in memory, the
        supervisor attempts trace-tail rehydration first (functional spec §5:
        desktop restart / graceful-stop leftovers), so a recoverable batch is
        indistinguishable from a live one to the browser. 404 when the
        conversation is unknown or nothing is pending."""
        if conversation_supervisor.get(session_id) is None:
            raise HTTPException(
                status_code=404, detail=f"Conversation not found: {session_id}"
            )
        batch = conversation_supervisor.pending_approval(session_id)
        if batch is None or batch.decided.is_set():
            batch = await conversation_supervisor.rehydrate_pending_approvals(
                session_id
            )
        if batch is None or batch.decided.is_set():
            raise HTTPException(
                status_code=404,
                detail=f"No pending approvals for conversation: {session_id}",
            )
        return PendingApprovalsResponse(batch_id=batch.batch_id, items=batch.items)

    @app.post(
        "/api/conversations/{session_id}/approvals/decisions",
        summary="Resolve the conversation's pending approval batch",
        tags=["Copilot"],
        status_code=202,
        openapi_extra=DENY_AGENT,
    )
    @no_write_lock
    async def post_approval_decisions(
        session_id: Annotated[str, Path(description="The conversation session id.")],
        body: ApprovalDecisionsRequest,
    ) -> Response:
        """Resolve a parked approval batch (functional spec §2/§5): the run
        resumes (or a resume run starts, for a rehydrated batch) and results
        stream on the events channel. One decision set per batch — first
        decision set wins; a second tab deciding the same batch gets 409;
        an unknown conversation/batch id gets 404."""
        outcome = conversation_supervisor.decide(
            session_id, body.batch_id, body.decisions
        )
        if outcome == "not_found":
            raise HTTPException(
                status_code=404,
                detail=f"No pending approval batch {body.batch_id} for "
                f"conversation: {session_id}",
            )
        if outcome == "conflict":
            raise HTTPException(
                status_code=409,
                detail=f"Approval batch already decided: {body.batch_id}",
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
    ) -> ConversationMessageAccepted:
        """Queue a user message (202, functional spec §2). Behavior by state:
        IDLE → starts a turn/burst; RUNNING → queued into the inbox, drained
        at the next round boundary; AWAITING_APPROVAL → queued until
        decisions resolve. The message is echoed to observers at enqueue
        time; the response carries its stable id so the sending tab can
        dedupe its own echo. 404 for unknown conversations, 409 for the
        narrow flag-off-but-still-auto-policy window during a disable (once
        the settle swaps the record back to interactive, sends run normal
        gated turns)."""
        record = conversation_supervisor.get(session_id)
        if record is None:
            raise HTTPException(
                status_code=404, detail=f"Conversation not found: {session_id}"
            )
        message_id = conversation_supervisor.send_message(session_id, body.content)
        if message_id is None:
            detail = (
                f"Auto mode is no longer active: {session_id}"
                if record.kind == "auto" and not record.auto_flag
                else f"Conversation already finished: {session_id}"
            )
            raise HTTPException(status_code=409, detail=detail)
        return ConversationMessageAccepted(message_id=message_id)
