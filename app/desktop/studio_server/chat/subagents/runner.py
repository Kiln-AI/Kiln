from __future__ import annotations

import json
import logging
import os
from typing import Any, Awaitable, Callable

import httpx
from app.desktop.studio_server.chat.auto.models import InboundMessage
from app.desktop.studio_server.chat.constants import CHAT_TIMEOUT
from app.desktop.studio_server.chat.stream_session import (
    RetryRoundResult,
    ToolCallInfo,
    _build_openai_tool_continuation,
    execute_tool_batch,
    iter_round_with_retries,
)
from app.desktop.studio_server.chat.tool_metadata import tool_input_executor_is_server
from kiln_ai.tools.built_in_tools.disable_auto_mode_tool import (
    DISABLE_AUTO_MODE_TOOL_NAME,
)
from kiln_ai.tools.built_in_tools.enable_auto_mode_tool import (
    ENABLE_AUTO_MODE_TOOL_NAME,
)

from .models import SubAgentSeed, SubAgentStatus
from .sse import (
    format_error,
    format_tool_exec_end,
    format_tool_exec_start,
    format_tool_output,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_ROUNDS = 50
MAX_ROUNDS_ENV_VAR = "KILN_CHAT_SUBAGENT_MAX_ROUNDS"

MAX_ROUNDS_MESSAGE = (
    "Sub-agent exceeded its maximum tool rounds and was stopped. "
    "Its last output is reported as-is."
)

# The canned first user message of a child session. The real job lives in the
# seed prompt (appended to the agent task's instruction backend-side); this just
# opens the turn — the backend rejects empty message lists. The name rides along
# because the session-list title derives from the first user message.
def _kickoff_message(name: str) -> str:
    return (
        f"Begin work on: {name}. Follow the operator briefing in your "
        "instructions and end with your final report."
    )


# Framing for a user message injected into a RUNNING child from the UI. Without
# it the model reads the message as a fresh conversational turn, replies in
# plain text, and that text turn would end the run as COMPLETED with the reply
# as its "report".
_STEER_REMINDER = (
    "<system-reminder>"
    "This message was sent by the user overseeing your background run. "
    "Incorporate the guidance and continue working in the same turn — do not "
    "end your turn just to reply. End only when your job (as adjusted) is done, "
    "with your final report."
    "</system-reminder>"
)


def _steer_message(msg: InboundMessage) -> dict[str, Any]:
    base = msg.as_chat_message()
    content = base.get("content") or ""
    return {**base, "content": f"{_STEER_REMINDER}\n\n{content}"}


# Tool results for calls a child must never act on. Orchestration calls are
# rejected (depth 1: sub-agents cannot manage sub-agents) and the auto-mode
# signals are no-ops (the child loop is already unattended). The backend doesn't
# wire these tools into child agent types, so these are defense in depth against
# a model hallucinating the calls.
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


def resolve_max_rounds(explicit: int | None = None) -> int:
    if explicit is not None:
        return explicit
    raw = os.environ.get(MAX_ROUNDS_ENV_VAR)
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return DEFAULT_MAX_ROUNDS


EmitCallback = Callable[[bytes], None]
OnTraceCallback = Callable[[str], Awaitable[None]]
DrainInboundCallback = Callable[[], list[InboundMessage]]


class SubAgentRunner:
    """Drives one sub-agent chat session autonomously.

    A slimmer sibling of ``AutoChatRunner`` sharing the same round primitives
    (``iter_round_with_retries``, ``execute_tool_batch``,
    ``_build_openai_tool_continuation``), differing in shape: one-shot lifecycle
    (a plain-text turn is the natural COMPLETED end, never an idle re-arm), an
    ``agent`` block on the first POST (agent type + seed prompt + lineage), and
    interception of orchestration/auto-mode calls instead of consent flows.

    The runner sets ``self.status`` and ``self.final_report`` on a natural end;
    the supervising registry task handles cancellation/timeout/exception and
    publishes the terminal status event.
    """

    def __init__(
        self,
        subagent_id: str,
        seed: SubAgentSeed,
        upstream_url: str,
        headers: dict[str, str],
        emit: EmitCallback,
        on_trace: OnTraceCallback | None = None,
        drain_inbound: DrainInboundCallback | None = None,
        orchestration_tool_names: frozenset[str] = frozenset(),
        max_rounds: int | None = None,
    ) -> None:
        self.subagent_id = subagent_id
        self._seed = seed
        self._url = upstream_url
        self._headers = headers
        self._emit = emit
        self._on_trace = on_trace
        self._drain_inbound = drain_inbound
        self._orchestration_tool_names = orchestration_tool_names
        self._max_rounds = resolve_max_rounds(max_rounds)
        self.status: SubAgentStatus = SubAgentStatus.RUNNING
        # Last assistant text seen — becomes the report (or its base) on any end.
        self.final_report: str | None = None
        self.rounds_used: int = 0
        self.stop_requested: bool = False

    def request_stop(self) -> None:
        self.stop_requested = True

    async def run(self) -> None:
        body = self._build_seed_body()
        trace_id_for_error: str | None = None
        async with httpx.AsyncClient(timeout=CHAT_TIMEOUT) as client:
            for _ in range(self._max_rounds):
                self.rounds_used += 1
                result = RetryRoundResult()
                async for payload in iter_round_with_retries(
                    client,
                    self._url,
                    self._headers,
                    body,
                    trace_id_for_error,
                    result,
                    run_id=self.subagent_id,
                    stop_requested=lambda: self.stop_requested,
                ):
                    self._emit(payload)

                round_state = result.round_state
                if round_state is not None:
                    trace_id_for_error = round_state.trace_id_for_error
                if result.status == "stopped":
                    self.status = SubAgentStatus.STOPPED
                    return
                if result.status != "ok" or round_state is None:
                    # Retries exhausted or non-retryable: the helper already
                    # emitted the error SSE.
                    self.status = SubAgentStatus.FAILED
                    return

                if round_state.assistant_text.strip():
                    self.final_report = round_state.assistant_text

                if round_state.trace_id and self._on_trace is not None:
                    await self._on_trace(round_state.trace_id)

                if round_state.trace_id:
                    # Rebuild minimal: the ``agent`` block is first-turn-only
                    # (the backend 400s agent + trace_id together).
                    body = {
                        "trace_id": round_state.trace_id,
                        "messages": [],
                        "auto_mode": True,
                    }

                if not round_state.finish_tool_calls:
                    if self.stop_requested:
                        self.status = SubAgentStatus.STOPPED
                        return
                    # Drain-before-finish: a steer message sent the instant the
                    # run would settle must not be dropped.
                    injected = self._drain()
                    if injected:
                        body = {
                            **body,
                            "messages": [_steer_message(m) for m in injected],
                        }
                        continue
                    # Plain-text terminal turn = the report; natural completion.
                    self.status = SubAgentStatus.COMPLETED
                    return

                client_events = [
                    e
                    for e in round_state.tool_input_events
                    if not tool_input_executor_is_server(e)
                ]

                # Interception: orchestration calls are rejected (depth 1) and
                # auto-mode signals resolve as no-ops — never executed, but every
                # tool_call_id must still be answered so the trace stays clean.
                intercepted_results: dict[str, str] = {}
                executable_events = []
                for e in client_events:
                    if e.toolName in self._orchestration_tool_names:
                        intercepted_results[e.toolCallId] = DEPTH_LIMIT_RESULT
                    elif e.toolName in (
                        ENABLE_AUTO_MODE_TOOL_NAME,
                        DISABLE_AUTO_MODE_TOOL_NAME,
                    ):
                        intercepted_results[e.toolCallId] = AUTO_MODE_NOOP_RESULT
                    else:
                        executable_events.append(e)

                # AUTO-APPROVE: consent was granted at spawn; there is no user
                # watching this loop to approve individual calls.
                tool_calls = [
                    ToolCallInfo(
                        toolCallId=e.toolCallId,
                        toolName=e.toolName,
                        input=e.input,
                        requiresApproval=False,
                    )
                    for e in executable_events
                ]

                self._emit(format_tool_exec_start(len(client_events)))
                results = await execute_tool_batch(tool_calls, {})
                results.update(intercepted_results)
                for tc_id, output in results.items():
                    self._emit(format_tool_output(tc_id, output))
                self._emit(format_tool_exec_end(len(results)))

                if not results:
                    if self.stop_requested:
                        self.status = SubAgentStatus.STOPPED
                        return
                    injected = self._drain()
                    if injected:
                        body = {
                            **body,
                            "messages": [_steer_message(m) for m in injected],
                        }
                        continue
                    self.status = SubAgentStatus.COMPLETED
                    return

                body = _build_openai_tool_continuation(
                    body,
                    round_state.assistant_text,
                    round_state.tool_input_events,
                    results,
                )
                if self.stop_requested:
                    # The tool results were fed back conceptually (the next POST
                    # never happens); the backend already persisted the pending
                    # calls, so the trace has a dangling batch — acceptable for a
                    # hard-stopped run.
                    self.status = SubAgentStatus.STOPPED
                    return
                injected = self._drain()
                if injected:
                    existing = list(body.get("messages", []))
                    existing.extend(_steer_message(m) for m in injected)
                    body = {**body, "messages": existing}

        self._emit(format_error(MAX_ROUNDS_MESSAGE, trace_id_for_error))
        self.status = SubAgentStatus.TIMEOUT
        return

    def _drain(self) -> list[InboundMessage]:
        # The registry echoes injected messages onto the bus/buffer at enqueue
        # time; drain only takes them (no re-echo), mirroring the auto runner.
        if self._drain_inbound is None:
            return []
        return self._drain_inbound()

    def _build_seed_body(self) -> dict[str, Any]:
        agent: dict[str, Any] = {
            "agent_type": self._seed.agent_type,
            "seed_prompt": self._seed.prompt,
        }
        if self._seed.parent_trace_id is not None:
            agent["parent_trace_id"] = self._seed.parent_trace_id
        return {
            "messages": [
                {"role": "user", "content": _kickoff_message(self._seed.name)}
            ],
            "agent": agent,
            "auto_mode": True,
        }
