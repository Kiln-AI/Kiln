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
    InboundMessage,
    _new_run_id,
    _utc_now,
)
from .runner import AutoChatRunner
from .sse import (
    format_auto_mode_idle,
    format_auto_mode_off,
    format_auto_mode_on,
    format_user_message,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_CONCURRENT = 5
MAX_CONCURRENT_ENV_VAR = "KILN_CHAT_AUTO_MAX_CONCURRENT"
# How long a terminal run lingers so a late re-attach still gets auto-mode-off.
TERMINAL_TTL_SECONDS = 300.0

# Map off statuses to the auto-mode-off reason. Revision R1: auto-mode-off is
# published ONLY on explicit disable (Stop or the disable_auto_mode tool); all
# burst-level endings go IDLE instead (see _supervise / format_auto_mode_idle).
_OFF_REASON = {
    AutoRunStatus.USER_STOPPED: "user_stopped",
    AutoRunStatus.USER_DISABLED: "user_disabled",
}


class AutoChatConcurrencyError(Exception):
    """Raised when starting a run would exceed the concurrency cap.

    Auto mode is interactive — there's no queueing, so this surfaces to the
    caller (Phase 3 maps it to HTTP 429)."""


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
    """Live in-memory machinery for one conversation's auto mode.

    Revision R1: the entry is **per-conversation and persistent**. It holds the
    conversation auto-mode flag (via ``record.status``: RUNNING/IDLE = on), the
    per-run ``AutoChatEventBus``, the current-turn byte ``buffer`` (everything
    since the last persisted snapshot, for gapless re-attach), an inbound message
    queue, and the **current burst's** ``AutoChatRunner`` (rebuilt per burst).
    The supervising ``asyncio.Task`` is owned by the registry, not here, so it
    survives client disconnects.
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
        self._upstream_url = upstream_url
        self._headers = headers
        self._on_trace = on_trace
        # Messages sent via /message while a burst is active, drained by the
        # runner at the next round boundary. Idle sends start a new burst instead.
        self.inbound: list[InboundMessage] = []
        self.runner = self._new_runner(seed)

    def _new_runner(self, seed: AutoChatSeed) -> AutoChatRunner:
        return AutoChatRunner(
            run_id=self.record.run_id,
            seed=seed,
            upstream_url=self._upstream_url,
            headers=self._headers,
            emit=self.emit,
            on_trace=self._on_trace,
            drain_inbound=self.drain_inbound,
        )

    def start_burst(self, seed: AutoChatSeed) -> AutoChatRunner:
        """Rebuild the runner for a fresh burst (idle → running)."""
        self.runner = self._new_runner(seed)
        return self.runner

    def enqueue(self, message: InboundMessage) -> None:
        self.inbound.append(message)

    def drain_inbound(self) -> list[InboundMessage]:
        messages = self.inbound
        self.inbound = []
        return messages

    def echo_user_message(self, message: InboundMessage) -> None:
        """Echo a user message onto the bus + current-turn buffer so observers
        (including the sender) render it immediately, consistent with replay."""
        self.emit(format_user_message(message.content))

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
            self.record.run_id, _off_reason_for(self.record.status)
        )

    def idle_marker_bytes(self) -> bytes:
        return format_auto_mode_idle(self.record.run_id, self.runner.idle_reason)


def _off_reason_for(status: AutoRunStatus) -> str:
    return _OFF_REASON.get(status, "user_stopped")


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
        """Runs whose conversation auto-mode flag is on (RUNNING or IDLE)."""
        return [run.record for run in self._runs.values() if run.record.status.flag_on]

    def run_id_for_trace(self, trace_id: str) -> str | None:
        """run_id for a trace, limited to runs whose flag is on (RUNNING or
        IDLE) — so the green dot persists while idle between bursts."""
        run_id = self._trace_index.get(trace_id)
        if run_id is None:
            return None
        run = self._runs.get(run_id)
        if run is None or not run.record.status.flag_on:
            return None
        return run_id

    def is_active_for_trace(self, trace_id: str) -> tuple[bool, str | None]:
        run_id = self.run_id_for_trace(trace_id)
        return (run_id is not None, run_id)

    def resolve_trace(self, trace_id: str) -> tuple[str, str] | None:
        """Resolve a (possibly stale) trace id to an active run.

        A tab that was gone while the server-owned run advanced holds a STALE
        leaf trace id — the run's current leaf has moved on. The whole-chain
        ``_trace_index`` (every seen trace id → run) lets us match anyway, so a
        hard refresh can resync. Returns ``(run_id, current_trace_id)`` for runs
        whose flag is on (RUNNING or IDLE), or ``None`` if there's no active run
        for the trace. The returned ``current_trace_id`` is the run's CURRENT
        leaf so the caller can hydrate the rounds completed while it was away."""
        run_id = self.run_id_for_trace(trace_id)
        if run_id is None:
            return None
        run = self._runs.get(run_id)
        if run is None:
            return None
        return (run_id, run.record.current_trace_id)

    # -- start ---------------------------------------------------------------

    def start(
        self,
        seed: AutoChatSeed,
        *,
        reason: str | None,
        upstream_url: str,
        headers: dict[str, str],
    ) -> AutoRunRecord:
        # Cap counts flag-on conversations (RUNNING or IDLE): each is a live
        # auto-mode conversation holding a registry entry.
        active = sum(1 for r in self._runs.values() if r.record.status.flag_on)
        if active >= self._max_concurrent:
            raise AutoChatConcurrencyError(
                f"Too many concurrent auto runs (max {self._max_concurrent}). "
                "Stop a running auto run and try again."
            )

        run_id = self._fresh_run_id()
        # Manual enable (Revision R1, functional spec §4.1(2)): when the seed has
        # nothing to send upstream — no enable_auto_mode call to resolve, no
        # pending sibling tool calls, and no extra messages — the conversation is
        # merely ARMED. Starting a burst here would POST an empty turn upstream,
        # which the backend rejects ("No messages were sent to the server").
        # Instead create the run IDLE (flag on, indicator shown) and do NOT
        # supervise; the first /message starts the burst via send_message().
        is_armed_only = (
            not seed.enable_tool_call_id
            and not seed.pending_tool_calls
            and not seed.extra_messages
        )

        record = AutoRunRecord(
            run_id=run_id,
            status=AutoRunStatus.IDLE if is_armed_only else AutoRunStatus.RUNNING,
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
        if is_armed_only:
            # Buffer the on→idle markers so a connecting observer immediately
            # lands on "flag on, idle (waiting for you)" with no live burst —
            # the indicator shows without an empty upstream POST. The first
            # /message starts the real burst (send_message, IDLE → RUNNING).
            run.runner.idle_reason = "armed"
            run.emit(format_auto_mode_on(run_id))
            run.emit(run.idle_marker_bytes())
            logger.info("Armed auto run %s (trace_id=%s)", run_id, seed.trace_id)
            return record
        self._tasks[run_id] = asyncio.create_task(self._supervise(run))
        logger.info("Started auto run %s (trace_id=%s)", run_id, seed.trace_id)
        return record

    def _fresh_run_id(self) -> str:
        run_id = _new_run_id()
        while run_id in self._runs:
            run_id = _new_run_id()
        return run_id

    # -- inbound message injection (Revision R1) -----------------------------

    def send_message(self, run_id: str, message: InboundMessage) -> bool:
        """Send a user message into an auto-mode conversation without disabling it.

        - If a burst is **active** (RUNNING): enqueue the message; the runner
          drains it at the next round boundary and appends it to the continuation.
        - If the run is **IDLE**: start a fresh burst seeded with the message.

        Echoes the message onto the run's bus + current-turn buffer so all
        observers (including the sender) render it immediately. Returns False if
        the run is unknown or its flag is off (caller maps to 404/409)."""
        run = self._runs.get(run_id)
        if run is None or not run.record.status.flag_on:
            return False

        run.echo_user_message(message)

        if run.record.status == AutoRunStatus.RUNNING:
            run.enqueue(message)
            return True

        # IDLE → start a new burst seeded with the queued message(s).
        seed = AutoChatSeed(
            trace_id=message.trace_id or run.record.current_trace_id,
            extra_messages=[message.as_chat_message()],
        )
        run.record.status = AutoRunStatus.RUNNING
        run.start_burst(seed)
        self._cancel_gc(run_id)
        self._tasks[run_id] = asyncio.create_task(self._supervise(run))
        self._touch(run)
        logger.info("Resumed auto run %s from idle via /message", run_id)
        return True

    async def disable(self, run_id: str) -> bool:
        """Clear the conversation flag in response to the disable_auto_mode tool.

        Used by the interactive (ChatStreamSession) interception path. The flag
        must be cleared even mid-burst: if a burst is RUNNING we mark the run
        USER_DISABLED and cancel its task (mirroring stop()), so _supervise's
        CancelledError handler tears the burst down WITHOUT re-settling to IDLE
        (CR Moderate 2 — otherwise the idle settle would clobber USER_DISABLED
        and re-enable the flag). If there's no live burst, clear the flag
        directly. Publishes auto-mode-off(user_disabled). Returns False if the
        run is unknown."""
        run = self._runs.get(run_id)
        if run is None:
            return False

        # Mark USER_DISABLED first so a cancelled burst's CancelledError handler
        # preserves it (rather than forcing USER_STOPPED) and publishes the
        # correct off-reason.
        if run.record.status.is_terminal:
            return True
        run.record.status = AutoRunStatus.USER_DISABLED

        task = self._tasks.get(run_id)
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.debug(
                    "Auto run %s raised during disable await", run_id, exc_info=True
                )
            return True

        # No live burst (idle). Clear the flag directly.
        run.inbound.clear()
        self._publish_off(run)
        self._touch(run)
        self._schedule_gc(run_id)
        return True

    async def disable_for_trace(self, trace_id: str) -> bool:
        run_id = self._trace_index.get(trace_id)
        if run_id is None:
            return False
        return await self.disable(run_id)

    # -- supervision ---------------------------------------------------------

    async def _supervise(self, run: AutoChatRun) -> None:
        """Own one burst's lifetime, decoupled from any HTTP request — like
        ``JobRegistry._supervise``.

        Revision R1: a settled burst transitions the run to IDLE (the
        conversation auto-mode flag stays on, the entry is NOT evicted) and
        publishes ``auto-mode-idle``. ``auto-mode-off`` + terminal GC happen only
        on explicit disable — user Stop (cancel → USER_STOPPED) or the
        ``disable_auto_mode`` tool (USER_DISABLED)."""
        run_id = run.record.run_id
        try:
            try:
                await run.runner.run()
            except asyncio.CancelledError:
                # A cancel from stop() leaves the flag at its pre-cancel value
                # (RUNNING/IDLE) → USER_STOPPED. A cancel from disable() has
                # already set USER_DISABLED; preserve any already-off status so
                # we publish the correct off-reason (CR Moderate 2).
                if not run.record.status.is_terminal:
                    run.record.status = AutoRunStatus.USER_STOPPED
                run.inbound.clear()
                self._publish_off(run)
                self._touch(run)
                raise
            except Exception:
                # An unrecoverable burst error ends the burst but leaves the flag
                # on so the user can retry or stop (functional spec §4.4).
                logger.exception("Auto run %s burst failed", run_id)
                run.runner.idle_reason = "error"
                run.record.status = AutoRunStatus.IDLE
            else:
                # If the flag was already cleared off-band (e.g. disable() raced
                # in just as the burst returned), don't resurrect it — leave the
                # terminal status as-is. Otherwise adopt the runner's status.
                if not run.record.status.is_terminal:
                    run.record.status = run.runner.status

            if run.record.status.is_terminal:
                # Explicitly disabled (or otherwise off): publish off, GC handled
                # in finally. Do NOT settle to IDLE (that would re-enable the
                # flag and republish the idle marker — CR Moderate 2).
                run.inbound.clear()
                self._publish_off(run)
            else:
                # Settled burst → IDLE; the flag stays on, entry not evicted.
                run.record.status = AutoRunStatus.IDLE
                run.bus.publish(run.idle_marker_bytes())
            self._touch(run)
            logger.info(
                "Auto run %s burst ended (status=%s)",
                run_id,
                run.record.status.value,
            )
        finally:
            self._tasks.pop(run_id, None)
            # Only off (explicitly-disabled) runs are GC'd; IDLE runs persist
            # until the user stops/disables them (or restart/eviction).
            if run.record.status.is_terminal:
                self._schedule_gc(run_id)

    def _publish_off(self, run: AutoChatRun) -> None:
        run.bus.publish(
            format_auto_mode_off(run.record.run_id, _off_reason_for(run.record.status))
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
        """Stop auto mode for the conversation (Stop button). Idempotent.

        Revision R1 + graceful stop (functional spec §4.4(1)): Stop is NOT a hard
        cancel. A RUNNING burst is asked to stop **gracefully** — the runner
        finishes the in-flight upstream round (no cut-off), then at the round
        boundary surfaces any pending client tool calls for normal approval
        (tool-calls-pending) and ends the burst USER_STOPPED. We only set the stop
        intent here and return promptly (the endpoint replies 202): the
        supervising task winds the burst down and publishes auto-mode-off on its
        own, so observers see the off marker when the round actually ends. An IDLE
        run has no burst task, so the flag is cleared here directly."""
        run = self._runs.get(run_id)
        task = self._tasks.get(run_id)
        if task is not None:
            if run is not None:
                run.runner.request_stop()
            return

        # No live burst (idle or already off). If the flag is still on, clear it.
        if run is None or run.record.status.is_terminal:
            return
        run.record.status = AutoRunStatus.USER_STOPPED
        run.inbound.clear()
        self._publish_off(run)
        self._touch(run)
        self._schedule_gc(run_id)

    # -- terminal GC ---------------------------------------------------------

    def _schedule_gc(self, run_id: str) -> None:
        existing = self._gc_tasks.get(run_id)
        if existing is not None and not existing.done():
            return
        self._gc_tasks[run_id] = asyncio.create_task(self._gc_after_ttl(run_id))

    def _cancel_gc(self, run_id: str) -> None:
        """Defensive: a fresh burst should never start on a GC-scheduled run
        (only off runs are GC'd, and a new burst only starts from IDLE), but
        cancel any pending GC if one exists."""
        gc_task = self._gc_tasks.pop(run_id, None)
        if gc_task is not None:
            gc_task.cancel()

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
