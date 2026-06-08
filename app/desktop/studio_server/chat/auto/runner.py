from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable

import httpx
from app.desktop.studio_server.chat.constants import CHAT_TIMEOUT, MAX_TOOL_ROUNDS
from app.desktop.studio_server.chat.stream_session import (
    RoundState,
    ToolCallInfo,
    _build_openai_tool_continuation,
    _format_tool_calls_pending_sse,
    execute_tool_batch,
    iter_upstream_round,
)
from app.desktop.studio_server.chat.tool_metadata import tool_input_executor_is_server
from kiln_ai.tools.built_in_tools.disable_auto_mode_tool import (
    DISABLE_AUTO_MODE_TOOL_NAME,
)

from .models import AutoChatSeed, AutoRunStatus, InboundMessage
from .sse import (
    format_auto_mode_on,
    format_error,
    format_tool_exec_end,
    format_tool_exec_start,
    format_tool_output,
)

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS_MESSAGE = "Maximum tool rounds exceeded. Please start a new message."

# The tool result the app server resolves an intercepted disable_auto_mode call
# to, fed back to the backend so it continues interactively.
DISABLE_AUTO_MODE_RESULT = json.dumps({"status": "disabled"}, ensure_ascii=False)

# Callback the runner invokes to push one SSE byte payload to the run's buffer +
# bus. It also detects kiln_chat_trace boundaries (buffer reset + index update).
EmitCallback = Callable[[bytes], None]
# Callback invoked with each observed leaf trace id (registry index update).
OnTraceCallback = Callable[[str], Awaitable[None]]
# Callback the runner invokes at each round boundary to atomically take (and
# clear) any user messages queued via /message since the last drain.
DrainInboundCallback = Callable[[], list[InboundMessage]]


class AutoChatRunner:
    """Drives the chat round loop autonomously, auto-approving every client tool
    and emitting to a per-run bus/buffer instead of yielding to an HTTP client.

    Reuses the interactive path's mechanics unchanged — ``iter_upstream_round``,
    ``RoundState``, ``tool_input_executor_is_server``, ``execute_tool_batch``,
    ``_build_openai_tool_continuation`` — differing only in: (1) no approval gate
    (all tool calls run with ``requires_approval=False``), and (2) output goes to
    ``emit`` rather than ``yield``.

    The runner sets ``self.status`` to a terminal value on a natural finish; the
    supervising registry task reads it (and handles cancellation/exception →
    USER_STOPPED/ERROR) and publishes the ``auto-mode-off`` marker.
    """

    def __init__(
        self,
        run_id: str,
        seed: AutoChatSeed,
        upstream_url: str,
        headers: dict[str, str],
        emit: EmitCallback,
        on_trace: OnTraceCallback | None = None,
        drain_inbound: DrainInboundCallback | None = None,
    ) -> None:
        self.run_id = run_id
        self._seed = seed
        self._url = upstream_url
        self._headers = headers
        self._emit = emit
        self._on_trace = on_trace
        self._drain_inbound = drain_inbound
        self.status: AutoRunStatus = AutoRunStatus.RUNNING
        # Revision R1: the burst-end reason carried on the auto-mode-idle event
        # the supervisor publishes. "asked_user" when the burst ended on a
        # plain-text assistant turn, "done" when a tool batch produced no
        # results, "error"/"max_rounds" for the backstops.
        self.idle_reason: str = "done"
        # Set when a disable_auto_mode call is intercepted mid-burst and resolved.
        # The runner answers the intercepted call itself (in _resolve_disable) and
        # signals the disable purely via status == USER_DISABLED; the supervisor
        # reads that status to clear the conversation flag. disable_trace_id is
        # self-consumed: _resolve_disable re-sets it to the resolving
        # continuation's trace id and passes it to on_trace.
        self.disable_trace_id: str | None = None
        # Graceful stop intent (Stop button, functional spec §4.4(1)). The
        # registry sets this instead of cancelling the task, so the in-flight
        # upstream round finishes streaming (no cut-off). At the round boundary
        # the runner stops WITHOUT starting a new round and WITHOUT auto-executing
        # this round's client tool calls: it surfaces them for normal approval via
        # tool-calls-pending, then ends the burst USER_STOPPED so the supervisor
        # publishes auto-mode-off(user_stopped) and the conversation returns to
        # normal mode.
        self.stop_requested: bool = False

    def request_stop(self) -> None:
        """Mark a graceful stop. The current round finishes; the loop then ends
        at the next boundary (no cancel, no cut-off)."""
        self.stop_requested = True

    async def run(self) -> None:
        self._emit(format_auto_mode_on(self.run_id))
        body = await self._build_seed_body()
        trace_id_for_error: str | None = self._seed.trace_id
        async with httpx.AsyncClient(timeout=CHAT_TIMEOUT) as client:
            for _ in range(MAX_TOOL_ROUNDS):
                round_state = RoundState(trace_id_for_error=trace_id_for_error)

                async for payload in iter_upstream_round(
                    client, self._url, self._headers, body, round_state
                ):
                    self._emit(payload)

                trace_id_for_error = round_state.trace_id_for_error

                if round_state.trace_id and self._on_trace is not None:
                    await self._on_trace(round_state.trace_id)

                if round_state.is_terminal_upstream_error:
                    # An unrecoverable upstream error ends the burst, but the
                    # conversation flag stays on (the supervisor routes this to
                    # IDLE with reason "error" so the user can retry or stop).
                    self.idle_reason = "error"
                    self.status = AutoRunStatus.IDLE
                    return

                if round_state.trace_id:
                    body = {
                        **body,
                        "trace_id": round_state.trace_id,
                        "messages": [],
                    }

                if not round_state.finish_tool_calls:
                    # Graceful stop (functional spec §4.4(1)): the final round was
                    # plain text — nothing to approve. Finish what was streamed,
                    # then disable auto mode. Drop any queued inbound (we do NOT
                    # start a new burst on stop). The supervisor publishes
                    # auto-mode-off(user_stopped) and the conversation returns to
                    # normal mode.
                    if self.stop_requested:
                        self.status = AutoRunStatus.USER_STOPPED
                        return
                    # Assistant emitted only text (a question or a wrap-up).
                    # Drain-before-idle (architecture §13.6): a message sent the
                    # instant the burst would settle must not be dropped — if one
                    # is queued, continue with it as a fresh user turn instead of
                    # going idle.
                    injected = self._drain()
                    if injected:
                        body = self._continue_with_user_messages(body, injected)
                        continue
                    # Nothing queued — the burst settles. The supervisor marks the
                    # run IDLE (flag stays on) and emits auto-mode-idle.
                    self.idle_reason = "asked_user"
                    self.status = AutoRunStatus.IDLE
                    return

                client_events = [
                    e
                    for e in round_state.tool_input_events
                    if not tool_input_executor_is_server(e)
                ]

                # disable_auto_mode interception (architecture §13.3): never
                # execute it. Clear the conversation flag, resolve the call as
                # disabled so the backend continues interactively, and end the
                # burst as USER_DISABLED (the supervisor publishes
                # auto-mode-off(user_disabled)).
                disable_evt = next(
                    (
                        e
                        for e in client_events
                        if e.toolName == DISABLE_AUTO_MODE_TOOL_NAME
                    ),
                    None,
                )
                if disable_evt is not None:
                    self.disable_trace_id = round_state.trace_id or trace_id_for_error
                    await self._resolve_disable(
                        client, body, round_state, disable_evt, client_events
                    )
                    self.status = AutoRunStatus.USER_DISABLED
                    return

                # Graceful stop (functional spec §4.4(1)): the in-flight round
                # finished streaming (no cut-off). Do NOT auto-execute this round's
                # client tool calls and do NOT start a new round — instead surface
                # them for normal approval via the EXISTING tool-calls-pending
                # mechanism (everything after the stop is subject to approval), then
                # end the burst USER_STOPPED. The browser resolves the surfaced
                # tools via the normal /api/chat/execute-tools approval flow, so the
                # persisted trace gets a clean continuation (no dangling tool calls
                # left by the runner). If the round had no client tool calls this
                # branch is skipped (finish_tool_calls with only server tools is
                # rare); a truly empty client batch just disables below via the
                # no-results path.
                if self.stop_requested and client_events:
                    self._emit(_format_tool_calls_pending_sse(client_events))
                    self.status = AutoRunStatus.USER_STOPPED
                    return

                # AUTO-APPROVE: requires_approval=False makes execute_tool_batch
                # skip the gate and run every client tool unattended.
                tool_calls = [
                    ToolCallInfo(
                        toolCallId=e.toolCallId,
                        toolName=e.toolName,
                        input=e.input,
                        requiresApproval=False,
                    )
                    for e in client_events
                ]

                self._emit(format_tool_exec_start(len(tool_calls)))
                results = await execute_tool_batch(tool_calls, {})
                for tc_id, output in results.items():
                    self._emit(format_tool_output(tc_id, output))
                self._emit(format_tool_exec_end(len(results)))

                if not results:
                    # No client tool results to feed back (e.g. server-only tool
                    # batch with no client tools to approve). On graceful stop just
                    # disable — there's nothing to surface for approval.
                    if self.stop_requested:
                        self.status = AutoRunStatus.USER_STOPPED
                        return
                    # Same drain-before-idle check applies.
                    injected = self._drain()
                    if injected:
                        body = self._continue_with_user_messages(body, injected)
                        continue
                    self.idle_reason = "done"
                    self.status = AutoRunStatus.IDLE
                    return

                body = _build_openai_tool_continuation(
                    body,
                    round_state.assistant_text,
                    round_state.tool_input_events,
                    results,
                )
                # Graceful stop after a fully auto-executed round: don't start a new
                # round. The tool results were fed back so the trace stays clean;
                # disable auto mode (the supervisor publishes auto-mode-off).
                if self.stop_requested:
                    self.status = AutoRunStatus.USER_STOPPED
                    return
                # Inject any messages queued during this round alongside the tool
                # results so the backend sees both on the next turn (§13.2).
                injected = self._drain()
                if injected:
                    body = self._append_user_messages(body, injected)

        # Loop exhausted MAX_TOOL_ROUNDS without a natural exit. The burst ends
        # but the conversation flag stays on (→ IDLE, reason "max_rounds").
        self._emit(format_error(MAX_TOOL_ROUNDS_MESSAGE, trace_id_for_error))
        self.idle_reason = "max_rounds"
        self.status = AutoRunStatus.IDLE

    async def _resolve_disable(
        self,
        client: httpx.AsyncClient,
        body: dict[str, Any],
        round_state: RoundState,
        disable_evt: Any,
        client_events: list[Any],
    ) -> None:
        """Resolve an intercepted ``disable_auto_mode`` call back to the backend
        (architecture §13.3, CR Moderate 3).

        The backend persisted an assistant turn carrying the ``disable_auto_mode``
        tool call; if that call is never answered the next interactive
        ``/api/chat`` turn on this trace has a dangling, unanswered tool call (the
        provider requires every tool call be answered before a new user message)
        and can error. So we resolve the call as ``{"status":"disabled"}`` — and
        execute any siblings in the same turn — then send one final continuation
        to the backend so it persists a clean snapshot before auto mode goes off.
        The model's reply to that continuation is forwarded to observers, but the
        burst does NOT continue past it: this is the terminal round."""
        # Execute any sibling client tools in the same turn (mirrors the
        # interactive disable path), so every tool_call_id is answered.
        siblings = [e for e in client_events if e is not disable_evt]
        sibling_results = (
            await execute_tool_batch(
                [
                    ToolCallInfo(
                        toolCallId=e.toolCallId,
                        toolName=e.toolName,
                        input=e.input,
                        requiresApproval=False,
                    )
                    for e in siblings
                ],
                {},
            )
            if siblings
            else {}
        )
        tool_results = {
            disable_evt.toolCallId: DISABLE_AUTO_MODE_RESULT,
            **sibling_results,
        }
        # Surface the resolved results to observers so the UI sees them.
        self._emit(format_tool_exec_start(len(tool_results)))
        for tc_id, output in tool_results.items():
            self._emit(format_tool_output(tc_id, output))
        self._emit(format_tool_exec_end(len(tool_results)))

        # Send the resolving continuation to the backend so the persisted trace
        # has no dangling tool call. This is terminal — forward the backend's
        # reply to observers but do not loop.
        continuation = _build_openai_tool_continuation(
            body,
            round_state.assistant_text,
            round_state.tool_input_events,
            tool_results,
        )
        final_state = RoundState(trace_id_for_error=round_state.trace_id_for_error)
        async for payload in iter_upstream_round(
            client, self._url, self._headers, continuation, final_state
        ):
            self._emit(payload)
        if final_state.trace_id is not None:
            self.disable_trace_id = final_state.trace_id
            if self._on_trace is not None:
                await self._on_trace(final_state.trace_id)

    def _drain(self) -> list[InboundMessage]:
        # The registry already echoes every message onto the bus + buffer at
        # enqueue time (registry.send_message → run.echo_user_message), and the
        # runner is only ever fed via that enqueue path. Echoing again here would
        # render the injected message twice to all observers, so drain only takes
        # the queued messages and does NOT re-echo (CR Moderate 1).
        if self._drain_inbound is None:
            return []
        return self._drain_inbound()

    @staticmethod
    def _append_user_messages(
        body: dict[str, Any], messages: list[InboundMessage]
    ) -> dict[str, Any]:
        """Append injected user messages after the tool results in a continuation
        body (they come last so the backend reads them as the latest input)."""
        existing = list(body.get("messages", []))
        existing.extend(m.as_chat_message() for m in messages)
        return {**body, "messages": existing}

    def _continue_with_user_messages(
        self, body: dict[str, Any], messages: list[InboundMessage]
    ) -> dict[str, Any]:
        """Build a fresh-turn continuation seeded only with injected user messages
        (the trace advanced, no pending tool results to carry)."""
        return {
            **body,
            "messages": [m.as_chat_message() for m in messages],
        }

    async def _build_seed_body(self) -> dict[str, Any]:
        """Construct the first upstream continuation body from the seed (§3.5).

        Starts from any ``extra_messages`` (manual idle path), resolves the
        accepted ``enable_auto_mode`` call as ``{"status":"enabled"}``, and
        auto-executes any sibling pending tool calls now, appending their
        ``role:tool`` results. The backend continues from ``trace_id`` with these
        results — the same continuation contract ``/execute-tools`` uses.
        """
        messages: list[dict[str, Any]] = list(self._seed.extra_messages)

        if self._seed.enable_tool_call_id:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": self._seed.enable_tool_call_id,
                    "content": json.dumps({"status": "enabled"}, ensure_ascii=False),
                }
            )

        if self._seed.pending_tool_calls:
            # Auto-approve siblings too (rare path).
            siblings = [
                ToolCallInfo(
                    toolCallId=tc.tool_call_id,
                    toolName=tc.tool_name,
                    input=tc.input,
                    requiresApproval=False,
                )
                for tc in self._seed.pending_tool_calls
            ]
            results = await execute_tool_batch(siblings, {})
            for tc_id, output in results.items():
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": output,
                    }
                )

        return {"trace_id": self._seed.trace_id, "messages": messages}
