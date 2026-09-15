---
status: complete
---

# Phase 6: Engine — conversation-scoped auto-mode (persist + inject + disable)

## Overview

Revision R1 decouples the conversation auto-mode FLAG from a single burst's liveness. The flag now
persists across bursts (idle between them), messages can be injected into an active burst or start a
new one when idle, and `disable_auto_mode` (new libs/core tool) is intercepted to turn the flag off.
libs/core + app server only (no web UI, no kiln_server).

## Steps

1. **libs/core `DisableAutoModeTool`** — mirror `enable_auto_mode_tool.py`:
   `KilnBuiltInToolId.DISABLE_AUTO_MODE`, `tool_registry.py` case, `disable_auto_mode` name, optional
   `reason`, signal-only `run()` returning `{"status":"disabled"}` (ensure_ascii=False), export
   `DISABLE_AUTO_MODE_TOOL_NAME`. NOT added to app server FUNCTION_NAME_TO_TOOL_ID. (done)

2. **models.py** — add `AutoRunStatus.IDLE` (flag-on, burst settled) and `USER_DISABLED` (off via
   tool). Add `flag_on` helper (RUNNING or IDLE). Add `InboundMessage` model (the queued user
   message + trace_id).

3. **constants.py + sse.py** — add `SSE_TYPE_AUTO_MODE_IDLE = "auto-mode-idle"`; add
   `format_auto_mode_idle(run_id, reason)` and `format_user_message(...)` echo helper.

4. **runner.py** — drain-before-idle: the runner takes an `inbound` queue accessor. At each round
   boundary, drain queued user messages and append them (`role:"user"`) to the continuation built via
   `_build_openai_tool_continuation`. Before settling on a plain-text handoff (no tool calls), check
   the queue: if a message is queued, continue with it as a fresh turn instead of going idle. Add
   `disable_auto_mode` interception in the round handler: clear flag, resolve tool result, end burst.
   Track `disabled` flag/reason for the supervisor. Burst-end statuses become IDLE-routing reasons.

5. **registry.py** — entry persists across bursts. `_supervise` happy-path → IDLE + `auto-mode-idle`
   (reason from runner), NOT auto-mode-off, NOT evicted. `auto-mode-off` + GC only on USER_STOPPED /
   USER_DISABLED. `run_id_for_trace` / `is_active_for_trace` reflect flag_on (RUNNING or IDLE). Add
   `send_message(run_id, message)`: enqueue if RUNNING, start new burst (reuse seed path) if IDLE.
   Add `disable(run_id)` for the runner-intercept path. Terminal GC only for off runs.

6. **api.py** — `POST /api/chat/auto/{run_id}/message` (body: user message + trace_id): echo onto
   bus + buffer, then `registry.send_message`. `/stop` → user_stopped.

7. **stream_session.py** — intercept `disable_auto_mode` in the interactive post-round handler:
   clear the conversation flag (registry.disable_for_trace), publish auto-mode-off(user_disabled),
   resolve tool result `{"status":"disabled"}` and CONTINUE interactively (do not return).

## Tests

- libs/core: DisableAutoModeTool metadata/schema/run; tool_registry case. (done)
- runner: IDLE transition on plain-text handoff (flag stays on, auto-mode-idle emitted, entry not
  evicted, is_active_for_trace still true); inject-at-boundary (queued user message appears in the
  continuation body); drain-before-idle (message queued exactly as burst settles is not dropped);
  disable_auto_mode interception in runner (flag cleared, off(user_disabled), tool result resolved,
  not executed).
- registry: send_message on idle starts a new burst; auto-mode-off only on stop/disable; GC only off.
- stream_session: disable_auto_mode interception (flag cleared, off(user_disabled), resolved,
  continues interactively, not executed).
- api: /message injects/starts burst; /stop => off(user_stopped).
- Golden interactive-unchanged test stays green.
