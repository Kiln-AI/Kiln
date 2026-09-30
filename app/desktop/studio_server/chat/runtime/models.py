"""Data model of the unified conversation runtime.

A conversation has two orthogonal axes on ``ConversationRecord``: ``state``
(one ``RunState`` enum for every kind) and ``auto_flag`` (the
per-conversation auto-mode flag, only meaningful for interactive/auto
records). Auto mode on/off maps onto them as:

- auto burst in flight           → state=RUNNING,  auto_flag=True
- auto on, between bursts        → state=IDLE,     auto_flag=True
- auto stopped by the user       → state=IDLE,     auto_flag=False, idle_reason="user_stopped"
- auto disabled by the user      → state=IDLE,     auto_flag=False, idle_reason="user_disabled"

Interactive/auto conversations never reach a terminal state — they idle
between turns (functional spec §1). A sub-agent run is one-shot: it goes
RUNNING → a terminal state (COMPLETED / FAILED / STOPPED / TIMEOUT).

Per-kind behavior is data: ``ConversationPolicy`` is a frozen dataclass built
by the ``interactive_policy`` / ``auto_policy`` / ``subagent_policy``
factories. A new conversation kind is a new policy factory (plus its
interceptor chain), and a kind-specific behavior is an explicit policy field
— never a subclass (architecture §11).
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Literal

from kiln_ai.adapters.model_adapters.stream_events import ToolInputAvailableEvent
from pydantic import BaseModel, ConfigDict, Field

from app.desktop.studio_server.chat.constants import MAX_TOOL_ROUNDS

if TYPE_CHECKING:
    # Import cycle avoidance only: interceptors.py imports models for the
    # context/result types, so the Interceptor callable type is quoted here.
    from app.desktop.studio_server.chat.runtime.interceptors import Interceptor

_ID_ALPHABET = "abcdefghijklmnopqrstuvwxyz234567"
_ID_LENGTH = 12


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _mint_id(prefix: str) -> str:
    suffix = "".join(secrets.choice(_ID_ALPHABET) for _ in range(_ID_LENGTH))
    return f"{prefix}_{suffix}"


def new_session_id() -> str:
    """Mint a conversation session id (``cv_<base32>``): the desktop-local
    handle of a live conversation. The upstream durable id is tracked
    separately on ``ConversationRecord.root_id``."""
    return _mint_id("cv")


def new_message_id() -> str:
    """Mint an inbound-message id (``cm_<base32>``).

    Echoed to observers on the ``user-message`` event so a re-attaching
    client can dedupe a replayed echo against a message it already renders.
    """
    return _mint_id("cm")


def new_batch_id() -> str:
    """Mint a pending-approval batch id (``ab_<base32>``)."""
    return _mint_id("ab")


ConversationKind = Literal["interactive", "auto", "subagent"]


class RunState(str, Enum):
    """Lifecycle state of a conversation's run (functional spec §1).

    ``COMPLETED``/``FAILED``/``STOPPED``/``TIMEOUT`` are reachable only by
    one-shot (sub-agent) policies. Interactive/auto conversations cycle
    IDLE ⇄ RUNNING ⇄ AWAITING_APPROVAL forever; "auto mode off" is the
    ``auto_flag`` axis, not a state. An IDLE conversation re-arms on the next
    message.
    """

    IDLE = "idle"  # no turn in flight (interactive/auto between turns)
    RUNNING = "running"  # a turn/burst is in flight
    AWAITING_APPROVAL = "awaiting_approval"  # parked on pending tool decisions
    COMPLETED = "completed"  # one-shot: final plain-text turn = the report
    FAILED = "failed"  # one-shot: unrecoverable error
    STOPPED = "stopped"  # one-shot: user or parent called stop
    TIMEOUT = "timeout"  # one-shot: round cap or wall-clock cap exceeded

    @property
    def is_terminal(self) -> bool:
        """Terminal == the run can never advance again (one-shot kinds only).

        An IDLE interactive/auto record is NOT terminal — it re-arms on the
        next message (Revision R1).
        """
        return self in _TERMINAL_STATES


_TERMINAL_STATES = frozenset(
    {RunState.COMPLETED, RunState.FAILED, RunState.STOPPED, RunState.TIMEOUT}
)


class ConversationRecord(BaseModel):
    """In-memory record of one live conversation (one per session id).

    Serializable snapshot of lifecycle state, shared between the engine
    (single writer while a run task is active), the supervisor
    (settle/publish/eviction), and the browser-facing API.
    """

    # THE handle. Permanent for the conversation's lifetime; the rotating
    # upstream trace_id becomes the internal `current_leaf_trace_id` detail.
    session_id: str = Field(default_factory=new_session_id)
    # The upstream session's DURABLE id (`session_meta.root_id` — the first
    # persisted snapshot's id, stamped backend-side by
    # `stream_orchestration.save_chat_snapshot`). Phase 5: this is the
    # browser's restart-recovery key (the in-memory `session_id` dies with
    # the desktop process; the old world persisted a leaf trace id for the
    # same purpose, which phase 5 removes from the browser surface). Learned
    # best-effort: stamped by the engine on a FRESH record's first
    # `kiln_chat_trace` (first persist ⇒ root == that snapshot id), by
    # adopt-by-root (`adopt_interactive(root_id=…)`), or backfilled from the
    # approval-rehydration snapshot fetch. None until one of those fires.
    root_id: str | None = None
    # The opaque upstream session key a COLD record was adopted from (phase 6):
    # a durable ``root_id`` for post-phase-5 history rows, or — legacy sessions
    # without ``session_meta`` only — a leaf id. The two are snapshot-id-shaped
    # and indistinguishable desktop-side, which is exactly why this is NOT
    # stamped into ``root_id`` (that field must stay the TRUE durable id the
    # browser persists as its recovery key; stamping a legacy LEAF there would
    # hand the browser a key that goes stale on the next persist). Used to
    # build ``session_id`` continuation bodies until the first
    # ``kiln_chat_trace`` reveals the real current leaf — the backend resolves
    # the key to the session's current leaf itself (architecture §8), so the
    # desktop needs no leaf to resume.
    resume_session_key: str | None = None
    kind: ConversationKind
    state: RunState = RunState.IDLE
    # Latest persisted upstream leaf (rotates every snapshot). Single writer =
    # the run loop, which updates it before calling EngineIO.on_trace.
    current_leaf_trace_id: str | None = None
    # Whole chain of leaves this conversation has touched. Needed internally:
    # the upstream sessions LIST is leaf-keyed (each row's ``id`` is its
    # current leaf), so the desktop's history join resolves upstream rows to
    # live records through this chain. Adopt-by-key seeds the adopted key
    # here too — it was a leaf once (a root IS the first leaf) and a
    # non-empty chain is what tells the engine this record joined
    # mid-conversation (root-stamp suppression).
    seen_trace_ids: list[str] = Field(default_factory=list)
    # Sub-agent lineage: the parent conversation's session id. It is stable,
    # so no alias chaining is needed as the parent's leaves rotate.
    parent_session_id: str | None = None
    # Sub-agent identity (None for interactive/auto records).
    name: str | None = None
    agent_type: str | None = None
    # The per-conversation auto-mode flag. Flips between turns only — a flip
    # mid-round is impossible because the policy swap happens at run
    # boundaries (architecture §2).
    auto_flag: bool = False
    # Why the run last went idle: asked_user / done / error / max_rounds /
    # armed while the flag is on; user_stopped / user_disabled when the flag
    # was just cleared (the off event publishes as a conversation-state
    # change with this reason attached).
    idle_reason: str | None = None
    # One-shot kinds: the model's final plain-text turn (or its partial-output
    # base while running). The supervisor's settle path synthesizes the
    # status-note framing for FAILED/STOPPED/TIMEOUT.
    final_report: str | None = None
    # True once the report reached the parent through any channel. Pins the
    # record against GC while False.
    report_delivered: bool = False
    rounds_used: int = 0
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class InboundMessage(BaseModel):
    """A user message queued into a conversation (send-while-running, steer,
    idle re-arm, or an injected ``<subagent_report>`` frame for an auto-flag
    parent).

    The supervisor echoes the message onto the bus at enqueue time; the
    engine drains WITHOUT re-echoing (echo-once).
    """

    # Stable id minted server-side so a re-attaching client can dedupe the
    # replayed echo against a message it already shows.
    id: str = Field(default_factory=new_message_id)
    # Fixed to the user role: message injection is documented as user input
    # only, so the schema enforces it rather than trusting a caller role.
    role: Literal["user"] = "user"
    content: str

    def as_chat_message(self) -> dict[str, Any]:
        return {"role": self.role, "content": self.content}


class SubAgentSeed(BaseModel):
    """Everything needed to start a sub-agent session upstream.

    Desktop-side lineage is the record's ``parent_session_id``.
    ``parent_trace_id`` rides the ``agent`` block: the BACKEND resolves it
    into durable lineage on the child session's meta, so it is part of the
    wire contract even though the desktop keys nothing on it.
    """

    agent_type: str
    name: str
    prompt: str
    parent_trace_id: str | None = None


def continuation_key_fields(record: ConversationRecord) -> dict[str, Any]:
    """The continuation-identity field(s) for a fresh upstream turn body.

    One helper so every idle-start body builder (message re-arm, consent
    decline, rehydrated approval batches) picks the SAME key with the same
    precedence:

    - a known leaf → ``trace_id`` (the normal in-process flow; DELIBERATELY
      kept on trace-id continuation — the engine's ``on_trace`` holds the
      fresh leaf, so switching these to session ids would only add a backend
      pointer resolution per turn for zero benefit);
    - no leaf but a ``resume_session_key`` (adopted from history, nothing
      persisted since) → ``session_id`` — the backend resolves the current
      leaf (phase 6; the desktop no longer resolves roots to leaves itself);
    - neither → empty: a brand-new conversation, the backend mints the first
      trace on the opening turn.

    Never both: the backend 400s ``trace_id`` + ``session_id`` together.
    """
    if record.current_leaf_trace_id is not None:
        return {"trace_id": record.current_leaf_trace_id}
    if record.resume_session_key is not None:
        return {"session_id": record.resume_session_key}
    return {}


def kickoff_message(name: str, prompt: str) -> str:
    """The first user message of a child session. It is persisted in the
    child's trace, so the text is part of the protocol contract (byte-pinned
    in ``test_interceptors.py``).

    It carries the full briefing — even though the briefing is ALSO seeded
    into the system prompt backend-side — so the user sees the sub-agent's
    instructions when they open its tab (the system prompt is never
    rendered). The name leads because the session-list title derives from the
    first user message.
    """
    return (
        f"{name} — your assignment:\n\n{prompt}\n\n"
        "Begin now, work autonomously, and end with your final report."
    )


def build_subagent_seed_body(seed: SubAgentSeed) -> dict[str, Any]:
    """The child's first upstream POST (byte-pinned in
    ``test_interceptors.py``).

    The ``agent`` block is first-turn-only (the backend 400s ``agent`` +
    ``trace_id`` together); the engine's trace-advance step drops it after
    the first persisted snapshot. ``auto_mode`` rides every continuation via
    the engine's ``{**body, ...}`` rebuilds.
    """
    agent: dict[str, Any] = {
        "agent_type": seed.agent_type,
        "seed_prompt": seed.prompt,
    }
    if seed.parent_trace_id is not None:
        agent["parent_trace_id"] = seed.parent_trace_id
    return {
        "messages": [
            {
                "role": "user",
                "content": kickoff_message(seed.name, seed.prompt),
            }
        ],
        "agent": agent,
        "auto_mode": True,
    }


def build_auto_seed_body(
    *,
    trace_id: str | None,
    enable_tool_call_id: str | None,
    extra_messages: list[dict[str, Any]],
    sibling_results: dict[str, str],
    session_id: str | None = None,
) -> dict[str, Any]:
    """The first upstream continuation body of an auto burst, pinned
    end-to-end by the ``auto_seed_and_tool_round`` golden fixture.

    Message order: any ``extra_messages`` first (the manual/armed-first-send
    path carries the user's message), then the accepted ``enable_auto_mode``
    call resolved as ``{"status":"enabled"}``, then one ``role:tool`` result
    per auto-executed sibling pending call. The caller
    (``ConversationSupervisor.enable_auto``) executes the siblings, which
    keeps this builder pure.

    ``auto_mode`` rides every continuation: the engine's ``{**body, ...}``
    rebuilds propagate it through the whole burst, so seeding it once here is
    enough. The upstream orchestrator reads it to phrase the auto-round-cap
    reminder for an absent user (act or report stuck, don't ask a question).

    When NEITHER continuation key is present (a brand-new conversation) the
    body omits both so the backend starts a fresh conversation and mints the
    first trace on the opening turn; the seed then carries the first user
    message in ``extra_messages`` so the opening turn is never empty.

    Spawn-consent accept (FR2) is the ``enable_tool_call_id=None`` shape: the
    gating spawn call rides ``sibling_results`` like any auto-approved
    pending sibling (its ``{"status": "spawned", ...}`` result answers the
    call), so the seed carries no enable row — the flag flip is the consent,
    not a tool result.

    ``session_id`` is the resume-by-key continuation for records
    adopted from history with no leaf yet (``resume_session_key``): the
    backend resolves the session's current leaf itself. ``trace_id`` wins
    when both are supplied — a known leaf is strictly fresher information and
    the backend rejects the two together (mutually exclusive).
    """
    messages: list[dict[str, Any]] = list(extra_messages)

    if enable_tool_call_id:
        messages.append(
            {
                "role": "tool",
                "tool_call_id": enable_tool_call_id,
                "content": json.dumps({"status": "enabled"}, ensure_ascii=False),
            }
        )

    for tc_id, output in sibling_results.items():
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tc_id,
                "content": output,
            }
        )

    if trace_id is not None:
        return {
            "trace_id": trace_id,
            "messages": messages,
            "auto_mode": True,
        }
    if session_id is not None:
        return {
            "session_id": session_id,
            "messages": messages,
            "auto_mode": True,
        }
    return {"messages": messages, "auto_mode": True}


def format_subagent_report(record: ConversationRecord) -> str:
    """The framed report injected into the parent conversation as a user-role
    message. The frame is stripped/specialized on hydration client-side and
    the skill teaches the model it is machinery, not the user speaking.

    The frame shape (tag, attribute names, body layout) is part of the
    protocol contract: it is persisted in parent traces and parsed by the
    client's report-panel detection. The ``id`` attribute carries the child's
    session id (``cv_``), an opaque handle to the client that stays
    resolvable.
    """
    body = record.final_report or "(no report produced)"
    return (
        f'<subagent_report id="{record.session_id}" '
        f'agent_type="{_escape_attr(record.agent_type or "")}" '
        f'status="{record.state.value}" '
        f'title="{_escape_attr(record.name or "")}">\n'
        f"{body}\n"
        f"</subagent_report>"
    )


def _escape_attr(value: str) -> str:
    return value.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


# What the engine's max-rounds backstop tells the user, per kind (surfaces in
# the UI and, for sub-agents, in the report note flow).
INTERACTIVE_MAX_ROUNDS_MESSAGE = (
    "Maximum tool rounds exceeded. Please start a new message."
)
SUBAGENT_MAX_ROUNDS_MESSAGE = (
    "Sub-agent exceeded its maximum tool rounds and was stopped. "
    "Its last output is reported as-is."
)

# Sub-agent budget knobs: defaults, overridable by operators via env vars.
DEFAULT_SUBAGENT_MAX_ROUNDS = 50
SUBAGENT_MAX_ROUNDS_ENV_VAR = "KILN_CHAT_SUBAGENT_MAX_ROUNDS"
DEFAULT_SUBAGENT_TIMEOUT_SECONDS = 1800.0
SUBAGENT_TIMEOUT_ENV_VAR = "KILN_CHAT_SUBAGENT_TIMEOUT_SECONDS"


def _resolve_positive_int_env(env_var: str, default: int) -> int:
    raw = os.environ.get(env_var)
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return default


def _resolve_positive_float_env(env_var: str, default: float) -> float:
    raw = os.environ.get(env_var)
    if raw:
        try:
            value = float(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return default


MessageFraming = Literal["none", "side_note", "steer"]


@dataclass(frozen=True)
class ConversationPolicy:
    """Frozen per-conversation behavior: derived from kind (+ flags), swapped
    on the SAME record between turns for auto flips (never mid-round).

    This is deliberately plain data + an interceptor chain: conversation kinds
    differ only in these few knobs (architecture §2, §11).
    """

    # "gated": tool calls flagged requires_approval park the run for user
    # decisions. "auto": every client tool executes unattended.
    approvals: Literal["gated", "auto"]
    # How drained inbox messages are framed before riding a continuation.
    # Generalizes the architecture's `side_note_framing: bool`, because the
    # two unattended kinds use DIFFERENT reminder texts that are persisted
    # verbatim: "side_note" = auto's mid-burst aside frame, "steer" = the
    # sub-agent steering frame, "none" = interactive (messages ride raw).
    message_framing: MessageFraming
    # One-shot lifecycle: a plain-text turn is COMPLETED (its text = the
    # report) and terminal states are reachable.
    one_shot: bool
    max_rounds: int
    # Wall-clock cap the supervisor applies via asyncio.wait_for (one-shot
    # kinds only). None = no cap.
    wall_clock_seconds: float | None
    # Ordered signal-tool interception chain (see interceptors.py). Order is
    # PRIORITY: the engine scans the whole round's client events per
    # interceptor, so e.g. the interactive chain's consent interception
    # outranks everything behind it.
    interceptors: tuple["Interceptor", ...]
    # Child creation: when set, the engine builds the first POST from this
    # seed (agent block + kickoff message) and echoes the kickoff onto the
    # stream.
    seed: SubAgentSeed | None = None
    # 0 for parent conversations, 1 for children. Children reject
    # orchestration calls (depth guard interceptor): sub-agents cannot manage
    # sub-agents.
    orchestration_depth: int = 0
    # Auto-mode graceful stop (functional spec §4.4(1)): when a stop lands at
    # a round boundary that has client tool calls, surface them via
    # tool-calls-pending for NORMAL approval instead of executing — after the
    # stop the conversation returns to interactive mode where everything is
    # subject to approval. Sub-agents just end (their calls die with them),
    # and interactive turns are cancelled, not gracefully stopped — hence a
    # policy flag rather than universal behavior.
    graceful_stop_surfaces_pending: bool = False
    max_rounds_message: str = INTERACTIVE_MAX_ROUNDS_MESSAGE
    # kiln-chat-retry events carry the session id as run_id on auto and
    # sub-agent streams but not on interactive ones.
    retry_events_carry_run_id: bool = True


class PendingApprovalBatch(BaseModel):
    """A parked approval round: the run task is suspended on ``decided`` while
    the user decides (architecture §2).

    ``items`` is the exact wire shape of the ``tool-calls-pending`` event
    items (toolCallId/toolName/input/requiresApproval[/permission/
    approvalDescription]).

    ``body`` / ``assistant_text`` / ``tool_input_events`` are the round
    context needed to rebuild the continuation. The engine holds the same
    context on its stack while parked, so these fields exist for the RECOVERY
    contract (architecture §2): the batch must be reconstructible from the
    persisted trace tail, which restart/refresh recovery builds on.
    """

    # asyncio.Event isn't a pydantic type; this record is in-memory only.
    model_config = ConfigDict(arbitrary_types_allowed=True)

    batch_id: str = Field(default_factory=new_batch_id)
    items: list[dict[str, Any]]
    body: dict[str, Any]
    assistant_text: str
    tool_input_events: list[ToolInputAvailableEvent]
    # Pre-answered calls riding the batch WITHOUT being user decisions
    # (tool_call_id → result JSON). Recovery: a rehydrated trace tail
    # can carry unanswered SIGNAL calls (enable/disable_auto_mode — and,
    # FR2, a flag-off gating spawn_subagent) next to real client calls —
    # signals are never executed as tools, so the resume run pre-answers
    # them purely so the persisted trace has no dangling tool call: a
    # pending enable_auto_mode (or flag-off spawn_subagent) resolves as
    # {"status": "declined"} (its consent dialog died with the restart,
    # mirroring the decline flow); a stale pending disable_auto_mode
    # resolves with the FR1 refusal shape (DISABLE_AUTO_MODE_STALE_RESULT —
    # the model has no off-switch). Empty for live batches (the interceptor
    # chain answers signals before a park can ever include one).
    preresolved_results: dict[str, str] = Field(default_factory=dict)
    # Set by the supervisor's decide() exactly once; the engine wakes, reads
    # `decisions`, and resumes. Partial decision sets are rejected upstream of
    # this model (one batch, one decision set — matches today's UI).
    decided: asyncio.Event = Field(default_factory=asyncio.Event)
    decisions: dict[str, bool] | None = None


# ── Kind → policy factories (architecture §2 mapping table) ─────────────────


def interactive_policy() -> ConversationPolicy:
    """Interactive: gated approvals, not one-shot, no framing, MAX_TOOL_ROUNDS.

    Approval-requiring tools park the run; enable_auto_mode surfaces the
    consent control event, and a spawn_subagent without auto mode surfaces
    the SAME consent flow with the spawn in the gating role (FR2: spawning
    requires auto mode). A stale disable_auto_mode call resolves as the FR1
    refusal and the turn continues (the model has no auto-mode off-switch).
    """
    from app.desktop.studio_server.chat.runtime.interceptors import (
        INTERACTIVE_INTERCEPTORS,
    )

    return ConversationPolicy(
        approvals="gated",
        message_framing="none",
        one_shot=False,
        max_rounds=MAX_TOOL_ROUNDS,
        wall_clock_seconds=None,
        interceptors=INTERACTIVE_INTERCEPTORS,
        max_rounds_message=INTERACTIVE_MAX_ROUNDS_MESSAGE,
        # Interactive retry events carry no run_id.
        retry_events_carry_run_id=False,
    )


def auto_policy() -> ConversationPolicy:
    """Auto mode: auto approvals, side-note framing, not one-shot.

    Every client tool runs unattended; a graceful stop surfaces the
    boundary's tool calls for normal approval. Auto mode turns off only by
    user action (FR1): a stale disable_auto_mode call resolves as a refusal
    and the burst continues.
    """
    from app.desktop.studio_server.chat.runtime.interceptors import (
        AUTO_INTERCEPTORS,
    )

    return ConversationPolicy(
        approvals="auto",
        message_framing="side_note",
        one_shot=False,
        max_rounds=MAX_TOOL_ROUNDS,
        wall_clock_seconds=None,
        interceptors=AUTO_INTERCEPTORS,
        graceful_stop_surfaces_pending=True,
        max_rounds_message=INTERACTIVE_MAX_ROUNDS_MESSAGE,
    )


def subagent_policy(
    seed: SubAgentSeed,
    *,
    max_rounds: int | None = None,
    wall_clock_seconds: float | None = None,
) -> ConversationPolicy:
    """Sub-agent: auto approvals (consent granted at spawn), one-shot, child
    budgets, steer framing, depth-1 interception.

    Budgets not passed explicitly resolve from the env-var overrides, then
    the defaults.
    """
    from app.desktop.studio_server.chat.runtime.interceptors import (
        SUBAGENT_INTERCEPTORS,
    )

    return ConversationPolicy(
        approvals="auto",
        message_framing="steer",
        one_shot=True,
        max_rounds=(
            max_rounds
            if max_rounds is not None
            else _resolve_positive_int_env(
                SUBAGENT_MAX_ROUNDS_ENV_VAR, DEFAULT_SUBAGENT_MAX_ROUNDS
            )
        ),
        wall_clock_seconds=(
            wall_clock_seconds
            if wall_clock_seconds is not None
            else _resolve_positive_float_env(
                SUBAGENT_TIMEOUT_ENV_VAR, DEFAULT_SUBAGENT_TIMEOUT_SECONDS
            )
        ),
        interceptors=SUBAGENT_INTERCEPTORS,
        seed=seed,
        orchestration_depth=1,
        max_rounds_message=SUBAGENT_MAX_ROUNDS_MESSAGE,
    )
