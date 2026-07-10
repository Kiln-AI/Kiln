"""Signal-tool interception for the unified engine (architecture §4).

Some "tool calls" are signals to the desktop, never tools to execute:
``enable_auto_mode`` / ``disable_auto_mode`` flip conversation policy, and
the sub-agent orchestration tools must be rejected at depth ≥ 1. Today this
logic is scattered across the three loops with subtly different shapes; here
it becomes ONE ordered chain of small functions carried on the policy, so a
future signal tool registers once for every kind.

Every intercepted call still gets ANSWERED (a result JSON fed back on the
continuation, or a control event that ends the turn) — the provider requires
every tool call be resolved before the next user message, so leaving one
dangling corrupts the persisted trace. That invariant is why the auto-mode
disable interception sends one final "resolving continuation" upstream (old
``AutoChatRunner._resolve_disable``, CR Moderate 3).

Chain order is PRIORITY, matching the old code's scan order exactly:

- interactive scanned ``enable_auto_mode`` (consent) BEFORE
  ``disable_auto_mode`` (``ChatStreamSession.stream()``);
- auto scanned ``disable_auto_mode`` (terminal) first — its redundant
  ``enable_auto_mode`` no-op was resolved with the ordinary batch.

The engine applies the first non-pass result whose kind takes over the round
(``control`` / ``resolve_terminal`` / ``resolve_immediate``); plain
``resolve`` results just pre-answer individual calls and the round proceeds
normally. See ``engine.py`` for the exact application semantics.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Literal

from app.desktop.studio_server.chat.stream_session import (
    DISABLE_AUTO_MODE_RESULT,
    _format_consent_required_sse,
)
from kiln_ai.adapters.model_adapters.stream_events import ToolInputAvailableEvent
from kiln_ai.tools.built_in_tools.disable_auto_mode_tool import (
    DISABLE_AUTO_MODE_TOOL_NAME,
)
from kiln_ai.tools.built_in_tools.enable_auto_mode_tool import (
    ENABLE_AUTO_MODE_TOOL_NAME,
)

from .models import ConversationPolicy, ConversationRecord

# The tool result for an enable_auto_mode call made WHILE auto mode is already
# on (i.e. during an auto burst). enable_auto_mode is a signal, never executed
# — but the toolset is intentionally stable (both auto-mode tools are always
# exposed so the prompt cache survives the whole conversation), so the model
# can still call it redundantly. Resolve it as a no-op "already enabled"
# instead of letting it fall through to execute_tool (which would return an
# "Unknown tool name" error), and continue the burst.
# Canonical (and only) home since phase 3 deleted chat/auto/runner.py's
# ENABLE_AUTO_MODE_RESULT; byte-pinned in test_interceptors.py because it is
# persisted in traces.
ENABLE_AUTO_MODE_RESULT = json.dumps(
    {"status": "enabled", "detail": "Auto mode is already enabled."},
    ensure_ascii=False,
)

# Tool results for calls a child must never act on. Orchestration calls are
# rejected (depth 1: sub-agents cannot manage sub-agents) and the auto-mode
# signals are no-ops (the child loop is already unattended). The backend
# doesn't wire these tools into child agent types, so these are defense in
# depth against a model hallucinating the calls.
# Canonical copies of chat/subagents/runner.py's constants (deleted in
# phase 2); byte-identical because they are persisted in traces.
DEPTH_LIMIT_RESULT = json.dumps(
    {"error": "Sub-agents cannot spawn or manage sub-agents."}, ensure_ascii=False
)
AUTO_MODE_NOOP_RESULT = json.dumps(
    {
        "status": "noop",
        "detail": "This session already runs autonomously; auto mode does not apply.",
    },
    ensure_ascii=False,
)

# Orchestration tool names — the CANONICAL home since phase 2 (the executor
# in chat/orchestration.py imports them from here; the old
# chat/subagents/orchestration.py copy is deleted). They live in this module
# rather than next to the executor because the import chain runs
# orchestration → supervisor → engine → interceptors: defining them at the
# leaf keeps the chain acyclic. Names must match the backend's
# client-visible tool schemas (kiln_server tools/subagent_tools.py) — they
# are how execute_tool_batch recognizes a call that needs conversation
# identity instead of the kiln_ai tool registry.
SPAWN_SUBAGENT_TOOL_NAME = "spawn_subagent"
GET_SUBAGENT_STATUS_TOOL_NAME = "get_subagent_status"
WAIT_FOR_SUBAGENTS_TOOL_NAME = "wait_for_subagents"
STOP_SUBAGENT_TOOL_NAME = "stop_subagent"
ORCHESTRATION_TOOL_NAMES: frozenset[str] = frozenset(
    [
        SPAWN_SUBAGENT_TOOL_NAME,
        GET_SUBAGENT_STATUS_TOOL_NAME,
        WAIT_FOR_SUBAGENTS_TOOL_NAME,
        STOP_SUBAGENT_TOOL_NAME,
    ]
)


@dataclass
class InterceptContext:
    """Round context an interceptor may need beyond the single event.

    ``client_events`` carries the round's full client-tool batch because two
    interceptions are batch-aware: the consent control event lists sibling
    calls (so accept/decline can resolve every tool_call_id the backend waits
    on), and the terminal/immediate disable paths execute siblings alongside
    the resolved signal. (The round's ``trace_id`` used to ride here purely
    so the consent event could carry it to the browser; phase 5 removed it —
    consent accept/decline is keyed by session id and the record's own leaf
    is authoritative, functional spec §4.)
    """

    record: ConversationRecord
    policy: ConversationPolicy
    client_events: list[ToolInputAvailableEvent]


# How the engine must apply an interception:
# - "resolve": answer this one call with result_json; the round otherwise
#   proceeds normally (approval gate, execution of the rest). Old examples:
#   auto's enable no-op, the child depth guard / auto-signal noops.
# - "resolve_immediate": answer this call AND resolve the whole batch NOW,
#   bypassing the approval park — siblings run through the per-tool gate with
#   no decisions, so approval-requiring siblings are DENIED rather than run
#   without consent; the loop then continues. This is exactly the old
#   interactive disable_auto_mode branch (ChatStreamSession.stream()).
# - "resolve_terminal": answer this call, auto-execute siblings, send ONE
#   final resolving continuation upstream (so the persisted trace has no
#   dangling tool call), forward its reply, then end the run. This is the old
#   AutoChatRunner._resolve_disable terminal round.
# - "control": emit control_bytes and end the turn WITHOUT answering the call
#   here — resolution happens out-of-band (the consent accept/decline
#   endpoints answer the enable call). Old interactive enable_auto_mode.
InterceptKind = Literal["resolve", "resolve_immediate", "resolve_terminal", "control"]


@dataclass(frozen=True)
class InterceptResult:
    kind: InterceptKind
    result_json: str | None = None
    control_bytes: bytes | None = None
    # Clear the conversation's auto-mode flag as part of applying this result
    # (both disable interceptions). The engine mutates the record; the
    # supervisor publishes the flag-off conversation-state at settle — the
    # same split as the old runner-status → registry-publish flow.
    clear_auto_flag: bool = False


# An interceptor inspects one event (with round context) and either passes
# (None) or takes an InterceptResult. Interceptors are pure decisions — all
# side effects (emitting, executing, mutating the record) belong to the
# engine, so the chain stays trivially testable.
Interceptor = Callable[
    [ToolInputAvailableEvent, InterceptContext], InterceptResult | None
]


def intercept_enable_auto_mode_consent(
    event: ToolInputAvailableEvent, ctx: InterceptContext
) -> InterceptResult | None:
    """Interactive ``enable_auto_mode``: surface a consent request and end the
    turn WITHOUT executing it. Accept/decline is handled out-of-band by the
    auto-mode endpoints (which resolve the call and flip the policy). Must
    outrank the approval gate so the consent UI takes precedence — hence its
    position at the head of the interactive chain.

    ``sibling_tool_calls`` carries any other client tool calls from the same
    round so the accept/decline paths can resolve every ``tool_call_id`` the
    backend is waiting on. The model is instructed to call ``enable_auto_mode``
    alone, so this is normally empty.
    """
    if event.toolName != ENABLE_AUTO_MODE_TOOL_NAME:
        return None
    siblings = [e for e in ctx.client_events if e is not event]
    return InterceptResult(
        kind="control",
        control_bytes=_format_consent_required_sse(
            enable_tool_call_id=event.toolCallId,
            reason=event.input.get("reason"),
            siblings=siblings,
        ),
    )


def intercept_disable_auto_mode_interactive(
    event: ToolInputAvailableEvent, ctx: InterceptContext
) -> InterceptResult | None:
    """Interactive ``disable_auto_mode``: never execute it. Clear the
    conversation's auto-mode flag, resolve the call as ``{"status":"disabled"}``,
    and CONTINUE streaming interactively so the backend proceeds without auto
    mode. Siblings in the same turn go through the normal per-tool approval
    verdict with no decisions — an approval-requiring sibling is denied here
    rather than run without consent (auto-approval is the auto policy's job,
    not this path's). Old ChatStreamSession.stream() disable branch."""
    if event.toolName != DISABLE_AUTO_MODE_TOOL_NAME:
        return None
    # Cascade status (phase 4, resolving the phase-1/3 TODOs that lived
    # here): the interceptor itself stays a pure decision — the ENGINE clears
    # the record's flag and, iff the flag was actually on, awaits
    # ``io.on_auto_flag_cleared``, which the supervisor wires to the full old
    # disable cascade (publish the flag-off state immediately, swap the
    # record back to its interactive life, stop_children) — the same
    # semantics the old world reached via
    # ChatStreamSession._clear_auto_mode_flag → disable_auto_for_trace.
    return InterceptResult(
        kind="resolve_immediate",
        result_json=DISABLE_AUTO_MODE_RESULT,
        clear_auto_flag=True,
    )


def intercept_disable_auto_mode_terminal(
    event: ToolInputAvailableEvent, ctx: InterceptContext
) -> InterceptResult | None:
    """Auto-mode ``disable_auto_mode``: never execute it. Resolve as disabled,
    clear the flag, and make this the TERMINAL round — the engine sends one
    final resolving continuation so the backend persists a clean snapshot (no
    dangling tool call), forwards its reply, and ends the burst. Old
    ``AutoChatRunner`` disable interception + ``_resolve_disable``."""
    if event.toolName != DISABLE_AUTO_MODE_TOOL_NAME:
        return None
    return InterceptResult(
        kind="resolve_terminal",
        result_json=DISABLE_AUTO_MODE_RESULT,
        clear_auto_flag=True,
    )


def intercept_enable_auto_mode_noop(
    event: ToolInputAvailableEvent, ctx: InterceptContext
) -> InterceptResult | None:
    """Auto-mode ``enable_auto_mode`` while already on → "already enabled"
    no-op resolve; the burst continues (see ENABLE_AUTO_MODE_RESULT above)."""
    if event.toolName != ENABLE_AUTO_MODE_TOOL_NAME:
        return None
    return InterceptResult(kind="resolve", result_json=ENABLE_AUTO_MODE_RESULT)


def intercept_orchestration_depth_guard(
    event: ToolInputAvailableEvent, ctx: InterceptContext
) -> InterceptResult | None:
    """Depth ≥ 1: orchestration calls are rejected before dispatch — sub-agents
    cannot spawn or manage sub-agents. Old SubAgentRunner interception."""
    if ctx.policy.orchestration_depth < 1:
        return None
    if event.toolName not in ORCHESTRATION_TOOL_NAMES:
        return None
    return InterceptResult(kind="resolve", result_json=DEPTH_LIMIT_RESULT)


def intercept_auto_mode_signals_noop(
    event: ToolInputAvailableEvent, ctx: InterceptContext
) -> InterceptResult | None:
    """Child loop: BOTH auto-mode signals are no-ops — the session already
    runs autonomously. Old SubAgentRunner interception."""
    if event.toolName not in (ENABLE_AUTO_MODE_TOOL_NAME, DISABLE_AUTO_MODE_TOOL_NAME):
        return None
    return InterceptResult(kind="resolve", result_json=AUTO_MODE_NOOP_RESULT)


# Per-kind chains, in the old scan-priority order (see module docstring).
INTERACTIVE_INTERCEPTORS: tuple[Interceptor, ...] = (
    intercept_enable_auto_mode_consent,
    intercept_disable_auto_mode_interactive,
)
AUTO_INTERCEPTORS: tuple[Interceptor, ...] = (
    intercept_disable_auto_mode_terminal,
    intercept_enable_auto_mode_noop,
)
SUBAGENT_INTERCEPTORS: tuple[Interceptor, ...] = (
    intercept_orchestration_depth_guard,
    intercept_auto_mode_signals_noop,
)
