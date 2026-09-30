"""Unified conversation runtime.

This package is the single home for every desktop-owned chat conversation —
interactive turns, auto-mode bursts, and sub-agent runs — built from:

- ONE data model (``models.ConversationRecord`` + ``models.RunState``),
- ONE event bus + replay buffer (``bus.ByteEventBus``),
- ONE round loop (``engine.ConversationEngine``), where the per-kind
  differences are frozen ``models.ConversationPolicy`` data plus a small
  ``interceptors`` chain — never subclasses,
- ONE lifecycle owner (``supervisor.ConversationSupervisor``) with a single
  settle path (including the cancel-before-first-run backstop),
- ONE control-event vocabulary (``sse.format_conversation_state``),
- ONE browser surface (``api.connect_conversations_api`` under
  ``/api/conversations``).

Interactive conversations are created/adopted via ``POST /api/conversations``
(kind="interactive"); each turn is a supervised task started by
``/{sid}/messages``; approvals PARK as batches (``/{sid}/approvals`` +
``.../decisions``) and are recoverable from the persisted trace tail after a
desktop restart. Auto mode is a policy + kind flip on the SAME record, in
both directions (consent accept / manual enable, and stop / disable):
``supervisor.enable_auto`` creates or flips a ``kind="auto"`` record whose
bursts run under ``auto_policy()``; consent decline goes through
``/{sid}/auto``.

Sub-agents are spawned by ``chat/orchestration.py`` (the orchestration tool
executor) onto the ``supervisor.conversation_supervisor`` singleton and are
observed via ``/api/conversations`` like any other conversation.

Helper strings that are persisted in traces are byte-pinned in
``test_interceptors.py``.

The per-round upstream mechanics live in ``chat/stream_session.py``
(``iter_upstream_round``, ``iter_round_with_retries``, ``execute_tool_batch``,
``_build_openai_tool_continuation`` and the pending/consent/retry SSE
formatters). Every kind shares them, so the upstream protocol cannot drift.

The upstream protocol contract lives in ``golden_scenarios.py`` +
``golden/*.json`` + ``test_golden_protocol.py``: the exact upstream
request-body sequences the engine must produce for scripted scenarios
(compared as parsed JSON, so key order is irrelevant).
"""

from .api import ConversationItem, connect_conversations_api
from .bus import BroadcastBus, ByteEventBus
from .engine import ConversationEngine, EngineIO
from .models import (
    ConversationPolicy,
    ConversationRecord,
    InboundMessage,
    PendingApprovalBatch,
    RunState,
    SubAgentSeed,
    auto_policy,
    interactive_policy,
    subagent_policy,
)
from .supervisor import (
    ConversationCapError,
    ConversationSupervisor,
    conversation_supervisor,
)

__all__ = [
    "BroadcastBus",
    "ByteEventBus",
    "ConversationCapError",
    "ConversationEngine",
    "ConversationItem",
    "ConversationPolicy",
    "ConversationRecord",
    "ConversationSupervisor",
    "EngineIO",
    "InboundMessage",
    "PendingApprovalBatch",
    "RunState",
    "SubAgentSeed",
    "auto_policy",
    "connect_conversations_api",
    "conversation_supervisor",
    "interactive_policy",
    "subagent_policy",
]
