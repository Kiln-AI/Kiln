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

Phase 4: the supervisor owns EVERY conversation kind. Interactive
conversations (the most-used path, formerly ``ChatStreamSession`` behind
``POST /api/chat``) run here as a TURN TASK per turn (IDLE → RUNNING → IDLE),
created/adopted via ``adopt_interactive`` and driven by ``send_message``'s
idle re-arm. The auto flip is now the true "same run, new policy" flip
(architecture §2): ``enable_auto`` swaps an interactive record's policy AND
kind to auto on the SAME record, and every flag-off settle swaps it back —
an off-auto conversation IS an idle interactive conversation, so it joins
the idle-interactive LRU pool instead of the old OFF-auto TTL GC. The last
old-world identity bridge (``ParentConversationIndex``'s ``trace:<leaf>``
parent keys) died with the old loop: every child now carries a real parent
session id.

Restart recovery (architecture §5, wired this phase): the supervisor
cold-starts empty; opening a conversation from history creates a record from
its leaf trace id (``adopt_interactive``) and pending approvals are
rehydrated from the persisted trace tail
(``rehydrate_pending_approvals``) — deciding a rehydrated (runless) batch
starts a RESUME RUN that executes the batch and continues the loop, exactly
the flow the old ``POST /api/chat/execute-tools`` endpoint drove.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import TYPE_CHECKING, Any, AsyncGenerator, Literal

import httpx
from app.desktop.studio_server.chat.constants import DENIED_TOOL_OUTPUT
from app.desktop.studio_server.chat.debug_log import chat_debug_log
from app.desktop.studio_server.chat.stream_session import (
    ToolCallInfo,
    _pending_item_from_event,
    execute_tool_batch,
)
from kiln_ai.adapters.model_adapters.stream_events import ToolInputAvailableEvent
from kiln_ai.tools.built_in_tools.disable_auto_mode_tool import (
    DISABLE_AUTO_MODE_TOOL_NAME,
)
from kiln_ai.tools.built_in_tools.enable_auto_mode_tool import (
    ENABLE_AUTO_MODE_TOOL_NAME,
)

from .bus import BroadcastBus, ByteEventBus
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
    build_auto_seed_body,
    continuation_key_fields,
    format_subagent_report,
    interactive_policy,
    subagent_policy,
)
from .sse import (
    format_conversation_state,
    format_tool_calls_pending,
    format_user_message,
)

if TYPE_CHECKING:
    # Import-cycle avoidance only: chat/orchestration.py imports this module
    # at module level (it targets the supervisor singleton), so the ctx type
    # is quoted and resolved lazily where instances are built.
    from app.desktop.studio_server.chat.orchestration import OrchestrationContext

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

# How long a terminal one-shot record lingers so a late re-attach still gets
# the terminal state marker. (Phase 4 note: OFF-auto records no longer TTL-GC
# — a flag-off settle swaps them back to interactive records, which are
# LRU-bounded instead.)
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


# Timeout for the one-off upstream snapshot GET the approval-rehydration path
# makes (architecture §2 recovery contract). Short and best-effort: a failed
# fetch just means "no pending approvals rehydrated", never an error surface.
REHYDRATE_FETCH_TIMEOUT_SECONDS = 15.0


def _trace_text_content(content: Any) -> str:
    """Text of a persisted trace message's ``content`` (string or the list
    form some providers persist). Mirrors the web UI's ``extractTextContent``
    so both ends read the same tail."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and "text" in part:
                parts.append(str(part["text"]))
        return "".join(parts)
    return ""


def _pending_events_from_trace_tail(
    trace: list[dict[str, Any]],
) -> tuple[list[ToolInputAvailableEvent], list[ToolInputAvailableEvent], str]:
    """Rebuild the UNANSWERED tool calls of a persisted trace's tail as
    tool-input events, split into ``(client_events, signal_events)``, plus
    the tail assistant text (architecture §2: "the batch is reconstructible
    from the persisted trace tail — an assistant message with unanswered
    tool calls").

    Reconstruction notes (documented behavior deltas, all conservative):

    - The stream-time ``kiln_metadata`` (executor / requires_approval /
      permission / approval_description) is NOT persisted in traces, so every
      rebuilt call carries ``{"requires_approval": True}`` — the user is asked
      about everything in a rehydrated batch, worst case including a call the
      live metadata would have run without asking. Denying still yields
      DENIED_TOOL_OUTPUT, so nothing can run un-consented.
    - The auto-mode SIGNAL tools come back in the SEPARATE ``signal_events``
      list: they are never executed as tools (interceptors answer them) and
      never enter the approval batch's items, but a signal riding NEXT TO a
      real client call must still be answered on the resume continuation
      (as declined — its consent dialog died with the restart) or the trace
      keeps a dangling tool call the provider rejects on the next turn.
    - Server-executed tool calls are answered inside the same persisted
      snapshot by the upstream orchestrator, so an unanswered call in the
      tail is a client call by construction.
    """
    last_assistant: dict[str, Any] | None = None
    last_assistant_idx = -1
    for idx in range(len(trace) - 1, -1, -1):
        if trace[idx].get("role") == "assistant":
            last_assistant = trace[idx]
            last_assistant_idx = idx
            break
    if last_assistant is None:
        return [], [], ""
    assistant_text = _trace_text_content(last_assistant.get("content"))
    tool_calls = last_assistant.get("tool_calls") or []
    if not isinstance(tool_calls, list) or not tool_calls:
        return [], [], assistant_text
    answered = {
        msg.get("tool_call_id")
        for msg in trace[last_assistant_idx + 1 :]
        if msg.get("role") == "tool"
    }
    events: list[ToolInputAvailableEvent] = []
    signal_events: list[ToolInputAvailableEvent] = []
    for tc in tool_calls:
        if not isinstance(tc, dict):
            continue
        tc_id = tc.get("id")
        function = tc.get("function") or {}
        name = function.get("name") if isinstance(function, dict) else None
        if not isinstance(tc_id, str) or not isinstance(name, str) or not name:
            continue
        if tc_id in answered:
            continue
        raw_args = function.get("arguments") if isinstance(function, dict) else None
        try:
            parsed = json.loads(raw_args) if isinstance(raw_args, str) else {}
        except json.JSONDecodeError:
            parsed = {}
        event = ToolInputAvailableEvent(
            toolCallId=tc_id,
            toolName=name,
            input=parsed if isinstance(parsed, dict) else {},
            kiln_metadata={"requires_approval": True},
        )
        if name in (ENABLE_AUTO_MODE_TOOL_NAME, DISABLE_AUTO_MODE_TOOL_NAME):
            signal_events.append(event)
        else:
            events.append(event)
    return events, signal_events, assistant_text


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
        # Correlation id for upstream requests: lets the backend's chat debug
        # log (kiln_server ``chat_debug_log_enabled``) key its events by this
        # conversation so the two sides' timelines can be joined. Always sent
        # — it's just an opaque id the backend ignores unless debugging.
        self.headers = {**headers, "X-Kiln-Conversation-Id": record.session_id}
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
        # Conversation identity for sub-agent orchestration tool calls, built
        # lazily by the supervisor for PARENT kinds (interactive/auto) and
        # reused across runs so consent/lineage bookkeeping is per-conversation
        # (old AutoChatRunner._ctx / ChatStreamSession._get_orchestration_ctx).
        # Children keep None: their orchestration calls are answered by the
        # depth-guard interceptor, and a None ctx is the execute_tool_batch
        # backstop ("unavailable") if one ever slipped past it.
        self.orchestration_ctx: "OrchestrationContext | None" = None
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
        # Every seen leaf trace id (plus any adopted resume key) → session id.
        # INTERNAL since phase 5 (the browser never sees trace ids). Phase 6
        # removed its RESUME role (the backend resolves session ids itself),
        # but the index stays for the HISTORY JOIN: the upstream sessions
        # list is leaf-keyed (each row's ``id`` is its current leaf), so the
        # list proxy resolves rows to live records through this chain, and
        # browser keys naming a live conversation (by any leaf it ever had,
        # or its adopted key) resolve here without an upstream round-trip.
        self._trace_index: dict[str, str] = {}
        # Terminal-but-undelivered child reports queued per PARENT session id
        # (child session ids, drained in completion order).
        self._pending_reports: dict[str, list[str]] = {}
        self._gc_tasks: dict[str, asyncio.Task] = {}
        # Registry-level conversation-state firehose (the old
        # SubAgentStatusBus, generalized): every state publish also lands
        # here, so the UI learns a child finished even when no per-run
        # observer stream is open. See _publish_state.
        self.status_bus = BroadcastBus()

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

    def auto_record_for_trace(self, trace_id: str) -> ConversationRecord | None:
        """Resolve a (possibly stale) leaf trace id to a live AUTO conversation
        whose flag is ON.

        Old ``AutoChatRegistry.run_id_for_trace`` semantics: the whole-chain
        index matches any leaf the conversation ever had, and the flag-on
        filter is what keeps the green dot / ``auto_active`` join persistent
        while the run idles between bursts, but gone once stopped/disabled.
        The kind guard is new-world necessity: this supervisor's index also
        holds sub-agent leaves (and interactive ones from phase 4), which the
        old auto registry's index never contained.
        """
        session_id = self._trace_index.get(trace_id)
        if session_id is None:
            return None
        conv = self._conversations.get(session_id)
        if conv is None:
            return None
        record = conv.record
        if record.kind != "auto" or not record.auto_flag:
            return None
        return record

    # Phase 5 note: ``resolve_auto_for_trace`` (the hard-refresh resync
    # lookup, old ``AutoChatRegistry.resolve_trace``) is DELETED with the
    # ``GET /api/conversations/resolve`` endpoint: the browser keys
    # conversations on session ids now, and an observed conversation
    # converges by design (replay + the on-subscribe state marker), so a
    # trace-keyed resync has nothing left to resolve.

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
            self._check_auto_cap()
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

    def _check_auto_cap(self) -> None:
        """Auto-enable cap: counts FLAG-ON conversations — each is a live
        auto-mode conversation holding a slot (old ``AutoChatRegistry.start``
        cap, message preserved verbatim; it surfaces to users as the HTTP 429
        detail). Checked both on create and when flipping an existing
        record's flag back on (``enable_auto``) — a flag-off record does not
        hold a slot, so re-enabling must re-compete for one."""
        active = sum(1 for c in self._conversations.values() if c.record.auto_flag)
        if active >= self._auto_max_concurrent:
            raise ConversationCapError(
                f"Too many concurrent auto runs (max {self._auto_max_concurrent}). "
                "Stop a running auto run and try again."
            )

    # ── The policy flip (phase 4, architecture §2). ────────────────────────────
    #
    # Interactive and auto are POLICIES on the same record, flipped only at
    # run boundaries: a live run holds the policy object it was started with
    # (the engine captures it as a run() argument), so a mid-run flip takes
    # effect at the next turn/burst. `kind` flips WITH the policy so every
    # existing kind-keyed guard (the frontend store, the sessions-list
    # `auto_record_for_trace` join, `/resolve`'s flag-on-auto filter, the
    # children `kind != "subagent"` guards) keeps meaning "how this
    # conversation currently behaves".

    def _flip_to_auto(self, conv: _Conversation) -> None:
        """Enable: the same record starts running auto bursts (caller
        cap-checks first — a flag-off record gave up its auto slot)."""
        conv.policy = auto_policy()
        conv.record.kind = "auto"
        conv.record.auto_flag = True

    def _swap_to_interactive(self, conv: _Conversation) -> None:
        """Flag-off settle: an OFF-auto conversation IS an idle interactive
        conversation (the phase-3 TODO). Replaces the old OFF-auto TTL GC —
        the record simply joins the idle-interactive LRU pool and the next
        send runs a normal gated interactive turn (which is also what lifts
        the phase-3 ``send_message`` flag-off refusal: post-swap the policy
        no longer auto-approves anything)."""
        conv.policy = interactive_policy()
        conv.record.kind = "interactive"

    # ── Interactive create/adopt + approval rehydration (phase 4). ─────────────

    async def adopt_interactive(
        self,
        session_key: str | None,
        *,
        upstream_url: str,
        headers: dict[str, str],
    ) -> ConversationRecord:
        """Create — or ADOPT — the interactive conversation for an upstream
        session key (POST /api/conversations kind="interactive").

        Phase 6: the key is OPAQUE — a durable ``root_id`` for post-phase-5
        history rows, a bare leaf for legacy rows, or a terminal record's
        current leaf (re-opening a finished sub-agent continues its trace on
        a fresh interactive record). The desktop no longer resolves roots to
        leaves (the phase-5 scan is gone): the key is stored as the record's
        ``resume_session_key`` and the FIRST turn continues upstream by
        ``session_id`` — the backend resolves the session's current leaf
        itself (architecture §8). After the first ``kiln_chat_trace`` the
        engine holds the real leaf and every later turn continues by
        ``trace_id`` exactly as before.

        The whole-chain index resolves any leaf the conversation ever had —
        and the adopted key itself (a root IS the conversation's first leaf,
        so it belongs in the chain) — making this idempotent: opening a
        history row twice (or racing tabs) returns the SAME record instead of
        minting duplicates. A resolving record of ANY kind is returned as-is
        — if the conversation is currently an auto conversation, that record
        IS the conversation (one record per conversation is the whole point
        of the flip model).

        A fresh create with a key is the history-open / desktop-restart path:
        adopt the key, then rehydrate pending approvals from the persisted
        trace tail (functional spec §5 — a parked approval survives a desktop
        restart via the persisted trace). The rehydration fetch also
        backfills the TRUE ``root_id`` from the snapshot response — which is
        why the key is never stamped into ``root_id`` directly: a legacy-leaf
        key there would hand the browser a recovery key that goes stale on
        the next persist (see the field comments on ``ConversationRecord``).
        """
        if session_key is not None:
            session_id = self._trace_index.get(session_key)
            if session_id is not None:
                existing = self._conversations.get(session_id)
                if existing is not None and not existing.record.state.is_terminal:
                    return existing.record

        record = self.create_conversation(
            "interactive", upstream_url=upstream_url, headers=headers
        )
        if session_key is not None:
            record.resume_session_key = session_key
            # Seeding the chain with the adopted key does double duty: it
            # keeps this adopt idempotent (and the sessions-list join able to
            # find the record by its row key), and a NON-EMPTY chain is what
            # tells the engine this record joined mid-conversation, so it
            # never mis-stamps a continuation trace as the durable root.
            record.seen_trace_ids.append(session_key)
            # Don't steal another record's index entry: a TERMINAL record can
            # still own this key (e.g. re-opening a finished sub-agent's
            # session from history continues its TRACE on a fresh interactive
            # record, but the child's sessions-list "finished" chip must keep
            # resolving until its record GCs). The new conversation's own
            # leaves index normally via on_trace from its first turn.
            if session_key not in self._trace_index:
                self._trace_index[session_key] = record.session_id
            await self.rehydrate_pending_approvals(record.session_id)
        logger.info(
            "Adopted interactive conversation %s (session_key=%s)",
            record.session_id,
            session_key,
        )
        return record

    async def rehydrate_pending_approvals(
        self, session_id: str
    ) -> PendingApprovalBatch | None:
        """Rebuild a pending approval batch from the persisted trace tail
        (architecture §2 recovery contract; functional spec §5).

        Covers both recovery shapes with one mechanism:

        - desktop restart: the parked run died with the process, but the
          upstream snapshot persisted the assistant turn with its unanswered
          tool calls — reopening the conversation rehydrates the batch;
        - graceful-stop leftovers: an auto burst that surfaced its final
          round's client calls instead of executing them (functional spec §3)
          left the same unanswered-calls tail.

        The rebuilt batch is RUNLESS: no task is parked on it. ``decide``
        detects that and starts a resume run (`start_run(resume_batch=...)`)
        that executes the batch and continues the loop — the same flow the
        old ``POST /api/chat/execute-tools`` drove. Best-effort: any fetch or
        parse failure returns None (no batch), never an error surface —
        exactly as recoverable as the old world (which lost the approval box
        entirely on restart).

        ACCEPTED RISK (re-execute on re-decide): if a resume run executes
        the batch but its continuation POST fails terminally, the settle
        clears the batch while the persisted tail still shows the calls
        unanswered — a later GET /approvals rehydrates a fresh batch and
        deciding it executes the tools AGAIN. This is the exact blast radius
        the old world had (a browser retry of a failed
        ``/api/chat/execute-tools`` re-executed the same batch), and the
        trace tail carries no marker to distinguish "executed but not
        persisted" from "never executed", so we keep the old behavior rather
        than invent one.

        Also re-emits the ``tool-calls-pending`` event onto the bus BUFFER so
        observers (attaching or live) re-surface the approval box; the
        buffer only resets on ``kiln_chat_trace``, so the event replays to
        every later subscriber while the batch is parked.
        """
        conv = self._conversations.get(session_id)
        if conv is None or conv.record.state.is_terminal:
            return None
        if conv.pending_batch is not None and not conv.pending_batch.decided.is_set():
            # A live (or already-rehydrated) undecided batch is authoritative.
            return conv.pending_batch
        if conv.task is not None and not conv.task.done():
            # A live run owns its own round context — never second-guess it.
            return None
        # The fetch key mirrors the continuation precedence (phase 6): the
        # record's own leaf when one is known, else the adopted resume key —
        # the upstream GET accepts either id kind and returns the session's
        # CURRENT leaf snapshot either way.
        fetch_key = conv.record.current_leaf_trace_id or conv.record.resume_session_key
        if fetch_key is None:
            return None

        trace = await self._fetch_persisted_trace(conv, fetch_key)
        if not trace:
            return None
        events, signal_events, assistant_text = _pending_events_from_trace_tail(trace)
        if not events:
            # Nothing approvable. A SIGNAL-ONLY tail (an unanswered
            # enable_auto_mode with no siblings) is a lost consent dialog —
            # which the old world also lost across restarts — not an
            # approval batch; it stays unanswered exactly like before.
            return None

        batch = PendingApprovalBatch(
            items=[_pending_item_from_event(e) for e in events],
            # The continuation base is the trace-only shape — identical to
            # what the old /execute-tools continuation POSTed, and what the
            # engine's parked path holds for a batch parked at this boundary.
            # For a key-adopted record with no known leaf the base is the
            # session_id equivalent: the backend resolves the current leaf —
            # whose tail is exactly what we just rebuilt the batch from —
            # and _build_openai_tool_continuation treats a session_id base
            # as trace-only too, so the wire stays role:tool results only.
            body={**continuation_key_fields(conv.record), "messages": []},
            assistant_text=assistant_text,
            # Signal calls ride the event list so their resolutions land on
            # the continuation, but never the ITEMS (nothing to approve)…
            tool_input_events=[*events, *signal_events],
            # …resolved as declined, mirroring the decline flow: the consent
            # dialog died with the restart, and an unanswered call would
            # leave the trace dangling (see _pending_events_from_trace_tail).
            preresolved_results={
                e.toolCallId: json.dumps({"status": "declined"}, ensure_ascii=False)
                for e in signal_events
            },
        )
        conv.pending_batch = batch
        conv.record.state = RunState.AWAITING_APPROVAL
        conv.bus.emit(format_tool_calls_pending(events))
        self._touch(conv)
        self._publish_state(conv)
        logger.info(
            "Rehydrated pending approval batch for %s (%d calls, key=%s)",
            session_id,
            len(events),
            fetch_key,
        )
        return batch

    async def _fetch_persisted_trace(
        self, conv: _Conversation, session_key: str
    ) -> list[dict[str, Any]] | None:
        """Fetch the persisted snapshot's trace for a session key
        (best-effort). ``session_key`` may be a leaf trace id OR a durable
        root id — the upstream endpoint resolves either kind to the session's
        current leaf (phase 6, architecture §8).

        The conversation's ``upstream_url`` is the chat POST URL
        (``…/v1/chat/``); the session snapshot lives beside it at
        ``…/v1/chat/sessions/{key}`` — same target the desktop's history
        proxy reads, fetched directly here because rehydration is a
        supervisor concern, not a browser round-trip.
        """
        # rstrip guards the join: upstream_url is minted with a trailing slash
        # (routes._chat_url), but a caller passing it bare would otherwise
        # silently produce …/v1/chatsessions/… and read as "nothing persisted".
        url = f"{conv.upstream_url.rstrip('/')}/sessions/{session_key}"
        try:
            async with httpx.AsyncClient(
                timeout=REHYDRATE_FETCH_TIMEOUT_SECONDS
            ) as client:
                response = await client.get(url, headers=conv.headers)
            if response.status_code != 200:
                return None
            data = response.json()
        except (httpx.HTTPError, json.JSONDecodeError, ValueError):
            logger.debug("Approval rehydration fetch failed for %s", session_key)
            return None
        if isinstance(data, dict) and conv.record.root_id is None:
            # Opportunistic backfill of the durable session handle (phase 5):
            # the upstream snapshot response carries ``session_meta.root_id``
            # at the top level, and a record adopted from a bare legacy leaf
            # has no other way to learn it.
            root_id = data.get("root_id")
            if isinstance(root_id, str) and root_id:
                conv.record.root_id = root_id
        task_run = data.get("task_run") if isinstance(data, dict) else None
        trace = task_run.get("trace") if isinstance(task_run, dict) else None
        if not isinstance(trace, list):
            return None
        return [msg for msg in trace if isinstance(msg, dict)]

    # ── Auto mode enable / disable (old chat/auto/ registry + api flows). ──────

    async def enable_auto(
        self,
        *,
        session_id: str | None,
        enable_tool_call_id: str | None,
        pending_tool_calls: list[ToolCallInfo],
        extra_messages: list[dict[str, Any]],
        upstream_url: str,
        headers: dict[str, str],
    ) -> ConversationRecord:
        """Enable auto mode: FLIP the named conversation's record — or create
        one (no ``session_id``) — and start the first burst if the seed
        carries anything to run.

        Replaces ``AutoChatRegistry.start`` + ``AutoChatRunner._build_seed_body``
        (POST /api/chat/auto/enable). Three preserved entry shapes, phase 5
        keyed by SESSION id (the browser no longer holds trace ids; since
        phase 4 the consent event always arrives on the observer of a live
        record, so a live session id is always in hand):

        - consent accept: ``session_id`` + ``enable_tool_call_id`` (+ rare
          pending siblings) → burst resolving the enable call as enabled;
        - manual enable on an existing conversation: ``session_id`` only →
          the record is merely ARMED (flag on, IDLE("armed"), NO run task).
          Starting a burst here would POST an empty turn upstream, which the
          backend rejects ("No messages were sent to the server") — the old
          ``is_armed_only`` branch. The first /messages send starts the real
          burst via ``send_message``'s idle re-arm. The old code buffered
          auto-mode-on + idle markers for connecting observers; the bus's
          on-subscribe ``conversation-state`` marker now carries the same
          truth (idle + flag on + reason "armed") with nothing buffered.
        - armed-first-send on a brand-new conversation (Revision R2): no
          ``session_id``, first user message in ``extra_messages`` → burst;
          the backend mints the first trace on the opening turn.

        Flip semantics (architecture §2: "consent flow flips the policy on
        the SAME run"): the named record's flag flips back on (cap
        re-checked; pending GC cancelled) instead of minting a duplicate
        record for the same conversation. The continuation seed uses the
        RECORD's own ``current_leaf_trace_id`` — the browser's copy of the
        same value died with phase 5 (the record's leaf is authoritative,
        exactly like the phase-4 decline fold-in).

        Raises ``KeyError`` for an unknown ``session_id`` (404 at the route —
        the record died with a restart/eviction, along with the consent
        dialog's context; the old create-a-record-for-any-trace branch is
        unreachable now that the browser can only name live conversations),
        ``ValueError`` for a sub-agent/terminal record (409 — a child's
        autonomy is not a user-facing toggle, mirroring ``set_auto_flag``),
        ``ConversationCapError`` (429), and lets ``start_run``'s "already has
        a run in flight" RuntimeError propagate (409 — the old world silently
        spawned a second concurrent run here, a latent bug, not a contract).
        """
        conv: _Conversation | None = None
        if session_id is not None:
            conv = self._conversations.get(session_id)
            if conv is None:
                raise KeyError(f"Conversation not found: {session_id}")
            # Phase 4: interactive records are flippable too — this is the
            # true "same run, new policy" flip (architecture §2: "consent
            # flow flips the policy on the SAME run"). A sub-agent record is
            # a CHILD session — enabling auto on it makes no sense.
            if conv.record.kind == "subagent" or conv.record.state.is_terminal:
                raise ValueError(f"Conversation cannot enable auto mode: {session_id}")

        if conv is None:
            record = self.create_conversation(
                "auto", upstream_url=upstream_url, headers=headers
            )
            conv = self._conversations[record.session_id]
        else:
            record = conv.record
            if not record.auto_flag:
                # Flipping the flag on takes an auto slot again (a flag-off
                # record does not hold one).
                self._check_auto_cap()
                self._flip_to_auto(conv)
            # Defensive parity with the old idle re-arm: a fresh enable on an
            # OFF record races its terminal TTL — cancel any pending GC.
            self._cancel_gc(record.session_id)

        # ARMED-only manual enable (Revision R1, functional spec §4.1(2)): the
        # seed has nothing to send upstream — see the docstring.
        if not enable_tool_call_id and not pending_tool_calls and not extra_messages:
            if conv.task is None or conv.task.done():
                # Only stamp the idle/armed shape when no burst is in flight —
                # arming a record whose burst is RUNNING (flip of a live
                # conversation) must not lie about its state; the flag is on
                # either way, which is all "armed" means.
                record.state = RunState.IDLE
                record.idle_reason = "armed"
            self._touch(conv)
            self._publish_state(conv)
            logger.info("Armed auto conversation %s", record.session_id)
            return record

        # Auto-approve sibling pending calls now (rare — the model is
        # instructed to call enable_auto_mode alone); their role:tool results
        # ride the seed body. Old AutoChatRunner._build_seed_body executed
        # these inside the runner with the run's orchestration ctx; the ctx
        # here is the same conversation identity, so spawn lineage/ownership
        # is unchanged.
        sibling_results: dict[str, str] = {}
        if pending_tool_calls:
            sibling_results = await execute_tool_batch(
                [
                    ToolCallInfo(
                        toolCallId=tc.tool_call_id,
                        toolName=tc.tool_name,
                        input=tc.input,
                        requiresApproval=False,
                    )
                    for tc in pending_tool_calls
                ],
                {},
                orchestration_ctx=self._orchestration_ctx(conv),
            )

        body = build_auto_seed_body(
            # The enable call belongs to the assistant turn persisted at the
            # conversation's tail — the record's own leaf is authoritative
            # (phase 5: the old endpoint took the browser's copy of the same
            # id; the engine's on_trace keeps this one fresh). A key-adopted
            # record with no leaf yet continues by session_id instead (phase
            # 6 — the backend resolves the current leaf); with NEITHER key a
            # fresh conversation starts (Revision R2).
            trace_id=record.current_leaf_trace_id,
            session_id=record.resume_session_key,
            enable_tool_call_id=enable_tool_call_id,
            extra_messages=extra_messages,
            sibling_results=sibling_results,
        )
        self.start_run(record.session_id, body)
        logger.info("Started auto conversation %s", record.session_id)
        return record

    async def disable_auto(self, session_id: str) -> bool:
        """Clear the conversation's auto-mode flag (old
        ``AutoChatRegistry.disable``, reason ``user_disabled``).

        The flag must clear even mid-burst: a RUNNING burst is pre-marked
        (flag off + reason) THEN cancelled, so the cancel handler and the
        settle path publish the true reason instead of clobbering it with
        ``user_stopped`` (old CR Moderate 2). With no live burst the flag
        clears directly (old idle branch): queued inbox dies with the flag
        and the off state publishes. Phase 4: instead of the old OFF-auto TTL
        GC, both paths swap the record back to its interactive life
        (``_swap_to_interactive`` — directly here for the idle branch, via
        ``_finish_run``'s off branch for the cancelled-burst one). Both paths
        cascade-stop the conversation's sub-agent children — their reports
        have nothing left to consume them (old ``disable`` →
        ``_stop_subagent_children``). Returns False for unknown records;
        already-off/terminal records are a True no-op.
        """
        conv = self._conversations.get(session_id)
        if conv is None:
            return False
        record = conv.record
        if record.state.is_terminal:
            # Old parity: disable() on a terminal record reported success
            # without re-publishing (nothing left to clear).
            return True
        if not record.auto_flag:
            return True

        # Pre-mark BEFORE any cancel (CR Moderate 2 — see docstring).
        record.auto_flag = False
        record.idle_reason = "user_disabled"

        task = conv.task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.debug(
                    "Conversation %s raised during disable await",
                    session_id,
                    exc_info=True,
                )
            # Backstop: a task cancelled before it ever ran never entered
            # _supervise, so its finally/_finish_run never fired (run-once —
            # the double call is a no-op). _finish_run publishes the off
            # state and, via the flag-off branch, swaps the record back to
            # its interactive life (phase 4 — no TTL GC anymore).
            self._finish_run(conv)
            await self.stop_children(session_id)
            return True

        # No live burst (idle). Clear directly — old disable() idle branch.
        # Publish carries the phase-3 event shape (kind=auto, flag off,
        # reason), THEN the record swaps to its interactive life (the swap is
        # not an event of its own — the next state event simply reports kind
        # interactive).
        conv.inbox.clear()
        self._touch(conv)
        self._publish_state(conv)
        if conv.policy.approvals == "auto" and not conv.policy.one_shot:
            self._swap_to_interactive(conv)
        await self.stop_children(session_id)
        return True

    async def set_auto_flag(
        self, session_id: str, enabled: bool
    ) -> Literal["ok", "not_found", "invalid"]:
        """Flip the auto-mode flag on an EXISTING conversation
        (POST /api/conversations/{sid}/auto, functional spec §2).

        ``enabled=False`` delegates to :meth:`disable_auto` (today's disable
        semantics; a no-op on an already-interactive record).
        ``enabled=True`` re-arms: the record flips to the auto policy
        (cap-checked — a flag-off record holds no slot; raises
        ``ConversationCapError`` for the route's 429) with NO upstream POST —
        the ARMED-only shape, so the next message starts the burst. Phase 4:
        interactive records are flippable too (the true policy flip on the
        SAME record, architecture §2); only sub-agent records stay "invalid"
        — a child's autonomy is not a user-facing toggle.
        """
        conv = self._conversations.get(session_id)
        if conv is None:
            return "not_found"
        record = conv.record
        if record.kind not in ("auto", "interactive") or record.state.is_terminal:
            return "invalid"
        if not enabled:
            await self.disable_auto(session_id)
            return "ok"
        if not record.auto_flag:
            self._check_auto_cap()
            self._flip_to_auto(conv)
        # A re-enable races the OFF record's terminal TTL — cancel pending GC.
        self._cancel_gc(session_id)
        if conv.task is None or conv.task.done():
            # ARMED shape only when no burst is in flight (mirrors
            # enable_auto's armed branch — never lie about a RUNNING state).
            record.state = RunState.IDLE
            record.idle_reason = "armed"
        self._touch(conv)
        self._publish_state(conv)
        return "ok"

    def decline_auto(
        self,
        session_id: str,
        *,
        enable_tool_call_id: str,
        siblings: list[ToolCallInfo],
    ) -> Literal["ok", "not_found", "invalid", "busy"]:
        """Decline a pending ``enable_auto_mode`` consent request
        (POST /api/conversations/{sid}/auto with a decline context — the
        phase-3 ``/api/conversations/auto/decline`` bridge, folded in now
        that interactive conversations own supervisor records).

        The engine's consent interception ended the turn WITHOUT answering
        the enable call, so the persisted trace has a dangling tool call the
        provider requires answered. Declining starts a normal interactive
        TURN whose seed resolves it as ``{"status": "declined"}`` and every
        sibling as denied — byte-identical to the old
        ``/api/chat/auto/decline`` continuation body (which streamed the same
        messages through a fresh ChatStreamSession); the reply now streams on
        the observer channel like any other turn. Declining never flips any
        policy: the record already runs (or swaps back to) the interactive
        policy.

        "busy" → a run is already in flight (a consent decline races a fresh
        send); the route maps it to 409 rather than corrupting the turn.
        """
        conv = self._conversations.get(session_id)
        if conv is None:
            return "not_found"
        record = conv.record
        if record.kind == "subagent" or record.state.is_terminal:
            return "invalid"
        if conv.task is not None and not conv.task.done():
            return "busy"

        messages: list[dict[str, Any]] = [
            {
                "role": "tool",
                "tool_call_id": enable_tool_call_id,
                # Exact old decline payload (routes-level json.dumps shape) —
                # persisted in the trace, so the bytes are part of the
                # protocol contract.
                "content": json.dumps({"status": "declined"}, ensure_ascii=False),
            }
        ]
        for sibling in siblings:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": sibling.tool_call_id,
                    "content": DENIED_TOOL_OUTPUT,
                }
            )
        # The dangling enable call lives in the conversation's tail snapshot —
        # the record's own leaf is authoritative (the old endpoint took the
        # browser's copy of the same id). continuation_key_fields also covers
        # the defensive corner of a key-adopted record with no leaf yet
        # (session_id continuation) — a live consent can't normally exist on
        # one, but the shared helper keeps every idle-start body consistent.
        body: dict[str, Any] = {
            **continuation_key_fields(record),
            "messages": messages,
        }
        self.start_run(session_id, body)
        logger.info("Declined auto mode for conversation %s", session_id)
        return "ok"

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
        self,
        session_id: str,
        initial_body: dict[str, Any] | None = None,
        resume_batch: PendingApprovalBatch | None = None,
    ) -> None:
        """Start a turn/burst/run task for the conversation.

        ``initial_body`` is the upstream request body for the first round
        (interactive turn / auto burst seed); None lets the engine build the
        one-shot seed body from policy.seed (child runs). ``resume_batch``
        starts the phase-4 RESUME RUN instead: execute the (already-decided)
        runless batch, then continue the loop from its continuation — see
        ``ConversationEngine.run``.
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
        chat_debug_log(
            "run_started",
            conversation_id=session_id,
            kind=conv.record.kind,
            auto_flag=conv.record.auto_flag,
            resume_batch=resume_batch is not None,
            inbox_len=len(conv.inbox),
        )
        self._touch(conv)
        conv.task = asyncio.create_task(
            self._supervise(conv, initial_body, resume_batch)
        )
        # Live observers learn the run started; attaching observers get the
        # same truth from the on-subscribe marker. (The firehose copy is what
        # tells the UI a NEW child appeared — the old registry published a
        # status on spawn, and spawn == create + start_run here.)
        self._publish_state(conv)

    async def _supervise(
        self,
        conv: _Conversation,
        initial_body: dict[str, Any] | None,
        resume_batch: PendingApprovalBatch | None = None,
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
        # BUG 1 (inbox stranding) guard: only a NATURAL settle (the engine's
        # run() returned without raising) may consume a stranded inbox by
        # restarting a fresh turn. A cancel (stop/disable) or an unexpected
        # exception must NOT resurrect a run — stop()/disable_auto() call
        # _finish_run again as a backstop and rely on it being run-once, so a
        # restart there would double-settle the freshly started turn (and a
        # user who explicitly stopped does not want their queued message to
        # silently relaunch — the client-side flush owns re-sending in that
        # case). Set False in both handlers below; stays True only on the
        # clean return path, which is exactly the drain-settle race window.
        ended_naturally = True
        try:
            try:
                # The kwarg is only passed on the resume path so test doubles
                # that fake the common run() signature keep working unchanged.
                if resume_batch is not None:
                    coro = engine.run(
                        record,
                        conv.policy,
                        io,
                        initial_body,
                        resume_batch=resume_batch,
                    )
                else:
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
                ended_naturally = False
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
                # Conservatively NOT a natural settle: a persistent upstream
                # error would otherwise re-launch the stranded message into
                # the same failure on every settle.
                ended_naturally = False
                logger.exception("Conversation %s run failed", record.session_id)
                if conv.policy.one_shot:
                    record.state = RunState.FAILED
                else:
                    record.state = RunState.IDLE
                    record.idle_reason = "error"
        finally:
            self._finish_run(conv, restart_stranded_inbox=ended_naturally)

    def _finish_run(
        self, conv: _Conversation, *, restart_stranded_inbox: bool = False
    ) -> None:
        """THE settle path — every run ends here exactly once (architecture
        §9: all settle/publish/deliver logic in one place).

        Runs from ``_supervise``'s ``finally`` on every exit (natural end,
        cancel, timeout, exception) AND from ``stop()`` as the backstop for
        tasks cancelled before they ever started (which never enter
        ``_supervise``). The ``run_finished`` guard makes the double call a
        no-op — the run-once ``_settle`` pattern from the old sub-agent
        registry, generalized to every kind.

        ``restart_stranded_inbox`` (BUG 1 fix): when True (a NATURAL settle —
        see ``_supervise``), a non-empty inbox at settle is consumed by
        starting a fresh turn instead of being left stranded. The default
        (False) is the safe choice for the ``stop()`` / ``disable_auto()``
        backstops, which must never resurrect a run: they call this AGAIN
        after awaiting the cancelled task, relying on the run-once guard, so a
        restart here would double-settle. Only the clean-return path — exactly
        the engine's drain-settle race window — passes True.
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
            self._publish_state(conv)
            self._deliver_report(conv)
            self._schedule_gc(record.session_id)
            logger.info(
                "Sub-agent conversation %s ended (state=%s, rounds=%d)",
                record.session_id,
                record.state.value,
                record.rounds_used,
            )
            chat_debug_log(
                "run_settled",
                conversation_id=record.session_id,
                state=record.state.value,
                rounds_used=record.rounds_used,
                report_delivered=record.report_delivered,
            )
            return

        # Interactive turn / auto burst settle: the conversation persists.
        if record.state in (RunState.RUNNING, RunState.AWAITING_APPROVAL):
            # The engine exited without recording an outcome (e.g. cancelled
            # before its first await, or a defensive fallback) — an idle
            # boundary is the safe truth.
            record.state = RunState.IDLE
        self._touch(conv)
        self._publish_state(conv)
        if (
            conv.policy.approvals == "auto"
            and not conv.policy.one_shot
            and not record.auto_flag
        ):
            # The auto-mode flag is off after a run under the AUTO policy
            # (stop/disable landed before or during this burst): old "off"
            # semantics for the burst itself — the queued inbox dies with the
            # flag (a message queued for an auto burst must never silently
            # start a gated turn). Keyed on the settled run's POLICY, not
            # record.kind: the policy is what made this an auto burst.
            # Phase 4 replaces the old OFF-auto TTL GC with the flip model:
            # the record swaps back to its interactive life (an off-auto
            # conversation IS an idle interactive conversation) and joins the
            # LRU-bounded idle-interactive pool — the off state was already
            # published above with the preserved reason vocabulary.
            conv.inbox.clear()
            self._swap_to_interactive(conv)
            self._evict_idle_interactive_lru()
        logger.info(
            "Conversation %s run ended (state=%s, auto_flag=%s, reason=%s)",
            record.session_id,
            record.state.value,
            record.auto_flag,
            record.idle_reason,
        )
        chat_debug_log(
            "run_settled",
            conversation_id=record.session_id,
            state=record.state.value,
            auto_flag=record.auto_flag,
            idle_reason=record.idle_reason,
            rounds_used=record.rounds_used,
            inbox_len=len(conv.inbox),
            restart_stranded_inbox=restart_stranded_inbox,
            current_leaf_trace_id=record.current_leaf_trace_id,
        )
        # BUG 1 fix — inbox-drain-on-settle. Logged the settle FIRST (above)
        # so the "run ended" line reflects the settled IDLE, then the restart
        # (which logs + publishes RUNNING for its own new turn) follows. The
        # off-auto branch already cleared the inbox, so this only fires for an
        # interactive turn / flag-on auto burst that settled with a message
        # POSTed into the inbox during the drain-settle race window.
        if restart_stranded_inbox and conv.inbox:
            self._restart_from_inbox(conv)

    def _restart_from_inbox(self, conv: _Conversation) -> None:
        """Consume a stranded inbox at settle by starting a fresh turn — the
        server-side complement to the client's queued-message flush (BUG 1).

        The stranding race (SERVER-SIDE): ``send_message`` appends to
        ``conv.inbox`` whenever the state is RUNNING/AWAITING_APPROVAL. There
        is a tiny window between the engine's LAST ``drain_inbox()`` (which
        returned empty, so the engine settles) and the state actually flipping
        to IDLE in ``_finish_run``. A POST landing in that window appends to
        the inbox, the engine settles IDLE, and NOTHING consumes the message —
        it strands until the user's next action. The browser rendered its echo
        (so it "looks sent") but the turn that would answer it never runs.

        This mirrors ``send_message``'s IDLE re-arm EXACTLY so the restarted
        turn's persisted trace is indistinguishable from a live idle-start:
        the same UNFRAMED user message(s) (framing is for MID-run drains only;
        the idle re-arm sends raw — see ``send_message``), the same next-turn
        sub-agent report injection for parent kinds, and the same
        ``continuation_key_fields`` + ``auto_mode`` propagation.

        Echo-once (old CR Moderate 1): the inbox messages were ALREADY echoed
        onto the bus by ``send_message`` at enqueue, so they are NOT re-echoed
        here. Only freshly drained reports (never echoed yet) are echoed, once,
        exactly as ``send_message``'s idle branch does.

        Re-entrancy: this runs from ``_finish_run`` where ``run_finished`` is
        already True and ``conv.task`` is None; ``start_run`` resets
        ``run_finished`` and creates a NEW task (it never awaits), so there is
        no double-run — and it is reached only on a natural settle, never the
        stop/disable backstop (see ``_finish_run``'s docstring).
        """
        record = conv.record
        drained = conv.drain_inbox()
        if not drained:
            return
        messages: list[dict[str, Any]] = [m.as_chat_message() for m in drained]
        # Next-turn report injection (parent kinds only — a child never owns a
        # report queue), matching send_message's idle branch; reports were not
        # echoed at enqueue, so echo them here (once).
        if record.kind != "subagent":
            for report in self.drain_reports(record.session_id):
                messages.append({"role": "user", "content": report})
                conv.bus.emit(format_user_message(report))
        body: dict[str, Any] = {
            "messages": messages,
            **continuation_key_fields(record),
        }
        if record.auto_flag:
            body["auto_mode"] = True
        self.start_run(record.session_id, body)
        logger.info(
            "Restarted conversation %s from stranded inbox (%d message(s))",
            record.session_id,
            len(drained),
        )

    def _orchestration_ctx(self, conv: _Conversation) -> "OrchestrationContext | None":
        """The conversation identity threaded into sub-agent orchestration
        calls (spawn/status/wait/stop dispatch inside execute_tool_batch).

        Parent kinds (interactive/auto records on this supervisor) get a real
        ctx carrying their SESSION id — stable, so no trace-alias chaining is
        ever needed for their children (the phase-2/3 alias bridges are
        gone). The spawn seed's ``parent_trace_id`` lineage no longer rides
        the ctx (phase 4 shrank it to ``{parent_session_id, depth}``): the
        spawn executor reads the parent record's ``current_leaf_trace_id``
        directly, which ``on_trace`` keeps fresh — same value the old
        per-round ``ctx.parent_trace_id`` refresh maintained, single-sourced.
        Children get None — see the field comment on
        ``_Conversation.orchestration_ctx``.
        """
        if conv.policy.orchestration_depth > 0:
            return None
        if conv.orchestration_ctx is None:
            # Lazy import: chat/orchestration.py imports this module at
            # module level (it targets the supervisor singleton).
            from app.desktop.studio_server.chat.orchestration import (
                OrchestrationContext,
            )

            conv.orchestration_ctx = OrchestrationContext(
                parent_session_id=conv.record.session_id,
            )
        return conv.orchestration_ctx

    def _engine_io(self, conv: _Conversation) -> EngineIO:
        """Wire the engine's io bundle onto this conversation's machinery."""
        record = conv.record
        orchestration_ctx = self._orchestration_ctx(conv)

        async def on_trace(trace_id: str) -> None:
            # The engine already updated the record (single-writer rule) —
            # including record.current_leaf_trace_id, which the spawn
            # executor reads for the agent block's parent_trace_id lineage
            # (old runners refreshed a ctx copy per round for the same
            # value); the supervisor only maintains its cross-conversation
            # index here.
            self._trace_index[trace_id] = record.session_id
            self._touch(conv)

        async def await_decisions(batch: PendingApprovalBatch) -> dict[str, bool]:
            conv.pending_batch = batch
            # Tell live observers the run parked (the engine already emitted
            # the tool-calls-pending payload with the batch contents; this is
            # the lifecycle marker).
            self._publish_state(conv)
            await batch.decided.wait()
            # The batch stays on the conversation (decided) until the run
            # settles or the next park replaces it, so a second decide can be
            # answered with a conflict rather than a 404 (functional spec §5:
            # two tabs — first decision set wins, the second gets 409).
            return dict(batch.decisions or {})

        async def on_auto_flag_cleared() -> None:
            # The engine's INTERACTIVE disable_auto_mode interception just
            # cleared a set flag mid-turn. Reproduce the full old cascade
            # (ChatStreamSession._clear_auto_mode_flag →
            # disable_auto_for_trace): publish the off state NOW with the
            # preserved reason — the old cascade published out-of-band,
            # before the turn settled — and cascade-stop the sub-agent
            # children (their reports have nothing left to consume them).
            # If the record had been flipped to the auto policy while this
            # interactive turn was still in flight (a manual-enable race),
            # swap it back — the model just disabled auto mode.
            record.idle_reason = "user_disabled"
            self._touch(conv)
            self._publish_state(conv)
            if conv.policy.approvals == "auto" and not conv.policy.one_shot:
                self._swap_to_interactive(conv)
            await self.stop_children(record.session_id)

        return EngineIO(
            emit=conv.bus.emit,
            on_trace=on_trace,
            drain_inbox=conv.drain_inbox,
            drain_reports=lambda: self.drain_reports(record.session_id),
            await_decisions=await_decisions,
            stop_requested=lambda: conv.stop_requested,
            # Parent kinds carry their conversation identity (session id +
            # fresh leaf — see _orchestration_ctx); sub-agents carry None:
            # their orchestration calls never reach dispatch (the depth-guard
            # interceptor answers them with DEPTH_LIMIT_RESULT first), and a
            # None ctx is the execute_tool_batch backstop — a call that
            # somehow slipped past the guard resolves to a structured
            # "unavailable" error instead of executing.
            orchestration_ctx=orchestration_ctx,
            on_auto_flag_cleared=on_auto_flag_cleared,
        )

    # ── Messages. ─────────────────────────────────────────────────────────────

    def send_message(self, session_id: str, content: str) -> str | None:
        """Queue a user message into the conversation (POST /messages).

        Behavior by state (functional spec §2): RUNNING/AWAITING_APPROVAL →
        queued, drained at the next round boundary (or after decisions
        resolve); IDLE → starts a turn seeded with the message. Echoes the
        message onto the bus + replay buffer at ENQUEUE time so every observer
        (including the sender) renders it immediately — and so the engine's
        drain must never re-echo (echo-once, old CR Moderate 1).

        Returns the accepted message's stable id (phase 4: the sending tab
        renders its typed text locally and uses the id to dedupe its own
        echo — the echoed content carries the app-context header the browser
        prepends, which only OTHER observers should render, stripped).

        Returns None for unknown/terminal conversations (routes map to
        404/409) AND for flag-off records still carrying the AUTO policy —
        the old registry's "no longer active" refusal, now only a narrow
        transient window (disable pre-marks the flag before the burst's
        settle swaps the policy back to interactive): a run started here
        would auto-approve every tool without an active consent. Post-swap
        the record is interactive and sends run normal gated turns.
        """
        conv = self._conversations.get(session_id)
        if conv is None or conv.record.state.is_terminal:
            return None
        if (
            conv.policy.approvals == "auto"
            and not conv.policy.one_shot
            and not conv.record.auto_flag
        ):
            return None
        message = InboundMessage(content=content)
        conv.bus.emit(format_user_message(message.content, message.id))
        self._touch(conv)

        if conv.record.state in (RunState.RUNNING, RunState.AWAITING_APPROVAL):
            conv.inbox.append(message)
            chat_debug_log(
                "message_enqueued",
                conversation_id=session_id,
                message_id=message.id,
                state=conv.record.state.value,
                inbox_len=len(conv.inbox),
            )
            return message.id
        chat_debug_log(
            "message_starts_idle_turn",
            conversation_id=session_id,
            message_id=message.id,
            stranded_inbox_len=len(conv.inbox),
            auto_flag=conv.record.auto_flag,
        )

        # IDLE → start a fresh turn/burst seeded with the message. Body shape
        # preserved from the old idle re-arm (AutoChatRegistry.send_message →
        # AutoChatSeed(extra_messages=[...])._build_seed_body): continue from
        # the current leaf, message unframed (framing is for MID-run drains
        # only), auto_mode riding iff the flag is on. This is ALSO the old
        # interactive ``POST /api/chat`` request shape ({trace_id?, messages:
        # [the user message]}), so an interactive turn started here persists
        # an indistinguishable trace.
        # Deliver any stranded inbox FIRST (messages that landed during a
        # non-natural settle — e.g. a turn that ended in a terminal upstream
        # error, which _finish_run deliberately does not restart from). They
        # were echoed at enqueue (echo-once), so no re-emit here; ordering
        # matches send order, with the fresh message last.
        stranded = conv.drain_inbox()
        messages: list[dict[str, Any]] = [m.as_chat_message() for m in stranded]
        messages.append(message.as_chat_message())
        # Next-turn report injection (old routes.post_chat): sub-agent
        # reports queued while the conversation idled ride this fresh turn
        # AFTER the user's message (the old endpoint appended them the same
        # way) and are echoed so the live transcript shows them immediately.
        # Parent kinds only — a child never owns a report queue.
        if conv.record.kind != "subagent":
            for report in self.drain_reports(session_id):
                messages.append({"role": "user", "content": report})
                conv.bus.emit(format_user_message(report))
        # Continuation key (phase 6): trace_id from the record's own leaf for
        # the normal in-process flow, session_id for a key-adopted record's
        # FIRST turn (the backend resolves the current leaf), nothing for a
        # brand-new conversation — see continuation_key_fields.
        body: dict[str, Any] = {
            "messages": messages,
            **continuation_key_fields(conv.record),
        }
        if conv.record.auto_flag:
            body["auto_mode"] = True
        self.start_run(session_id, body)
        logger.info("Resumed conversation %s from idle via message", session_id)
        return message.id

    # ── Approvals. ────────────────────────────────────────────────────────────

    def decide(
        self, session_id: str, batch_id: str, decisions: dict[str, bool]
    ) -> Literal["ok", "not_found", "conflict"]:
        """Resolve a parked approval batch (POST approvals/decisions).

        "not_found" → no such conversation / no such batch / wrong batch id
        (route: 404); "conflict" → the batch was already decided — first
        decision set wins, the second tab gets 409 (functional spec §5).

        Two batch shapes resolve here (phase 4):

        - a LIVE batch: the engine's run task is parked on ``decided`` —
          setting it wakes the engine, which executes and continues in-place;
        - a RUNLESS batch (rehydrated from the persisted trace tail after a
          desktop restart, or the graceful-stop leftovers): nothing is
          awaiting the event, so deciding starts the RESUME RUN that executes
          the batch and continues the loop — the old
          ``POST /api/chat/execute-tools`` flow, in-process.
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
        if conv.task is None or conv.task.done():
            # Runless batch — start the resume run. The batch stays on the
            # conversation (decided) until this run settles, so a racing
            # second decide still gets "conflict", same as the parked case.
            self.start_run(session_id, resume_batch=batch)
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
        is a no-op). Cascades to children for auto/sub-agent records (the old
        cascade — their reports have nothing left to consume them) but NOT
        for a plain interactive turn cancel: the old interactive Stop was a
        stream abort that never touched running sub-agents, and functional
        spec §2 keeps it "cancel in-flight turn" only. Session DELETION still
        cascades regardless (``orchestration.handle_session_deleted`` calls
        ``stop_children`` explicitly).
        """
        conv = self._conversations.get(session_id)
        if conv is None or conv.record.state.is_terminal:
            return
        record = conv.record
        # Evaluated up front: the settle below can swap an auto record back
        # to kind "interactive", and the cascade decision belongs to what the
        # conversation WAS when the user stopped it.
        cascade_children = record.kind != "interactive"

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
            if cascade_children:
                await self.stop_children(session_id)
            return

        # No live run. One-shot records without a task are either terminal
        # (guarded above) or not yet started (spawn always starts, so this is
        # unreachable in practice) — nothing to do beyond the flag clear for
        # idle auto conversations (old AutoChatRegistry.stop idle branch;
        # phase 4 swaps the record to its interactive life instead of the old
        # OFF-auto TTL GC, publishing the off state first).
        if record.auto_flag:
            record.auto_flag = False
            record.idle_reason = "user_stopped"
            conv.inbox.clear()
            self._touch(conv)
            self._publish_state(conv)
            if conv.policy.approvals == "auto" and not conv.policy.one_shot:
                self._swap_to_interactive(conv)
        if cascade_children:
            await self.stop_children(session_id)

    async def stop_children(self, parent_session_id: str) -> int:
        """Cascade-stop every running child of a parent (parent
        stopped/disabled/deleted). The parent is being torn down, so its
        children's reports are DROPPED — nothing is left to consume them.
        Returns how many children were stopped. (Old
        SubAgentRegistry.stop_children.)

        Report suppression (important since reports now WAKE parents): a
        child's report is delivered from inside its own ``_finish_run`` when it
        settles. Now that delivery goes through the parent's inbox — which
        would START A TURN on the (about-to-be-deleted) parent — clearing the
        pending-reports QUEUE afterwards is no longer enough (the report never
        touches the queue on the wake path). So mark each child
        ``report_delivered`` BEFORE stopping it: ``_deliver_report`` early-
        returns on that guard, so the cascade never wakes the parent. This is
        the cascade path ONLY — a standalone ``stop(child)`` (the user stopping
        one helper) still delivers its stop-note report so the parent learns
        the outcome.
        """
        stopped = 0
        for record in self.children_of(parent_session_id):
            # Suppress delivery (see docstring) for EVERY child — even an
            # already-terminal one may hold an undelivered queued report.
            record.report_delivered = True
            if not record.state.is_terminal:
                await self.stop(record.session_id)
                stopped += 1
        # Belt and suspenders: drop any reports already queued before this
        # cascade (e.g. children that settled earlier while the parent idled).
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

    # ── State publishing. ─────────────────────────────────────────────────────

    def _publish_state(self, conv: _Conversation) -> None:
        """Publish the conversation's current state to BOTH channels: the
        per-conversation bus (live observers of this run) and the registry
        firehose (the UI's children store, which may have no per-run stream
        open). One helper so the two can never drift — the old registry's
        ``_publish_status`` did the same dual publish. ``publish`` (not
        ``emit``) on the run bus: lifecycle markers must not enter the replay
        buffer (a replayed stale state would lie to a late subscriber; the
        on-subscribe marker provides the fresh truth instead)."""
        payload = format_conversation_state(conv.record)
        conv.bus.publish(payload)
        self.status_bus.publish(payload)

    # ── Report delivery (completion injection). ───────────────────────────────

    def _deliver_report(self, conv: _Conversation) -> None:
        """Deliver a settled child's report to its parent.

        The report is pushed to the parent as an INBOX message (via
        ``send_message``) for EVERY live parent — auto OR interactive. This is
        the unified-runtime win over the old split behavior:

        - Auto-flag parent: the report wakes an IDLE parent into a fresh burst
          (native since phase 3) — unchanged.
        - Interactive parent: the report now ALSO wakes an idle parent to
          process it (it starts a normal gated turn), instead of the old v1
          limitation where an interactive parent's report merely queued and
          waited for the USER's next message to drain it. That deferral
          defeated the point of sub-agents (you delegate work, the helpers
          finish, and nothing happens until you poke the parent). Waking the
          parent is safe: an interactive turn is still fully GATED — any tool
          call the parent makes while processing the report parks for user
          approval; only the already-consented sub-agent spawns run without a
          prompt. (Product decision confirmed with the user; the old
          "interactive never runs unattended" choice is deliberately reversed
          for the report-arrival case.)

        ``send_message``'s state routing does the right thing for both kinds:
        IDLE → start a turn (wake); RUNNING/AWAITING_APPROVAL → append to the
        inbox, drained at the next round boundary (or by inbox-drain-on-settle
        — BUG 1 fix). The report frame is delivered UNFRAMED (the engine's
        ``_frame_inbox_message`` excludes ``<subagent_report>`` from side-note
        framing) and echoed onto the bus, so the report panel appears LIVE the
        moment the child finishes.

        Queue fallback: ``send_message`` returns None when the parent is
        unknown/terminal, or a flag-off auto record (the narrow disable window
        — a report must never silently start a gated turn on a record that was
        just disabled; the old auto-parent-gone fallback). In those cases the
        report is queued in ``_pending_reports`` so a later resumed turn's
        ``drain_reports`` still picks it up. An interactive conversation is
        never terminal, so a live interactive parent always takes the wake
        path; the queue only catches an evicted/unknown parent.
        """
        record = conv.record
        if record.report_delivered or record.parent_session_id is None:
            return
        parent = self._conversations.get(record.parent_session_id)
        if parent is not None and not parent.record.state.is_terminal:
            delivered = self.send_message(
                parent.record.session_id, format_subagent_report(record)
            )
            if delivered:
                self._mark_report_delivered(conv)
                return
            # send_message refused (flag-off auto record in the disable
            # window, or otherwise not deliverable right now): fall through to
            # the queue so a resumed turn can still pick the report up.
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
            # An undelivered report pins the record (up to the longer cap) —
            # old sub-agent registry pinning: a settled CHILD whose report
            # was never consumed (one-shot, not report_delivered) must not be
            # lost to GC while an idle interactive parent could still drain
            # it. (Phase 4: the parent-side pin moved to the interactive LRU
            # filter — OFF-auto parents no longer TTL-GC at all; the
            # has_pending_reports clause here is a defensive leftover for any
            # record that somehow scheduled a TTL while holding a queue.)
            if conv is not None and (
                (conv.policy.one_shot and not conv.record.report_delivered)
                or self.has_pending_reports(session_id)
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
        # Every index entry pointing at this record has its key in the
        # record's own seen chain (on_trace appends before indexing; adopt
        # appends the adopted key), so iterating the chain beats a full-index
        # scan. The ownership check is load-bearing, not defensive: an
        # adopted record's chain can carry a key whose index entry belongs to
        # ANOTHER record (see adopt_interactive's don't-steal guard) — that
        # entry must survive this eviction.
        for tid in conv.record.seen_trace_ids:
            if self._trace_index.get(tid) == session_id:
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
            # Phase-4 pinning (OFF-auto records live in this pool now, so
            # the old undelivered-report pinning re-homes here): never evict
            # a record whose report queue still holds children's reports —
            # eviction drops the queue AND the trace-index entries the
            # next-turn drain resolves through — nor one with live children
            # (their settle needs the parent record for report routing).
            and not self.has_pending_reports(conv.record.session_id)
            and not any(
                not child.state.is_terminal
                for child in self.children_of(conv.record.session_id)
            )
        ]
        overflow = len(idle) - self._max_idle_interactive_records
        if overflow <= 0:
            return
        for conv in sorted(idle, key=lambda c: c.record.updated_at)[:overflow]:
            self._evict(conv.record.session_id)


# The one process-wide supervisor (phase 2 onward), mirroring the old
# module-level ``subagent_registry`` / ``auto_chat_registry`` singletons.
# Everything that owns a conversation targets THIS instance:
# chat/orchestration.py (spawn/status/wait/stop + report drains + cascades)
# and runtime/api.py (the /api/conversations browser surface). Tests construct
# their own instances and patch this name where needed (same pattern the old
# registry tests used).
conversation_supervisor = ConversationSupervisor()
