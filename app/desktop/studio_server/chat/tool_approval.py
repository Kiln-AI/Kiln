import asyncio
import json
import logging
import threading
from dataclasses import dataclass
from typing import Any, Literal

from fastapi import HTTPException, Request
from kiln_ai.adapters.model_adapters.stream_events import ToolInputAvailableEvent

from app.desktop.studio_server.chat.constants import SSE_TYPE_TOOL_APPROVAL_REQUIRED
from app.desktop.studio_server.chat.tool_metadata import _parse_kiln_tool_metadata

logger = logging.getLogger(__name__)


@dataclass
class PendingToolApproval:
    future: asyncio.Future[dict[str, bool]]
    required_tool_call_ids: frozenset[str]


class ToolApprovalRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: dict[str, PendingToolApproval] = {}

    async def register_wait(
        self, batch_id: str, required_tool_call_ids: frozenset[str]
    ) -> asyncio.Future[dict[str, bool]]:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, bool]] = loop.create_future()
        pending = PendingToolApproval(
            future=future, required_tool_call_ids=required_tool_call_ids
        )
        with self._lock:
            self._pending[batch_id] = pending
        return future

    def pop_pending(self, batch_id: str) -> PendingToolApproval | None:
        with self._lock:
            return self._pending.pop(batch_id, None)

    def submit_decisions(self, batch_id: str, decisions: dict[str, bool]) -> None:
        with self._lock:
            pending = self._pending.get(batch_id)
        if pending is None:
            raise HTTPException(
                status_code=404, detail="Timed out waiting for tool approval"
            )
        if pending.future.done():
            raise HTTPException(
                status_code=409, detail="Approval batch was already completed"
            )
        required = pending.required_tool_call_ids
        got = frozenset(decisions.keys())
        if got != required:
            raise HTTPException(
                status_code=400,
                detail="decisions must include exactly each toolCallId in the approval batch",
            )
        with self._lock:
            self._pending.pop(batch_id, None)
        pending.future.set_result(decisions)


_tool_approval_registry = ToolApprovalRegistry()


async def _register_tool_approval_wait(
    batch_id: str, required_tool_call_ids: frozenset[str]
) -> asyncio.Future[dict[str, bool]]:
    return await _tool_approval_registry.register_wait(batch_id, required_tool_call_ids)


def _pop_pending_tool_approval(batch_id: str) -> PendingToolApproval | None:
    return _tool_approval_registry.pop_pending(batch_id)


async def submit_tool_approval_decisions(
    batch_id: str, decisions: dict[str, bool]
) -> None:
    _tool_approval_registry.submit_decisions(batch_id, decisions)


def _format_tool_approval_required_sse(
    batch_id: str, items: list[dict[str, Any]]
) -> bytes:
    payload = {
        "type": SSE_TYPE_TOOL_APPROVAL_REQUIRED,
        "approvalBatchId": batch_id,
        "items": items,
    }
    return f"data: {json.dumps(payload)}\n\n".encode()


def _approval_item_from_event(event: ToolInputAvailableEvent) -> dict[str, Any]:
    meta = _parse_kiln_tool_metadata(event.kiln_metadata)
    item: dict[str, Any] = {
        "toolCallId": event.toolCallId,
        "toolName": event.toolName,
    }
    if meta.permission is not None:
        item["permission"] = meta.permission
    if meta.approval_description is not None:
        item["approvalDescription"] = meta.approval_description
    return item


async def _wait_for_tool_approval(
    batch_id: str,
    future: asyncio.Future[dict[str, bool]],
    _request: Request | None,
    timeout_sec: float,
) -> dict[str, bool] | Literal["timeout"]:
    try:
        return await asyncio.wait_for(future, timeout=timeout_sec)
    except asyncio.TimeoutError:
        _pop_pending_tool_approval(batch_id)
        if not future.done():
            future.cancel()
        return "timeout"
    except asyncio.CancelledError:
        _pop_pending_tool_approval(batch_id)
        if not future.done():
            future.cancel()
        raise
