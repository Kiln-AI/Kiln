---
status: complete
---

# Phase 9: Reattach loading state + live working/idle on attach

## Overview

When a conversation reattaches to an active auto run (hard-refresh `resyncOnLoad`
OR History restore), the UI used to look fully loaded/idle until the next event
happened to arrive — so a burst mid-think (model thinking server-side, momentarily
between events) showed no activity. This phase (a) surfaces the run's CURRENT
working/idle liveness on attach so the UI reflects true state immediately, and
(b) shows a transient "Reconnecting…" affordance during the resolve→hydrate→attach
window.

## Steps

1. **App server — on-subscribe liveness marker.**
   - `constants.py`: add `SSE_TYPE_AUTO_MODE_STATE = "auto-mode-state"`.
   - `auto/sse.py`: add `format_auto_mode_state(run_id, *, flag_on, working)`.
   - `auto/registry.py` (`AutoChatRun`): add `state_marker_bytes()` (working iff
     status RUNNING).
   - `auto/events.py` (`AutoChatEventBus.subscribe`): after the buffer replay, for
     a RUNNING run emit the state marker (the buffer may be empty mid-think); IDLE
     keeps emitting its existing idle marker; terminal keeps the off marker. No
     double-fire.

2. **App server — resolve returns status.**
   - `auto/registry.py`: `resolve_trace` returns `(run_id, current_trace_id,
     status)`.
   - `auto/api.py`: `ResolveAutoResponse` gains `status: AutoRunStatus`; endpoint
     returns it. Regenerate `api_schema.d.ts`.

3. **Web UI — reconnecting state + on-attach liveness.**
   - `streaming_chat.ts` `StreamEvent`: add `flag_on?`, `working?`.
   - `auto_run_store.ts`: add `reconnecting` store + `beginReconnect()`; handle
     `auto-mode-state` (set working/flag, clear reconnecting); clear reconnecting
     on open / first event / idle / off / error / detach; `attach(runId,
     initialWorking?)` drives working from the surfaced liveness.
   - `chat_session_store.ts` `resyncOnLoad`: `beginReconnect()` after resolve
     succeeds; `attach(run_id, status === "running")`.
   - `chat_history.svelte` restore path: `beginReconnect()` before `attach`.
   - `chat.svelte`: subscribe `auto_run_store.reconnecting`; fold into
     `transcriptLoading`; render a small "Reconnecting…" BrailleSpinner row.

4. **Can't-get-stuck guarantees:** reconnecting clears on attach-established,
   error/404, off, idle, detach. Normal (non-reattach) enable flow never sets it.

## Tests

- `test_subscribe_emits_working_state_marker_for_running_mid_think` — RUNNING with
  empty buffer → working state marker.
- `test_subscribe_emits_idle_marker_for_idle_run` / `_for_armed_run` — idle marker,
  no state marker.
- resolve registry/api tests assert the `status` field (running / idle).
- auto_run_store: beginReconnect/attach-clears-on-open, clears-on-first-event,
  initialWorking drives indicator, state snapshot sets working+clears reconnecting,
  clears on 404/off/detach; resolve returns status.
- chat_session_store: resyncOnLoad calls beginReconnect + attach(run_id, working);
  no beginReconnect on 404.
