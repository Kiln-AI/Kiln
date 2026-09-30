"""ConversationSupervisor — the ONE lifecycle owner (architecture §5).

A single registry keyed by session id. It owns, for every conversation:

- the ``ConversationRecord`` + frozen ``ConversationPolicy``,
- the run ``asyncio.Task`` (decoupled from any HTTP request — a client
  disconnect only tears down its SSE subscription, never the run),
- one ``ByteEventBus`` + replay buffer,
- the inbox queue (send-while-running),
- the pending approval batch,
- the auto-mode concurrency cap,
- stop, and eviction of idle records (LRU).

Interactive conversations run as a TURN TASK per turn (IDLE → RUNNING →
IDLE), created/adopted via ``adopt_interactive`` and driven by
``send_message``'s idle re-arm. Auto mode is a POLICY FLIP on the same
record (architecture §2): ``enable_auto`` swaps an interactive record's
policy AND kind to auto, and every flag-off settle swaps it back — an
off-auto conversation IS an idle interactive conversation.

Settle-once rule (architecture §9): every run ends through exactly one
method, ``_finish_run`` — reached from ``_supervise``'s ``finally`` on every
exit path, plus the ``stop()``/``disable_auto()`` backstop for tasks
cancelled before they ever started (a cancelled-before-first-run task never
enters ``_supervise``, so its ``finally`` never fires).

Restart recovery (architecture §5): the supervisor cold-starts empty;
opening a conversation from history creates a record from its session key
(``adopt_interactive``) and pending approvals are rehydrated from the
persisted trace tail (``rehydrate_pending_approvals``) — deciding a
rehydrated (runless) batch starts a RESUME RUN that executes the batch and
continues the loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.parse
from typing import Any, AsyncGenerator, Literal

import httpx
from kiln_ai.adapters.model_adapters.stream_events import ToolInputAvailableEvent
from kiln_ai.tools.built_in_tools.disable_auto_mode_tool import (
    DISABLE_AUTO_MODE_TOOL_NAME,
)
from kiln_ai.tools.built_in_tools.enable_auto_mode_tool import (
    ENABLE_AUTO_MODE_TOOL_NAME,
)

from app.desktop.studio_server.chat.constants import DENIED_TOOL_OUTPUT
from app.desktop.studio_server.chat.debug_log import chat_debug_log
from app.desktop.studio_server.chat.stream_session import (
    ToolCallInfo,
    _pending_item_from_event,
    execute_tool_batch,
)

from .bus import ByteEventBus
from .engine import ConversationEngine, EngineIO
from .interceptors import DISABLE_AUTO_MODE_STALE_RESULT
from .models import (
    ConversationKind,
    ConversationPolicy,
    ConversationRecord,
    InboundMessage,
    PendingApprovalBatch,
    RunState,
    _utc_now,
    auto_policy,
    build_auto_seed_body,
    continuation_key_fields,
    interactive_policy,
)
from .sse import (
    format_conversation_state,
    format_tool_calls_pending,
    format_user_message,
)

logger = logging.getLogger(__name__)

# ── Caps. ─────────────────────────────────────────────────────────────────────

DEFAULT_AUTO_MAX_CONCURRENT = 5
AUTO_MAX_CONCURRENT_ENV_VAR = "KILN_CHAT_AUTO_MAX_CONCURRENT"

# Idle interactive records are just a record + empty bus once their turn task
# ends — cheap — so instead of a TTL they're LRU-evicted only when the pool
# grows beyond this. (The conversation itself lives upstream in history; an
# evicted record is recreated on the next open — architecture §5.)
MAX_IDLE_INTERACTIVE_RECORDS = 100


class ConversationCapError(Exception):
    """Raised when enabling auto mode would exceed the concurrency cap (the
    API maps it to HTTP 429)."""


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
      (``enable_auto_mode`` as declined — its consent dialog died with the
      restart; a stale ``disable_auto_mode`` with the FR1 refusal shape) or
      the trace keeps a dangling tool call the provider rejects on the next
      turn.
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
    supervisor map, referenced here for lifecycle checks."""

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
        # Correlation id for upstream requests: the hosted chat server's debug
        # log keys its events by this conversation, so the desktop and server
        # timelines can be joined. Always sent; the server ignores it unless
        # its debug log is on.
        self.headers = {**headers, "X-Kiln-Conversation-Id": record.session_id}
        # The bus's on-subscribe marker must reflect the record AT SUBSCRIBE
        # TIME, hence a lambda over the live record rather than a stored value.
        self.bus = ByteEventBus(
            marker_provider=lambda: format_conversation_state(self.record),
        )
        # Messages queued while a run is in flight, drained by the engine at
        # round boundaries. Idle sends start a run instead.
        self.inbox: list[InboundMessage] = []
        self.pending_batch: PendingApprovalBatch | None = None
        self.task: asyncio.Task | None = None
        # Graceful-stop intent polled by the engine.
        self.stop_requested: bool = False
        # Per-run settle guard: _finish_run must run exactly once per run
        # (reset by start_run). See the settle-once rule in the module doc.
        self.run_finished: bool = True

    def drain_inbox(self) -> list[InboundMessage]:
        """Atomically take-and-clear (the engine's round-boundary drain)."""
        messages = self.inbox
        self.inbox = []
        return messages


class ConversationSupervisor:
    """Single registry owning every live conversation (see module docstring).

    Cap knobs are constructor-injectable for tests; production uses the
    env-var/env-default resolution.
    """

    def __init__(
        self,
        *,
        auto_max_concurrent: int | None = None,
        max_idle_interactive_records: int = MAX_IDLE_INTERACTIVE_RECORDS,
    ) -> None:
        self._auto_max_concurrent = (
            auto_max_concurrent
            if auto_max_concurrent is not None
            else _resolve_int_env(
                AUTO_MAX_CONCURRENT_ENV_VAR, DEFAULT_AUTO_MAX_CONCURRENT
            )
        )
        self._max_idle_interactive_records = max_idle_interactive_records
        self._conversations: dict[str, _Conversation] = {}
        # Every seen leaf trace id (plus any adopted resume key) → session id.
        # Internal (the browser never sees trace ids). It serves the HISTORY
        # JOIN: the upstream sessions list is leaf-keyed (each row's ``id`` is
        # its current leaf), so the list proxy resolves rows to live records
        # through this chain, and browser keys naming a live conversation (by
        # any leaf it ever had, or its adopted key) resolve here without an
        # upstream round-trip.
        self._trace_index: dict[str, str] = {}

    # ── Reads. ────────────────────────────────────────────────────────────────

    def get(self, session_id: str) -> ConversationRecord | None:
        conv = self._conversations.get(session_id)
        return conv.record if conv is not None else None

    def list_records(self) -> list[ConversationRecord]:
        return sorted(
            (conv.record for conv in self._conversations.values()),
            key=lambda r: r.created_at,
        )

    def session_for_trace(self, trace_id: str) -> str | None:
        """History join: resolve a (possibly stale) leaf trace id to its live
        conversation (whole-chain index)."""
        return self._trace_index.get(trace_id)

    def auto_record_for_trace(self, trace_id: str) -> ConversationRecord | None:
        """Resolve a (possibly stale) leaf trace id to a live AUTO conversation
        whose flag is ON.

        The whole-chain index matches any leaf the conversation ever had, and
        the flag-on filter is what keeps the green dot / ``auto_active`` join
        persistent while the run idles between bursts, but gone once
        stopped/disabled. The kind guard excludes interactive records, which
        share the index.
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
    ) -> ConversationRecord:
        """Create (but do not start) a conversation of the given kind.

        Creating an auto conversation takes an auto slot, so it is
        cap-checked here (``ConversationCapError``).
        """
        if kind == "auto":
            self._check_auto_cap()
            policy = auto_policy()
            record = ConversationRecord(kind="auto", auto_flag=True)
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
        auto-mode conversation holding a slot (the message surfaces to users
        as the HTTP 429 detail). Checked both on create and when flipping an
        existing record's flag back on (``enable_auto``) — a flag-off record
        does not hold a slot, so re-enabling must re-compete for one."""
        active = sum(1 for c in self._conversations.values() if c.record.auto_flag)
        if active >= self._auto_max_concurrent:
            raise ConversationCapError(
                f"Too many concurrent auto runs (max {self._auto_max_concurrent}). "
                "Stop a running auto run and try again."
            )

    # ── The policy flip (architecture §2). ──────────────────────────────────────
    #
    # Interactive and auto are POLICIES on the same record, flipped only at
    # run boundaries: a live run holds the policy object it was started with
    # (the engine captures it as a run() argument), so a mid-run flip takes
    # effect at the next turn/burst. `kind` flips WITH the policy so every
    # kind-keyed guard (the frontend store, the sessions-list
    # `auto_record_for_trace` join) keeps meaning "how this conversation
    # currently behaves".

    def _flip_to_auto(self, conv: _Conversation) -> None:
        """Enable: the same record starts running auto bursts (caller
        cap-checks first — a flag-off record gave up its auto slot)."""
        conv.policy = auto_policy()
        conv.record.kind = "auto"
        conv.record.auto_flag = True

    def _swap_to_interactive(self, conv: _Conversation) -> None:
        """Flag-off settle: an OFF-auto conversation IS an idle interactive
        conversation. The record joins the idle-interactive LRU pool and the
        next send runs a normal gated interactive turn (which is also what
        lifts the ``send_message`` flag-off refusal: post-swap the policy no
        longer auto-approves anything)."""
        conv.policy = interactive_policy()
        conv.record.kind = "interactive"

    # ── Interactive create/adopt + approval rehydration. ───────────────────────

    async def adopt_interactive(
        self,
        session_key: str | None,
        *,
        upstream_url: str,
        headers: dict[str, str],
    ) -> ConversationRecord:
        """Create — or ADOPT — the interactive conversation for an upstream
        session key (POST /api/conversations kind="interactive").

        The key is OPAQUE — a durable ``root_id`` for history rows, or a bare
        leaf for legacy rows. The desktop does not resolve roots to leaves:
        the key is stored as the record's ``resume_session_key`` and the
        FIRST turn continues upstream by ``session_id`` — the backend resolves
        the session's current leaf itself (architecture §8). After the first
        ``kiln_chat_trace`` the engine holds the real leaf and every later
        turn continues by ``trace_id``.

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
                if existing is not None:
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
        if conv is None:
            return None
        if conv.pending_batch is not None and not conv.pending_batch.decided.is_set():
            # A live (or already-rehydrated) undecided batch is authoritative.
            return conv.pending_batch
        if conv.task is not None and not conv.task.done():
            # A live run owns its own round context — never second-guess it.
            return None
        # The fetch key mirrors the continuation precedence: the
        # record's own leaf when one is known, else the adopted resume key —
        # the upstream GET accepts either id kind and returns the session's
        # CURRENT leaf snapshot either way.
        fetch_key = conv.record.current_leaf_trace_id or conv.record.resume_session_key
        if fetch_key is None:
            return None

        trace = await self._fetch_persisted_trace(conv, fetch_key)
        if not trace:
            return None
        # Re-run the entry guards after the fetch await: two tabs refreshing
        # concurrently both pass the checks above, and without this re-check
        # each would mint its OWN batch — the second overwriting the first, so
        # the first tab's batch id 404s on decide and the pending event is
        # emitted twice. First fetch to complete wins; the loser returns the
        # winner's batch (or defers to a run that started meanwhile).
        if conv.pending_batch is not None and not conv.pending_batch.decided.is_set():
            return conv.pending_batch
        if conv.task is not None and not conv.task.done():
            return None
        events, signal_events, assistant_text = _pending_events_from_trace_tail(trace)
        if not events:
            # Nothing approvable. A SIGNAL-ONLY tail is not an approval batch
            # and stays unanswered — starting a resume run for a batch with
            # nothing to approve would invent a turn the user never asked
            # for. Two shapes land here: an unanswered enable_auto_mode with
            # no siblings (a lost consent dialog), and a stale
            # disable_auto_mode-only tail.
            return None

        batch = PendingApprovalBatch(
            items=[_pending_item_from_event(e) for e in events],
            # The continuation base is the trace-only shape — what the
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
            # …pre-resolved so no call dangles on the persisted trace (see
            # _pending_events_from_trace_tail): a pending enable_auto_mode is
            # declined (its consent dialog died with the restart, mirroring
            # the decline flow); a stale pending disable_auto_mode gets the
            # FR1 refusal — the model has no off-switch, so it must never
            # resolve as if the disable succeeded.
            preresolved_results={
                e.toolCallId: (
                    DISABLE_AUTO_MODE_STALE_RESULT
                    if e.toolName == DISABLE_AUTO_MODE_TOOL_NAME
                    else json.dumps({"status": "declined"}, ensure_ascii=False)
                )
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
        current leaf (architecture §8).

        The conversation's ``upstream_url`` is the chat POST URL
        (``…/v1/chat/``); the session snapshot lives beside it at
        ``…/v1/chat/sessions/{key}`` — same target the desktop's history
        proxy reads, fetched directly here because rehydration is a
        supervisor concern, not a browser round-trip.
        """
        # rstrip guards the join: upstream_url is minted with a trailing slash
        # (routes._chat_url), but a caller passing it bare would otherwise
        # silently produce …/v1/chatsessions/… and read as "nothing persisted".
        # The key is quoted (safe=""): it can be the verbatim session_id a
        # browser POSTed, and an unencoded '/', '..', '?' or '#' would reach a
        # different upstream path with the user's bearer token attached.
        url = (
            f"{conv.upstream_url.rstrip('/')}/sessions/"
            f"{urllib.parse.quote(session_key, safe='')}"
        )
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
            # Opportunistic backfill of the durable session handle:
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

    # ── Auto mode enable / disable. ───────────────────────────────────────────

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

        Three entry shapes, keyed by SESSION id (the consent event always
        arrives on the observer of a live record, so a live session id is
        always in hand):

        - consent accept: ``session_id`` + ``enable_tool_call_id`` (+ rare
          pending siblings) → burst resolving the enable call as enabled;
        - manual enable on an existing conversation: ``session_id`` only →
          the record is merely ARMED (flag on, IDLE("armed"), NO run task).
          Starting a burst here would POST an empty turn upstream, which the
          backend rejects ("No messages were sent to the server"). The first
          /messages send starts the real burst via ``send_message``'s idle
          re-arm. The bus's on-subscribe ``conversation-state`` marker carries
          the armed truth (idle + flag on + reason "armed");
        - armed-first-send on a brand-new conversation: no ``session_id``,
          first user message in ``extra_messages`` → burst; the backend mints
          the first trace on the opening turn.

        Flip semantics (architecture §2: "consent flow flips the policy on
        the SAME run"): the named record's flag flips back on (cap
        re-checked) instead of minting a duplicate record for the same
        conversation. The continuation seed uses the RECORD's own
        ``current_leaf_trace_id``.

        Raises ``KeyError`` for an unknown ``session_id`` (404 at the route —
        the record died with a restart/eviction, along with the consent
        dialog's context), ``ConversationCapError`` (429), and
        ``RuntimeError`` (409) when a non-armed-only enable races a run
        already in flight — checked before the flag flips, so a busy accept
        leaves the record untouched (armed-only flips stay legal while a
        burst runs).
        """
        conv: _Conversation | None = None
        if session_id is not None:
            conv = self._conversations.get(session_id)
            if conv is None:
                raise KeyError(f"Conversation not found: {session_id}")

        armed_only = (
            not enable_tool_call_id and not pending_tool_calls and not extra_messages
        )

        if conv is None:
            record = self.create_conversation(
                "auto", upstream_url=upstream_url, headers=headers
            )
            conv = self._conversations[record.session_id]
        else:
            record = conv.record
            # Busy guard BEFORE any side effects (same shape as decline_auto's
            # "busy"): a consent accept racing an in-flight run must 409 with
            # nothing changed — no cap slot taken, no record left flipped to
            # auto with no seeded burst (the racing run started under the
            # interactive policy, so _finish_run's swap-back-to-interactive
            # check would never fire and the record would stay stuck as auto).
            # Armed-only enables skip the guard: flipping the flag while a
            # burst is RUNNING is legal (the run holds its policy; the flag
            # applies at the next boundary). The window between this guard and
            # start_run (the pending-batch await below) is closed by
            # pre-marking the record RUNNING for the batch's duration, so a
            # racing send cannot start a burst in between.
            if not armed_only and conv.task is not None and not conv.task.done():
                raise RuntimeError(
                    f"conversation {record.session_id} already has a run in flight"
                )
            if not record.auto_flag:
                # Flipping the flag on takes an auto slot again (a flag-off
                # record does not hold one).
                self._check_auto_cap()
                self._flip_to_auto(conv)

        # ARMED-only manual enable (functional spec §4.1(2)): the
        # seed has nothing to send upstream — see the docstring.
        if armed_only:
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

        # Auto-approve pending calls now; their role:tool results ride the
        # seed body. Rare (the model is instructed to call enable_auto_mode
        # alone).
        sibling_results: dict[str, str] = {}
        if pending_tool_calls:
            # Pre-mark RUNNING across the await: the busy guard above ran
            # before this batch executes, so a ``POST /{sid}/messages``
            # landing in this await window must queue to the inbox (the
            # RUNNING branch of send_message), not start a burst that would
            # make start_run below 409 and strand the executed calls' results.
            # Rolled back if the batch raises so the record isn't stuck
            # RUNNING with no task.
            prior_state = record.state
            record.state = RunState.RUNNING
            try:
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
                )
            except BaseException:
                record.state = prior_state
                raise

        body = build_auto_seed_body(
            # The enable call belongs to the assistant turn persisted at the
            # conversation's tail — the record's own leaf is authoritative
            # (the engine's on_trace keeps it fresh). A key-adopted record with
            # no leaf yet continues by session_id instead (the backend
            # resolves the current leaf); with NEITHER key a fresh
            # conversation starts.
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
        """Clear the conversation's auto-mode flag (reason ``user_disabled``).

        The flag must clear even mid-burst: a RUNNING burst is pre-marked
        (flag off + reason) THEN cancelled, so the cancel handler and the
        settle path publish the true reason instead of clobbering it with
        ``user_stopped``. With no live burst the flag clears directly: queued
        inbox dies with the flag and the off state publishes. Both paths swap
        the record back to its interactive life (``_swap_to_interactive`` —
        directly here for the idle branch, via ``_finish_run``'s off branch
        for the cancelled-burst one). Returns False for unknown records;
        already-off records are a True no-op.
        """
        conv = self._conversations.get(session_id)
        if conv is None:
            return False
        record = conv.record
        if not record.auto_flag:
            return True

        # Pre-mark BEFORE any cancel (see docstring).
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
            # its interactive life.
            self._finish_run(conv)
            return True

        # No live burst (idle): clear directly. The publish carries the auto
        # event shape (kind=auto, flag off, reason), THEN the record swaps to
        # its interactive life (the swap is not an event of its own — the
        # next state event simply reports kind interactive).
        conv.inbox.clear()
        self._touch(conv)
        self._publish_state(conv)
        if conv.policy.approvals == "auto":
            self._swap_to_interactive(conv)
        return True

    async def set_auto_flag(
        self, session_id: str, enabled: bool
    ) -> Literal["ok", "not_found"]:
        """Flip the auto-mode flag on an EXISTING conversation
        (POST /api/conversations/{sid}/auto, functional spec §2).

        ``enabled=False`` delegates to :meth:`disable_auto` (a no-op on an
        already-interactive record). ``enabled=True`` re-arms: the record
        flips to the auto policy (cap-checked — a flag-off record holds no
        slot; raises ``ConversationCapError`` for the route's 429) with NO
        upstream POST — the ARMED-only shape, so the next message starts the
        burst.
        """
        conv = self._conversations.get(session_id)
        if conv is None:
            return "not_found"
        record = conv.record
        if not enabled:
            await self.disable_auto(session_id)
            return "ok"
        if not record.auto_flag:
            self._check_auto_cap()
            self._flip_to_auto(conv)
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
        gating_tool_call_id: str,
        siblings: list[ToolCallInfo],
    ) -> Literal["ok", "not_found", "busy"]:
        """Decline a pending auto-mode consent request
        (POST /api/conversations/{sid}/auto with a decline context).

        ``gating_tool_call_id`` is the ``enable_auto_mode`` call that
        surfaced the consent flow. The engine's consent interception ended
        the turn WITHOUT answering it, so the persisted trace has a dangling
        tool call the provider requires answered. Declining starts a normal
        interactive TURN whose seed resolves it as ``{"status": "declined"}``
        and every sibling as denied; the reply streams on the observer
        channel like any other turn. Declining never flips any policy: the
        record already runs (or swaps back to) the interactive policy.

        "busy" → a run is already in flight (a consent decline races a fresh
        send); the route maps it to 409 rather than corrupting the turn.
        """
        conv = self._conversations.get(session_id)
        if conv is None:
            return "not_found"
        record = conv.record
        if conv.task is not None and not conv.task.done():
            return "busy"

        messages: list[dict[str, Any]] = [
            {
                "role": "tool",
                "tool_call_id": gating_tool_call_id,
                # Persisted in the trace, so the bytes are part of the
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
        # The dangling gating call lives in the conversation's tail snapshot —
        # the record's own leaf is authoritative. continuation_key_fields also covers
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

    # ── Run lifecycle. ────────────────────────────────────────────────────────

    def start_run(
        self,
        session_id: str,
        initial_body: dict[str, Any] | None = None,
        resume_batch: PendingApprovalBatch | None = None,
    ) -> None:
        """Start a turn/burst/run task for the conversation.

        ``initial_body`` is the upstream request body for the first round
        (interactive turn / auto burst seed). ``resume_batch`` starts the
        RESUME RUN instead: execute the (already-decided) runless batch, then
        continue the loop from its continuation — see
        ``ConversationEngine.run``.
        """
        conv = self._conversations[session_id]
        if conv.task is not None and not conv.task.done():
            raise RuntimeError(f"conversation {session_id} already has a run in flight")
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
        # same truth from the on-subscribe marker.
        self._publish_state(conv)

    async def _supervise(
        self,
        conv: _Conversation,
        initial_body: dict[str, Any] | None,
        resume_batch: PendingApprovalBatch | None = None,
    ) -> None:
        """Own one run's lifetime, decoupled from any HTTP request.

        The engine records natural outcomes on the record itself; this wrapper
        only classifies the abnormal endings (architecture §9): cancellation
        → IDLE(user_stopped) when the flag was on, unexpected exception →
        IDLE(error) with the flag left on. Every path funnels through
        ``_finish_run`` in the ``finally``.
        """
        record = conv.record
        engine = ConversationEngine(conv.upstream_url, conv.headers)
        io = self._engine_io(conv)
        # Inbox-stranding guard: only a NATURAL settle (the engine's run()
        # returned without raising) may consume a stranded inbox by
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
                    await engine.run(
                        record,
                        conv.policy,
                        io,
                        initial_body,
                        resume_batch=resume_batch,
                    )
                else:
                    await engine.run(record, conv.policy, io, initial_body)
            except asyncio.CancelledError:
                # A cancel from stop()/disable_auto() already pre-marked the
                # outcome (flag-off + reason), which we must preserve so the
                # correct reason publishes. Only fill in defaults when nothing
                # was pre-marked.
                ended_naturally = False
                record.state = RunState.IDLE
                if record.auto_flag:
                    record.auto_flag = False
                    record.idle_reason = "user_stopped"
                raise
            except Exception:
                # An unrecoverable engine error: the burst ends but the flag
                # stays on so the user can retry or stop. Conservatively NOT a
                # natural settle: a persistent upstream error would otherwise
                # re-launch the stranded message into the same failure on
                # every settle.
                ended_naturally = False
                logger.exception("Conversation %s run failed", record.session_id)
                record.state = RunState.IDLE
                record.idle_reason = "error"
        finally:
            self._finish_run(conv, restart_stranded_inbox=ended_naturally)

    def _finish_run(
        self, conv: _Conversation, *, restart_stranded_inbox: bool = False
    ) -> None:
        """THE settle path — every run ends here exactly once (architecture
        §9: all settle/publish logic in one place).

        Runs from ``_supervise``'s ``finally`` on every exit (natural end,
        cancel, exception) AND from ``stop()``/``disable_auto()`` as the
        backstop for tasks cancelled before they ever started (which never
        enter ``_supervise``). The ``run_finished`` guard makes the double
        call a no-op.

        ``restart_stranded_inbox``: when True (a NATURAL settle — see
        ``_supervise``), a non-empty inbox at settle is consumed by starting
        a fresh turn instead of being left stranded. The default (False) is
        the safe choice for the ``stop()`` / ``disable_auto()`` backstops,
        which must never resurrect a run: they call this AGAIN after awaiting
        the cancelled task, relying on the run-once guard, so a restart here
        would double-settle. Only the clean-return path — exactly the
        engine's drain-settle race window — passes True.
        """
        if conv.run_finished:
            return
        conv.run_finished = True
        record = conv.record
        conv.task = None
        conv.stop_requested = False
        # A parked batch can't outlive its run (the awaiting engine is gone).
        # Restart recovery rebuilds batches from the trace tail.
        conv.pending_batch = None

        # The conversation persists across runs.
        if record.state in (RunState.RUNNING, RunState.AWAITING_APPROVAL):
            # The engine exited without recording an outcome (e.g. cancelled
            # before its first await, or a defensive fallback) — an idle
            # boundary is the safe truth.
            record.state = RunState.IDLE
        self._touch(conv)
        self._publish_state(conv)
        if conv.policy.approvals == "auto" and not record.auto_flag:
            # The auto-mode flag is off after a run under the AUTO policy
            # (stop/disable landed before or during this burst): the queued
            # inbox dies with the flag (a message queued for an auto burst
            # must never silently start a gated turn). Keyed on the settled
            # run's POLICY, not record.kind: the policy is what made this an
            # auto burst. The record swaps back to its interactive life (an
            # off-auto conversation IS an idle interactive conversation) and
            # joins the LRU-bounded idle-interactive pool — the off state was
            # already published above with its reason.
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
            inbox_len=len(conv.inbox),
            restart_stranded_inbox=restart_stranded_inbox,
            current_leaf_trace_id=record.current_leaf_trace_id,
        )
        # Inbox-drain-on-settle. Logged the settle FIRST (above) so the "run
        # ended" line reflects the settled IDLE, then the restart (which logs
        # + publishes RUNNING for its own new turn) follows. The off-auto
        # branch already cleared the inbox, so this only fires for an
        # interactive turn / flag-on auto burst that settled with a message
        # POSTed into the inbox during the drain-settle race window.
        if restart_stranded_inbox and conv.inbox:
            self._restart_from_inbox(conv)

    def _restart_from_inbox(self, conv: _Conversation) -> None:
        """Consume a stranded inbox at settle by starting a fresh turn — the
        server-side complement to the client's queued-message flush.

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
        the idle re-arm sends raw — see ``send_message``) and the same
        ``continuation_key_fields`` + ``auto_mode`` propagation.

        Echo-once: the inbox messages were ALREADY echoed onto the bus by
        ``send_message`` at enqueue, so they are NOT re-echoed here.

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

    def _engine_io(self, conv: _Conversation) -> EngineIO:
        """Wire the engine's io bundle onto this conversation's machinery."""
        record = conv.record

        async def on_trace(trace_id: str) -> None:
            # The engine already updated the record (single-writer rule); the
            # supervisor only maintains its cross-conversation index here.
            self._trace_index[trace_id] = record.session_id
            self._touch(conv)

        async def await_decisions(batch: PendingApprovalBatch) -> dict[str, bool]:
            conv.pending_batch = batch
            # Tell live observers the run parked (the engine already emitted
            # the tool-calls-pending payload with the batch contents; this is
            # the lifecycle marker).
            self._publish_state(conv)
            await batch.decided.wait()
            # Tell live observers the run resumed. The frontend's box-clearing
            # logic relies on a RUNNING conversation-state event to clear a
            # stale approval box in OTHER tabs; the runless-batch path gets
            # this from start_run, but this live-parked path would otherwise
            # publish nothing. Stamp RUNNING before publishing so the event carries
            # the true state (the engine re-stamps it right after we return).
            record.state = RunState.RUNNING
            self._publish_state(conv)
            # The batch stays on the conversation (decided) until the run
            # settles or the next park replaces it, so a second decide can be
            # answered with a conflict rather than a 404 (functional spec §5:
            # two tabs — first decision set wins, the second gets 409).
            return dict(batch.decisions or {})

        return EngineIO(
            emit=conv.bus.emit,
            on_trace=on_trace,
            drain_inbox=conv.drain_inbox,
            await_decisions=await_decisions,
            stop_requested=lambda: conv.stop_requested,
        )

    # ── Messages. ─────────────────────────────────────────────────────────────

    def send_message(self, session_id: str, content: str) -> str | None:
        """Queue a user message into the conversation (POST /messages).

        Behavior by state (functional spec §2): RUNNING/AWAITING_APPROVAL →
        queued, drained at the next round boundary (or after decisions
        resolve); IDLE → starts a turn seeded with the message. Echoes the
        message onto the bus + replay buffer at ENQUEUE time so every observer
        (including the sender) renders it immediately — and so the engine's
        drain must never re-echo (echo-once).

        Returns the accepted message's stable id (the sending tab renders its
        typed text locally and uses the id to dedupe its own echo — the
        echoed content carries the app-context header the browser prepends,
        which only OTHER observers should render, stripped).

        Returns None for unknown conversations (route maps to 404) AND for
        flag-off records still carrying the AUTO policy — a narrow transient
        window (disable pre-marks the flag before the burst's settle swaps the
        policy back to interactive): a run started here would auto-approve
        every tool without an active consent. Post-swap the record is
        interactive and sends run normal gated turns.
        """
        conv = self._conversations.get(session_id)
        if conv is None:
            return None
        if conv.policy.approvals == "auto" and not conv.record.auto_flag:
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

        # IDLE → start a fresh turn/burst seeded with the message: continue
        # from the current leaf, message unframed (framing is for MID-run
        # drains only), auto_mode riding iff the flag is on.
        # Deliver any stranded inbox FIRST (messages that landed during a
        # non-natural settle — e.g. a turn that ended in a terminal upstream
        # error, which _finish_run deliberately does not restart from). They
        # were echoed at enqueue (echo-once), so no re-emit here; ordering
        # matches send order, with the fresh message last.
        stranded = conv.drain_inbox()
        messages: list[dict[str, Any]] = [m.as_chat_message() for m in stranded]
        messages.append(message.as_chat_message())
        # Continuation key: trace_id from the record's own leaf for the normal
        # in-process flow, session_id for a key-adopted record's FIRST turn
        # (the backend resolves the current leaf), nothing for a brand-new
        # conversation — see continuation_key_fields.
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

        Two batch shapes resolve here:

        - a LIVE batch: the engine's run task is parked on ``decided`` —
          setting it wakes the engine, which executes and continues in-place;
        - a RUNLESS batch (rehydrated from the persisted trace tail after a
          desktop restart, or the graceful-stop leftovers): nothing is
          awaiting the event, so deciding starts the RESUME RUN that executes
          the batch and continues the loop.
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

    # ── Stop. ─────────────────────────────────────────────────────────────────

    async def stop(self, session_id: str) -> None:
        """Stop the conversation's run. Idempotent.

        - auto: the Stop button — cancel the in-flight burst immediately and
          clear the flag, pre-marking flag-off/user_stopped so the cancel
          handler preserves the reason.
        - interactive: cancel the in-flight turn; the record idles.

        Always runs the cancel-before-first-run backstop (a task cancelled
        before it ever ran never entered _supervise, so its finally/_finish_run
        never fired — settle here; _finish_run is run-once so the double call
        is a no-op).
        """
        conv = self._conversations.get(session_id)
        if conv is None:
            return
        record = conv.record

        task = conv.task
        if task is not None and not task.done():
            # Pre-mark the outcome BEFORE cancelling so the CancelledError
            # handler (and any observer of the settle) sees the true reason.
            if record.auto_flag:
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
            return

        # No live run: only an idle auto conversation has anything to clear.
        # Publish the off state first, then swap the record to its
        # interactive life.
        if record.auto_flag:
            record.auto_flag = False
            record.idle_reason = "user_stopped"
            conv.inbox.clear()
            self._touch(conv)
            self._publish_state(conv)
            if conv.policy.approvals == "auto":
                self._swap_to_interactive(conv)

    # ── State publishing. ─────────────────────────────────────────────────────

    def _publish_state(self, conv: _Conversation) -> None:
        """Publish the conversation's current state to its live observers.
        ``publish`` (not ``emit``): lifecycle markers must not enter the
        replay buffer (a replayed stale state would lie to a late
        subscriber; the on-subscribe marker provides the fresh truth
        instead)."""
        conv.bus.publish(format_conversation_state(conv.record))

    # ── Bookkeeping. ──────────────────────────────────────────────────────────

    def _touch(self, conv: _Conversation) -> None:
        conv.record.updated_at = _utc_now()

    # ── Eviction. ─────────────────────────────────────────────────────────────

    def _evict(self, session_id: str) -> None:
        conv = self._conversations.pop(session_id, None)
        if conv is None:
            return
        # End any live observer streams: an evicted conversation's bus can
        # never emit again, so a subscriber left attached would otherwise park
        # forever on a dead queue. EOF lets the client re-open from history,
        # which recreates the record.
        conv.bus.close()
        # Every index entry pointing at this record has its key in the
        # record's own seen chain (on_trace appends before indexing; adopt
        # appends the adopted key), so iterating the chain beats a full-index
        # scan. The ownership check keeps an entry that another record owns.
        for tid in conv.record.seen_trace_ids:
            if self._trace_index.get(tid) == session_id:
                del self._trace_index[tid]
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


# The one process-wide supervisor. Everything that owns a conversation targets
# THIS instance (runtime/api.py for the /api/conversations browser surface,
# chat/routes.py for the history join). Tests construct their own instances
# and patch this name where needed.
conversation_supervisor = ConversationSupervisor()
