---
status: complete
---

# Phase 10: Enable auto-mode on a brand-new conversation (Revision R2)

## Overview

Make the footer "Auto mode" toggle usable before any message is sent. On a
brand-new conversation there is no `trace_id` to key a server run, so enabling
arms auto-mode client-side (indicator on, no server call). The user's FIRST
message then creates the server-owned run seeded with that message and no
`trace_id` — the backend starts a fresh conversation and mints the first trace —
so the very first turn runs in auto-mode. No empty turn is ever POSTed.
Existing-conversation behavior (Phases 7/9) is unchanged.

## Steps

1. **`models.py`** — `AutoChatSeed.trace_id` → `str | None = None`;
   `AutoRunRecord.current_trace_id` → `str | None = None` (no leaf until the
   first `kiln_chat_trace`).
2. **`runner.py`** — `_build_seed_body` omits `trace_id` when absent (returns
   `{"messages": ...}`) so the backend starts a fresh conversation.
3. **`registry.py`** — `start` accepts a no-trace seed: no `_trace_index` entry
   and empty `seen_trace_ids` until the first trace; `is_armed_only` already
   requires no `extra_messages`, so a no-trace seed carrying the first message
   starts RUNNING (real content), not the armed-only IDLE case. `resolve_trace`
   guards `current_trace_id is None` (a no-trace run isn't resolvable until its
   first trace).
4. **`api.py`** — `AutoSessionItem.current_trace_id` → `str | None`
   (`/enable` already accepts no `trace_id` via the optional seed field).
5. **`api_schema.d.ts`** — regenerated (trace_id optional on EnableAutoRequest;
   current_trace_id optional on AutoSessionItem).
6. **`auto_run_store.ts`** — add a client-only `armed` store + `arm()`/`disarm()`;
   `requestEnable` opens an assistant turn + clears armed when the seed starts a
   burst (now includes `extra_messages`); `clearToOff`/`detach` clear armed.
7. **`chat_session_store.ts`** — `sendMessage` routes an armed-without-run first
   send through `beginArmedAutoRun`: render the user message locally (the server
   doesn't echo a seed's `extra_messages`) then `requestEnable({ extra_messages:
   [msg] })` with no `trace_id`. Existing-trace inject path unchanged.
8. **`chat.svelte`** — footer toggle always clickable (disabled only while a
   consent prompt is open); on accept, arm client-side when there's no trace,
   else enable the server run; indicator binds to `autoModeOn || armed`; Stop
   also disarms.

## Tests

- runner: `_build_seed_body` omits trace_id for a no-trace seed; a no-trace seed
  POSTs the first message with no trace_id and records the first minted trace.
- registry: a no-trace seed with the first message starts RUNNING, has no index
  entry until the first trace, then indexes on the first trace; opening POST is
  never empty.
- api: `/enable` with no trace_id + extra_messages starts a RUNNING run that
  POSTs the message and indexes on the first round.
- auto_run_store: `arm`/`disarm` toggle armed with no server call; no-trace
  enable seeds the first message, opens a turn, attaches, clears armed.
- chat_session_store: armed-first-send creates the run via enable (no trace_id,
  message in extra_messages), renders the message locally, never injects/streams;
  an enable failure surfaces an inline error and doesn't consume the input.
