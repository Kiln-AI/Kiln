"""Signal-tool interception for the unified engine (architecture §4).

Some "tool calls" are signals to the desktop, never tools to execute:
``enable_auto_mode`` asks for consent in an interactive conversation and is a
no-op while auto mode is already on. The logic lives in ONE ordered chain of
small functions carried on the policy, so a signal tool registers once for
every kind.

Every intercepted call still gets ANSWERED (a result JSON fed back on the
continuation, or a control event that ends the turn) — the provider requires
every tool call be resolved before the next user message, so leaving one
dangling corrupts the persisted trace.

``disable_auto_mode`` is deliberately NOT a real signal anymore (assistant
autonomy lifecycle FR1): auto mode turns off only by user action, and the
upstream toolset does not offer the tool. A call can still arrive (a
hallucinated call, or an older server), so both chains end in a stale-call
backstop that refuses it without side effects.

Chain order is PRIORITY: the engine applies the first non-pass result whose
kind takes over the round (``control``); plain ``resolve`` results just
pre-answer individual calls and the round proceeds normally. See
``engine.py`` for the exact application semantics.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Literal

from kiln_ai.adapters.model_adapters.stream_events import ToolInputAvailableEvent
from kiln_ai.tools.built_in_tools.disable_auto_mode_tool import (
    DISABLE_AUTO_MODE_TOOL_NAME,
)
from kiln_ai.tools.built_in_tools.enable_auto_mode_tool import (
    ENABLE_AUTO_MODE_TOOL_NAME,
)

from app.desktop.studio_server.chat.stream_session import (
    _format_consent_required_sse,
)

from .models import ConversationPolicy, ConversationRecord

# The tool result for an enable_auto_mode call made WHILE auto mode is already
# on (i.e. during an auto burst). enable_auto_mode is a signal, never executed
# — but the toolset is intentionally stable (both auto-mode tools are always
# exposed so the prompt cache survives the whole conversation), so the model
# can still call it redundantly. Resolve it as a no-op "already enabled"
# instead of letting it fall through to execute_tool (which would return an
# "Unknown tool name" error), and continue the burst. Byte-pinned in
# test_interceptors.py because it is persisted in traces.
ENABLE_AUTO_MODE_RESULT = json.dumps(
    {"status": "enabled", "detail": "Auto mode is already enabled."},
    ensure_ascii=False,
)

# The refusal result for a STALE disable_auto_mode call (FR1). The tool is not
# offered upstream — auto mode turns off only by user action — but a call can
# still arrive (a hallucinated call, or an older server). Refused without side
# effects: no flag clear, the burst/turn continues. The message doubles
# as the model's instruction when a user asks it to stop auto mode: direct
# them to the Stop button. Byte-pinned in test_interceptors.py because it is
# persisted in traces.
DISABLE_AUTO_MODE_STALE_RESULT = json.dumps(
    {
        "status": "not_available",
        "message": "Auto mode can only be turned off by the user (Stop button).",
    },
    ensure_ascii=False,
)


@dataclass
class InterceptContext:
    """Round context an interceptor may need beyond the single event.

    ``client_events`` carries the round's full client-tool batch because the
    consent interception is batch-aware: its control event lists sibling
    calls, so accept/decline can resolve every tool_call_id the backend waits
    on. Consent accept/decline is keyed by session id and the record's own
    leaf is authoritative (functional spec §4), so no trace id rides here.
    """

    record: ConversationRecord
    policy: ConversationPolicy
    client_events: list[ToolInputAvailableEvent]


# How the engine must apply an interception:
# - "resolve": answer this one call with result_json; the round otherwise
#   proceeds normally (approval gate, execution of the rest). Examples:
#   auto's enable no-op, the stale disable backstop.
# - "control": emit control_bytes and end the turn WITHOUT answering the call
#   here — resolution happens out-of-band (the consent accept/decline
#   endpoints answer the gating call). Interactive enable_auto_mode consent.
InterceptKind = Literal["resolve", "control"]


@dataclass(frozen=True)
class InterceptResult:
    kind: InterceptKind
    result_json: str | None = None
    control_bytes: bytes | None = None


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
            trigger="enable_auto_mode",
            gating_tool_call_id=event.toolCallId,
            reason=event.input.get("reason"),
            siblings=siblings,
        ),
    )


def intercept_disable_auto_mode_stale(
    event: ToolInputAvailableEvent, ctx: InterceptContext
) -> InterceptResult | None:
    """``disable_auto_mode`` is not offered upstream (FR1); a call can still
    arrive. Refuse without side effects: no flag clear, the burst/turn
    continues."""
    if event.toolName != DISABLE_AUTO_MODE_TOOL_NAME:
        return None
    return InterceptResult(kind="resolve", result_json=DISABLE_AUTO_MODE_STALE_RESULT)


def intercept_enable_auto_mode_noop(
    event: ToolInputAvailableEvent, ctx: InterceptContext
) -> InterceptResult | None:
    """Auto-mode ``enable_auto_mode`` while already on → "already enabled"
    no-op resolve; the burst continues (see ENABLE_AUTO_MODE_RESULT above)."""
    if event.toolName != ENABLE_AUTO_MODE_TOOL_NAME:
        return None
    return InterceptResult(kind="resolve", result_json=ENABLE_AUTO_MODE_RESULT)


# Per-kind chains, in priority order (see module docstring). The consent
# interception leads the interactive chain so the consent UI outranks the
# approval gate; both chains end in the stale-disable backstop.
INTERACTIVE_INTERCEPTORS: tuple[Interceptor, ...] = (
    intercept_enable_auto_mode_consent,
    intercept_disable_auto_mode_stale,
)
AUTO_INTERCEPTORS: tuple[Interceptor, ...] = (
    intercept_enable_auto_mode_noop,
    intercept_disable_auto_mode_stale,
)
