from __future__ import annotations

import json
from typing import Annotated, Any, AsyncGenerator

from app.desktop.studio_server.chat.constants import DENIED_TOOL_OUTPUT
from app.desktop.studio_server.chat.routes import (
    _build_upstream_headers,
    _upstream_chat_url,
)
from app.desktop.studio_server.chat.stream_session import (
    ChatStreamSession,
    ToolCallInfo,
)
from app.desktop.studio_server.utils.copilot_utils import get_copilot_api_key
from fastapi import FastAPI, HTTPException, Path, Query, Response
from kiln_server.cancellable_streaming_response import CancellableStreamingResponse
from kiln_server.git_sync_decorators import no_write_lock
from kiln_server.utils.agent_checks.policy import DENY_AGENT
from pydantic import BaseModel, Field

from .events import KeepalivePing, iter_with_keepalive
from .models import AutoChatSeed, AutoRunStatus, InboundMessage
from .registry import AutoChatConcurrencyError, auto_chat_registry

# Quiet-window keepalive for the per-run events stream (mirrors jobs/api.py).
KEEPALIVE_SECONDS = 15.0


class EnableAutoRequest(AutoChatSeed):
    """``AutoChatSeed`` plus the optional model-supplied reason recorded on the run."""

    reason: str | None = None


class EnableAutoResponse(BaseModel):
    run_id: str


class DeclineAutoRequest(BaseModel):
    trace_id: str
    enable_tool_call_id: str
    # Other client tool calls from the same turn the backend is awaiting results
    # for. Normally empty (the model is instructed to call enable_auto_mode alone);
    # each is resolved as denied so the conversation can continue interactively.
    siblings: list[ToolCallInfo] = Field(default_factory=list)


class SendMessageRequest(BaseModel):
    """A user message sent into an auto-mode conversation via ``/message``
    (Revision R1) — injected into the active burst or starts a new one if idle."""

    content: str
    trace_id: str | None = None


class AutoSessionItem(BaseModel):
    run_id: str
    current_trace_id: str
    status: AutoRunStatus
    reason: str | None = None


class ResolveAutoResponse(BaseModel):
    """Result of resolving a (possibly stale) trace id to an active auto run."""

    run_id: str
    current_trace_id: str
    # Phase 9: the run's current lifecycle status (running | idle) so the web UI
    # can choose the right post-resync state — show the thinking indicator
    # immediately when running, or "· waiting for you" when idle — without
    # waiting for the events stream to surface liveness.
    status: AutoRunStatus


async def _events_stream(run) -> AsyncGenerator[bytes, None]:
    """Pure-observer SSE generator over a run's per-run bus.

    Replays the in-progress turn buffer then goes live (the bus owns that), with a
    keepalive comment during quiet windows. Closing this generator (client
    disconnect) only unsubscribes — it never touches the run's supervising task,
    so the run keeps going. The keepalive goes through the shared feeder-task
    helper so a quiet-window timeout can't tear down the subscription.
    """
    async for item in iter_with_keepalive(run.bus.subscribe(), KEEPALIVE_SECONDS):
        if isinstance(item, KeepalivePing):
            yield b": ping\n\n"
        else:
            yield item


def connect_chat_auto_api(app: FastAPI) -> None:
    @app.post(
        "/api/chat/auto/enable",
        summary="Enable auto mode for a chat",
        tags=["Copilot"],
        openapi_extra=DENY_AGENT,
    )
    @no_write_lock
    async def enable_auto_mode(body: EnableAutoRequest) -> EnableAutoResponse:
        """Start a server-owned auto run that continues the chat autonomously.

        Begins a fresh upstream continuation from the seed's ``trace_id`` (resolving
        the accepted ``enable_auto_mode`` call as enabled). The run is supervised by
        the registry and survives client disconnects.
        """
        api_key = get_copilot_api_key()
        seed = AutoChatSeed.model_validate(body.model_dump())
        try:
            record = auto_chat_registry.start(
                seed,
                reason=body.reason,
                upstream_url=_upstream_chat_url(),
                headers=_build_upstream_headers(api_key),
            )
        except AutoChatConcurrencyError as exc:
            raise HTTPException(status_code=429, detail=str(exc))
        return EnableAutoResponse(run_id=record.run_id)

    @app.post(
        "/api/chat/auto/decline",
        summary="Decline auto mode and resume interactive chat",
        tags=["Copilot"],
        openapi_extra=DENY_AGENT,
    )
    @no_write_lock
    async def decline_auto_mode(
        body: DeclineAutoRequest,
    ) -> CancellableStreamingResponse:
        """Resolve the ``enable_auto_mode`` call as declined and resume the normal
        interactive chat stream. Any sibling tool calls are resolved as denied."""
        api_key = get_copilot_api_key()
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
            upstream_url=_upstream_chat_url(),
            headers=_build_upstream_headers(api_key),
            initial_body={"trace_id": body.trace_id, "messages": messages},
        )
        return CancellableStreamingResponse(
            content=session.stream(),
            media_type="text/event-stream",
        )

    @app.post(
        "/api/chat/auto/{run_id}/stop",
        summary="Stop an auto run",
        tags=["Copilot"],
        status_code=202,
        openapi_extra=DENY_AGENT,
    )
    @no_write_lock
    async def stop_auto_run(
        run_id: Annotated[str, Path(description="The auto run id to stop.")],
    ) -> Response:
        """Cooperatively cancel the run. Idempotent — stopping an unknown or
        already-terminal run is a no-op."""
        await auto_chat_registry.stop(run_id)
        return Response(status_code=202)

    @app.post(
        "/api/chat/auto/{run_id}/message",
        summary="Send a user message into an auto-mode conversation",
        tags=["Copilot"],
        status_code=202,
        openapi_extra=DENY_AGENT,
    )
    @no_write_lock
    async def send_auto_message(
        run_id: Annotated[str, Path(description="The auto run id to message.")],
        body: SendMessageRequest,
    ) -> Response:
        """Inject a user message without disabling auto mode (Revision R1).

        If a burst is active the message is queued and delivered at the next round
        boundary; if the conversation is idle a new burst is started seeded with
        the message. The echoed message and resulting events arrive on the run's
        observer stream. 404 if the run is unknown or its flag is already off."""
        message = InboundMessage(content=body.content, trace_id=body.trace_id)
        accepted = auto_chat_registry.send_message(run_id, message)
        if not accepted:
            raise HTTPException(
                status_code=404,
                detail=f"Auto run not found or no longer active: {run_id}",
            )
        return Response(status_code=202)

    @app.get(
        "/api/chat/auto/{run_id}/events",
        summary="Stream auto run events",
        tags=["Copilot"],
        openapi_extra=DENY_AGENT,
    )
    async def stream_auto_events(
        run_id: Annotated[str, Path(description="The auto run id to observe.")],
    ) -> CancellableStreamingResponse:
        """Pure-observer SSE stream of a run's chat events (404 if unknown/GC'd)."""
        run = auto_chat_registry.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Auto run not found: {run_id}")
        return CancellableStreamingResponse(
            content=_events_stream(run),
            media_type="text/event-stream",
        )

    @app.get(
        "/api/chat/auto/resolve",
        summary="Resolve a trace id to an active auto run",
        tags=["Copilot"],
        openapi_extra=DENY_AGENT,
    )
    async def resolve_auto_run(
        trace_id: Annotated[
            str,
            Query(description="A trace id from the conversation (may be stale)."),
        ],
    ) -> ResolveAutoResponse:
        """Resolve a (possibly stale) trace id to the active auto run for its
        conversation, returning the run id and the run's CURRENT leaf trace id.

        Used by the web UI to resync after a hard refresh: the stored trace id is
        the leaf the tab last saw, but the server-owned run advances the leaf each
        round while the tab is gone. The registry's whole-chain trace index (every
        seen trace id → run) matches the stale id anyway, and the returned
        ``current_trace_id`` lets the client hydrate the rounds it missed before
        attaching to the live events stream. 404 if no active run owns the
        trace."""
        resolved = auto_chat_registry.resolve_trace(trace_id)
        if resolved is None:
            raise HTTPException(
                status_code=404,
                detail=f"No active auto run for trace: {trace_id}",
            )
        run_id, current_trace_id, status = resolved
        return ResolveAutoResponse(
            run_id=run_id, current_trace_id=current_trace_id, status=status
        )

    @app.get(
        "/api/chat/auto/sessions",
        summary="List active auto runs",
        tags=["Copilot"],
        openapi_extra=DENY_AGENT,
    )
    async def list_auto_sessions() -> list[AutoSessionItem]:
        return [
            AutoSessionItem(
                run_id=record.run_id,
                current_trace_id=record.current_trace_id,
                status=record.status,
                reason=record.reason,
            )
            for record in auto_chat_registry.list_active()
        ]
