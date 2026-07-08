from __future__ import annotations

import asyncio
import logging
import os

from app.desktop.studio_server.chat.auto.models import InboundMessage
from app.desktop.studio_server.chat.auto.registry import _extract_trace_id

from .events import SubAgentEventBus, SubAgentStatusBus
from .models import (
    SubAgentRecord,
    SubAgentSeed,
    SubAgentStatus,
    _utc_now,
    format_subagent_report,
)
from .runner import SubAgentRunner
from .sse import format_subagent_status

logger = logging.getLogger(__name__)

DEFAULT_MAX_CONCURRENT = 5
MAX_CONCURRENT_ENV_VAR = "KILN_CHAT_SUBAGENT_MAX_CONCURRENT"
DEFAULT_MAX_PER_PARENT = 3
MAX_PER_PARENT_ENV_VAR = "KILN_CHAT_SUBAGENT_MAX_PER_PARENT"
# Wall-clock cap per sub-agent run.
DEFAULT_TIMEOUT_SECONDS = 1800.0
TIMEOUT_ENV_VAR = "KILN_CHAT_SUBAGENT_TIMEOUT_SECONDS"
# Terminal entries linger for late re-attach; an UNDELIVERED report pins the
# entry longer so an idle interactive parent doesn't lose it.
TERMINAL_TTL_SECONDS = 300.0
UNDELIVERED_REPORT_TTL_SECONDS = 3600.0


class SubAgentCapError(Exception):
    """Raised when a spawn would exceed a concurrency cap. Surfaced to the
    MODEL as a tool-result error (never an HTTP error) so it can adapt."""


def _resolve_int_env(env_var: str, default: int) -> int:
    raw = os.environ.get(env_var)
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return default


def _resolve_timeout() -> float:
    raw = os.environ.get(TIMEOUT_ENV_VAR)
    if raw:
        try:
            value = float(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return DEFAULT_TIMEOUT_SECONDS


class SubAgentRun:
    """Live in-memory machinery for one sub-agent: record + current-turn byte
    buffer + per-run bus + inbound steer queue. The supervising task is owned by
    the registry (decoupled from any HTTP request)."""

    def __init__(
        self,
        record: SubAgentRecord,
        runner: SubAgentRunner,
    ) -> None:
        self.record = record
        self.buffer: list[bytes] = []
        self.bus = SubAgentEventBus(self)
        self.inbound: list[InboundMessage] = []
        self.runner = runner
        self.terminal_event = asyncio.Event()

    def enqueue(self, message: InboundMessage) -> None:
        self.inbound.append(message)

    def drain_inbound(self) -> list[InboundMessage]:
        messages = self.inbound
        self.inbound = []
        return messages

    def emit(self, payload: bytes) -> None:
        """Buffer + publish; reset the buffer at each persisted snapshot so it
        always holds exactly "events since the last snapshot" (same contract as
        ``AutoChatRun.emit``)."""
        self.buffer.append(payload)
        self.bus.publish(payload)
        if _extract_trace_id(payload) is not None:
            self.buffer.clear()

    def status_marker_bytes(self) -> bytes:
        return format_subagent_status(self.record)


class SubAgentRegistry:
    """In-memory registry owning sub-agent lifecycle, caps, consent memory, and
    report delivery. Singleton per process, modeled on ``AutoChatRegistry``."""

    def __init__(
        self,
        max_concurrent: int | None = None,
        max_per_parent: int | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self._max_concurrent = (
            max_concurrent
            if max_concurrent is not None
            else _resolve_int_env(MAX_CONCURRENT_ENV_VAR, DEFAULT_MAX_CONCURRENT)
        )
        self._max_per_parent = (
            max_per_parent
            if max_per_parent is not None
            else _resolve_int_env(MAX_PER_PARENT_ENV_VAR, DEFAULT_MAX_PER_PARENT)
        )
        self._timeout_seconds = (
            timeout_seconds if timeout_seconds is not None else _resolve_timeout()
        )
        self._runs: dict[str, SubAgentRun] = {}
        # Child leaf trace id (whole chain) → subagent_id, for the sessions join.
        self._trace_index: dict[str, str] = {}
        # Any seen PARENT leaf trace id → parent_key. Interactive parents rotate
        # their leaf every turn; note_parent_trace() chains new leaves to the
        # same key so consent memory / pending reports / child listing survive.
        self._parent_alias: dict[str, str] = {}
        # Parents (by parent_key) that have granted spawn consent.
        self._consented_parents: set[str] = set()
        # Terminal-but-undelivered reports queued per parent_key (subagent_ids).
        self._pending_reports: dict[str, list[str]] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._gc_tasks: dict[str, asyncio.Task] = {}
        self.status_bus = SubAgentStatusBus()

    # -- parent keys -----------------------------------------------------------

    def parent_key_for_auto_run(self, run_id: str) -> str:
        return f"auto:{run_id}"

    def parent_key_for_trace(self, trace_id: str) -> str:
        """Resolve (or mint) the stable parent key for an interactive parent's
        leaf trace id, registering the alias."""
        key = self._parent_alias.get(trace_id)
        if key is None:
            key = f"trace:{trace_id}"
            self._parent_alias[trace_id] = key
        return key

    def note_parent_trace(self, old_leaf: str | None, new_leaf: str | None) -> None:
        """Chain an interactive parent's rotating leaf ids to its stable key."""
        if not old_leaf or not new_leaf or old_leaf == new_leaf:
            return
        key = self._parent_alias.get(old_leaf)
        if key is not None:
            self._parent_alias[new_leaf] = key

    # -- consent ----------------------------------------------------------------

    def mark_consented(self, parent_key: str) -> None:
        self._consented_parents.add(parent_key)

    def is_consented(self, parent_key: str) -> bool:
        return parent_key in self._consented_parents

    # -- reads -------------------------------------------------------------------

    def get(self, subagent_id: str) -> SubAgentRun | None:
        return self._runs.get(subagent_id)

    def list_for_parent(self, parent_key: str) -> list[SubAgentRecord]:
        return sorted(
            (
                run.record
                for run in self._runs.values()
                if run.record.parent_key == parent_key
            ),
            key=lambda r: r.created_at,
        )

    def list_all(self) -> list[SubAgentRecord]:
        return sorted(
            (run.record for run in self._runs.values()), key=lambda r: r.created_at
        )

    def list_for_parent_trace(self, trace_id: str) -> list[SubAgentRecord]:
        """Children of the conversation owning this (possibly stale) leaf trace
        id — resolves through the parent alias chain, so any leaf the
        conversation has ever had works."""
        key = self._parent_alias.get(trace_id)
        if key is None:
            return []
        return self.list_for_parent(key)

    def subagent_for_trace(self, trace_id: str) -> SubAgentRecord | None:
        subagent_id = self._trace_index.get(trace_id)
        if subagent_id is None:
            return None
        run = self._runs.get(subagent_id)
        return run.record if run is not None else None

    # -- spawn -------------------------------------------------------------------

    def spawn(
        self,
        seed: SubAgentSeed,
        *,
        upstream_url: str,
        headers: dict[str, str],
        orchestration_tool_names: frozenset[str] = frozenset(),
    ) -> SubAgentRecord:
        running = [
            run for run in self._runs.values() if not run.record.status.is_terminal
        ]
        if len(running) >= self._max_concurrent:
            raise SubAgentCapError(
                f"Too many concurrent sub-agents (max {self._max_concurrent}). "
                "Wait for one to finish (wait_for_subagents) or stop one first."
            )
        per_parent = sum(
            1 for run in running if run.record.parent_key == seed.parent_key
        )
        if per_parent >= self._max_per_parent:
            raise SubAgentCapError(
                f"This conversation already has {per_parent} running sub-agents "
                f"(max {self._max_per_parent}). Wait for one to finish or stop one."
            )

        record = SubAgentRecord(
            name=seed.name,
            agent_type=seed.agent_type,
            parent_key=seed.parent_key,
            parent_trace_id_at_spawn=seed.parent_trace_id,
        )

        async def _on_trace(new_trace_id: str) -> None:
            self._on_trace(record.subagent_id, new_trace_id)

        run_holder: list[SubAgentRun] = []

        def _emit(payload: bytes) -> None:
            run_holder[0].emit(payload)

        runner = SubAgentRunner(
            subagent_id=record.subagent_id,
            seed=seed,
            upstream_url=upstream_url,
            headers=headers,
            emit=_emit,
            on_trace=_on_trace,
            drain_inbound=lambda: run_holder[0].drain_inbound(),
            orchestration_tool_names=orchestration_tool_names,
        )
        run = SubAgentRun(record=record, runner=runner)
        run_holder.append(run)
        self._runs[record.subagent_id] = run
        self._publish_status(run)
        self._tasks[record.subagent_id] = asyncio.create_task(self._supervise(run))
        logger.info(
            "Spawned sub-agent %s (%s, parent=%s)",
            record.subagent_id,
            seed.agent_type,
            seed.parent_key,
        )
        return record

    # -- steer / stop -------------------------------------------------------------

    def send_message(self, subagent_id: str, content: str) -> bool:
        """Inject a user steer message into a RUNNING child (drained at the next
        round boundary). Echoes onto the child's bus so observers render it.
        Returns False for unknown/terminal runs (caller maps to 404/409)."""
        run = self._runs.get(subagent_id)
        if run is None or run.record.status.is_terminal:
            return False
        message = InboundMessage(content=content)
        from .sse import format_user_message

        run.emit(format_user_message(message.content, message.id))
        run.enqueue(message)
        self._touch(run)
        return True

    async def stop(self, subagent_id: str) -> str:
        """Hard-stop a running sub-agent. Returns one of
        ``stopped`` / ``not_found`` / ``already_finished``."""
        run = self._runs.get(subagent_id)
        if run is None:
            return "not_found"
        if run.record.status.is_terminal:
            return "already_finished"

        run.record.status = SubAgentStatus.STOPPED
        task = self._tasks.get(subagent_id)
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.debug(
                    "Sub-agent %s raised during stop await", subagent_id, exc_info=True
                )
        # A task cancelled before it first ran never entered _supervise, so its
        # finally (and _settle) never fired — settle here. _settle is run-once,
        # so this is a no-op when the supervisor already handled it.
        self._settle(run)
        return "stopped"

    async def handle_session_deleted(self, trace_id: str) -> None:
        """Cascade for a deleted chat session: if it was a sub-agent parent,
        stop its children and drop their pending reports; if the id belongs to a
        child's own session, stop that child."""
        parent_key = self._parent_alias.get(trace_id)
        if parent_key is not None:
            await self.stop_children(parent_key)
        record = self.subagent_for_trace(trace_id)
        if record is not None and not record.status.is_terminal:
            await self.stop(record.subagent_id)

    async def stop_children(self, parent_key: str) -> int:
        """Cascade-stop every running child of a parent (parent stopped/deleted).
        Also drops the parent's undelivered reports — there is nothing left to
        consume them. Returns how many children were stopped."""
        stopped = 0
        for record in self.list_for_parent(parent_key):
            if not record.status.is_terminal:
                outcome = await self.stop(record.subagent_id)
                if outcome == "stopped":
                    stopped += 1
        self._pending_reports.pop(parent_key, None)
        return stopped

    # -- wait ---------------------------------------------------------------------

    async def wait(
        self, subagent_ids: list[str], timeout_seconds: float
    ) -> tuple[list[SubAgentRecord], list[str]]:
        """Block until the given sub-agents are terminal or the timeout elapses.

        Returns ``(records, timed_out_ids)`` where ``records`` covers every known
        id (terminal or not) and ``timed_out_ids`` lists those still running.
        Reports on returned terminal records are considered delivered (the
        caller feeds them straight to the model)."""

        known = [sid for sid in subagent_ids if sid in self._runs]

        async def _wait_one(run: SubAgentRun) -> None:
            await run.terminal_event.wait()

        pending_runs = [
            self._runs[sid]
            for sid in known
            if not self._runs[sid].record.status.is_terminal
        ]
        if pending_runs:
            waiters = [asyncio.create_task(_wait_one(run)) for run in pending_runs]
            try:
                await asyncio.wait_for(
                    asyncio.gather(*waiters), timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                pass
            finally:
                for waiter in waiters:
                    waiter.cancel()

        records: list[SubAgentRecord] = []
        timed_out: list[str] = []
        for sid in known:
            run = self._runs[sid]
            records.append(run.record)
            if run.record.status.is_terminal:
                self._mark_report_delivered(run)
            else:
                timed_out.append(sid)
        return records, timed_out

    # -- report delivery ------------------------------------------------------------

    def drain_reports(self, parent_key: str) -> list[str]:
        """Take (and mark delivered) all undelivered reports queued for a parent,
        formatted as framed user-message payloads."""
        queued = self._pending_reports.pop(parent_key, [])
        reports: list[str] = []
        for subagent_id in queued:
            run = self._runs.get(subagent_id)
            if run is None or run.record.report_delivered:
                continue
            reports.append(format_subagent_report(run.record))
            self._mark_report_delivered(run)
        return reports

    def pending_reports_for_trace(self, trace_id: str) -> list[str]:
        """Reports awaiting delivery to the interactive parent whose (possibly
        rotated) leaf trace id this is. Used by the next-turn injection in the
        chat route."""
        key = self._parent_alias.get(trace_id)
        if key is None:
            return []
        return self.drain_reports(key)

    def has_pending_reports(self, parent_key: str) -> bool:
        return bool(self._pending_reports.get(parent_key))

    def mark_report_delivered(self, subagent_id: str) -> None:
        run = self._runs.get(subagent_id)
        if run is not None:
            self._mark_report_delivered(run)

    def _mark_report_delivered(self, run: SubAgentRun) -> None:
        if run.record.report_delivered:
            return
        run.record.report_delivered = True
        queued = self._pending_reports.get(run.record.parent_key)
        if queued and run.record.subagent_id in queued:
            queued.remove(run.record.subagent_id)
            if not queued:
                self._pending_reports.pop(run.record.parent_key, None)
        self._touch(run)

    # -- supervision -------------------------------------------------------------

    async def _supervise(self, run: SubAgentRun) -> None:
        subagent_id = run.record.subagent_id
        try:
            try:
                await asyncio.wait_for(run.runner.run(), timeout=self._timeout_seconds)
            except asyncio.CancelledError:
                if not run.record.status.is_terminal:
                    run.record.status = SubAgentStatus.STOPPED
                raise
            except asyncio.TimeoutError:
                run.record.status = SubAgentStatus.TIMEOUT
            except Exception:
                logger.exception("Sub-agent %s failed", subagent_id)
                run.record.status = SubAgentStatus.FAILED
            else:
                if not run.record.status.is_terminal:
                    run.record.status = run.runner.status
        finally:
            self._settle(run)

    def _settle(self, run: SubAgentRun) -> None:
        """Terminal bookkeeping — runs exactly once (guarded by terminal_event),
        from _supervise's finally on every exit path, plus a stop() backstop for
        tasks cancelled before they ever started."""
        if run.terminal_event.is_set():
            return
        subagent_id = run.record.subagent_id
        if not run.record.status.is_terminal:
            run.record.status = SubAgentStatus.FAILED
        run.record.rounds_used = run.runner.rounds_used
        run.record.final_report = self._final_report_for(run)
        run.inbound.clear()
        self._touch(run)
        self._tasks.pop(subagent_id, None)
        run.terminal_event.set()
        self._publish_status(run)
        self._deliver_report(run)
        self._schedule_gc(subagent_id)
        logger.info(
            "Sub-agent %s ended (status=%s, rounds=%d)",
            subagent_id,
            run.record.status.value,
            run.record.rounds_used,
        )

    def _final_report_for(self, run: SubAgentRun) -> str:
        """The report text for a terminal run. COMPLETED = the model's final
        text verbatim; other terminals get a status note prefixed so the parent
        always learns the outcome."""
        base = run.runner.final_report or ""
        status = run.record.status
        if status == SubAgentStatus.COMPLETED:
            return base or "(the sub-agent finished without producing a report)"
        notes = {
            SubAgentStatus.FAILED: "This sub-agent FAILED before completing its job.",
            SubAgentStatus.STOPPED: "This sub-agent was STOPPED before completing its job.",
            SubAgentStatus.TIMEOUT: "This sub-agent TIMED OUT before completing its job.",
        }
        note = notes.get(status, "")
        partial = base or "(no partial output was produced)"
        return f"{note}\nPartial output before it ended:\n{partial}"

    def _deliver_report(self, run: SubAgentRun) -> None:
        """Completion injection. Auto-run parents get the framed report pushed
        as an inbound message immediately (waking an IDLE parent); interactive
        parents get it queued for wait/status/next-turn delivery."""
        if run.record.report_delivered:
            return
        parent_key = run.record.parent_key
        if parent_key.startswith("auto:"):
            run_id = parent_key.removeprefix("auto:")
            # Lazy import: the auto registry imports this module's siblings.
            from app.desktop.studio_server.chat.auto.registry import auto_chat_registry

            delivered = auto_chat_registry.send_message(
                run_id, InboundMessage(content=format_subagent_report(run.record))
            )
            if delivered:
                self._mark_report_delivered(run)
                return
            # Auto parent gone (stopped/GC'd): fall through to the queue so a
            # resumed interactive turn on the same trace can still pick it up.
        self._pending_reports.setdefault(parent_key, []).append(run.record.subagent_id)

    def _publish_status(self, run: SubAgentRun) -> None:
        payload = format_subagent_status(run.record)
        run.emit(payload)
        self.status_bus.publish(payload)

    # -- trace index ----------------------------------------------------------------

    def _on_trace(self, subagent_id: str, new_trace_id: str) -> None:
        run = self._runs.get(subagent_id)
        if run is None:
            return
        if new_trace_id not in run.record.seen_trace_ids:
            run.record.seen_trace_ids.append(new_trace_id)
        run.record.current_trace_id = new_trace_id
        self._trace_index[new_trace_id] = subagent_id
        self._touch(run)
        self._publish_status(run)

    def _touch(self, run: SubAgentRun) -> None:
        run.record.updated_at = _utc_now()

    # -- GC ---------------------------------------------------------------------------

    def _schedule_gc(self, subagent_id: str) -> None:
        existing = self._gc_tasks.get(subagent_id)
        if existing is not None and not existing.done():
            return
        self._gc_tasks[subagent_id] = asyncio.create_task(
            self._gc_after_ttl(subagent_id)
        )

    async def _gc_after_ttl(self, subagent_id: str) -> None:
        try:
            await asyncio.sleep(TERMINAL_TTL_SECONDS)
            run = self._runs.get(subagent_id)
            # An undelivered report pins the entry (up to the longer cap) so an
            # idle interactive parent doesn't lose it to GC.
            if run is not None and not run.record.report_delivered:
                await asyncio.sleep(
                    max(UNDELIVERED_REPORT_TTL_SECONDS - TERMINAL_TTL_SECONDS, 0)
                )
        except asyncio.CancelledError:
            return
        finally:
            self._gc_tasks.pop(subagent_id, None)
        self._evict(subagent_id)

    def _evict(self, subagent_id: str) -> None:
        run = self._runs.pop(subagent_id, None)
        if run is None:
            return
        for tid in list(self._trace_index):
            if self._trace_index[tid] == subagent_id:
                del self._trace_index[tid]
        queued = self._pending_reports.get(run.record.parent_key)
        if queued and subagent_id in queued:
            queued.remove(subagent_id)
            if not queued:
                self._pending_reports.pop(run.record.parent_key, None)
        logger.debug("Evicted terminal sub-agent %s after TTL", subagent_id)


subagent_registry = SubAgentRegistry()
