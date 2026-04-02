---
status: complete
---

# Implementation Plan: Chat Session Store

## Phase 1: `sessionStorageStore` utility

Add `sessionStorageStore<T>()` to `app/web_ui/src/lib/stores/local_storage_store.ts`, mirroring the existing `localStorageStore` pattern but backed by `sessionStorage`.

- [x] Add `sessionStorageStore` function
- [x] Add unit tests for the new utility (restore, save, SSR safety, size guard)

## Phase 2: Chat session store

Create `app/web_ui/src/lib/chat/chat_session_store.ts` with the store factory and global instance.

- [ ] Define `PersistedChatSession`, `ChatSessionState`, `ChatSessionStore` types
- [ ] Implement `createChatSessionStore()` using `sessionStorageStore` for persisted fields
- [ ] Implement action methods: `sendMessage`, `stop`, `retryLastRequest`, `reset`, `togglePartCollapsed`
- [ ] Export `createChatSessionStore` factory and `chatSessionStore` global instance
- [ ] Add unit tests: state transitions, persistence round-trip, independent instances, reset clears storage

## Phase 3: Refactor `chat.svelte` to use the store

Refactor `chat.svelte` to be a pure UI component that subscribes to a `ChatSessionStore`.

- [ ] Add `export let store` prop defaulting to `chatSessionStore`
- [ ] Replace local `messages`, `status`, `abortController`, `collapsedPartKeys` with `$store` subscriptions
- [ ] Replace `handleSubmit`, `stop`, `retryLastRequest`, `togglePartCollapsed` with store method calls
- [ ] Remove `streamChat` import, `CHAT_API_URL`, `updateLastAssistant`, `removeErrors` — all moved to store
- [ ] Keep component-local: DOM refs, scroll, input text, reasoning timing, formatting helpers
- [ ] Verify all three usage sites work (chat page, sidebar, dialog) and share the same session
- [ ] Run linting, formatting, type checking
