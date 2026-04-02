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

- [x] Define `PersistedChatSession`, `ChatSessionState`, `ChatSessionStore` types
- [x] Implement `createChatSessionStore()` using `sessionStorageStore` for persisted fields
- [x] Implement action methods: `sendMessage`, `stop`, `retryLastRequest`, `reset`, `togglePartCollapsed`
- [x] Export `createChatSessionStore` factory and `chatSessionStore` global instance
- [x] Add unit tests: state transitions, persistence round-trip, independent instances, reset clears storage

## Phase 3: Refactor `chat.svelte` to use the store

Refactor `chat.svelte` to be a pure UI component that subscribes to a `ChatSessionStore`.

- [x] Add `export let store` prop defaulting to `chatSessionStore`
- [x] Replace local `messages`, `status`, `abortController`, `collapsedPartKeys` with `$store` subscriptions
- [x] Replace `handleSubmit`, `stop`, `retryLastRequest`, `togglePartCollapsed` with store method calls
- [x] Remove `streamChat` import, `CHAT_API_URL`, `updateLastAssistant`, `removeErrors` — all moved to store
- [x] Keep component-local: DOM refs, scroll, input text, reasoning timing, formatting helpers
- [x] Verify all three usage sites work (chat page, sidebar, dialog) and share the same session
- [x] Run linting, formatting, type checking
