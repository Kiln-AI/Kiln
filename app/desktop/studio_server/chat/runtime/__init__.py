"""Unified conversation runtime (assistant_unified_runtime, phases 1-3).

This package is the single home for every desktop-owned chat conversation —
interactive, auto mode, and sub-agents — replacing the three parallel loops
(``ChatStreamSession.stream()``, ``AutoChatRunner``, ``SubAgentRunner``) and
their two registries with:

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

Wiring status by phase:

- Phase 1 built everything below fully tested but UNWIRED.
- Phase 2: SUB-AGENTS run here for real — spawned by
  ``chat/orchestration.py`` (the relocated tool executor) onto the
  ``supervisor.conversation_supervisor`` singleton, observed via
  ``/api/conversations``. ``chat/subagents/`` was deleted.
- Phase 3: AUTO conversations run here too — consent accept / manual enable
  creates (or flips) a ``kind="auto"`` record (``supervisor.enable_auto``)
  whose bursts run on the engine under ``auto_policy()``; the browser
  surface re-homed under ``/api/conversations``. ``chat/auto/`` was deleted.
- Phase 4 (current): INTERACTIVE conversations run here — created/adopted
  via ``POST /api/conversations`` (kind="interactive"), each turn a
  supervised task started by ``/{sid}/messages``, approvals PARKED as
  batches (``/{sid}/approvals`` + ``.../decisions``) instead of ending the
  stream, consent decline folded into ``/{sid}/auto``, and pending
  approvals recoverable from the persisted trace tail after a desktop
  restart. The old interactive surface (``POST /api/chat``,
  ``/api/chat/execute-tools``, ``ChatStreamSession``) and the last
  parent-identity bridge (``ParentConversationIndex``) were deleted; the
  auto flip now swaps policy + kind on the SAME record in both directions.

The helpers this package needed from the doomed old packages exist here as
canonical copies, each annotated with the old location it preserves (and
byte-pinned in ``test_interceptors.py`` where the strings are persisted in
traces).

What IS shared across every phase — deliberately, so the upstream protocol
cannot drift — are the round primitives in ``chat/stream_session.py``
(``iter_upstream_round``, ``iter_round_with_retries``, ``execute_tool_batch``,
``_build_openai_tool_continuation`` and the pending/consent/retry SSE
formatters). Those survive every phase.

The behavior contract that later phases must keep passing lives in
``golden_scenarios.py`` + ``golden/*.json`` + ``test_golden_protocol.py``:
the exact upstream request-body sequences the OLD loops produce(d) for
scripted scenarios, which the new engine must reproduce byte-for-byte
(compared as parsed JSON, so key order is irrelevant). Fixtures whose old
loop is deleted remain the durable contract.
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
