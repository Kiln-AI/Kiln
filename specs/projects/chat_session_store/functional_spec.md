---
status: complete
---

# Functional Spec: Chat Session Store

## Problem

`chat.svelte` currently owns both chat state (messages, status, abort controller) and chat UI (rendering, scroll, input). The chat component is instantiated in 3 places — the `/chat` page, the sidebar panel (large screens), and the dialog (small screens). Each instance has its own independent message history, so messages sent in the sidebar don't appear on the `/chat` page or in the dialog.

## Solution

Extract all chat state into a Svelte writable store. A single global store instance serves as the primary chat session. All `Chat` component instances subscribe to this shared store, so messages, status, and streaming state are synchronized everywhere.

## Store Shape

The store holds everything that is currently component-local state related to the chat session:

```typescript
interface ChatSessionState {
  messages: ChatMessage[]
  status: "ready" | "submitted" | "streaming"
  abortController: AbortController | null
  collapsedPartKeys: Record<string, boolean>
}
```

The store exposes actions as methods (not just raw state):

- `sendMessage(text: string)` — creates user + placeholder assistant messages, initiates streaming
- `stop()` — aborts the current request
- `retryLastRequest()` — removes errors, replays last user message
- `reset()` — clears all messages and resets to initial state
- `togglePartCollapsed(key: string, currentlyCollapsed: boolean)` — toggles collapse state for a reasoning/tool block

## What Stays in the Component

`chat.svelte` becomes a pure UI component. It keeps only:

- **DOM refs**: `messagesContainer`, `messagesEndRef`, `textareaRef`
- **Scroll behavior**: `MutationObserver`, `suppressAutoScroll`
- **UI-only state**: `reasoningPartStartTimes`, `reasoningPartEndTimes`, `lastSeenLastPartKey` (timing is cosmetic and per-view — different views may mount at different times)
- **Input text**: `input` (local to each input box)
- **Layout helpers**: `adjustTextareaHeight`, `handleTextareaKeydown`

## Store API

```typescript
// Create a chat session store
function createChatSessionStore(): ChatSessionStore

// The global primary session
const chatSessionStore: ChatSessionStore
```

The component subscribes to the store via Svelte's `$store` syntax. It calls store methods for actions (send, stop, retry).

## Default Behavior

- `chat.svelte` uses the global `chatSessionStore` by default
- An optional prop allows passing a different store instance (for future use — e.g., multiple independent chats)
- The component reads `$store.messages`, `$store.status`, etc. reactively

## Session Storage (Persistence)

Messages persist across page reloads within the same browser tab using `sessionStorage`:

- On every message change, serialize `messages` to `sessionStorage`
- On store creation, restore from `sessionStorage` if present
- Key: `"kiln_chat_session"` (or similar)
- A new tab gets a fresh empty chat (sessionStorage is per-tab)
- Only `messages` are persisted; `status` and `abortController` reset to defaults on reload

### What to persist

- `messages` array (full ChatMessage objects including parts and traceId)
- `collapsedPartKeys` (so collapse state survives reload too)
- `status` resets to "ready", `abortController` resets to null (not persisted)

### Serialization

- `JSON.stringify` / `JSON.parse` for messages
- Guard against corrupt data: if parse fails, start fresh

## Edge Cases

- **Streaming interrupted by reload**: Status resets to "ready". The last assistant message may be incomplete — that's acceptable. The user can see what was streamed so far.
- **Store subscribed by zero components**: The store still exists and holds state. When a component mounts, it picks up current state.
- **Multiple components subscribing simultaneously**: Both sidebar and dialog could theoretically be showing. Both render the same messages. Only one input should send at a time — the store's `sendMessage` checks `status !== "ready"` before proceeding, same as today.

## Out of Scope

- UI for managing multiple conversations (list, naming, switching) — though the store is designed as a factory (`createChatSessionStore()`) so multiple independent sessions are trivial to create
- Server-side persistence of chat history
- Cross-tab synchronization
- "New chat" button (can be added later with `reset()`)
