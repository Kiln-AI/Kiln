---
status: draft
---

# Phase 1: Core Infrastructure

## Overview

Build the `agentInfo` store, `AppState` types, `buildContextHeader` logic, and integrate context header prepending into the chat session store's `beginStreaming` flow. This phase does not touch any `+page.svelte` files -- that is Phase 2.

## Steps

1. Create `app/web_ui/src/lib/agent.ts` with:
   - `AgentPageInfo` interface and `agentInfo` writable store
   - `AppState` interface
   - `getCurrentAppState()` function reading from `agentInfo`, `ui_state`, and `window.location.pathname`
   - `buildContextHeader(current, lastSent)` function returning the XML block or null
   - Internal `formatHeader` and `formatChangedHeader` helpers that map field names and skip nulls

2. Modify `app/web_ui/src/lib/chat/chat_session_store.ts`:
   - Add `lastSentAppState: AppState | null` to `PersistedChatSession` interface
   - Update `EMPTY_PERSISTED` to include `lastSentAppState: null`
   - Update `reset()` to include `lastSentAppState: null` in the `persisted.set()` call
   - In `beginStreaming`, after constructing `userMessage` and before calling `streamChat`:
     - Call `getCurrentAppState()`
     - Call `buildContextHeader(currentState, get(persisted).lastSentAppState)`
     - If header is non-null, create a modified user message with prepended header for the API call
     - Update `persisted` with the new `lastSentAppState`
   - The stored message keeps original user text; only the API payload gets the header

3. Create `app/web_ui/src/lib/agent.test.ts` with tests for:
   - `buildContextHeader` with lastSent=null (first message, full header)
   - `buildContextHeader` with no changes (returns null)
   - `buildContextHeader` with partial changes (only changed fields)
   - Null fields omitted from output
   - Path-only change when agentInfo is null
   - `formatHeader` / `formatChangedHeader` correct XML format

4. Add integration tests in `chat_session_store.test.ts` for:
   - Context header prepended on first message
   - Context header not prepended when state unchanged
   - `lastSentAppState` persisted and reset on `reset()`
   - Stored user message does not contain the header

## Tests

- `buildContextHeader returns full header when lastSent is null`: all non-null fields present
- `buildContextHeader returns null when nothing changed`: identical current/last
- `buildContextHeader returns only changed fields`: partial diff
- `buildContextHeader omits null fields`: agentInfo null means no Page Name/Description
- `buildContextHeader includes path when only path changed`: path-only scenario
- `formatHeader produces correct XML block`: verify exact format
- `formatChangedHeader produces correct XML block with subset of fields`: verify partial format
- `chat session prepends context header on first message`: streamChat receives header + text
- `chat session does not prepend header when state unchanged`: second identical message has no header
- `chat session stores clean user text without header`: persisted messages are clean
- `chat session resets lastSentAppState on reset`: after reset, next message gets full header
