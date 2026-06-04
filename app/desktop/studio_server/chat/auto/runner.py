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
    execute_tool_batch,
    iter_upstream_round,
)
from app.desktop.studio_server.chat.tool_metadata import tool_input_executor_is_server

from .models import AutoChatSeed, AutoRunStatus
from .sse import (
    format_auto_mode_on,
    format_error,
    format_tool_exec_end,
    format_tool_exec_start,
    format_tool_output,
)

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS_MESSAGE = "Maximum tool rounds exceeded. Please start a new message."

# Callback the runner invokes to push one SSE byte payload to the run's buffer +
# bus. It also detects kiln_chat_trace boundaries (buffer reset + index update).
EmitCallback = Callable[[bytes], None]
# Callback invoked with each observed leaf trace id (registry index update).
OnTraceCallback = Callable[[str], Awaitable[None]]


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
    ) -> None:
        self.run_id = run_id
        self._seed = seed
        self._url = upstream_url
        self._headers = headers
        self._emit = emit
        self._on_trace = on_trace
        self.status: AutoRunStatus = AutoRunStatus.RUNNING
        # Finer-grained reason for the DONE status, surfaced as auto-mode-off's
        # reason: "asked_user" when the run ended on a plain-text assistant turn
        # (a question / wrap-up handing control back), else "done".
        self.done_reason: str = "done"

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
                    self.status = AutoRunStatus.ERROR
                    return

                if round_state.trace_id:
                    body = {
                        **body,
                        "trace_id": round_state.trace_id,
                        "messages": [],
                    }

                if not round_state.finish_tool_calls:
                    # Assistant emitted only text (a question or a wrap-up) — the
                    # turn is complete and control is back with the user.
                    self.done_reason = "asked_user"
                    self.status = AutoRunStatus.DONE
                    return

                client_events = [
                    e
                    for e in round_state.tool_input_events
                    if not tool_input_executor_is_server(e)
                ]
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
                    self.status = AutoRunStatus.DONE
                    return

                body = _build_openai_tool_continuation(
                    body,
                    round_state.assistant_text,
                    round_state.tool_input_events,
                    results,
                )

        # Loop exhausted MAX_TOOL_ROUNDS without a natural exit.
        self._emit(format_error(MAX_TOOL_ROUNDS_MESSAGE, trace_id_for_error))
        self.status = AutoRunStatus.MAX_ROUNDS

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
