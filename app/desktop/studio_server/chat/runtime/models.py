"""Data model of the unified conversation runtime.

One record shape + one state enum replace the two old lifecycle enums
(``AutoRunStatus`` and ``SubAgentStatus``) whose semantics overlapped but
differed:

- ``AutoRunStatus`` conflated two orthogonal facts — whether a burst is in
  flight (RUNNING/IDLE) and whether the conversation's auto-mode flag is on
  (RUNNING/IDLE = on, USER_STOPPED/USER_DISABLED = off).
- ``SubAgentStatus`` was a one-shot lifecycle (RUNNING → terminal).

Here those become two orthogonal axes on ``ConversationRecord``: ``state``
(one ``RunState`` enum for everyone) and ``auto_flag`` (the per-conversation
auto-mode flag, only meaningful for interactive/auto records). The old
mappings, preserved exactly:

- ``AutoRunStatus.RUNNING``      → state=RUNNING,  auto_flag=True
- ``AutoRunStatus.IDLE``         → state=IDLE,     auto_flag=True
- ``AutoRunStatus.USER_STOPPED`` → state=IDLE,     auto_flag=False, idle_reason="user_stopped"
- ``AutoRunStatus.USER_DISABLED``→ state=IDLE,     auto_flag=False, idle_reason="user_disabled"
- ``SubAgentStatus.*``           → the identical terminal ``RunState`` values.

Interactive/auto conversations never reach a terminal state — they idle
(functional spec §1). Terminal states exist for one-shot (sub-agent) runs
only.

Per-kind behavior is data: ``ConversationPolicy`` is a frozen dataclass built
by the ``interactive_policy`` / ``auto_policy`` / ``subagent_policy``
factories. If a kind ever needs a genuinely unique behavior it gets an
explicit policy field here — never a subclass (architecture §11).
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

from app.desktop.studio_server.chat.constants import MAX_TOOL_ROUNDS
from kiln_ai.adapters.model_adapters.stream_events import ToolInputAvailableEvent
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    # Import cycle avoidance only: interceptors.py imports models for the
    # context/result types, so the Interceptor callable type is quoted here.
    from app.desktop.studio_server.chat.runtime.interceptors import Interceptor

# Same id alphabet/length as the old auto (`ar_`) and sub-agent (`sa_`) ids so
# ids stay visually consistent across the migration.
_ID_ALPHABET = "abcdefghijklmnopqrstuvwxyz234567"
_ID_LENGTH = 12


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _mint_id(prefix: str) -> str:
    suffix = "".join(secrets.choice(_ID_ALPHABET) for _ in range(_ID_LENGTH))
    return f"{prefix}_{suffix}"


def new_session_id() -> str:
    """Mint a conversation session id (``cv_<base32>``).

    Phase 1 note: the architecture defines the session id as the upstream
    ``root_id`` "minted here or adopted from the first kiln_chat_trace's
    session meta". Adoption of the upstream root id lands with the API phases
    (2+); until then the supervisor mints a local handle so the runtime is
    fully testable in isolation.
    """
    return _mint_id("cv")


def new_message_id() -> str:
    """Mint an inbound-message id (``cm_<base32>``).

    Echoed to observers on the ``user-message`` event (same mechanism as the
    old auto ``am_`` ids) so a re-attaching client can dedupe a replayed echo
    against a message it already renders.
    """
    return _mint_id("cm")


def new_batch_id() -> str:
    """Mint a pending-approval batch id (``ab_<base32>``)."""
    return _mint_id("ab")


ConversationKind = Literal["interactive", "auto", "subagent"]


class RunState(str, Enum):
    """Lifecycle state of a conversation's run (functional spec §1).

    ``COMPLETED``/``FAILED``/``STOPPED``/``TIMEOUT`` are reachable only by
    one-shot (sub-agent) policies — they preserve ``SubAgentStatus``'s
    one-shot semantics 1:1. Interactive/auto conversations cycle
    IDLE ⇄ RUNNING ⇄ AWAITING_APPROVAL forever; "auto mode off" is the
    ``auto_flag`` axis, not a state.
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

        Deliberately mirrors ``SubAgentStatus.is_terminal``; an IDLE
        interactive/auto record is NOT terminal — it re-arms on the next
        message (old ``AutoRunStatus.IDLE`` semantics, Revision R1).
        """
        return self in _TERMINAL_STATES


_TERMINAL_STATES = frozenset(
    {RunState.COMPLETED, RunState.FAILED, RunState.STOPPED, RunState.TIMEOUT}
)


class ConversationRecord(BaseModel):
    """In-memory record of one live conversation (one per session id).

    Serializable snapshot of lifecycle state, shared between the engine
    (single writer while a run task is active — mirrors the old
    runner-owns-status contract), the supervisor (settle/publish/GC), and the
    browser-facing API (later phases).
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
    # the run loop, via EngineIO.on_trace (same contract as the old
    # record.current_trace_id updated only by the runner's on_trace callback).
    current_leaf_trace_id: str | None = None
    # Whole chain of leaves this conversation has touched — preserved from
    # both old registries; still needed INTERNALLY: the upstream sessions
    # LIST is leaf-keyed (each row's ``id`` is its current leaf), so the
    # desktop's history join resolves upstream rows to live records through
    # this chain. Adopt-by-key seeds the adopted key here too — it was a leaf
    # once (a root IS the first leaf) and a non-empty chain is what tells the
    # engine this record joined mid-conversation (root-stamp suppression).
    seen_trace_ids: list[str] = Field(default_factory=list)
    # Sub-agent lineage: the parent conversation's session id. Replaces the
    # old parent_key ("auto:<run_id>" / "trace:<leaf>") + parent-alias maps —
    # a stable id needs no alias chaining as leaves rotate.
    parent_session_id: str | None = None
    # Sub-agent identity (None for interactive/auto records).
    name: str | None = None
    agent_type: str | None = None
    # The per-conversation auto-mode flag (old AutoRunStatus.flag_on axis).
    # Flips between turns only — a flip mid-round is impossible because the
    # policy swap happens at run boundaries (architecture §2).
    auto_flag: bool = False
    # Why the run last went idle. Preserves the auto vocabulary exactly:
    # asked_user / done / error / max_rounds / armed while the flag is on;
    # user_stopped / user_disabled when the flag was just cleared (these were
    # the old auto-mode-off reasons — the off event now publishes as a
    # conversation-state change with this reason attached).
    idle_reason: str | None = None
    # One-shot kinds: the model's final plain-text turn (or its partial-output
    # base while running). The supervisor's settle path synthesizes the
    # status-note framing for FAILED/STOPPED/TIMEOUT, exactly like the old
    # SubAgentRegistry._final_report_for.
    final_report: str | None = None
    # True once the report reached the parent through any channel. Pins the
    # record against GC while False (old undelivered-report pinning).
    report_delivered: bool = False
    rounds_used: int = 0
    # Spawn-consent memory, keyed by session id simply by living on the
    # record (architecture §5: "consent memory ... the parent-alias maps
    # die"). Set when the conversation's first spawn_subagent executes
    # (i.e. was approved); later spawns skip the approval gate — the same
    # one-time downgrade `subagent_registry.mark_consented` provided.
    spawn_consent_granted: bool = False
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class InboundMessage(BaseModel):
    """A user message queued into a conversation (send-while-running, steer,
    idle re-arm, or an injected ``<subagent_report>`` frame for an auto-flag
    parent).

    Canonical copy of ``chat/auto/models.py``'s ``InboundMessage`` (that
    package is deleted in phase 3). Same contract: the supervisor echoes the
    message onto the bus at enqueue time; the engine drains WITHOUT
    re-echoing (echo-once — old CR Moderate 1).
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

    Canonical copy of ``chat/subagents/models.py``'s seed minus
    ``parent_key`` (lineage is the record's ``parent_session_id`` now).
    ``parent_trace_id`` still rides the ``agent`` block: the BACKEND resolves
    it into durable lineage on the child session's meta, so it stays part of
    the wire contract even though the desktop no longer keys anything on it.
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
    """The first user message of a child session — byte-identical to the old
    ``subagents/runner.py`` ``_kickoff_message`` (it is persisted in the
    child's trace, so the text is part of the protocol contract).

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
    """The child's first upstream POST — byte-identical port of
    ``SubAgentRunner._build_seed_body``.

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
    """The first upstream continuation body of an auto burst — byte-identical
    port of ``AutoChatRunner._build_seed_body`` (``chat/auto/runner.py``,
    deleted in phase 3), pinned end-to-end by the ``auto_seed_and_tool_round``
    golden fixture.

    Message order preserved from the old builder: any ``extra_messages``
    first (the manual/armed-first-send path carries the user's message), then
    the accepted ``enable_auto_mode`` call resolved as ``{"status":"enabled"}``,
    then one ``role:tool`` result per auto-executed sibling pending call. The
    caller (``ConversationSupervisor.enable_auto``) executes the siblings —
    the old runner awaited ``execute_tool_batch`` inline; splitting execution
    out keeps this builder pure/testable while the wire shape stays identical.

    ``auto_mode`` rides every continuation: the engine's ``{**body, ...}``
    rebuilds propagate it through the whole burst, so seeding it once here is
    enough. The upstream orchestrator reads it to phrase the auto-round-cap
    reminder for an absent user (act or report stuck, don't ask a question).

    Revision R2 preserved: when NEITHER continuation key is present (a
    brand-new conversation) the body omits both so the backend starts a fresh
    conversation and mints the first trace on the opening turn; the seed then
    carries the first user message in ``extra_messages`` so the opening turn
    is never empty.

    ``session_id`` (phase 6) is the resume-by-key continuation for records
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

    Canonical copy of ``chat/subagents/models.py``'s formatter (deleted in
    phase 2). Frame shape (tag, attribute names, body layout) is byte-
    identical — it is persisted in parent traces and parsed by the client's
    report-panel detection. The ``id`` attribute now carries the child's
    session id (``cv_``) instead of the old ``sa_`` registry id; both are
    opaque handles to the client, and the session id is the one that stays
    resolvable in the unified world.
    """
    body = record.final_report or "(no report produced)"
    return (
        f'<subagent_report id="{record.session_id}" '
        f'agent_type="{record.agent_type}" '
        f'status="{record.state.value}" '
        f'title="{_escape_attr(record.name or "")}">\n'
        f"{body}\n"
        f"</subagent_report>"
    )


def _escape_attr(value: str) -> str:
    return value.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


# What the engine's max-rounds backstop tells the user, per kind — both texts
# preserved verbatim (they surface in the UI and, for sub-agents, in the
# report note flow).
INTERACTIVE_MAX_ROUNDS_MESSAGE = (
    "Maximum tool rounds exceeded. Please start a new message."
)
SUBAGENT_MAX_ROUNDS_MESSAGE = (
    "Sub-agent exceeded its maximum tool rounds and was stopped. "
    "Its last output is reported as-is."
)

# Sub-agent budget knobs — same defaults and env vars as the old
# subagents/runner.py + subagents/registry.py resolvers, so operator
# overrides keep working across the migration.
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

    This is deliberately plain data + an interceptor chain — the whole point
    of the refactor is that the three loops differ only in these few knobs
    (architecture §2, §11).
    """

    # "gated": tool calls flagged requires_approval park the run for user
    # decisions (old interactive tool-calls-pending flow). "auto": every
    # client tool executes unattended (old auto/sub-agent runners).
    approvals: Literal["gated", "auto"]
    # How drained inbox messages are framed before riding a continuation.
    # Generalizes the architecture's `side_note_framing: bool`, because the
    # two unattended kinds use DIFFERENT reminder texts that must be preserved
    # verbatim: "side_note" = auto's mid-burst aside frame, "steer" = the
    # sub-agent steering frame, "none" = interactive (messages ride raw).
    message_framing: MessageFraming
    # One-shot lifecycle: a plain-text turn is COMPLETED (its text = the
    # report) and terminal states are reachable. Old SubAgentRunner shape.
    one_shot: bool
    max_rounds: int
    # Wall-clock cap the supervisor applies via asyncio.wait_for (one-shot
    # kinds only — old SubAgentRegistry._supervise timeout). None = no cap.
    wall_clock_seconds: float | None
    # Ordered signal-tool interception chain (see interceptors.py). Order is
    # PRIORITY: the engine scans the whole round's client events per
    # interceptor, so e.g. the interactive chain's consent interception
    # outranks everything behind it.
    interceptors: tuple["Interceptor", ...]
    # Child creation: when set, the engine builds the first POST from this
    # seed (agent block + kickoff message) and echoes the kickoff onto the
    # stream — old SubAgentRunner.run() preamble.
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
    # Old protocol detail preserved exactly: kiln-chat-retry events carried a
    # run_id on the auto/sub-agent streams but NOT on the interactive stream.
    # (The id becomes the session id in the unified vocabulary.)
    retry_events_carry_run_id: bool = True


class PendingApprovalBatch(BaseModel):
    """A parked approval round: the run task is suspended on ``decided`` while
    the user decides (architecture §2).

    ``items`` is the exact wire shape of today's ``tool-calls-pending`` event
    items (toolCallId/toolName/input/requiresApproval[/permission/
    approvalDescription]) so the approval box UX is unchanged.

    ``body`` / ``assistant_text`` / ``tool_input_events`` are the round
    context needed to rebuild the continuation. The engine holds the same
    context on its stack while parked, so these fields exist for the RECOVERY
    contract (architecture §2): the batch must be reconstructible from the
    persisted trace tail, which phase 4's restart/refresh recovery builds on.
    """

    # asyncio.Event isn't a pydantic type; this record is in-memory only.
    model_config = ConfigDict(arbitrary_types_allowed=True)

    batch_id: str = Field(default_factory=new_batch_id)
    items: list[dict[str, Any]]
    body: dict[str, Any]
    assistant_text: str
    tool_input_events: list[ToolInputAvailableEvent]
    # Pre-answered calls riding the batch WITHOUT being user decisions
    # (tool_call_id → result JSON). Phase-4 recovery: a rehydrated trace tail
    # can carry unanswered SIGNAL calls (enable/disable_auto_mode) next to
    # real client calls — signals are never executed as tools, so the resume
    # run pre-answers them purely so the persisted trace has no dangling tool
    # call: a pending enable_auto_mode resolves as {"status": "declined"}
    # (its consent dialog died with the restart, mirroring the decline flow);
    # a stale pending disable_auto_mode resolves with the FR1 refusal shape
    # (DISABLE_AUTO_MODE_STALE_RESULT — the model has no off-switch). Empty
    # for live batches (the interceptor chain answers signals before a park
    # can ever include one).
    preresolved_results: dict[str, str] = Field(default_factory=dict)
    # Set by the supervisor's decide() exactly once; the engine wakes, reads
    # `decisions`, and resumes. Partial decision sets are rejected upstream of
    # this model (one batch, one decision set — matches today's UI).
    decided: asyncio.Event = Field(default_factory=asyncio.Event)
    decisions: dict[str, bool] | None = None


# ── Kind → policy factories (architecture §2 mapping table) ─────────────────


def interactive_policy() -> ConversationPolicy:
    """Interactive: gated approvals, not one-shot, no framing, MAX_TOOL_ROUNDS.

    Preserves ``ChatStreamSession.stream()``'s shape: approval-requiring tools
    park the run; enable_auto_mode surfaces the consent control event. A stale
    disable_auto_mode call resolves as the FR1 refusal and the turn continues
    (the model has no auto-mode off-switch).
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
        # Old interactive retry events carried no run_id.
        retry_events_carry_run_id=False,
    )


def auto_policy() -> ConversationPolicy:
    """Auto mode: auto approvals, side-note framing, not one-shot.

    Preserves ``AutoChatRunner``'s shape: every client tool runs unattended;
    a graceful stop surfaces the boundary's tool calls for normal approval.
    Auto mode turns off only by user action (FR1): a stale disable_auto_mode
    call resolves as a refusal and the burst continues.
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

    Preserves ``SubAgentRunner``'s shape, including the env-var budget
    overrides.
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
