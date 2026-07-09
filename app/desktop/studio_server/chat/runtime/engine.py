"""ConversationEngine — THE chat round loop (architecture §3).

One loop replaces three: ``ChatStreamSession.stream()`` (interactive),
``AutoChatRunner.run()`` (auto mode), and ``SubAgentRunner.run()``
(sub-agents). All per-round logic already existed, scattered across those
loops; here each pipeline step carries a comment naming the old code path it
preserves. The differences between kinds are exclusively:

- frozen ``ConversationPolicy`` data (approval gating, framing, one-shot,
  budgets, backstop message), and
- the policy's ``interceptors`` chain (signal-tool handling).

Design invariants:

- **Zero HTTP awareness.** The engine never touches FastAPI/SSE responses.
  Everything flows through the ``EngineIO`` callback bundle; the only network
  the engine drives is the upstream chat POST via the SHARED round primitives
  in ``stream_session.py`` (``iter_round_with_retries`` /
  ``iter_upstream_round``) — reused, never duplicated, so retry
  classification and error shapes cannot drift from the old paths while they
  coexist.
- **Byte-identical upstream protocol.** Continuation bodies, the ``agent``
  block lifecycle, ``auto_mode`` propagation, message framings, and tool
  results must produce persisted traces indistinguishable from today's
  (functional spec §3) — pinned by test_golden_protocol.py.
- **Outcome via the record.** The engine records its terminal outcome on the
  ``ConversationRecord`` (state / idle_reason / auto_flag / final_report),
  exactly like the old runners recorded ``self.status`` for their
  supervising registries. The supervisor's single settle path normalizes
  cancellation/timeout/exception on top and does all publishing.
- **Stop semantics preserved.** ``io.stop_requested`` is polled at the same
  boundaries as today (round retries, post-round, post-execution). Hard
  cancellation (task.cancel) is the supervisor's job.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import httpx
from app.desktop.studio_server.chat.constants import CHAT_TIMEOUT, DENIED_TOOL_OUTPUT
from app.desktop.studio_server.chat.stream_session import (
    RetryRoundResult,
    RoundState,
    ToolCallInfo,
    _build_openai_tool_continuation,
    _pending_item_from_event,
    execute_tool_batch,
    iter_round_with_retries,
    iter_upstream_round,
)
from app.desktop.studio_server.chat.tool_metadata import (
    tool_input_executor_is_server,
    tool_requires_user_approval,
)
from kiln_ai.adapters.model_adapters.stream_events import ToolInputAvailableEvent

from .interceptors import (
    SPAWN_SUBAGENT_TOOL_NAME,
    InterceptContext,
    InterceptResult,
)
from .models import (
    ConversationPolicy,
    ConversationRecord,
    InboundMessage,
    PendingApprovalBatch,
    RunState,
    build_subagent_seed_body,
    kickoff_message,
)
from .sse import (
    format_error,
    format_tool_calls_pending,
    format_tool_exec_end,
    format_tool_exec_start,
    format_tool_output,
    format_user_message,
)

logger = logging.getLogger(__name__)


# Framing prepended to a user message that arrives WHILE an auto burst is in
# flight (drained mid-round). Without it the model treats the message as a
# fresh conversational turn, replies in plain text, and that text-only turn
# settles the burst IDLE ("asked_user") — so a quick aside from the user halts
# the autonomous run. Framed as a side note, the model weaves its reply into a
# turn that still carries tool calls, so it answers AND keeps working. It does
# NOT apply to seed messages (the task itself) or to a message that wakes an
# idle run (those ride unframed — see the supervisor's idle re-arm).
# Canonical (and only) home since phase 3 deleted chat/auto/runner.py's
# _SIDE_NOTE_REMINDER; byte-pinned in test_interceptors.py because it is
# persisted in traces.
SIDE_NOTE_REMINDER = (
    "<system-reminder>"
    "This message arrived from the user while you are working autonomously in auto "
    "mode. Treat it as a side note: weave any acknowledgment or answer into your "
    "ongoing work and keep going in the same turn — do not end your turn just to "
    "reply. Stop only if the message explicitly asks you to, or your task is "
    "already complete."
    "</system-reminder>"
)

# Framing for a user message injected into a RUNNING sub-agent from the UI.
# Without it the model reads the message as a fresh conversational turn,
# replies in plain text, and that text turn would end the run as COMPLETED
# with the reply as its "report".
# Canonical copy of chat/subagents/runner.py's _STEER_REMINDER (deleted in
# phase 2); byte-identical because it is persisted in traces.
STEER_REMINDER = (
    "<system-reminder>"
    "This message was sent by the user overseeing your background run. "
    "Incorporate the guidance and continue working in the same turn — do not "
    "end your turn just to reply. End only when your job (as adjusted) is done, "
    "with your final report."
    "</system-reminder>"
)


def _frame_inbox_message(
    msg: InboundMessage, policy: ConversationPolicy
) -> dict[str, Any]:
    """Frame a drained inbox message per the policy (old _side_note_message /
    _steer_message / raw interactive)."""
    base = msg.as_chat_message()
    # `or ""` so an explicit None content can't become the string "None"
    # (defensive parity with the old auto helper).
    content = str(base.get("content") or "")
    if policy.message_framing == "side_note":
        # Sub-agent completion reports ride the same inbound channel (an
        # auto-flag parent receives them as inbox messages) but are NOT user
        # asides: the side-note frame would misdescribe them to the model AND
        # break the client's report-panel detection (which keys on the
        # persisted message starting with the report frame). Deliver them
        # unwrapped. (Old auto _side_note_message behavior.)
        if content.startswith("<subagent_report"):
            return {**base, "content": content}
        return {**base, "content": f"{SIDE_NOTE_REMINDER}\n\n{content}"}
    if policy.message_framing == "steer":
        # Old sub-agent _steer_message applied the frame unconditionally
        # (children never receive report frames), preserved as-is.
        return {**base, "content": f"{STEER_REMINDER}\n\n{content}"}
    return base


def _append_messages(
    body: dict[str, Any], messages: list[dict[str, Any]]
) -> dict[str, Any]:
    """Append messages after whatever the continuation already carries (they
    come last so the backend reads them as the latest input — old
    _append_user_messages contract)."""
    existing = list(body.get("messages", []))
    existing.extend(messages)
    return {**body, "messages": existing}


@dataclass
class EngineIO:
    """Everything the engine can do to the outside world (architecture §3).

    Bundled so the engine has exactly one seam: the supervisor wires these to
    the conversation's bus/inbox/batch machinery, and tests wire them to
    lists. All callbacks must be non-blocking except the awaitables.
    """

    # Push one SSE byte payload to the conversation's bus + replay buffer.
    # (Old runners' emit callback; the interactive loop's `yield`.)
    emit: Callable[[bytes], None]
    # Called with each newly persisted leaf trace id, AFTER the engine updated
    # record.current_leaf_trace_id / seen_trace_ids (the record is the run
    # loop's to write — single-writer rule; the supervisor only maintains its
    # trace→session index and bookkeeping here).
    on_trace: Callable[[str], Awaitable[None]] | None = None
    # Atomically take (and clear) user messages queued since the last drain.
    # The supervisor echoes messages at ENQUEUE time; the engine never
    # re-echoes drained messages (echo-once — old CR Moderate 1).
    drain_inbox: Callable[[], list[InboundMessage]] = field(default=lambda: [])
    # Take (and mark delivered) framed sub-agent reports queued for THIS
    # conversation. Interactive-parent channel only: the supervisor routes an
    # auto-flag parent's reports through the inbox instead (waking an idle
    # burst), so the two channels can never double-deliver.
    drain_reports: Callable[[], list[str]] = field(default=lambda: [])
    # Park on a pending approval batch until the user decides; returns the
    # decision map. Only gated policies call this. No upstream connection is
    # held while parked — the run task simply awaits the batch event.
    await_decisions: (
        Callable[[PendingApprovalBatch], Awaitable[dict[str, bool]]] | None
    ) = None
    # Graceful-stop intent, polled at the same boundaries the old runners
    # polled self.stop_requested. (The old interactive loop had no stop
    # polling; its io returns False forever, so behavior is unchanged there.)
    stop_requested: Callable[[], bool] = field(default=lambda: False)
    # Opaque conversation identity for sub-agent orchestration tool calls,
    # passed straight through to execute_tool_batch (which dispatches
    # spawn/status/wait/stop). None resolves those calls to an "unavailable"
    # error — correct for phase 1 where orchestration still targets the old
    # registries; phase 2 retargets it onto the supervisor.
    orchestration_ctx: Any | None = None


class ConversationEngine:
    """Drives the chat round loop for ONE run (an interactive turn, an auto
    burst, or a whole sub-agent run) against the upstream chat endpoint.

    A plain class: construct with the upstream target, call ``run`` once per
    run. The engine is stateless across runs — all conversation state lives on
    the record (and the supervisor's machinery), which is what lets an auto
    flip swap the policy on the SAME record between turns.
    """

    def __init__(self, upstream_url: str, headers: dict[str, str]) -> None:
        self._url = upstream_url
        self._headers = headers

    async def run(
        self,
        record: ConversationRecord,
        policy: ConversationPolicy,
        io: EngineIO,
        initial_body: dict[str, Any] | None = None,
    ) -> None:
        """Run one turn/burst/run to its natural end, recording the outcome on
        ``record``. Raises only on unexpected internal errors (the supervisor
        classifies those per architecture §9); upstream errors are handled
        in-band exactly like the old loops."""
        if initial_body is not None:
            body = dict(initial_body)
        else:
            # Child creation (policy.seed): the engine owns the first POST —
            # agent block + kickoff message (old SubAgentRunner.run preamble).
            if policy.seed is None:
                raise ValueError(
                    "ConversationEngine.run needs an initial_body or a policy seed"
                )
            body = build_subagent_seed_body(policy.seed)
            # Echo the kickoff message onto the run's stream: the observer SSE
            # only carries response events (the kickoff rides the request
            # body), so without this an observer attaching before the first
            # snapshot persists would never see the sub-agent's instructions.
            # The stable id lets a client dedupe the echo against a transcript
            # it already shows (old id was kickoff-<subagent_id>; the handle
            # is the session id now).
            io.emit(
                format_user_message(
                    kickoff_message(policy.seed.name, policy.seed.prompt),
                    f"kickoff-{record.session_id}",
                )
            )

        record.state = RunState.RUNNING
        # Seed the error-correlation trace id from the body (the conversation
        # continuation leaf) or the record — same seeding the old loops used.
        trace_id_for_error: str | None = (
            body.get("trace_id") or record.current_leaf_trace_id
        )

        async with httpx.AsyncClient(timeout=CHAT_TIMEOUT) as client:
            for _ in range(policy.max_rounds):
                # rounds_used is one-shot reporting (old SubAgentRunner
                # counted every attempted round, including the failing one);
                # harmless bookkeeping for the other kinds.
                record.rounds_used += 1

                # ── 1. Round (shared retry helper — identical transient-error
                # classification/backoff for every kind). ────────────────────
                result = RetryRoundResult()
                async for payload in iter_round_with_retries(
                    client,
                    self._url,
                    self._headers,
                    body,
                    trace_id_for_error,
                    result,
                    # Old protocol detail: retry events carried a run id on the
                    # auto/sub-agent streams but not the interactive one. The
                    # id is the session id in the unified vocabulary.
                    run_id=(
                        record.session_id if policy.retry_events_carry_run_id else None
                    ),
                    stop_requested=io.stop_requested,
                ):
                    io.emit(payload)

                round_state = result.round_state
                if round_state is not None:
                    trace_id_for_error = round_state.trace_id_for_error
                if result.status == "stopped":
                    # Stop pressed mid-retry: the helper surfaced no error;
                    # settle stopped (old auto USER_STOPPED / sub-agent STOPPED).
                    self._finish_stopped(record, policy)
                    return
                if result.status != "ok" or round_state is None:
                    # Non-retryable or retry-exhausted upstream error; the
                    # error SSE was already emitted. One-shot runs FAIL (old
                    # sub-agent), others idle with reason "error" — the flag
                    # stays on so the user can retry or stop (old auto).
                    self._finish_error(record, policy)
                    return

                # ── 2. Trace advance. ────────────────────────────────────────
                if policy.one_shot and round_state.assistant_text.strip():
                    # Last assistant text seen becomes the report (or its
                    # partial-output base) on any end — old SubAgentRunner.
                    record.final_report = round_state.assistant_text
                if round_state.trace_id:
                    # Single-writer rule: the run loop owns the leaf pointer.
                    record.current_leaf_trace_id = round_state.trace_id
                    if round_state.trace_id not in record.seen_trace_ids:
                        record.seen_trace_ids.append(round_state.trace_id)
                    if io.on_trace is not None:
                        await io.on_trace(round_state.trace_id)
                    # Rebuild the continuation base: continue from the new
                    # leaf with empty messages. The `agent` block is dropped —
                    # it is first-POST-only (the backend 400s agent + trace_id
                    # together; old SubAgentRunner rebuilt minimally for the
                    # same reason). Everything else ({**body}) is preserved so
                    # auto_mode and any extra interactive body fields keep
                    # riding every continuation (old interactive/auto rebuild).
                    body = {k: v for k, v in body.items() if k != "agent"}
                    body = {**body, "trace_id": round_state.trace_id, "messages": []}

                # ── 3/4. Natural end (no tool-call finish boundary). ─────────
                if not round_state.finish_tool_calls:
                    if io.stop_requested():
                        # Graceful stop on a plain-text final round: finish
                        # what streamed, then settle stopped — nothing to
                        # approve, and queued inbox is dropped (a stop never
                        # starts a new round; old auto behavior).
                        self._finish_stopped(record, policy)
                        return
                    # Drain-before-idle: a message sent the instant the run
                    # would settle must not be dropped — continue with it as a
                    # fresh (framed) user turn instead of settling. (Old auto
                    # drain-before-idle + sub-agent drain-before-finish; the
                    # interactive inbox is empty until phase 4 wires sends.)
                    injected = io.drain_inbox()
                    if injected:
                        body = {
                            **body,
                            "messages": [
                                _frame_inbox_message(m, policy) for m in injected
                            ],
                        }
                        continue
                    if policy.one_shot:
                        # Plain-text terminal turn = the report (final_report
                        # already captured above); natural completion.
                        record.state = RunState.COMPLETED
                        return
                    # Assistant emitted only text (a question or a wrap-up):
                    # the run settles idle awaiting the user (old auto
                    # "asked_user"; the old interactive stream simply ended
                    # its turn here, which is the same IDLE in the new model).
                    self._finish_idle(record, "asked_user")
                    return

                # ── 5. Partition tool events via the interceptor chain. ─────
                client_events = [
                    e
                    for e in round_state.tool_input_events
                    if not tool_input_executor_is_server(e)
                ]
                ictx = InterceptContext(
                    record=record,
                    policy=policy,
                    trace_id=round_state.trace_id,
                    client_events=client_events,
                )

                # Priority scan: the first interceptor (in chain order) whose
                # result takes over the round wins — this reproduces the old
                # `next(...)` scans (interactive checked enable before
                # disable; auto checked disable first). Plain resolves are
                # collected afterwards; interceptors are pure so re-invoking
                # them below is safe.
                takeover: tuple[ToolInputAvailableEvent, InterceptResult] | None = None
                for interceptor in policy.interceptors:
                    for e in client_events:
                        res = interceptor(e, ictx)
                        if res is not None and res.kind != "resolve":
                            takeover = (e, res)
                            break
                    if takeover is not None:
                        break

                if takeover is not None:
                    event, res = takeover
                    if res.kind == "control":
                        # enable_auto_mode consent (interactive): emit the
                        # consent-required control event and END the turn
                        # without executing anything. The call is resolved
                        # out-of-band by the accept/decline flow, which flips
                        # the policy — old ChatStreamSession enable branch.
                        assert res.control_bytes is not None
                        io.emit(res.control_bytes)
                        # The old stream just ended here; in the unified model
                        # that is an idle turn boundary (the consent-pending
                        # bookkeeping is the enable endpoint's job, phase 3).
                        record.state = RunState.IDLE
                        return
                    if res.kind == "resolve_terminal":
                        # disable_auto_mode during an auto burst: resolve +
                        # siblings + ONE final resolving continuation, then
                        # the burst ends with the flag off. (Old
                        # AutoChatRunner._resolve_disable, CR Moderate 3.)
                        await self._resolve_terminal(
                            client, record, io, body, round_state, event, res
                        )
                        if res.clear_auto_flag:
                            record.auto_flag = False
                        # Preserved off-reason vocabulary: the model asked.
                        self._finish_idle(record, "user_disabled")
                        return
                    if res.kind == "resolve_immediate":
                        # disable_auto_mode on the interactive path: resolve
                        # the signal, clear the flag, execute siblings through
                        # the per-tool gate WITH NO DECISIONS (an
                        # approval-requiring sibling is denied rather than run
                        # without consent), and CONTINUE the loop. Old
                        # ChatStreamSession disable branch — including its
                        # quirk of NOT draining reports/inbox on this
                        # continuation (`continue` skipped the report append).
                        if res.clear_auto_flag:
                            # Flag lives on the record now; the supervisor
                            # publishes the state change at the next settle
                            # (old path called auto_registry.disable_for_trace
                            # which published auto-mode-off out-of-band).
                            record.auto_flag = False
                        body = await self._resolve_immediate(
                            record, io, body, round_state, event, res, client_events
                        )
                        continue

                # ── 8. Graceful stop at a tool boundary (auto policy only):
                # the in-flight round finished streaming (no cut-off). Do NOT
                # execute this round's client tool calls and do NOT start a
                # new round — surface them for normal approval via
                # tool-calls-pending (everything after the stop is subject to
                # approval), then settle stopped. Old AutoChatRunner behavior;
                # its position (after the disable interception, before
                # execution) is preserved. ────────────────────────────────────
                if (
                    policy.graceful_stop_surfaces_pending
                    and io.stop_requested()
                    and client_events
                ):
                    io.emit(format_tool_calls_pending(client_events))
                    self._finish_stopped(record, policy)
                    return

                # Plain per-event resolves (auto enable no-op, child depth
                # guard / auto-signal noops): the call is answered locally,
                # never executed, and the batch otherwise proceeds.
                intercepted: dict[str, str] = {}
                executable: list[ToolInputAvailableEvent] = []
                for e in client_events:
                    resolved = self._plain_resolve(e, ictx, policy)
                    if resolved is not None:
                        intercepted[e.toolCallId] = resolved
                    else:
                        executable.append(e)

                # ── 5b. Approval gate (gated policy; architecture §3.5). ─────
                decisions: dict[str, bool] = {}
                parked = False
                if policy.approvals == "gated":
                    needs_approval = [
                        e
                        for e in executable
                        if self._effective_requires_approval(e, record)
                    ]
                    if needs_approval:
                        # The pending event lists the WHOLE client batch (the
                        # user sees non-approval siblings for context), same
                        # bytes as the old interactive stream.
                        io.emit(format_tool_calls_pending(client_events))
                        batch = PendingApprovalBatch(
                            items=[_pending_item_from_event(e) for e in client_events],
                            body=body,
                            assistant_text=round_state.assistant_text,
                            tool_input_events=round_state.tool_input_events,
                        )
                        if io.await_decisions is None:
                            raise RuntimeError(
                                "gated policy requires io.await_decisions"
                            )
                        # Park. No upstream connection is held; the task
                        # simply awaits the decision event. This replaces the
                        # old two-request flow (stream ends at pending; the
                        # browser POSTs /execute-tools to continue) with a
                        # parked run — the wire bodies are identical.
                        record.state = RunState.AWAITING_APPROVAL
                        decisions = await io.await_decisions(batch)
                        record.state = RunState.RUNNING
                        parked = True

                # ── 6. Execute the batch. ────────────────────────────────────
                # requiresApproval per call:
                # - auto policy: False for everything (AUTO-APPROVE — the old
                #   runners' unattended contract).
                # - gated, parked: the metadata verdict — exactly the flags
                #   the pending event surfaced, which is what the old browser
                #   echoed back to /execute-tools. (A user's denial must deny
                #   even a call the effective verdict would have downgraded.)
                # - gated, not parked: the effective verdict (all False by
                #   construction — otherwise we'd have parked), matching the
                #   old non-parked interactive execution.
                def _requires_approval(e: ToolInputAvailableEvent) -> bool:
                    if policy.approvals != "gated":
                        return False
                    if parked:
                        return tool_requires_user_approval(e)
                    return self._effective_requires_approval(e, record)

                tool_calls = [
                    ToolCallInfo(
                        toolCallId=e.toolCallId,
                        toolName=e.toolName,
                        input=e.input,
                        requiresApproval=_requires_approval(e),
                    )
                    for e in executable
                ]
                # exec framing counts: start = the round's client batch size,
                # end = number of results — both preserved from the old loops
                # (they differ only when intercepted calls resolve without
                # executing, which the old loops counted the same way).
                io.emit(format_tool_exec_start(len(client_events)))
                results = await execute_tool_batch(
                    tool_calls, decisions, orchestration_ctx=io.orchestration_ctx
                )
                results.update(intercepted)
                for tc_id, output in results.items():
                    io.emit(format_tool_output(tc_id, output))
                io.emit(format_tool_exec_end(len(results)))

                # Spawn-consent memory: an EXECUTED spawn_subagent means the
                # user approved it (or consent already existed) — later spawns
                # in this conversation skip the approval gate. Mirrors the old
                # registry-authoritative mark_consented inside the spawn
                # executor; keyed by session id simply by living on the record.
                for tc in tool_calls:
                    if (
                        tc.tool_name == SPAWN_SUBAGENT_TOOL_NAME
                        and results.get(tc.tool_call_id) != DENIED_TOOL_OUTPUT
                    ):
                        record.spawn_consent_granted = True

                # ── 4b. No client tool results to feed back (e.g. a
                # server-only batch): nothing to continue with. ───────────────
                if not results:
                    if io.stop_requested():
                        # On graceful stop just settle — nothing to surface
                        # for approval (old auto empty-results stop branch).
                        self._finish_stopped(record, policy)
                        return
                    injected = io.drain_inbox()
                    if injected:
                        body = {
                            **body,
                            "messages": [
                                _frame_inbox_message(m, policy) for m in injected
                            ],
                        }
                        continue
                    if policy.one_shot:
                        record.state = RunState.COMPLETED
                        return
                    # Old auto reason vocabulary: a tool batch that produced
                    # no results settles "done". (The old interactive stream
                    # simply ended its turn here.)
                    self._finish_idle(record, "done")
                    return

                # ── 7. Continuation. ─────────────────────────────────────────
                body = _build_openai_tool_continuation(
                    body,
                    round_state.assistant_text,
                    round_state.tool_input_events,
                    results,
                )
                # Graceful stop after a fully executed round: the tool results
                # were fed into the continuation body conceptually, but no new
                # round starts (old auto post-execution stop; the persisted
                # trace already holds the calls — acceptable for a stop).
                if io.stop_requested():
                    self._finish_stopped(record, policy)
                    return
                # Sub-agent reports that landed while this run was in flight
                # ride the continuation as user messages (completion
                # injection, mid-stream path) and are echoed to the live
                # transcript — old ChatStreamSession._append_pending_
                # subagent_reports. Never framed: the report frame IS the
                # message. Auto-flag parents receive reports via the inbox
                # instead (supervisor routing), so drain_reports is empty for
                # them — no double delivery is possible.
                reports = io.drain_reports()
                if reports:
                    body = _append_messages(
                        body, [{"role": "user", "content": r} for r in reports]
                    )
                    for r in reports:
                        io.emit(format_user_message(r))
                # Messages queued during this round ride the continuation
                # after the tool results (framed per policy) so the backend
                # sees both on the next turn — old auto _append_user_messages.
                injected = io.drain_inbox()
                if injected:
                    body = _append_messages(
                        body, [_frame_inbox_message(m, policy) for m in injected]
                    )

        # Loop exhausted max_rounds without a natural exit. One-shot runs go
        # TIMEOUT (old sub-agent round cap); others settle idle with reason
        # "max_rounds" — the flag stays on so the user can re-arm (old auto
        # backstop; the old interactive stream ended after the same error).
        io.emit(format_error(policy.max_rounds_message, trace_id_for_error))
        if policy.one_shot:
            record.state = RunState.TIMEOUT
            return
        self._finish_idle(record, "max_rounds")

    # ── Outcome helpers (the engine-side halves of the old runner statuses;
    # the supervisor's settle path publishes them). ──────────────────────────

    def _finish_idle(self, record: ConversationRecord, reason: str | None) -> None:
        # NOTE (CR m2): the auto idle vocabulary (asked_user/done/error/
        # max_rounds/user_stopped) is recorded uniformly — INCLUDING on
        # interactive-kind records, where the old world had no such concept
        # (the interactive stream just ended its turn). The uniform write
        # keeps the engine kind-agnostic and gives the supervisor one settle
        # shape; conversation-state events therefore carry idle_reason for
        # interactive conversations too. Phase 4's frontend must key any
        # idle_reason rendering on kind == "auto" (or auto_flag) and ignore
        # it for interactive conversations — see the phase-4 note in the
        # phase-1 plan.
        record.state = RunState.IDLE
        if reason is not None:
            record.idle_reason = reason

    def _finish_stopped(
        self, record: ConversationRecord, policy: ConversationPolicy
    ) -> None:
        if policy.one_shot:
            record.state = RunState.STOPPED
            return
        # Auto graceful stop clears the conversation flag (old USER_STOPPED →
        # auto-mode-off(user_stopped)); for interactive records the flag is
        # already off, so this is a no-op there.
        record.auto_flag = False
        self._finish_idle(record, "user_stopped")

    def _finish_error(
        self, record: ConversationRecord, policy: ConversationPolicy
    ) -> None:
        if policy.one_shot:
            record.state = RunState.FAILED
            return
        # A burst-level upstream failure leaves the flag ON so the user can
        # retry or stop (old auto IDLE("error") semantics).
        self._finish_idle(record, "error")

    # ── Interception application. ────────────────────────────────────────────

    def _plain_resolve(
        self,
        event: ToolInputAvailableEvent,
        ictx: InterceptContext,
        policy: ConversationPolicy,
    ) -> str | None:
        """First chain match for this event, if it is a plain resolve.

        Round-takeover kinds were already handled by the priority scan; if one
        matches here it belongs to a DIFFERENT event than the takeover winner
        and the old loops would not have specially handled it either (their
        `next(...)` scans picked one winner) — treat it as executable.
        """
        for interceptor in policy.interceptors:
            res = interceptor(event, ictx)
            if res is None:
                continue
            if res.kind == "resolve":
                assert res.result_json is not None
                return res.result_json
            return None
        return None

    async def _resolve_terminal(
        self,
        client: httpx.AsyncClient,
        record: ConversationRecord,
        io: EngineIO,
        body: dict[str, Any],
        round_state: RoundState,
        event: ToolInputAvailableEvent,
        res: InterceptResult,
    ) -> None:
        """Resolve an intercepted signal back to the backend and end the run
        after ONE final continuation (old ``AutoChatRunner._resolve_disable``).

        The backend persisted an assistant turn carrying the signal tool call;
        if that call is never answered the next turn on this trace has a
        dangling, unanswered tool call (the provider requires every tool call
        be answered before a new user message) and can error. So we resolve
        the call — and execute any siblings in the same turn, auto-approved —
        then send one final continuation so the backend persists a clean
        snapshot. The model's reply to that continuation is forwarded to
        observers, but the run does NOT continue past it: this is the terminal
        round.
        """
        assert res.result_json is not None
        siblings = [e for e in round_state.tool_input_events if e is not event]
        siblings = [e for e in siblings if not tool_input_executor_is_server(e)]
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
                orchestration_ctx=io.orchestration_ctx,
            )
            if siblings
            else {}
        )
        tool_results = {event.toolCallId: res.result_json, **sibling_results}
        # Surface the resolved results to observers so the UI sees them.
        io.emit(format_tool_exec_start(len(tool_results)))
        for tc_id, output in tool_results.items():
            io.emit(format_tool_output(tc_id, output))
        io.emit(format_tool_exec_end(len(tool_results)))

        continuation = _build_openai_tool_continuation(
            body,
            round_state.assistant_text,
            round_state.tool_input_events,
            tool_results,
        )
        # Deliberately the PLAIN round iterator (no retry wrapper) — the old
        # terminal resolve did not retry this best-effort final continuation,
        # and the run is ending regardless of its outcome.
        final_state = RoundState(trace_id_for_error=round_state.trace_id_for_error)
        async for payload in iter_upstream_round(
            client, self._url, self._headers, continuation, final_state
        ):
            io.emit(payload)
        if final_state.trace_id is not None:
            # The clean snapshot's leaf becomes the conversation's resume
            # point (old disable_trace_id + on_trace bookkeeping).
            record.current_leaf_trace_id = final_state.trace_id
            if final_state.trace_id not in record.seen_trace_ids:
                record.seen_trace_ids.append(final_state.trace_id)
            if io.on_trace is not None:
                await io.on_trace(final_state.trace_id)

    async def _resolve_immediate(
        self,
        record: ConversationRecord,
        io: EngineIO,
        body: dict[str, Any],
        round_state: RoundState,
        event: ToolInputAvailableEvent,
        res: InterceptResult,
        client_events: list[ToolInputAvailableEvent],
    ) -> dict[str, Any]:
        """Resolve an intercepted signal inline and continue the loop (old
        interactive ``disable_auto_mode`` branch of ``ChatStreamSession``).

        Siblings execute through the normal per-tool approval verdict with NO
        decisions: an approval-requiring sibling gets DENIED_TOOL_OUTPUT
        rather than running without consent (auto-approval is the auto
        policy's job, not this path's). The model is instructed to call the
        signal alone, so siblings are normally empty. Returns the continuation
        body for the next round.
        """
        assert res.result_json is not None
        siblings = [e for e in client_events if e is not event]
        sibling_results = await execute_tool_batch(
            [
                ToolCallInfo(
                    toolCallId=e.toolCallId,
                    toolName=e.toolName,
                    input=e.input,
                    requiresApproval=self._effective_requires_approval(e, record),
                )
                for e in siblings
            ],
            {},
            orchestration_ctx=io.orchestration_ctx,
        )
        tool_results = {event.toolCallId: res.result_json, **sibling_results}
        io.emit(format_tool_exec_start(len(tool_results)))
        for tc_id, output in tool_results.items():
            io.emit(format_tool_output(tc_id, output))
        io.emit(format_tool_exec_end(len(tool_results)))
        # NOTE: deliberately no report/inbox drain on this continuation — the
        # old interactive disable branch `continue`d before the report append,
        # and the golden protocol pins that shape.
        return _build_openai_tool_continuation(
            body,
            round_state.assistant_text,
            round_state.tool_input_events,
            tool_results,
        )

    # ── Approval verdict. ─────────────────────────────────────────────────────

    def _effective_requires_approval(
        self, event: ToolInputAvailableEvent, record: ConversationRecord
    ) -> bool:
        """Per-tool approval verdict, with the spawn-consent downgrade: once a
        conversation has approved its first spawn_subagent, later spawns run
        without asking again. Consent memory lives on the record (keyed by
        session id), replacing the old registry + parent-alias lookup."""
        if not tool_requires_user_approval(event):
            return False
        if event.toolName == SPAWN_SUBAGENT_TOOL_NAME and record.spawn_consent_granted:
            return False
        return True
