"""Unified conversation runtime (assistant_unified_runtime, phase 1).

This package is the future single home for every desktop-owned chat
conversation — interactive, auto mode, and sub-agents — replacing the three
parallel loops (``ChatStreamSession.stream()``, ``AutoChatRunner``,
``SubAgentRunner``) and their two registries with:

- ONE data model (``models.ConversationRecord`` + ``models.RunState``),
- ONE event bus + replay buffer (``bus.ByteEventBus``),
- ONE round loop (``engine.ConversationEngine``), where the per-kind
  differences are frozen ``models.ConversationPolicy`` data plus a small
  ``interceptors`` chain — never subclasses,
- ONE lifecycle owner (``supervisor.ConversationSupervisor``) with a single
  settle path (including the cancel-before-first-run backstop),
- ONE control-event vocabulary (``sse.format_conversation_state``).

IMPORTANT (phase 1): NOTHING here is wired into the running app. The old
code paths (``chat/routes.py``, ``chat/auto/``, ``chat/subagents/``) remain
untouched and authoritative. This package must therefore never import from
``chat/auto/`` or ``chat/subagents/`` (both are deleted as later phases port
their kinds); the few helpers it needs from those doomed packages exist here
as canonical copies, each annotated with the old location it preserves.

What IS shared with the old world — deliberately, so the upstream protocol
cannot drift — are the round primitives in ``chat/stream_session.py``
(``iter_upstream_round``, ``iter_round_with_retries``, ``execute_tool_batch``,
``_build_openai_tool_continuation`` and the pending/consent/retry SSE
formatters). Those survive every phase.

The behavior contract that later phases must keep passing lives in
``golden_scenarios.py`` + ``golden/*.json`` + ``test_golden_protocol.py``:
the exact upstream request-body sequences the OLD loops produce for scripted
scenarios, which the new engine must reproduce byte-for-byte (compared as
parsed JSON, so key order is irrelevant).
"""

from .bus import ByteEventBus
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
from .supervisor import ConversationCapError, ConversationSupervisor

__all__ = [
    "ByteEventBus",
    "ConversationCapError",
    "ConversationEngine",
    "ConversationPolicy",
    "ConversationRecord",
    "ConversationSupervisor",
    "EngineIO",
    "InboundMessage",
    "PendingApprovalBatch",
    "RunState",
    "SubAgentSeed",
    "auto_policy",
    "interactive_policy",
    "subagent_policy",
]
