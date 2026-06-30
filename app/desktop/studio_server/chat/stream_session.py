import asyncio
import json
import logging
import random
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Literal

import httpx
from app.desktop.studio_server.chat.constants import (
    CHAT_TIMEOUT,
    DENIED_TOOL_OUTPUT,
    FUNCTION_NAME_TO_TOOL_ID,
    MAX_TOOL_ROUNDS,
    SSE_TYPE_AUTO_MODE_CONSENT_REQUIRED,
    SSE_TYPE_CHAT_RETRY,
    SSE_TYPE_TOOL_CALLS_PENDING,
    SSE_TYPE_TOOL_EXEC_END,
    SSE_TYPE_TOOL_EXEC_START,
)
from app.desktop.studio_server.chat.sse_parser import EventParser
from app.desktop.studio_server.chat.tool_metadata import (
    _parse_kiln_tool_metadata,
    tool_input_executor_is_server,
    tool_requires_user_approval,
)
from kiln_ai.adapters.model_adapters.stream_events import ToolInputAvailableEvent
from kiln_ai.tools.built_in_tools.disable_auto_mode_tool import (
    DISABLE_AUTO_MODE_TOOL_NAME,
)
from kiln_ai.tools.built_in_tools.enable_auto_mode_tool import (
    ENABLE_AUTO_MODE_TOOL_NAME,
)
from kiln_ai.tools.tool_registry import tool_from_id
from pydantic import BaseModel, ConfigDict, Field

# The tool result the app server resolves an intercepted disable_auto_mode call
# to, fed back to the backend so it continues interactively.
DISABLE_AUTO_MODE_RESULT = json.dumps({"status": "disabled"}, ensure_ascii=False)

logger = logging.getLogger(__name__)


@dataclass
class RoundState:
    """Accumulated state from one upstream round.

    The first four fields are the public per-round outputs the caller reads.
    The trailing two carry the small amount of cross-round/error context that
    ``iter_upstream_round`` needs so it can own the non-200 / RemoteProtocolError
    handling that used to be inline in ``ChatStreamSession.stream()``:

    - ``trace_id_for_error``: the last trace id seen so far (seeded from the
      caller's known trace id), stamped onto error payloads so the UI can
      correlate. ``trace_id`` is the trace id observed *this* round.
    - ``seen_upstream_error``: whether an upstream ``error`` event was already
      forwarded, so a subsequent connection close isn't reported as a duplicate
      generic error.
    """

    finish_tool_calls: bool = False
    tool_input_events: list[ToolInputAvailableEvent] = field(default_factory=list)
    assistant_text: str = ""
    trace_id: str | None = None
    trace_id_for_error: str | None = None
    seen_upstream_error: bool = False
    # Set when iter_upstream_round hit a terminal `error` (non-200 response, or a
    # RemoteProtocolError with no finish boundary). The caller uses this to stop
    # the loop — distinct from a forwarded upstream `error` event, which is
    # non-terminal and leaves the loop free to continue. The payload is normally
    # yielded inline; in ``defer_terminal_error`` mode it is held on
    # ``deferred_error_payload`` instead so the caller can decide whether to retry.
    emitted_terminal_error: bool = False
    # Populated only in ``defer_terminal_error`` mode (the auto runner): the error
    # SSE bytes that would have been yielded, plus the classification the runner
    # needs to decide on a retry. ``error_status_code`` is the upstream HTTP status
    # (None for a connection-level failure); ``error_retryable`` is True for a
    # transient non-200 (429/5xx) that streamed no content and is safe to re-POST.
    deferred_error_payload: bytes | None = None
    error_status_code: int | None = None
    error_retryable: bool = False

    @property
    def is_terminal_upstream_error(self) -> bool:
        """Single source of truth for "this round ended on an upstream error and
        the loop must stop." Two distinct cases collapse here:

        - ``emitted_terminal_error``: iter_upstream_round already yielded a
          terminal error SSE (non-200, or RemoteProtocolError with no finish
          boundary) — nothing left to drive.
        - a forwarded upstream ``error`` event followed by a connection close
          with no tool-call finish boundary (``seen_upstream_error and not
          finish_tool_calls``): the duplicate generic error was suppressed and
          there is nothing more to continue from.

        Both the interactive ``ChatStreamSession.stream()`` and the auto-run
        ``AutoChatRunner`` consult this so the two paths can't drift.
        """
        return self.emitted_terminal_error or (
            self.seen_upstream_error and not self.finish_tool_calls
        )


class ToolCallInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tool_call_id: str = Field(alias="toolCallId")
    tool_name: str = Field(alias="toolName")
    input: dict[str, Any]
    requires_approval: bool = Field(alias="requiresApproval")


def _pending_item_from_event(event: ToolInputAvailableEvent) -> dict[str, Any]:
    meta = _parse_kiln_tool_metadata(event.kiln_metadata)
    item: dict[str, Any] = {
        "toolCallId": event.toolCallId,
        "toolName": event.toolName,
        "input": event.input,
        "requiresApproval": meta.requires_approval is True,
    }
    if meta.permission is not None:
        item["permission"] = meta.permission
    if meta.approval_description is not None:
        item["approvalDescription"] = meta.approval_description
    return item


def _format_tool_calls_pending_sse(events: list[ToolInputAvailableEvent]) -> bytes:
    items = [_pending_item_from_event(e) for e in events]
    payload = {"type": SSE_TYPE_TOOL_CALLS_PENDING, "items": items}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


def _format_consent_required_sse(
    trace_id: str | None,
    enable_tool_call_id: str,
    reason: str | None,
    siblings: list[ToolInputAvailableEvent],
) -> bytes:
    """Format the ``auto-mode-consent-required`` SSE the interactive stream emits
    when the model calls ``enable_auto_mode``.

    ``sibling_tool_calls`` carries any other (non-server) client tool calls from
    the same round so the accept/decline paths can resolve every ``tool_call_id``
    the backend is waiting on. The model is instructed to call ``enable_auto_mode``
    alone, so this is normally empty.
    """
    payload = {
        "type": SSE_TYPE_AUTO_MODE_CONSENT_REQUIRED,
        "trace_id": trace_id,
        "enable_tool_call_id": enable_tool_call_id,
        "reason": reason,
        "sibling_tool_calls": [_pending_item_from_event(e) for e in siblings],
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


# Transient upstream HTTP statuses worth retrying in auto mode (the request never
# produced a streamed response, so re-POSTing is safe). 4xx client errors (400,
# 401, 403, 404, 422) are deliberately excluded — they won't self-heal.
RETRYABLE_UPSTREAM_STATUS: frozenset[int] = frozenset({429, 500, 502, 503, 504})

# A transient upstream failure is retried with backoff rather than surfaced
# immediately, on BOTH the interactive chat stream and the unattended auto runner
# (they share ``iter_round_with_retries``). The schedule ramps up and caps at 60s
# so the run rides out a real remote/network blip (~5 min total) instead of
# burning all attempts in seconds, but still settles instead of hanging forever.
# Per-attempt seconds, 1-based: attempt N uses index N-1, clamped to the last.
_RETRY_BACKOFF_SCHEDULE: tuple[float, ...] = (
    1.0,
    2.0,
    5.0,
    10.0,
    20.0,
    30.0,
    60.0,
    60.0,
    60.0,
    60.0,
)
MAX_CHAT_RETRIES = len(_RETRY_BACKOFF_SCHEDULE)
# ±15% jitter so retries don't align across concurrent streams.
_RETRY_JITTER = 0.15


def _retry_backoff_seconds(attempt: int) -> float:
    """Backoff before retry ``attempt`` (1-based), from the fixed schedule with
    light jitter. Attempts past the schedule clamp to its last (capped) entry."""
    idx = min(attempt, len(_RETRY_BACKOFF_SCHEDULE)) - 1
    base = _RETRY_BACKOFF_SCHEDULE[max(idx, 0)]
    return base * random.uniform(1.0 - _RETRY_JITTER, 1.0 + _RETRY_JITTER)


def format_chat_retry(
    *,
    attempt: int,
    max_attempts: int,
    status_code: int | None = None,
    run_id: str | None = None,
) -> bytes:
    """SSE event emitted between retry attempts so the UI can show "retrying
    N/M…". ``status_code`` is the upstream HTTP status (omitted for a
    connection-level failure); ``run_id`` is present only on the auto stream."""
    payload: dict[str, Any] = {
        "type": SSE_TYPE_CHAT_RETRY,
        "attempt": attempt,
        "max_attempts": max_attempts,
    }
    if status_code is not None:
        payload["status_code"] = status_code
    if run_id is not None:
        payload["run_id"] = run_id
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


async def iter_upstream_round(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    round_state: RoundState,
    defer_terminal_error: bool = False,
) -> AsyncIterator[bytes]:
    """POST one upstream round; yield forward-bytes as they stream; mutate
    ``round_state`` in place.

    Shared by the interactive ``ChatStreamSession.stream()`` and the auto-run
    ``AutoChatRunner``. It owns exactly the per-round upstream mechanics that
    used to be inline in ``stream()``: open the upstream POST, parse the SSE,
    forward the bytes, accumulate ``finish_tool_calls`` / ``tool_input_events`` /
    ``assistant_text`` / ``trace_id`` onto ``round_state``, and handle non-200
    responses and ``RemoteProtocolError`` by yielding the standard ``error`` SSE
    bytes and returning. It does NOT apply any post-round policy (approval gate,
    tool execution, continuation) — that stays caller-specific.

    ``round_state.trace_id_for_error`` should be seeded by the caller with the
    last known trace id before the first round; this generator updates it as new
    trace ids stream in and reads it when building error payloads.
    """
    parser = EventParser()

    async with client.stream(
        "POST",
        url,
        content=json.dumps(body, ensure_ascii=False).encode(),
        headers=headers,
    ) as upstream:
        if upstream.status_code != 200:
            error_body = await upstream.aread()
            detail = "Chat request failed."
            code: str | None = None
            if error_body.startswith(b"{"):
                try:
                    parsed = json.loads(error_body)
                    detail = parsed.get("message", detail) or detail
                    code = parsed.get("code")
                except json.JSONDecodeError:
                    pass
            error_payload: dict[str, Any] = {
                "type": "error",
                "message": detail,
            }
            if code:
                error_payload["code"] = code
            if round_state.trace_id_for_error:
                error_payload["trace_id"] = round_state.trace_id_for_error
            round_state.emitted_terminal_error = True
            error_bytes = (
                f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n".encode()
            )
            if defer_terminal_error:
                # Don't surface the error yet — hand it to the caller (the auto
                # runner) with the status so it can retry transient failures and
                # only emit on give-up. No content streamed at this point, so a
                # retryable status is safe to re-POST.
                round_state.deferred_error_payload = error_bytes
                round_state.error_status_code = upstream.status_code
                round_state.error_retryable = (
                    upstream.status_code in RETRYABLE_UPSTREAM_STATUS
                )
                return
            yield error_bytes
            return

        try:
            async for chunk in upstream.aiter_bytes():
                result = parser.parse(chunk)
                if result.has_error_event:
                    round_state.seen_upstream_error = True
                if result.finish_tool_calls:
                    round_state.finish_tool_calls = True
                round_state.tool_input_events.extend(result.tool_input_events)
                round_state.assistant_text += result.text_delta
                if result.chat_trace_id is not None:
                    round_state.trace_id = result.chat_trace_id
                    round_state.trace_id_for_error = result.chat_trace_id
                if result.lines_to_forward:
                    yield b"\n".join(result.lines_to_forward) + b"\n"
        except httpx.RemoteProtocolError:
            if round_state.finish_tool_calls:
                logger.debug(
                    "Connection closed after streamed tool boundary "
                    "(AI SDK tool-calls finish; expected)"
                )
            elif round_state.seen_upstream_error:
                # we already passed on an error coming out of upstream server, the UI should be rendering it
                # we don't need to also tell it the stream was closed by the upstream server
                logger.debug(
                    "Connection closed after upstream error event; "
                    "suppressing duplicate error"
                )
            else:
                trace_id = round_state.trace_id_for_error or str(uuid.uuid4())
                error_payload = {
                    "type": "error",
                    "message": "Something went wrong.",
                    "trace_id": trace_id,
                }
                round_state.emitted_terminal_error = True
                error_bytes = f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n".encode()
                if defer_terminal_error:
                    # Hold for the caller. error_retryable stays False: the stream
                    # already dropped mid-round (possibly after partial content),
                    # so re-POSTing is not safe to do blindly.
                    round_state.deferred_error_payload = error_bytes
                else:
                    yield error_bytes
                logger.exception(
                    "RemoteProtocolError during streaming (trace_id=%s)",
                    trace_id,
                )


@dataclass
class RetryRoundResult:
    """Outcome of ``iter_round_with_retries``, reported back to the caller after
    the generator is exhausted (an async generator can't return a value):

    - ``status == "ok"``: ``round_state`` is the successful attempt's state —
      the caller continues its round loop.
    - ``status == "stopped"``: a Stop was requested mid-retry (auto runner only)
      — the caller settles ``USER_STOPPED``.
    - ``status == "error"``: a non-retryable or retry-exhausted failure; the
      error was already yielded — the caller ends the stream.
    """

    status: Literal["ok", "stopped", "error"] = "error"
    round_state: RoundState | None = None


async def iter_round_with_retries(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    trace_id_for_error: str | None,
    result: RetryRoundResult,
    *,
    run_id: str | None = None,
    stop_requested: Callable[[], bool] | None = None,
) -> AsyncIterator[bytes]:
    """Stream one upstream round, retrying transient failures with backoff.

    Shared by the interactive ``ChatStreamSession.stream()`` and the unattended
    ``AutoChatRunner`` so both get identical retry behavior. Yields forward bytes
    as they stream, plus a ``kiln-chat-retry`` event between attempts and, on
    give-up, the held-back error. The terminal outcome is reported via ``result``.

    Only failures that streamed NO content this attempt are retried (a non-200
    caught before any bytes, or a pre-response connection error), so a retry can
    never duplicate already-emitted output. ``defer_terminal_error`` holds the
    error back until we either retry past it or give up.

    ``stop_requested`` (auto runner only) is polled each round so a Stop pressed
    mid-retry abandons the loop with ``status == "stopped"``.
    """
    attempt = 0
    while True:
        round_state = RoundState(trace_id_for_error=trace_id_for_error)
        result.round_state = round_state
        emitted_any = False
        transport_error = False
        try:
            async for payload in iter_upstream_round(
                client, url, headers, body, round_state, defer_terminal_error=True
            ):
                emitted_any = True
                yield payload
        except httpx.HTTPError:
            # Pre-response connection/timeout failure (RemoteProtocolError is
            # handled inside iter_upstream_round). A ReadTimeout after the POST
            # may re-trigger a duplicate upstream generation, but no tools run
            # until bytes stream, so the accepted blast radius is a wasted
            # generation, never duplicated side effects.
            transport_error = True

        if not transport_error and not round_state.is_terminal_upstream_error:
            result.status = "ok"
            return

        streamed_content = (
            emitted_any
            or round_state.trace_id is not None
            or bool(round_state.assistant_text)
            or bool(round_state.tool_input_events)
        )
        retryable = not streamed_content and (
            transport_error or round_state.error_retryable
        )
        stop = stop_requested() if stop_requested is not None else False
        if retryable and attempt < MAX_CHAT_RETRIES and not stop:
            attempt += 1
            yield format_chat_retry(
                attempt=attempt,
                max_attempts=MAX_CHAT_RETRIES,
                status_code=round_state.error_status_code,
                run_id=run_id,
            )
            await asyncio.sleep(_retry_backoff_seconds(attempt))
            continue

        # Stop takes precedence over surfacing the error (auto runner only).
        if stop:
            result.status = "stopped"
            return
        # Give up: surface the held-back error (the suppressed-duplicate terminal
        # case has nothing deferred and yields nothing) and end the stream.
        if round_state.deferred_error_payload is not None:
            yield round_state.deferred_error_payload
        elif transport_error:
            error_payload = {
                "type": "error",
                "message": "Something went wrong.",
                "trace_id": round_state.trace_id_for_error or str(uuid.uuid4()),
            }
            yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n".encode()
        result.status = "error"
        return


async def execute_tool_batch(
    tool_calls: list[ToolCallInfo],
    decisions: dict[str, bool],
) -> dict[str, str]:
    results: dict[str, str] = {}
    for tc in tool_calls:
        if tc.requires_approval:
            approved = decisions.get(tc.tool_call_id)
            if approved is not True:
                results[tc.tool_call_id] = DENIED_TOOL_OUTPUT
                continue
        tool_result = await execute_tool(tc.tool_name, tc.input)
        results[tc.tool_call_id] = tool_result
    return results


class ChatStreamSession:
    """Owns the multi-round streaming loop for a single chat request."""

    def __init__(
        self,
        upstream_url: str,
        headers: dict[str, str],
        initial_body: dict[str, Any],
    ) -> None:
        self._upstream_url = upstream_url
        self._headers = headers
        self._body = initial_body
        self._initial_trace_id: str | None = initial_body.get("trace_id")

    async def stream(self):
        """AsyncGenerator yielding SSE bytes to the client."""
        trace_id_for_error: str | None = self._initial_trace_id
        async with httpx.AsyncClient(timeout=CHAT_TIMEOUT) as client:
            for _ in range(MAX_TOOL_ROUNDS):
                # Retry transient upstream failures (rate limit / 5xx / connection)
                # with backoff, emitting kiln-chat-retry events the UI renders as
                # "retrying N/M…", instead of surfacing the error immediately.
                result = RetryRoundResult()
                async for forward_bytes in iter_round_with_retries(
                    client,
                    self._upstream_url,
                    self._headers,
                    self._body,
                    trace_id_for_error,
                    result,
                ):
                    yield forward_bytes

                round_state = result.round_state
                if round_state is not None:
                    trace_id_for_error = round_state.trace_id_for_error

                # A non-retryable or retry-exhausted upstream error: the error SSE
                # was already yielded — nothing more to drive, end the stream.
                # ("stopped" is auto-runner-only and never occurs here.)
                if result.status != "ok" or round_state is None:
                    return

                if round_state.trace_id:
                    self._body = {
                        **self._body,
                        "trace_id": round_state.trace_id,
                        "messages": [],
                    }

                if round_state.finish_tool_calls:
                    client_events = [
                        e
                        for e in round_state.tool_input_events
                        if not tool_input_executor_is_server(e)
                    ]

                    # enable_auto_mode interception (architecture §3.4): the model
                    # asked to enable auto mode. Surface a consent request and
                    # return WITHOUT executing it — enable_auto_mode is a signal,
                    # never run as a tool. Accept/decline is handled out-of-band by
                    # the auto-mode endpoints. This must run before the approval
                    # gate so the consent UI takes precedence.
                    enable_evt = next(
                        (
                            e
                            for e in client_events
                            if e.toolName == ENABLE_AUTO_MODE_TOOL_NAME
                        ),
                        None,
                    )
                    if enable_evt is not None:
                        siblings = [e for e in client_events if e is not enable_evt]
                        yield _format_consent_required_sse(
                            trace_id=round_state.trace_id,
                            enable_tool_call_id=enable_evt.toolCallId,
                            reason=enable_evt.input.get("reason"),
                            siblings=siblings,
                        )
                        return

                    # disable_auto_mode interception (architecture §13.3): never
                    # execute it. Clear the conversation auto-mode flag (publishing
                    # auto-mode-off(user_disabled) to any observer), resolve the
                    # call as {"status":"disabled"}, and CONTINUE streaming
                    # interactively so the backend proceeds without auto mode. Any
                    # siblings in the same turn are executed through the normal
                    # approval gate (requiresApproval per tool) — on this
                    # interactive path consent still applies. The model is
                    # instructed to call disable_auto_mode alone so siblings are
                    # normally empty.
                    disable_evt = next(
                        (
                            e
                            for e in client_events
                            if e.toolName == DISABLE_AUTO_MODE_TOOL_NAME
                        ),
                        None,
                    )
                    if disable_evt is not None:
                        await self._clear_auto_mode_flag(round_state.trace_id)
                        non_disable = [e for e in client_events if e is not disable_evt]
                        # Interactive path: gate siblings normally. A sibling that
                        # requires approval is denied here (no decisions passed, so
                        # execute_tool_batch returns DENIED_TOOL_OUTPUT) rather than
                        # run without consent. Auto-mode auto-approval is the
                        # runner's job, not this path's.
                        sibling_results = await execute_tool_batch(
                            [
                                ToolCallInfo(
                                    toolCallId=e.toolCallId,
                                    toolName=e.toolName,
                                    input=e.input,
                                    requiresApproval=tool_requires_user_approval(e),
                                )
                                for e in non_disable
                            ],
                            {},
                        )
                        tool_results = {
                            disable_evt.toolCallId: DISABLE_AUTO_MODE_RESULT,
                            **sibling_results,
                        }
                        yield self._format_tool_exec_start(len(tool_results))
                        for tc_id, output in tool_results.items():
                            yield self._format_tool_output(tc_id, output)
                        yield self._format_tool_exec_end(len(tool_results))
                        self._body = _build_openai_tool_continuation(
                            self._body,
                            round_state.assistant_text,
                            round_state.tool_input_events,
                            tool_results,
                        )
                        continue

                    needs_approval = [
                        e for e in client_events if tool_requires_user_approval(e)
                    ]
                    if needs_approval:
                        yield _format_tool_calls_pending_sse(client_events)
                        return

                    expected_tool_count = len(client_events)
                    yield self._format_tool_exec_start(expected_tool_count)
                    tool_results = await self._execute_client_tools(round_state, None)
                    for tc_id, output in tool_results.items():
                        yield self._format_tool_output(tc_id, output)
                    yield self._format_tool_exec_end(len(tool_results))

                    if not tool_results:
                        return

                    self._body = _build_openai_tool_continuation(
                        self._body,
                        round_state.assistant_text,
                        round_state.tool_input_events,
                        tool_results,
                    )
                    continue

                return

        # Loop exhausted all MAX_TOOL_ROUNDS without a natural exit
        error_payload = {
            "type": "error",
            "message": "Maximum tool rounds exceeded. Please start a new message.",
        }
        if trace_id_for_error:
            error_payload["trace_id"] = trace_id_for_error
        yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n".encode()

    async def _execute_client_tools(
        self,
        round_state: RoundState,
        approval_decisions: dict[str, bool] | None,
    ) -> dict[str, str]:
        tool_calls: list[ToolCallInfo] = []
        for event in round_state.tool_input_events:
            if tool_input_executor_is_server(event):
                logger.debug(
                    "Skipping local tool execution (executor=server): %s (call_id=%s)",
                    event.toolName,
                    event.toolCallId,
                )
                continue
            tool_calls.append(
                ToolCallInfo(
                    toolCallId=event.toolCallId,
                    toolName=event.toolName,
                    input=event.input,
                    requiresApproval=tool_requires_user_approval(event),
                )
            )
        return await execute_tool_batch(tool_calls, approval_decisions or {})

    @staticmethod
    async def _clear_auto_mode_flag(trace_id: str | None) -> None:
        """Clear the conversation's auto-mode flag for an intercepted
        disable_auto_mode call. Imported lazily to avoid a circular import
        (the auto registry depends on this module's round mechanics)."""
        if not trace_id:
            return
        from app.desktop.studio_server.chat.auto.registry import auto_chat_registry

        await auto_chat_registry.disable_for_trace(trace_id)

    @staticmethod
    def _format_tool_output(tc_id: str, output: str) -> bytes:
        return f"data: {json.dumps({'type': 'tool-output-available', 'toolCallId': tc_id, 'output': output}, ensure_ascii=False)}\n\n".encode()

    @staticmethod
    def _format_tool_exec_start(tool_count: int) -> bytes:
        payload = {"type": SSE_TYPE_TOOL_EXEC_START, "tool_count": tool_count}
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()

    @staticmethod
    def _format_tool_exec_end(tool_count: int) -> bytes:
        payload = {"type": SSE_TYPE_TOOL_EXEC_END, "tool_count": tool_count}
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


async def execute_tool(tool_name: str, args: dict[str, Any]) -> str:
    """Run a Kiln built-in tool by OpenAI function name; return its output string."""
    logger.info("Executing server tool %s", tool_name)
    args_str = json.dumps(args, default=str, ensure_ascii=False)
    logger.debug("Tool %s args: %.500s", tool_name, args_str)
    tool_id = FUNCTION_NAME_TO_TOOL_ID.get(tool_name)
    if tool_id is None:
        return json.dumps(
            {"error": f"Unknown tool name: {tool_name}"}, ensure_ascii=False
        )
    try:
        tool = tool_from_id(tool_id)
        result = await tool.run(**args)
        return result.output
    except Exception as e:
        logger.exception("Built-in tool %s failed", tool_name)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _build_openai_tool_continuation(
    original_body: dict[str, Any],
    assistant_text: str,
    tool_input_events: list[ToolInputAvailableEvent],
    tool_results_by_call_id: dict[str, str],
) -> dict[str, Any]:
    """Build the request body for continuing after server-side AI SDK tool calls.

    Appends an ``assistant`` message with ``tool_calls`` (when there are local
    results) followed by one ``role: tool`` message per call that has an entry
    in *tool_results_by_call_id*, matching the OpenAI message schema the
    backend's ``convert_to_openai_messages`` expects.

    Only tool calls with a local result appear; upstream-only calls are omitted
    entirely rather than sent with empty ``content``.
    """
    local_events = [
        e for e in tool_input_events if e.toolCallId in tool_results_by_call_id
    ]

    tool_messages: list[dict[str, Any]] = []
    for event in local_events:
        tc_id = event.toolCallId
        tool_content = tool_results_by_call_id[tc_id]
        tool_messages.append(
            {
                "role": "tool",
                "tool_call_id": tc_id,
                "content": tool_content,
            }
        )

    prior_messages = list(original_body.get("messages", []))
    trace_only_continuation = bool(original_body.get("trace_id")) and not prior_messages

    if trace_only_continuation:
        new_messages = tool_messages
    else:
        tool_calls: list[dict[str, Any]] = []
        for event in local_events:
            tc_id = event.toolCallId
            tool_name = event.toolName
            args_str = json.dumps(event.input, ensure_ascii=False)
            tool_calls.append(
                {
                    "id": tc_id,
                    "type": "function",
                    "function": {"name": tool_name, "arguments": args_str},
                }
            )
        content: str | None = (
            assistant_text if assistant_text and assistant_text.strip() else None
        )
        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": content,
        }
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls
        new_messages = prior_messages + [assistant_msg] + tool_messages

    return {**original_body, "messages": new_messages}
