"""Unified conversation runtime.

This package is the single home for every desktop-owned chat conversation —
interactive turns and auto-mode bursts — built from:

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
both directions (consent accept / manual enable, and stop / disable).

The per-round upstream mechanics live in ``chat/stream_session.py`` (``iter_upstream_round``,
``iter_round_with_retries``, ``execute_tool_batch``,
``_build_openai_tool_continuation`` and the pending/consent/retry SSE
formatters).

The upstream protocol contract lives in ``golden_scenarios.py`` +
``golden/*.json`` + ``test_golden_protocol.py``: the exact upstream
request-body sequences the engine must produce for scripted scenarios
(compared as parsed JSON, so key order is irrelevant).
"""

from .api import ConversationItem, connect_conversations_api
from .bus import ByteEventBus
from .engine import ConversationEngine, EngineIO
from .models import (
    ConversationPolicy,
    ConversationRecord,
    InboundMessage,
    PendingApprovalBatch,
    RunState,
    auto_policy,
    interactive_policy,
)
from .supervisor import (
    ConversationCapError,
    ConversationSupervisor,
    conversation_supervisor,
)

__all__ = [
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
    "auto_policy",
    "connect_conversations_api",
    "conversation_supervisor",
    "interactive_policy",
]
