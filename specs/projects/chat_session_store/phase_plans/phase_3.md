---
status: complete
---

# Phase 3: Refactor chat.svelte to use the store

## Goal

Refactor `chat.svelte` from owning chat state (messages, status, abortController, collapsedPartKeys) to subscribing to the shared `ChatSessionStore`. All three usage sites (chat page, sidebar, dialog) will share one global store instance, keeping messages synchronized.

## Changes

### `chat.svelte` — Major refactor

**Add:**
- `export let store: ChatSessionStore = chatSessionStore` prop with default
- Subscribe to `$store` for reactive access to `messages`, `status`, `abortController`, `collapsedPartKeys`
- Derived variables (`isLoading`, `lastMessage`, etc.) now reference `$store.status`, `$store.messages`
- `handleSubmit` calls `store.sendMessage(input)` then clears local `input`
- `stop` calls `store.stop()`
- `retryLastRequest` calls `store.retryLastRequest()`
- `togglePartCollapsed` computes the key and current collapsed state, then calls `store.togglePartCollapsed(key, current)`
- Wire tool approval handler via `store.setOnToolCallsPending(handleToolCallsPending)` on mount, clear on destroy

**Remove:**
- Local `messages`, `status`, `abortController`, `collapsedPartKeys` variables
- `CHAT_API_URL` constant
- `streamChat`, `chatGenerateId`, `traceIdForNextChatRequest` imports (moved to store)
- `base_url` import (no longer needed)
- `handleSubmit` streaming logic, `updateLastAssistant`, `removeErrors` functions

**Keep as-is (component-local):**
- DOM refs: `messagesContainer`, `messagesEndRef`, `textareaRef`
- Scroll: `MutationObserver`, `suppressAutoScroll`
- Input: `input` text binding
- Reasoning timing: `reasoningPartStartTimes`, `reasoningPartEndTimes`, `lastSeenLastPartKey`
- Formatting helpers: `formatToolName`, `hasToolInput`, `formatToolInput`, `formatToolOutput`, `getToolOutputError`, `durationLabel`, `reasoningDurationSeconds`
- `partKey()`, `shouldAutoCollapse()`, `isPartCollapsed()` (these read from `$store` now)
- `isReasoningStreaming()` (reads from `$store`)
- Tool approval UI state: `toolApprovalWaiter`, `toolApprovalPicks`, and related functions
- Layout helpers: `adjustTextareaHeight`, `handleTextareaKeydown`
- All template markup and styles (unchanged)

### Usage sites — No changes needed

All three sites (`+page.svelte`, sidebar in `chat_bar.svelte`, dialog in `chat_bar.svelte`) use `<Chat />` without props, which will use the default global `chatSessionStore`.

## Testing strategy

- Existing store unit tests (phase 2) cover all state logic
- Run `svelte-check`, `prettier`, `eslint` to verify type safety and formatting
- Run `vitest` to verify no regressions
- Manual verification that all three usage sites compile and share the same session
