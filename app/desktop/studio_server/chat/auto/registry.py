from __future__ import annotations

import asyncio
import json
import logging
import os

from app.desktop.studio_server.chat.constants import KILN_SSE_CHAT_TRACE

from .events import AutoChatEventBus
from .models import (
    AutoChatSeed,
    AutoRunRecord,
    AutoRunStatus,
    _new_run_id,
    _utc_now,
)
from .runner import AutoChatRunner
from .sse import format_auto_mode_off

logger = logging.getLogger(__name__)

DEFAULT_MAX_CONCURRENT = 5
MAX_CONCURRENT_ENV_VAR = "KILN_CHAT_AUTO_MAX_CONCURRENT"
# How long a terminal run lingers so a late re-attach still gets auto-mode-off.
TERMINAL_TTL_SECONDS = 300.0

# Map terminal statuses to the auto-mode-off reason. DONE is special-cased off
# the runner's finer-grained done_reason (done vs asked_user).
_OFF_REASON = {
    AutoRunStatus.USER_STOPPED: "user_stopped",
    AutoRunStatus.ERROR: "error",
    AutoRunStatus.MAX_ROUNDS: "max_rounds",
}


class AutoChatConcurrencyError(Exception):
    """Raised when starting a run would exceed the concurrency cap.

    Auto mode is interactive — there's no queueing, so this surfaces to the
    caller (Phase 3 maps it to HTTP 429)."""


class AutoRunNotFoundError(Exception):
    pass


def _resolve_max_concurrent(explicit: int | None) -> int:
    if explicit is not None:
        return explicit
    raw = os.environ.get(MAX_CONCURRENT_ENV_VAR)
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return DEFAULT_MAX_CONCURRENT


def _extract_trace_id(payload: bytes) -> str | None:
    """Return the trace id if ``payload`` carries a kiln_chat_trace SSE event.

    Each forwarded chunk is newline-joined SSE lines; scan the ``data:`` lines
    for the trace event so the buffer reset/index update lands exactly when a
    snapshot was persisted upstream.

    This is a deliberate second, narrow SSE parse (the full pipeline parse lives
    in EventParser) — emit() runs on every forwarded chunk and only needs the
    trace boundary, not full event semantics. A cheap substring guard skips the
    JSON parse entirely for the overwhelming majority of chunks that can't carry
    the event, keeping the dual-parse cost negligible."""
    if KILN_SSE_CHAT_TRACE.encode() not in payload:
        return None
    for line in payload.split(b"\n"):
        if not line.startswith(b"data: "):
            continue
        body = line[6:].strip()
        if not body or body == b"[DONE]":
            continue
        try:
            event = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(event, dict) and event.get("type") == KILN_SSE_CHAT_TRACE:
            tid = event.get("trace_id")
            if isinstance(tid, str) and tid:
                return tid
    return None


class AutoChatRun:
    """Live in-memory machinery for one auto run.

    Holds the serializable ``AutoRunRecord``, the per-run ``AutoChatEventBus``,
    the current-turn byte ``buffer`` (everything since the last persisted
    snapshot, for gapless re-attach), and the ``AutoChatRunner``. The supervising
    ``asyncio.Task`` is owned by the registry, not here, so it survives client
    disconnects.
    """

    def __init__(
        self,
        record: AutoRunRecord,
        seed: AutoChatSeed,
        upstream_url: str,
        headers: dict[str, str],
        on_trace,
    ) -> None:
        self.record = record
        self.buffer: list[bytes] = []
        self.bus = AutoChatEventBus(self)
        self.runner = AutoChatRunner(
            run_id=record.run_id,
            seed=seed,
            upstream_url=upstream_url,
            headers=headers,
            emit=self.emit,
            on_trace=on_trace,
        )

    def emit(self, payload: bytes) -> None:
        """Append to the current-turn buffer and publish to subscribers.

        When the payload carries a ``kiln_chat_trace`` event a snapshot was just
        persisted upstream, so the in-progress turn ends: forward the event
        first, then reset the buffer so it always holds exactly "events since the
        last snapshot". The registry index update is handled separately via the
        runner's on_trace callback (which has the awaitable lock-free path)."""
        self.buffer.append(payload)
        self.bus.publish(payload)
        if _extract_trace_id(payload) is not None:
            self.buffer.clear()

    def terminal_off_bytes(self) -> bytes:
        return format_auto_mode_off(
            self.record.run_id, _off_reason_for(self.record.status, self.runner)
        )


def _off_reason_for(status: AutoRunStatus, runner: AutoChatRunner) -> str:
    if status == AutoRunStatus.DONE:
        return runner.done_reason
    return _OFF_REASON.get(status, "done")


class AutoChatRegistry:
    """In-memory registry owning auto-run lifecycle and concurrency.

    Singleton per process, modeled on ``JobRegistry``. Supervising tasks are
    owned here and decoupled from any HTTP request — a client disconnect only
    tears down its SSE subscription; the run keeps going.
    """

    def __init__(self, max_concurrent: int | None = None) -> None:
        self._max_concurrent = _resolve_max_concurrent(max_concurrent)
        self._runs: dict[str, AutoChatRun] = {}
        # Every seen leaf trace id maps to its run (for history correlation /
        # session-list enrichment).
        self._trace_index: dict[str, str] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._gc_tasks: dict[str, asyncio.Task] = {}

    # -- reads ---------------------------------------------------------------

    def get(self, run_id: str) -> AutoChatRun | None:
        return self._runs.get(run_id)

    def list_active(self) -> list[AutoRunRecord]:
        return [
            run.record
            for run in self._runs.values()
            if run.record.status == AutoRunStatus.RUNNING
        ]

    def run_id_for_trace(self, trace_id: str) -> str | None:
        """run_id for a trace, limited to active runs."""
        run_id = self._trace_index.get(trace_id)
        if run_id is None:
            return None
        run = self._runs.get(run_id)
        if run is None or run.record.status != AutoRunStatus.RUNNING:
            return None
        return run_id

    def is_active_for_trace(self, trace_id: str) -> tuple[bool, str | None]:
        run_id = self.run_id_for_trace(trace_id)
        return (run_id is not None, run_id)

    # -- start ---------------------------------------------------------------

    def start(
        self,
        seed: AutoChatSeed,
        *,
        reason: str | None,
        upstream_url: str,
        headers: dict[str, str],
    ) -> AutoRunRecord:
        active = sum(
            1 for r in self._runs.values() if r.record.status == AutoRunStatus.RUNNING
        )
        if active >= self._max_concurrent:
            raise AutoChatConcurrencyError(
                f"Too many concurrent auto runs (max {self._max_concurrent}). "
                "Stop a running auto run and try again."
            )

        run_id = self._fresh_run_id()
        record = AutoRunRecord(
            run_id=run_id,
            status=AutoRunStatus.RUNNING,
            current_trace_id=seed.trace_id,
            seen_trace_ids=[seed.trace_id],
            reason=reason,
        )

        async def _on_trace(new_trace_id: str) -> None:
            self._on_trace(run_id, new_trace_id)

        run = AutoChatRun(
            record=record,
            seed=seed,
            upstream_url=upstream_url,
            headers=headers,
            on_trace=_on_trace,
        )
        self._runs[run_id] = run
        self._trace_index[seed.trace_id] = run_id
        self._tasks[run_id] = asyncio.create_task(self._supervise(run))
        logger.info("Started auto run %s (trace_id=%s)", run_id, seed.trace_id)
        return record

    def _fresh_run_id(self) -> str:
        run_id = _new_run_id()
        while run_id in self._runs:
            run_id = _new_run_id()
        return run_id

    # -- supervision ---------------------------------------------------------

    async def _supervise(self, run: AutoChatRun) -> None:
        """Own the run's whole lifetime, decoupled from any HTTP request — like
        ``JobRegistry._supervise``. Run the runner, translate the outcome to a
        terminal status, publish ``auto-mode-off``, and schedule terminal GC."""
        run_id = run.record.run_id
        try:
            try:
                await run.runner.run()
                run.record.status = run.runner.status
            except asyncio.CancelledError:
                run.record.status = AutoRunStatus.USER_STOPPED
                self._publish_off(run)
                self._touch(run)
                raise
            except Exception:
                logger.exception("Auto run %s failed", run_id)
                run.record.status = AutoRunStatus.ERROR
            self._publish_off(run)
            self._touch(run)
            logger.info(
                "Auto run %s finished (status=%s)", run_id, run.record.status.value
            )
        finally:
            self._tasks.pop(run_id, None)
            self._schedule_gc(run_id)

    def _publish_off(self, run: AutoChatRun) -> None:
        run.bus.publish(
            format_auto_mode_off(
                run.record.run_id, _off_reason_for(run.record.status, run.runner)
            )
        )

    # -- trace index ---------------------------------------------------------

    def _on_trace(self, run_id: str, new_trace_id: str) -> None:
        run = self._runs.get(run_id)
        if run is None:
            return
        if new_trace_id not in run.record.seen_trace_ids:
            run.record.seen_trace_ids.append(new_trace_id)
        run.record.current_trace_id = new_trace_id
        self._trace_index[new_trace_id] = run_id
        self._touch(run)

    def _touch(self, run: AutoChatRun) -> None:
        run.record.updated_at = _utc_now()

    # -- stop ----------------------------------------------------------------

    async def stop(self, run_id: str) -> None:
        """Cancel the run cooperatively. Idempotent. The supervising task's
        CancelledError handler sets USER_STOPPED and publishes auto-mode-off."""
        task = self._tasks.get(run_id)
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.debug("Auto run %s raised during stop await", run_id, exc_info=True)

    # -- terminal GC ---------------------------------------------------------

    def _schedule_gc(self, run_id: str) -> None:
        existing = self._gc_tasks.get(run_id)
        if existing is not None and not existing.done():
            return
        self._gc_tasks[run_id] = asyncio.create_task(self._gc_after_ttl(run_id))

    async def _gc_after_ttl(self, run_id: str) -> None:
        try:
            await asyncio.sleep(TERMINAL_TTL_SECONDS)
        except asyncio.CancelledError:
            return
        finally:
            self._gc_tasks.pop(run_id, None)
        self._evict(run_id)

    def _evict(self, run_id: str) -> None:
        run = self._runs.pop(run_id, None)
        if run is None:
            return
        for tid in list(self._trace_index):
            if self._trace_index[tid] == run_id:
                del self._trace_index[tid]
        logger.debug("Evicted terminal auto run %s after TTL", run_id)


auto_chat_registry = AutoChatRegistry()
