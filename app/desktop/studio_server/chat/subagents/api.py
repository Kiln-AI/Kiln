from __future__ import annotations

from typing import Annotated, AsyncGenerator

from fastapi import FastAPI, HTTPException, Path, Query, Response
from kiln_server.cancellable_streaming_response import CancellableStreamingResponse
from kiln_server.git_sync_decorators import no_write_lock
from kiln_server.utils.agent_checks.policy import DENY_AGENT
from pydantic import BaseModel

from .events import KeepalivePing, iter_with_keepalive
from .models import SubAgentRecord, SubAgentStatus
from .registry import SubAgentRun, subagent_registry

# Quiet-window keepalive for the SSE streams (mirrors auto/api.py).
KEEPALIVE_SECONDS = 15.0


class SubAgentItem(BaseModel):
    """UI-facing view of a sub-agent run."""

    subagent_id: str
    name: str
    agent_type: str
    status: SubAgentStatus
    current_trace_id: str | None = None
    parent_trace_id_at_spawn: str | None = None
    rounds_used: int = 0
    report_available: bool = False
    report_delivered: bool = False
    # Included only when detail is requested with include_report.
    final_report: str | None = None

    @classmethod
    def from_record(
        cls, record: SubAgentRecord, include_report: bool = False
    ) -> "SubAgentItem":
        return cls(
            subagent_id=record.subagent_id,
            name=record.name,
            agent_type=record.agent_type,
            status=record.status,
            current_trace_id=record.current_trace_id,
            parent_trace_id_at_spawn=record.parent_trace_id_at_spawn,
            rounds_used=record.rounds_used,
            report_available=record.final_report is not None,
            report_delivered=record.report_delivered,
            final_report=record.final_report if include_report else None,
        )


class SendSubAgentMessageRequest(BaseModel):
    content: str


async def _run_events_stream(run: SubAgentRun) -> AsyncGenerator[bytes, None]:
    """Pure-observer SSE over one sub-agent's bus: buffer replay + status marker
    + live tail. Disconnecting only unsubscribes; the run keeps going."""
    async for item in iter_with_keepalive(run.bus.subscribe(), KEEPALIVE_SECONDS):
        if isinstance(item, KeepalivePing):
            yield b": ping\n\n"
        else:
            yield item


async def _status_firehose_stream() -> AsyncGenerator[bytes, None]:
    """Registry-level status firehose: an initial snapshot (one status event per
    known run) followed by live status events for every run. The UI store
    filters by parent client-side."""
    from .sse import format_subagent_status

    async def _with_snapshot() -> AsyncGenerator[bytes, None]:
        for record in subagent_registry.list_all():
            yield format_subagent_status(record)
        async for payload in subagent_registry.status_bus.subscribe():
            yield payload

    async for item in iter_with_keepalive(_with_snapshot(), KEEPALIVE_SECONDS):
        if isinstance(item, KeepalivePing):
            yield b": ping\n\n"
        else:
            yield item


def connect_chat_subagents_api(app: FastAPI) -> None:
    @app.get(
        "/api/chat/subagents",
        summary="List sub-agent runs",
        tags=["Copilot"],
        openapi_extra=DENY_AGENT,
    )
    async def list_subagents(
        parent_trace_id: Annotated[
            str | None,
            Query(
                description=(
                    "Filter to children of the conversation owning this (possibly "
                    "stale) leaf trace id. Omit for all runs."
                )
            ),
        ] = None,
    ) -> list[SubAgentItem]:
        if parent_trace_id is not None:
            records = subagent_registry.list_for_parent_trace(parent_trace_id)
        else:
            records = subagent_registry.list_all()
        return [SubAgentItem.from_record(record) for record in records]

    @app.get(
        "/api/chat/subagents/events",
        summary="Stream sub-agent status events",
        tags=["Copilot"],
        openapi_extra=DENY_AGENT,
    )
    async def stream_subagent_status_events() -> CancellableStreamingResponse:
        """Registry-level firehose of kiln-subagent-status events (snapshot then
        live). Lets the UI learn a child finished even when the parent
        conversation has no stream in flight."""
        return CancellableStreamingResponse(
            content=_status_firehose_stream(),
            media_type="text/event-stream",
        )

    @app.get(
        "/api/chat/subagents/{subagent_id}",
        summary="Get a sub-agent run",
        tags=["Copilot"],
        openapi_extra=DENY_AGENT,
        response_model_exclude_none=True,
    )
    async def get_subagent(
        subagent_id: Annotated[str, Path(description="The sub-agent id.")],
        include_report: Annotated[
            bool, Query(description="Include the final report for terminal runs.")
        ] = False,
    ) -> SubAgentItem:
        run = subagent_registry.get(subagent_id)
        if run is None:
            raise HTTPException(
                status_code=404, detail=f"Sub-agent not found: {subagent_id}"
            )
        return SubAgentItem.from_record(run.record, include_report=include_report)

    @app.get(
        "/api/chat/subagents/{subagent_id}/events",
        summary="Stream a sub-agent's chat events",
        tags=["Copilot"],
        openapi_extra=DENY_AGENT,
    )
    async def stream_subagent_events(
        subagent_id: Annotated[str, Path(description="The sub-agent id to observe.")],
    ) -> CancellableStreamingResponse:
        """Pure-observer SSE of the child's chat stream (buffer replay + live);
        404 if unknown or GC'd."""
        run = subagent_registry.get(subagent_id)
        if run is None:
            raise HTTPException(
                status_code=404, detail=f"Sub-agent not found: {subagent_id}"
            )
        return CancellableStreamingResponse(
            content=_run_events_stream(run),
            media_type="text/event-stream",
        )

    @app.post(
        "/api/chat/subagents/{subagent_id}/stop",
        summary="Stop a sub-agent run",
        tags=["Copilot"],
        status_code=202,
        openapi_extra=DENY_AGENT,
    )
    @no_write_lock
    async def stop_subagent(
        subagent_id: Annotated[str, Path(description="The sub-agent id to stop.")],
    ) -> Response:
        """Hard-stop the run. Idempotent — stopping an unknown or terminal run
        is a no-op (its report, if any, is still delivered to the parent)."""
        await subagent_registry.stop(subagent_id)
        return Response(status_code=202)

    @app.post(
        "/api/chat/subagents/{subagent_id}/message",
        summary="Send a user message into a running sub-agent",
        tags=["Copilot"],
        status_code=202,
        openapi_extra=DENY_AGENT,
    )
    @no_write_lock
    async def send_subagent_message(
        subagent_id: Annotated[str, Path(description="The sub-agent id to message.")],
        body: SendSubAgentMessageRequest,
    ) -> Response:
        """Inject a steer message from the overseeing user; drained by the child
        at its next round boundary. 404 for unknown runs, 409 for terminal ones."""
        run = subagent_registry.get(subagent_id)
        if run is None:
            raise HTTPException(
                status_code=404, detail=f"Sub-agent not found: {subagent_id}"
            )
        accepted = subagent_registry.send_message(subagent_id, body.content)
        if not accepted:
            raise HTTPException(
                status_code=409,
                detail=f"Sub-agent already finished: {subagent_id}",
            )
        return Response(status_code=202)
