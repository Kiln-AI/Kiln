---
status: complete
---

# Phase 2: Chat Session Store

## Goal

Create `app/web_ui/src/lib/chat/chat_session_store.ts` containing the store factory, types, action methods, and a global instance. This store encapsulates all chat session state (messages, status, abortController, collapsedPartKeys) and exposes methods for sending messages, stopping, retrying, resetting, and toggling part collapse.

## Types

- `PersistedChatSession` -- the subset persisted to sessionStorage: `messages` and `collapsedPartKeys`
- `ChatSessionState` -- full runtime state extending persisted with `status` and `abortController`
- `ChatSessionStore` -- extends `Readable<ChatSessionState>` with action methods

## Store Factory: `createChatSessionStore(sessionStorageKey?)`

- If `sessionStorageKey` is provided, use `sessionStorageStore<PersistedChatSession>` for persistence; otherwise use a plain `writable`
- Runtime-only fields (`status`, `abortController`) are held as local variables (not persisted)
- Combine persisted store and runtime state into a single derived-like subscription that emits `ChatSessionState`
- Return object implementing `ChatSessionStore` with `subscribe` and action methods

## Action Methods

- `sendMessage(text)` -- guards on `status === "ready"`, creates user + empty assistant messages, sets status to submitted, creates AbortController, calls `streamChat()` with callbacks that update the store
- `stop()` -- calls `abortController.abort()`
- `retryLastRequest()` -- finds last user message, trims messages before it, re-sends
- `reset()` -- clears messages, collapsedPartKeys, sets status to ready, aborts any in-flight request, clears sessionStorage
- `togglePartCollapsed(key, currentlyCollapsed)` -- flips boolean for that key

## Global Instance

Export `chatSessionStore` created with `SESSION_STORAGE_KEY = "kiln_chat_session"`.

## Files

- **New**: `app/web_ui/src/lib/chat/chat_session_store.ts`
- **New**: `app/web_ui/src/lib/chat/chat_session_store.test.ts`

## Tests

Unit tests in `chat_session_store.test.ts`:

1. **Initial state** -- new store has empty messages, status "ready", null abortController, empty collapsedPartKeys
2. **sendMessage state transitions** -- mock fetch/streamChat, verify status goes from ready -> submitted -> streaming -> ready, messages are appended correctly
3. **sendMessage guards** -- calling sendMessage when status !== "ready" is a no-op
4. **stop** -- calling stop aborts the controller
5. **retryLastRequest** -- trims messages from last user message onward, re-sends that text
6. **reset** -- clears all state, clears sessionStorage
7. **togglePartCollapsed** -- flips the boolean for a given key
8. **Persistence round-trip** -- messages written to sessionStorage are restored on new store creation with same key
9. **Independent instances** -- two stores with different keys have independent state
10. **No persistence without key** -- store created without sessionStorageKey doesn't write to sessionStorage
