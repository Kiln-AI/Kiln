---
status: complete
---

# Phase 4: Web UI

## Overview

Add the browser-side experience for assistant auto-mode on the existing assistant chat page.
The app-server endpoints (Phase 3) already exist and `api_schema.d.ts` already carries the new
endpoints/fields. This phase builds:

1. `auto_run_store.ts` — owns the auto-run lifecycle for the active conversation (enable / decline
   / stop / attach), feeding the per-run SSE into the EXISTING `StreamEventProcessor` and handling
   the `auto-mode-on` / `auto-mode-off` control events. Mirrors the connection handling in
   `jobs_store.ts`.
2. `chat_session_store.ts` integration — surface `auto-mode-consent-required` from the interactive
   stream, open a consent dialog, and hand off to the auto-run store on accept / call decline on
   cancel. Interrupt-on-send while auto-mode is on.
3. `auto_mode_consent_dialog.svelte` — blocking `Dialog` with the copy from ui_design §3 (shows the
   model reason when present); Accept → enable, Cancel → decline.
4. Footer block in `chat.svelte` near `ChatCostDisclaimer` — muted "⏵⏵ Auto mode" ghost (off) ↔
   green "⏵⏵ auto mode on · Stop" (on), bound to the auto-run store.
5. `chat_history.svelte` — green dot + "Working…" on `auto_active` rows, a "Working now" group above
   the rest, and re-attach (`selectSession` then `auto_run_store.attach`) on selecting an active row.

`api_schema.d.ts` is already current (verified — has `/api/chat/auto/*`, `auto_active`,
`auto_run_id`, `EnableAutoRequest`, `DeclineAutoRequest`, `AutoSessionItem`). No regen needed;
re-run the generator only if a check shows drift.

## Steps

1. **Export reusable streaming pieces** from `lib/chat/streaming_chat.ts`:
   - Export `StreamEventProcessor` (currently module-private) and its options type
     `StreamEventProcessorOptions`.
   - Export a small `parseSseLines(buffer, onEvent)` style helper OR reuse the existing inline
     parsing by extracting a `consumeSseStream(reader, processor, { onControlEvent })` async fn that
     reads a `ReadableStreamDefaultReader`, decodes, splits on `\n`, JSON-parses `data:` lines, and
     dispatches each event to `processor.handleEvent` unless a caller-provided `onControlEvent`
     claims it (returns true). This is what the decline interactive-resume path reuses; the
     EventSource path reuses just the processor + control handling.
   - Keep `streamChat` behavior byte-for-byte unchanged (it can be refactored to call the shared
     consumer, but only if safe; otherwise leave it and just export the processor).

2. **`lib/chat/auto_run_store.ts`** (new). `createAutoRunStore()` returning a singleton
   `auto_run_store`. Public API:
   - `autoModeOn: Readable<boolean>`, `runId: Readable<string | null>`,
     `offReason: Readable<string | null>`, `connection: Readable<AutoConnection>`.
   - `bind(sink: AutoRunChatSink)` — chat_session_store registers the message-driving callbacks
     (`onAssistantMessage`, `onChatTrace`, `onInlineError`, `onToolExecutionStart`,
     `onToolExecutionEnd`, `onShowActivityIndicator`, `beginAssistantTurn`, `onAutoModeOff`).
   - `requestEnable(seed: EnableAutoRequest): Promise<{ ok: boolean; error?: string }>` — POST
     `/api/chat/auto/enable`; on `{ run_id }` start a turn (`sink.beginAssistantTurn()`) and
     `attach(run_id)`. On 429 / error return `{ ok: false, error }` (consent dialog surfaces it).
   - `decline(req: DeclineAutoRequest): Promise<void>` — POST `/api/chat/auto/decline`, then consume
     the returned interactive stream with the shared SSE consumer feeding the sink (same as
     streamChat's reader path). Begins a fresh assistant turn first.
   - `stop(): Promise<void>` — POST `/api/chat/auto/{runId}/stop` for the current run; optimistic —
     the authoritative clear comes from `auto-mode-off`.
   - `attach(runId: string): void` — open `EventSource('/api/chat/auto/{runId}/events')`, set
     `autoModeOn`/`runId`, feed `message` events into the processor; handle `auto-mode-on`
     (set on) and `auto-mode-off` (clear + record `offReason`, call `sink.onAutoModeOff`). On
     EventSource error: if the connection never opened treat as a 404/gone fallback → clear to off
     (re-attach to a GC'd run), matching ui_design §5; if it had opened, the run may have ended —
     clear to off. No reconnect loop (a finished run won't come back; a transient drop lands in the
     hydrated-history off state, which is safe).
   - Internal `_close()` closes the EventSource; `_clearToOff(reason)` resets stores.
   - Module logger-style `console` not needed; keep quiet like jobs_store.

3. **`lib/chat/chat_session_store.ts`** integration:
   - Add `onAutoModeConsentRequired: ((payload) => Promise<boolean>) | null` settable hook (like
     `onConsentNeeded`). Payload carries `trace_id`, `enable_tool_call_id`, `reason`,
     `sibling_tool_calls`.
   - In `beginStreaming`, pass a new `onAutoModeConsentRequired` callback to `streamChat` (added to
     `StreamChatOptions`). `streamChat` recognizes the `auto-mode-consent-required` event, calls the
     callback (await), and `return`s the stream (same shape as `tool-calls-pending`). The store's
     callback opens the consent dialog; on accept it calls `auto_run_store.requestEnable(seed)` and
     on cancel `auto_run_store.decline(req)`.
   - `bind` the chat sink to `auto_run_store` once at store creation: `auto_run_store.bind({...})`
     wiring `onAssistantMessage → updateLastAssistant`, `onChatTrace → set traceId on last
     assistant`, `onInlineError → push error message`, the tool/activity flags → combined updates,
     `beginAssistantTurn → append a fresh empty assistant message + clear flags`, `onAutoModeOff →
     clear flags` (runtime stays "ready"; the conversation is already persisted server-side).
   - `sendMessage` interrupt-on-send: if `get(auto_run_store.autoModeOn)`, call
     `auto_run_store.stop()` first, then proceed to send interactively (existing path). Continuation
     trace id comes from the latest assistant `traceId` as today (the auto run has been advancing it
     via `onChatTrace`).
   - `loadSession`/`reset` do not need to touch the auto store directly (attach is driven from
     history); but `reset` should not clobber an active run's UI — keep minimal, matching existing
     behavior.

4. **`routes/(app)/assistant/auto_mode_consent_dialog.svelte`** (new). Uses `$lib/ui/dialog.svelte`.
   - `prompt(payload): Promise<boolean>` returns true on accept, false on cancel/dismiss (mirrors
     `chat_cost_disclaimer.svelte`).
   - Title "Turn on auto mode?"; body copy verbatim from ui_design §3; when `payload.reason` is set,
     a quoted callout: *"The assistant suggests auto mode to: {reason}."* above the bullets.
   - Buttons Cancel (`isCancel`) and "Turn on auto mode" (`isPrimary`). Cancel / backdrop / Escape /
     close → resolve(false). Accept → resolve(true).
   - Optional `error` text slot area for a 429 message (consent stays open if enable fails).

5. **`routes/(app)/assistant/chat.svelte`** footer + wiring:
   - Import `auto_run_store` + `AutoModeConsentDialog`. Add `let consentDialog` and wire
     `store.onAutoModeConsentRequired = async (payload) => { ... consentDialog.prompt(payload) ...
     enable/decline ... }`.
   - Footer row directly under the `<form>`, in the same zone as the cost disclaimer. Off: muted
     `btn btn-ghost btn-xs` "⏵⏵ Auto mode" with tooltip; click → open consent for the manual path
     (seed = `{ trace_id: continuation }`); disabled if there is no conversation yet / while loading.
     On: green `text-success` "⏵⏵ auto mode on" with a gently pulsing glyph + a Stop ghost link
     (error-tinted) calling `auto_run_store.stop()`. Convey state with text, not color alone.
   - Render `ChatCostDisclaimer` placement unchanged; the auto row sits in the footer zone and wraps
     on narrow widths.

6. **`routes/(app)/assistant/chat_history.svelte`**:
   - Split `sessionRows` into `activeRows` (`auto_active`) and `recentRows`. If any active, render a
     "Working now" section header, the active rows, a divider, then "Recent" + the rest. Else flat
     list as today.
   - Active row: green pulsing dot (`size-2 rounded-full bg-success`) with
     `aria-label="Auto mode running"` + tooltip before the title; date column shows "Working…" in
     `text-success` instead of the timestamp.
   - On selecting an active row, after `selectSession` (hydrate) call
     `auto_run_store.attach(row.auto_run_id)` (guard on presence).
   - Keep the list fresh while open via the existing fetch on open (no new poll needed for this
     phase; cheap and matches "no sub-second accuracy").

7. **Schema**: verify `npm run check` is clean against the committed `api_schema.d.ts`. Only run the
   generator if drift appears.

## Tests

`auto_run_store.test.ts` (jsdom, mock `EventSource` + `fetch`, mock `$lib/api_client` base_url):
- `enable → attach → events feed into processor`: requestEnable POSTs enable, opens events
  EventSource at the right URL, an `auto-mode-on` message sets `autoModeOn`, a `text-delta` message
  drives `sink.onAssistantMessage`.
- `auto-mode-off clears state`: off message clears `autoModeOn`/`runId`, records `offReason`, calls
  `sink.onAutoModeOff`, closes the EventSource.
- `stop`: POSTs `/api/chat/auto/{runId}/stop`; state remains until the off event arrives.
- `decline`: POSTs `/api/chat/auto/decline` with the right body, consumes the returned interactive
  SSE stream into the sink (a `text-delta` reaches `onAssistantMessage`).
- `re-attach (hydrate + attach)`: attach to a run id directly opens the events stream and replayed
  buffered events feed the processor with no gap (simulate buffered `text-delta` then live).
- `events 404 fallback`: enable returns run_id but the events EventSource errors before open →
  clears to off without throwing (UI lands in hydrate-only/off).
- `enable 429`: requestEnable returns `{ ok: false, error }` and does not open an EventSource.
- pure-observer: closing the events stream (off / error) never POSTs stop.

`auto_mode_consent_dialog.test.ts` (jsdom, @testing-library/svelte):
- accept resolves `prompt` true; cancel/close resolves false; the reason callout renders only when
  `reason` is present.

`chat_history` grouping (unit on a small pure helper `splitSessionRows(rows)` extracted from the
component): rows with `auto_active` go to the active group, the rest to recent; ordering preserved;
no active → empty active group.
