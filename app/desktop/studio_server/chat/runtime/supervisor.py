"""ConversationSupervisor — the ONE lifecycle owner (architecture §5).

Replaces both old registries (``AutoChatRegistry`` + ``SubAgentRegistry``)
with a single registry keyed by session id. It owns, for every conversation:

- the ``ConversationRecord`` + frozen ``ConversationPolicy``,
- the run ``asyncio.Task`` (decoupled from any HTTP request — a client
  disconnect only tears down its SSE subscription, never the run; same
  contract both old registries had, modeled on ``JobRegistry``),
- one ``ByteEventBus`` + replay buffer,
- the inbox queue (send-while-running / steer / report injection),
- the pending approval batch,
- consent memory (on the record, keyed by session id — the old
  parent-alias maps die with the registries),
- the children index (``parent_session_id``) and the report queue/delivery,
- concurrency caps (auto concurrent; sub-agent per-parent/global — same
  numbers, env vars, and message texts as today),
- ``wait``/``stop``/cascades, and GC (terminal TTL + undelivered-report
  pinning; OFF-auto TTL; interactive LRU eviction).

Settle-once rule (architecture §9): every run ends through exactly one
method, ``_finish_run`` — reached from ``_supervise``'s ``finally`` on every
exit path, plus the ``stop()`` backstop for tasks cancelled before they ever
started (a cancelled-before-first-run task never enters ``_supervise``, so
its ``finally`` never fires — the old ``SubAgentRegistry.stop()`` backstop,
now generalized to every kind).

Phase 1: nothing constructs the module-level instance for the running app —
the supervisor exists purely under test until phase 2 wires sub-agents onto
it.

Restart recovery (architecture §5): the supervisor cold-starts empty; later
phases create records from history session ids on first observe/send and
rehydrate pending approvals from the persisted trace tail.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, AsyncGenerator, Literal

from .bus import ByteEventBus
from .engine import ConversationEngine, EngineIO
from .models import (
    ConversationKind,
    ConversationPolicy,
    ConversationRecord,
    InboundMessage,
    PendingApprovalBatch,
    RunState,
    SubAgentSeed,
    _utc_now,
    auto_policy,
    format_subagent_report,
    interactive_policy,
    subagent_policy,
)
from .sse import format_conversation_state, format_user_message

logger = logging.getLogger(__name__)

# ── Caps & TTLs: same defaults, env vars, and semantics as the old
# registries, so operator overrides and user-visible limits are unchanged
# across the migration. ───────────────────────────────────────────────────────

DEFAULT_AUTO_MAX_CONCURRENT = 5
AUTO_MAX_CONCURRENT_ENV_VAR = "KILN_CHAT_AUTO_MAX_CONCURRENT"
DEFAULT_SUBAGENT_MAX_CONCURRENT = 5
SUBAGENT_MAX_CONCURRENT_ENV_VAR = "KILN_CHAT_SUBAGENT_MAX_CONCURRENT"
DEFAULT_SUBAGENT_MAX_PER_PARENT = 3
SUBAGENT_MAX_PER_PARENT_ENV_VAR = "KILN_CHAT_SUBAGENT_MAX_PER_PARENT"

# How long a terminal one-shot record (or an OFF-auto record) lingers so a
# late re-attach still gets the terminal/off state marker.
TERMINAL_TTL_SECONDS = 300.0
# An UNDELIVERED sub-agent report pins the record longer so an idle
# interactive parent doesn't lose it to GC (old sub-agent registry pinning).
UNDELIVERED_REPORT_TTL_SECONDS = 3600.0
# Idle interactive records are just a record + empty bus once their turn task
# ends — cheap — so instead of a TTL they're LRU-evicted only when the pool
# grows beyond this. (The conversation itself lives upstream in history; an
# evicted record is recreated on the next open — architecture §5.)
MAX_IDLE_INTERACTIVE_RECORDS = 100


class ConversationCapError(Exception):
    """Raised when creating/enabling a conversation would exceed a concurrency
    cap. Later phases map it exactly as today: HTTP 429 for auto enable, a
    tool-result error (never HTTP) for spawns."""


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


class _Conversation:
    """Live in-memory machinery for one conversation: record + policy + bus +
    inbox + pending approval batch. The supervising task is owned by the
    supervisor map, referenced here for lifecycle checks (the old
    AutoChatRun/SubAgentRun split, unified)."""

    def __init__(
        self,
        record: ConversationRecord,
        policy: ConversationPolicy,
        upstream_url: str,
        headers: dict[str, str],
    ) -> None:
        self.record = record
        self.policy = policy
        self.upstream_url = upstream_url
        self.headers = headers
        # The bus's on-subscribe marker must reflect the record AT SUBSCRIBE
        # TIME, hence lambdas over the live record rather than stored values.
        self.bus = ByteEventBus(
            marker_provider=lambda: format_conversation_state(self.record),
            terminal_check=lambda: self.record.state.is_terminal,
        )
        # Messages queued while a run is in flight, drained by the engine at
        # round boundaries. Idle sends start a run instead.
        self.inbox: list[InboundMessage] = []
        self.pending_batch: PendingApprovalBatch | None = None
        self.task: asyncio.Task | None = None
        # Graceful-stop intent polled by the engine (old runner.stop_requested).
        self.stop_requested: bool = False
        # Per-run settle guard: _finish_run must run exactly once per run
        # (reset by start_run). See the settle-once rule in the module doc.
        self.run_finished: bool = True
        # Set once, when a one-shot run reaches a terminal state — wait()
        # blocks on this (old SubAgentRun.terminal_event).
        self.settled: asyncio.Event = asyncio.Event()

    def drain_inbox(self) -> list[InboundMessage]:
        """Atomically take-and-clear (the engine's round-boundary drain)."""
        messages = self.inbox
        self.inbox = []
        return messages


class ConversationSupervisor:
    """Single registry owning every live conversation (see module docstring).

    Cap/TTL knobs are constructor-injectable for tests; production uses the
    env-var/env-default resolution exactly like the old registries.
    """

    def __init__(
        self,
        *,
        auto_max_concurrent: int | None = None,
        subagent_max_concurrent: int | None = None,
        subagent_max_per_parent: int | None = None,
        terminal_ttl_seconds: float = TERMINAL_TTL_SECONDS,
        undelivered_report_ttl_seconds: float = UNDELIVERED_REPORT_TTL_SECONDS,
        max_idle_interactive_records: int = MAX_IDLE_INTERACTIVE_RECORDS,
    ) -> None:
        self._auto_max_concurrent = (
            auto_max_concurrent
            if auto_max_concurrent is not None
            else _resolve_int_env(
                AUTO_MAX_CONCURRENT_ENV_VAR, DEFAULT_AUTO_MAX_CONCURRENT
            )
        )
        self._subagent_max_concurrent = (
            subagent_max_concurrent
            if subagent_max_concurrent is not None
            else _resolve_int_env(
                SUBAGENT_MAX_CONCURRENT_ENV_VAR, DEFAULT_SUBAGENT_MAX_CONCURRENT
            )
        )
        self._subagent_max_per_parent = (
            subagent_max_per_parent
            if subagent_max_per_parent is not None
            else _resolve_int_env(
                SUBAGENT_MAX_PER_PARENT_ENV_VAR, DEFAULT_SUBAGENT_MAX_PER_PARENT
            )
        )
        self._terminal_ttl_seconds = terminal_ttl_seconds
        self._undelivered_report_ttl_seconds = undelivered_report_ttl_seconds
        self._max_idle_interactive_records = max_idle_interactive_records
        self._conversations: dict[str, _Conversation] = {}
        # Every seen leaf trace id → session id. Still required for the
        # history join (session rows are keyed by leaf trace id until phase 5
        # keys them on session ids).
        self._trace_index: dict[str, str] = {}
        # Terminal-but-undelivered child reports queued per PARENT session id
        # (child session ids, drained in completion order).
        self._pending_reports: dict[str, list[str]] = {}
        self._gc_tasks: dict[str, asyncio.Task] = {}

    # ── Reads. ────────────────────────────────────────────────────────────────

    def get(self, session_id: str) -> ConversationRecord | None:
        conv = self._conversations.get(session_id)
        return conv.record if conv is not None else None

    def list_records(self) -> list[ConversationRecord]:
        return sorted(
            (conv.record for conv in self._conversations.values()),
            key=lambda r: r.created_at,
        )

    def children_of(self, parent_session_id: str) -> list[ConversationRecord]:
        """Children index — replaces SubAgentRegistry.list_for_parent (and the
        trace-keyed list_for_parent_trace: session ids are stable, so no alias
        chain is needed)."""
        return sorted(
            (
                conv.record
                for conv in self._conversations.values()
                if conv.record.parent_session_id == parent_session_id
            ),
            key=lambda r: r.created_at,
        )

    def session_for_trace(self, trace_id: str) -> str | None:
        """History join: resolve a (possibly stale) leaf trace id to its live
        conversation. Whole-chain index, like both old registries kept."""
        return self._trace_index.get(trace_id)

    def pending_approval(self, session_id: str) -> PendingApprovalBatch | None:
        """The parked batch awaiting decisions, if any (GET approvals)."""
        conv = self._conversations.get(session_id)
        return conv.pending_batch if conv is not None else None

    def subscribe(self, session_id: str) -> AsyncGenerator[bytes, None]:
        """Observer stream: current-turn replay → conversation-state marker →
        live. Raises KeyError for unknown conversations (route maps to 404).
        Disconnect only unsubscribes — the run is never affected."""
        return self._conversations[session_id].bus.subscribe()

    # ── Create. ───────────────────────────────────────────────────────────────

    def create_conversation(
        self,
        kind: ConversationKind,
        *,
        upstream_url: str,
        headers: dict[str, str],
        parent_session_id: str | None = None,
        seed: SubAgentSeed | None = None,
        max_rounds: int | None = None,
        wall_clock_seconds: float | None = None,
    ) -> ConversationRecord:
        """Create (but do not start) a conversation of the given kind.

        Enforces the same caps as the old registries at the same moment:
        auto-enable counts flag-on conversations (each is a live auto-mode
        conversation holding a slot — old AutoChatRegistry.start); spawns
        count non-terminal children per parent and globally (old
        SubAgentRegistry.spawn). Cap error messages are preserved verbatim —
        they surface to users/models today.
        """
        if kind == "auto":
            active = sum(1 for c in self._conversations.values() if c.record.auto_flag)
            if active >= self._auto_max_concurrent:
                raise ConversationCapError(
                    f"Too many concurrent auto runs (max {self._auto_max_concurrent}). "
                    "Stop a running auto run and try again."
                )
            policy = auto_policy()
            record = ConversationRecord(kind="auto", auto_flag=True)
        elif kind == "subagent":
            if seed is None:
                raise ValueError("subagent conversations require a seed")
            if parent_session_id is None:
                raise ValueError("subagent conversations require a parent_session_id")
            running = [
                c
                for c in self._conversations.values()
                if c.record.kind == "subagent" and not c.record.state.is_terminal
            ]
            if len(running) >= self._subagent_max_concurrent:
                raise ConversationCapError(
                    f"Too many concurrent sub-agents (max {self._subagent_max_concurrent}). "
                    "Wait for one to finish (wait_for_subagents) or stop one first."
                )
            per_parent = sum(
                1 for c in running if c.record.parent_session_id == parent_session_id
            )
            if per_parent >= self._subagent_max_per_parent:
                raise ConversationCapError(
                    f"This conversation already has {per_parent} running sub-agents "
                    f"(max {self._subagent_max_per_parent}). Wait for one to finish or stop one."
                )
            policy = subagent_policy(
                seed,
                max_rounds=max_rounds,
                wall_clock_seconds=wall_clock_seconds,
            )
            record = ConversationRecord(
                kind="subagent",
                parent_session_id=parent_session_id,
                name=seed.name,
                agent_type=seed.agent_type,
            )
        else:
            policy = interactive_policy()
            record = ConversationRecord(kind="interactive")

        conv = _Conversation(record, policy, upstream_url, headers)
        self._conversations[record.session_id] = conv
        # Keep the idle-interactive pool bounded (see MAX_IDLE_INTERACTIVE_
        # RECORDS). Run on every create so the pool can't creep past the cap.
        self._evict_idle_interactive_lru()
        return record

    def spawn_subagent(
        self,
        seed: SubAgentSeed,
        *,
        parent_session_id: str,
        upstream_url: str,
        headers: dict[str, str],
        max_rounds: int | None = None,
        wall_clock_seconds: float | None = None,
    ) -> ConversationRecord:
        """Create AND start a child run — spawn == start, exactly like the old
        SubAgentRegistry.spawn (the engine builds the seed body + kickoff echo
        from policy.seed)."""
        record = self.create_conversation(
            "subagent",
            upstream_url=upstream_url,
            headers=headers,
            parent_session_id=parent_session_id,
            seed=seed,
            max_rounds=max_rounds,
            wall_clock_seconds=wall_clock_seconds,
        )
        self.start_run(record.session_id)
        logger.info(
            "Spawned sub-agent conversation %s (%s, parent=%s)",
            record.session_id,
            seed.agent_type,
            parent_session_id,
        )
        return record

    # ── Run lifecycle. ────────────────────────────────────────────────────────

    def start_run(
        self, session_id: str, initial_body: dict[str, Any] | None = None
    ) -> None:
        """Start a turn/burst/run task for the conversation.

        ``initial_body`` is the upstream request body for the first round
        (interactive turn / auto burst seed); None lets the engine build the
        one-shot seed body from policy.seed (child runs).
        """
        conv = self._conversations[session_id]
        if conv.record.state.is_terminal:
            raise RuntimeError(f"conversation {session_id} already ended")
        if conv.task is not None and not conv.task.done():
            raise RuntimeError(f"conversation {session_id} already has a run in flight")
        # A fresh run should never start on a GC-scheduled record (only
        # off/terminal records are GC'd), but an idle re-arm on an OFF-auto
        # record races its TTL — cancel any pending GC defensively (old
        # registry _cancel_gc).
        self._cancel_gc(session_id)
        conv.run_finished = False
        conv.stop_requested = False
        conv.record.state = RunState.RUNNING
        self._touch(conv)
        conv.task = asyncio.create_task(self._supervise(conv, initial_body))
        # Live observers learn the run started; attaching observers get the
        # same truth from the on-subscribe marker.
        conv.bus.publish(format_conversation_state(conv.record))

    async def _supervise(
        self, conv: _Conversation, initial_body: dict[str, Any] | None
    ) -> None:
        """Own one run's lifetime, decoupled from any HTTP request.

        The engine records natural outcomes on the record itself; this wrapper
        only classifies the abnormal endings (architecture §9):
        cancellation → STOPPED/IDLE(user_stopped), wall-clock → TIMEOUT
        (one-shot only), unexpected exception → FAILED (one-shot) or
        IDLE(error) with the flag left on. Every path funnels through
        ``_finish_run`` in the ``finally``.
        """
        record = conv.record
        engine = ConversationEngine(conv.upstream_url, conv.headers)
        io = self._engine_io(conv)
        try:
            try:
                coro = engine.run(record, conv.policy, io, initial_body)
                if conv.policy.one_shot and conv.policy.wall_clock_seconds:
                    # Wall-clock budget applies to one-shot kinds only (old
                    # SubAgentRegistry._supervise wait_for). The TIMEOUT
                    # classification is scoped to THIS wait_for: on
                    # Python ≥ 3.11 asyncio.TimeoutError IS the builtin
                    # TimeoutError, which arbitrary libraries can raise — a
                    # TimeoutError escaping the engine on an interactive/auto
                    # run must NOT mark a terminal TIMEOUT on a kind whose
                    # states cycle forever (functional spec §1); it falls to
                    # the generic-exception → IDLE("error") branch below,
                    # matching old auto's behavior (its _supervise had no
                    # TimeoutError handler). (CR M1.)
                    try:
                        await asyncio.wait_for(
                            coro, timeout=conv.policy.wall_clock_seconds
                        )
                    except asyncio.TimeoutError:
                        record.state = RunState.TIMEOUT
                else:
                    await coro
            except asyncio.CancelledError:
                # A cancel from stop() already pre-marked the outcome
                # (STOPPED / flag-off), which we must preserve so the correct
                # reason publishes (old CR Moderate 2: don't clobber a
                # pre-set USER_DISABLED/USER_STOPPED). Only fill in defaults
                # when nothing was pre-marked.
                if not record.state.is_terminal:
                    if conv.policy.one_shot:
                        record.state = RunState.STOPPED
                    else:
                        record.state = RunState.IDLE
                        if record.auto_flag:
                            record.auto_flag = False
                            record.idle_reason = "user_stopped"
                raise
            except Exception:
                # An unrecoverable engine error: one-shot runs FAIL; for
                # interactive/auto the burst ends but the flag stays on so
                # the user can retry or stop (old registry exception paths).
                logger.exception("Conversation %s run failed", record.session_id)
                if conv.policy.one_shot:
                    record.state = RunState.FAILED
                else:
                    record.state = RunState.IDLE
                    record.idle_reason = "error"
        finally:
            self._finish_run(conv)

    def _finish_run(self, conv: _Conversation) -> None:
        """THE settle path — every run ends here exactly once (architecture
        §9: all settle/publish/deliver logic in one place).

        Runs from ``_supervise``'s ``finally`` on every exit (natural end,
        cancel, timeout, exception) AND from ``stop()`` as the backstop for
        tasks cancelled before they ever started (which never enter
        ``_supervise``). The ``run_finished`` guard makes the double call a
        no-op — the run-once ``_settle`` pattern from the old sub-agent
        registry, generalized to every kind.
        """
        if conv.run_finished:
            return
        conv.run_finished = True
        record = conv.record
        conv.task = None
        conv.stop_requested = False
        # A parked batch can't outlive its run (the awaiting engine is gone).
        # Phase 4's restart recovery rebuilds batches from the trace tail.
        conv.pending_batch = None

        if conv.policy.one_shot:
            # Terminal bookkeeping (old SubAgentRegistry._settle).
            if not record.state.is_terminal:
                # Defensive: a one-shot run that exits without a terminal
                # state failed in a way we didn't classify.
                record.state = RunState.FAILED
            record.final_report = self._final_report_for(record)
            conv.inbox.clear()
            conv.settled.set()
            self._touch(conv)
            conv.bus.publish(format_conversation_state(record))
            self._deliver_report(conv)
            self._schedule_gc(record.session_id)
            logger.info(
                "Sub-agent conversation %s ended (state=%s, rounds=%d)",
                record.session_id,
                record.state.value,
                record.rounds_used,
            )
            return

        # Interactive turn / auto burst settle: the conversation persists.
        if record.state in (RunState.RUNNING, RunState.AWAITING_APPROVAL):
            # The engine exited without recording an outcome (e.g. cancelled
            # before its first await, or a defensive fallback) — an idle
            # boundary is the safe truth.
            record.state = RunState.IDLE
        self._touch(conv)
        conv.bus.publish(format_conversation_state(record))
        if record.kind == "auto" and not record.auto_flag:
            # The auto-mode flag cleared during this burst (stop/disable):
            # old "off" semantics — queued inbox dies with the flag, and the
            # record is GC'd after the terminal TTL (a late re-attach still
            # gets the off marker until then).
            conv.inbox.clear()
            self._schedule_gc(record.session_id)
        logger.info(
            "Conversation %s run ended (state=%s, auto_flag=%s, reason=%s)",
            record.session_id,
            record.state.value,
            record.auto_flag,
            record.idle_reason,
        )

    def _engine_io(self, conv: _Conversation) -> EngineIO:
        """Wire the engine's io bundle onto this conversation's machinery."""
        record = conv.record

        async def on_trace(trace_id: str) -> None:
            # The engine already updated the record (single-writer rule);
            # the supervisor only maintains its cross-conversation index.
            self._trace_index[trace_id] = record.session_id
            self._touch(conv)

        async def await_decisions(batch: PendingApprovalBatch) -> dict[str, bool]:
            conv.pending_batch = batch
            # Tell live observers the run parked (the engine already emitted
            # the tool-calls-pending payload with the batch contents; this is
            # the lifecycle marker).
            conv.bus.publish(format_conversation_state(record))
            await batch.decided.wait()
            # The batch stays on the conversation (decided) until the run
            # settles or the next park replaces it, so a second decide can be
            # answered with a conflict rather than a 404 (functional spec §5:
            # two tabs — first decision set wins, the second gets 409).
            return dict(batch.decisions or {})

        return EngineIO(
            emit=conv.bus.emit,
            on_trace=on_trace,
            drain_inbox=conv.drain_inbox,
            drain_reports=lambda: self.drain_reports(record.session_id),
            await_decisions=await_decisions,
            stop_requested=lambda: conv.stop_requested,
            # Phase 1: orchestration tools still execute against the OLD
            # registries via the old loops; the new engine has no
            # orchestration identity until phase 2 retargets
            # execute_orchestration_tool onto this supervisor. A None ctx
            # resolves those calls to a structured "unavailable" error.
            orchestration_ctx=None,
        )

    # ── Messages. ─────────────────────────────────────────────────────────────

    def send_message(self, session_id: str, content: str) -> bool:
        """Queue a user message into the conversation (POST /messages).

        Behavior by state (functional spec §2): RUNNING/AWAITING_APPROVAL →
        queued, drained at the next round boundary (or after decisions
        resolve); IDLE → starts a turn seeded with the message. Echoes the
        message onto the bus + replay buffer at ENQUEUE time so every observer
        (including the sender) renders it immediately — and so the engine's
        drain must never re-echo (echo-once, old CR Moderate 1).

        Returns False for unknown/terminal conversations (routes map to
        404/409). Unlike the old auto registry this also accepts messages for
        flag-off records: an OFF-auto conversation IS an idle interactive
        conversation in the unified model, and messaging it re-arms a normal
        interactive turn (phase 4 behavior; harmless and unreachable until
        then).
        """
        conv = self._conversations.get(session_id)
        if conv is None or conv.record.state.is_terminal:
            return False
        message = InboundMessage(content=content)
        conv.bus.emit(format_user_message(message.content, message.id))
        self._touch(conv)

        if conv.record.state in (RunState.RUNNING, RunState.AWAITING_APPROVAL):
            conv.inbox.append(message)
            return True

        # IDLE → start a fresh turn/burst seeded with the message. Body shape
        # preserved from the old idle re-arm (AutoChatRegistry.send_message →
        # AutoChatSeed(extra_messages=[...])._build_seed_body): continue from
        # the current leaf, message unframed (framing is for MID-run drains
        # only), auto_mode riding iff the flag is on.
        body: dict[str, Any] = {"messages": [message.as_chat_message()]}
        if conv.record.current_leaf_trace_id is not None:
            body["trace_id"] = conv.record.current_leaf_trace_id
        if conv.record.auto_flag:
            body["auto_mode"] = True
        self.start_run(session_id, body)
        logger.info("Resumed conversation %s from idle via message", session_id)
        return True

    # ── Approvals. ────────────────────────────────────────────────────────────

    def decide(
        self, session_id: str, batch_id: str, decisions: dict[str, bool]
    ) -> Literal["ok", "not_found", "conflict"]:
        """Resolve a parked approval batch (POST approvals/decisions).

        "not_found" → no such conversation / no such batch (route: 404);
        "conflict" → the batch was already decided — first decision set wins,
        the second tab gets 409 (functional spec §5).
        """
        conv = self._conversations.get(session_id)
        if conv is None or conv.pending_batch is None:
            return "not_found"
        batch = conv.pending_batch
        if batch.batch_id != batch_id:
            return "not_found"
        if batch.decided.is_set():
            return "conflict"
        batch.decisions = dict(decisions)
        batch.decided.set()
        self._touch(conv)
        return "ok"

    # ── Stop / cascades. ──────────────────────────────────────────────────────

    async def stop(self, session_id: str) -> None:
        """Stop the conversation's run. Idempotent.

        - one-shot: hard stop — cancel the task immediately (old
          SubAgentRegistry.stop), pre-marking STOPPED so the cancel handler
          preserves the reason.
        - auto: the Stop button — cancel the in-flight burst immediately and
          clear the flag (old AutoChatRegistry.stop hard-cancel semantics),
          pre-marking flag-off/user_stopped for the same reason-preservation.
        - interactive: cancel the in-flight turn; the record idles.

        Always runs the cancel-before-first-run backstop (a task cancelled
        before it ever ran never entered _supervise, so its finally/_finish_run
        never fired — settle here; _finish_run is run-once so the double call
        is a no-op). Cascades to children in every case: their reports have
        nothing left to consume them (old cascade).
        """
        conv = self._conversations.get(session_id)
        if conv is None or conv.record.state.is_terminal:
            return
        record = conv.record

        task = conv.task
        if task is not None and not task.done():
            # Pre-mark the outcome BEFORE cancelling so the CancelledError
            # handler (and any observer of the settle) sees the true reason
            # (old CR Moderate 2 pattern, mirrored from both registries).
            if conv.policy.one_shot:
                record.state = RunState.STOPPED
            elif record.auto_flag:
                record.auto_flag = False
                record.idle_reason = "user_stopped"
            conv.stop_requested = True
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.debug(
                    "Conversation %s raised during stop await",
                    session_id,
                    exc_info=True,
                )
            # Backstop (see docstring).
            self._finish_run(conv)
            await self.stop_children(session_id)
            return

        # No live run. One-shot records without a task are either terminal
        # (guarded above) or not yet started (spawn always starts, so this is
        # unreachable in practice) — nothing to do beyond the flag clear for
        # idle auto conversations (old AutoChatRegistry.stop idle branch).
        if record.auto_flag:
            record.auto_flag = False
            record.idle_reason = "user_stopped"
            conv.inbox.clear()
            self._touch(conv)
            conv.bus.publish(format_conversation_state(record))
            self._schedule_gc(session_id)
        await self.stop_children(session_id)

    async def stop_children(self, parent_session_id: str) -> int:
        """Cascade-stop every running child of a parent (parent
        stopped/disabled/deleted). Also drops the parent's undelivered
        reports — there is nothing left to consume them. Returns how many
        children were stopped. (Old SubAgentRegistry.stop_children.)"""
        stopped = 0
        for record in self.children_of(parent_session_id):
            if not record.state.is_terminal:
                await self.stop(record.session_id)
                stopped += 1
        self._pending_reports.pop(parent_session_id, None)
        return stopped

    # ── Wait (the wait_for_subagents primitive). ──────────────────────────────

    async def wait(
        self, session_ids: list[str], timeout_seconds: float
    ) -> tuple[list[ConversationRecord], list[str]]:
        """Block until the given (one-shot) conversations are terminal or the
        timeout elapses. Returns ``(records, timed_out_ids)`` where records
        covers every known id and timed_out_ids lists those still running.

        Deliberately does NOT consume reports: they flow exclusively through
        the injection channel (``<subagent_report>`` user messages) so the
        report is always persisted in the parent's trace and rendered as a
        report panel — a wait result is a tool output buried in a step group.
        (Old SubAgentRegistry.wait contract, verbatim.)
        """
        known = [sid for sid in session_ids if sid in self._conversations]
        pending = [
            self._conversations[sid]
            for sid in known
            if not self._conversations[sid].record.state.is_terminal
        ]
        if pending:
            waiters = [asyncio.create_task(conv.settled.wait()) for conv in pending]
            try:
                await asyncio.wait_for(
                    asyncio.gather(*waiters), timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                pass
            finally:
                for waiter in waiters:
                    waiter.cancel()

        records: list[ConversationRecord] = []
        timed_out: list[str] = []
        for sid in known:
            conv = self._conversations[sid]
            records.append(conv.record)
            if not conv.record.state.is_terminal:
                timed_out.append(sid)
        return records, timed_out

    # ── Report delivery (completion injection). ───────────────────────────────

    def _deliver_report(self, conv: _Conversation) -> None:
        """Deliver a settled child's report to its parent.

        Mechanism unchanged from the old registries, now keyed by stable ids:
        an auto-flag parent gets the framed report pushed as an inbox message
        immediately (waking an IDLE parent into a fresh burst); an interactive
        parent gets it queued for the next-turn / mid-stream drain
        (``drain_reports``). Exactly one channel per report — the routing here
        is what lets the engine call drain_reports unconditionally.
        """
        record = conv.record
        if record.report_delivered or record.parent_session_id is None:
            return
        parent = self._conversations.get(record.parent_session_id)
        if (
            parent is not None
            and parent.record.auto_flag
            and not parent.record.state.is_terminal
        ):
            delivered = self.send_message(
                parent.record.session_id, format_subagent_report(record)
            )
            if delivered:
                self._mark_report_delivered(conv)
                return
            # Parent vanished between the check and the send: fall through to
            # the queue so a resumed turn can still pick the report up (old
            # auto-parent-gone fallback).
        self._pending_reports.setdefault(record.parent_session_id, []).append(
            record.session_id
        )

    def drain_reports(self, parent_session_id: str) -> list[str]:
        """Take (and mark delivered) all undelivered reports queued for a
        parent, formatted as framed user-message payloads (the engine appends
        them to the continuation and echoes them)."""
        queued = self._pending_reports.pop(parent_session_id, [])
        reports: list[str] = []
        for child_sid in queued:
            conv = self._conversations.get(child_sid)
            if conv is None or conv.record.report_delivered:
                continue
            reports.append(format_subagent_report(conv.record))
            self._mark_report_delivered(conv)
        return reports

    def has_pending_reports(self, parent_session_id: str) -> bool:
        return bool(self._pending_reports.get(parent_session_id))

    def _mark_report_delivered(self, conv: _Conversation) -> None:
        record = conv.record
        if record.report_delivered:
            return
        record.report_delivered = True
        if record.parent_session_id is not None:
            queued = self._pending_reports.get(record.parent_session_id)
            if queued and record.session_id in queued:
                queued.remove(record.session_id)
                if not queued:
                    self._pending_reports.pop(record.parent_session_id, None)
        self._touch(conv)

    def _final_report_for(self, record: ConversationRecord) -> str:
        """The report text for a settled one-shot run. COMPLETED = the model's
        final text verbatim; other terminals get a status note prefixed so the
        parent always learns the outcome. (Old SubAgentRegistry._final_report_
        for, verbatim texts — they are persisted in parent traces.)"""
        base = record.final_report or ""
        if record.state == RunState.COMPLETED:
            return base or "(the sub-agent finished without producing a report)"
        notes = {
            RunState.FAILED: "This sub-agent FAILED before completing its job.",
            RunState.STOPPED: "This sub-agent was STOPPED before completing its job.",
            RunState.TIMEOUT: "This sub-agent TIMED OUT before completing its job.",
        }
        note = notes.get(record.state, "")
        partial = base or "(no partial output was produced)"
        return f"{note}\nPartial output before it ended:\n{partial}"

    # ── Bookkeeping. ──────────────────────────────────────────────────────────

    def _touch(self, conv: _Conversation) -> None:
        conv.record.updated_at = _utc_now()

    # ── GC. ───────────────────────────────────────────────────────────────────

    def _schedule_gc(self, session_id: str) -> None:
        existing = self._gc_tasks.get(session_id)
        if existing is not None and not existing.done():
            return
        self._gc_tasks[session_id] = asyncio.create_task(self._gc_after_ttl(session_id))

    def _cancel_gc(self, session_id: str) -> None:
        gc_task = self._gc_tasks.pop(session_id, None)
        if gc_task is not None:
            gc_task.cancel()

    async def _gc_after_ttl(self, session_id: str) -> None:
        try:
            await asyncio.sleep(self._terminal_ttl_seconds)
            conv = self._conversations.get(session_id)
            # An undelivered report pins the record (up to the longer cap) so
            # an idle interactive parent doesn't lose it to GC (old sub-agent
            # registry pinning).
            if (
                conv is not None
                and conv.policy.one_shot
                and not conv.record.report_delivered
            ):
                await asyncio.sleep(
                    max(
                        self._undelivered_report_ttl_seconds
                        - self._terminal_ttl_seconds,
                        0,
                    )
                )
        except asyncio.CancelledError:
            return
        finally:
            self._gc_tasks.pop(session_id, None)
        self._evict(session_id)

    def _evict(self, session_id: str) -> None:
        conv = self._conversations.pop(session_id, None)
        if conv is None:
            return
        # End any live observer streams: an evicted conversation's bus can
        # never emit again, so a subscriber left attached (possible on the
        # interactive LRU path in particular — CR n3) would otherwise park
        # forever on a dead queue. EOF lets the client re-open from history,
        # which recreates the record.
        conv.bus.close()
        for tid in list(self._trace_index):
            if self._trace_index[tid] == session_id:
                del self._trace_index[tid]
        # Drop this record from its parent's report queue (it can never be
        # formatted again) and orphan its own children's queue.
        parent_sid = conv.record.parent_session_id
        if parent_sid is not None:
            queued = self._pending_reports.get(parent_sid)
            if queued and session_id in queued:
                queued.remove(session_id)
                if not queued:
                    self._pending_reports.pop(parent_sid, None)
        self._pending_reports.pop(session_id, None)
        logger.debug("Evicted conversation %s", session_id)

    def _evict_idle_interactive_lru(self) -> None:
        """Bound the idle-interactive pool: evict least-recently-touched IDLE
        interactive records (no task, nothing parked) beyond the cap. Cheap by
        design — an idle interactive conversation is just a record + empty bus
        (architecture §5); the transcript lives upstream and reopening the
        conversation recreates the record."""
        idle = [
            conv
            for conv in self._conversations.values()
            if conv.record.kind == "interactive"
            and conv.record.state == RunState.IDLE
            and conv.task is None
            and conv.pending_batch is None
        ]
        overflow = len(idle) - self._max_idle_interactive_records
        if overflow <= 0:
            return
        for conv in sorted(idle, key=lambda c: c.record.updated_at)[:overflow]:
            self._evict(conv.record.session_id)
