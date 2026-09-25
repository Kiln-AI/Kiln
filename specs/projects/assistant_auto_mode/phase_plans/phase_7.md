---
status: complete
---

# Phase 7: Web UI — inject-on-send + persistent flag + loading-indicator fix

## Overview

Revision R1 web UI: sends while auto-mode is on inject into the server-owned run
(no interrupt/stop), the indicator + Stop bind to the conversation auto-mode flag
(persisting across IDLE bursts), consent is requested only once per conversation,
and the in-transcript loading affordances (thinking dots / animated icon) drive
off the same logic during auto bursts as during normal streaming. Web UI only;
the Phase 6 app-server endpoints + `auto-mode-idle` event already exist.

## Steps

1. `streaming_chat.ts` — add `content?: string` to `StreamEvent` (carries the
   `user-message` echo).
2. `auto_run_store.ts`:
   - Add a `working` store (burst RUNNING vs IDLE) + `setWorking()` that mirrors
     to the sink.
   - Extend `AutoRunChatSink` with `onWorkingChange`, `onUserMessage`,
     `onAutoModeIdle`.
   - Handle control events: `auto-mode-on` → on + working; `auto-mode-idle` →
     stay on, working off, `onAutoModeIdle`; `auto-mode-off` → clear; new
     `user-message` → working on + `onUserMessage`. `attach` presumes working
     (idle replay clears it). `detach`/`clearToOff` clear working.
   - Add `sendMessage(text, traceId)` → `POST /api/chat/auto/{run_id}/message`
     (`{content, trace_id}`); sets working optimistically; never stops.
3. `chat_session_store.ts`:
   - Add `autoWorking` to `ChatSessionState`; wire `onWorkingChange`,
     `onUserMessage` (append user turn + fresh assistant turn), `onAutoModeIdle`
     (clear working/tool/activity).
   - `sendMessage`: when `autoModeOn`, route to `autoRunStore.sendMessage`
     (inject) instead of `beginStreaming`/`stop`; surface failures inline.
     Keep the `status !== "ready"` guard for the interactive path only.
4. `chat.svelte`:
   - `transcriptLoading = isLoading || autoWorking`; swap the transcript
     indicator gates (`showStreamingCursor`, `isMessageVisible`,
     `isStepGroupLoading`, the `isActiveMessage` consts, the `ChatStatusSteps`
     `isLoading` prop) to `transcriptLoading`. Input/Stop/send stay on
     `isLoading` so the textarea stays usable for inject.
   - Footer: pulse only while working; show "· waiting for you" sub-state while
     idle. Indicator already binds to `$autoModeOn` (now persists across idle).

## Tests

- auto_run_store: `auto-mode-idle` keeps flag on / clears working; only
  `auto-mode-off` clears after idle; `sendMessage` posts to `/message` (never
  `/stop`); `sendMessage` with no run errors; `user-message` echo renders + marks
  working.
- chat_session_store: inject via auto run (not `/api/chat`), never stopping;
  no auto-mode consent re-prompt while on; injects even when interactive status
  not ready; inline error on inject failure; `autoWorking` driven by the bound
  sink and cleared on idle/off; echoed user message rendered as a fresh turn.
