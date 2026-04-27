---
status: complete
---

# Architecture: Chat Session Store

## New File

### `app/web_ui/src/lib/chat/chat_session_store.ts`

The single new file. Contains the store factory, types, persistence logic, and the default global instance.

```typescript
import { writable, get, type Writable, type Readable } from "svelte/store"
import {
  streamChat,
  chatGenerateId,
  traceIdForNextChatRequest,
  type ChatMessage,
} from "./streaming_chat"
import { base_url } from "$lib/api_client"

const CHAT_API_URL = `${base_url}/api/chat`
const SESSION_STORAGE_KEY = "kiln_chat_session"

// --- Types ---

interface ChatSessionState {
  messages: ChatMessage[]
  status: "ready" | "submitted" | "streaming"
  abortController: AbortController | null
  collapsedPartKeys: Record<string, boolean>
}

interface ChatSessionStore extends Readable<ChatSessionState> {
  sendMessage(text: string): void
  stop(): void
  retryLastRequest(): void
  reset(): void
  togglePartCollapsed(key: string, currentlyCollapsed: boolean): void
}
```

## Session Storage Utility

Add a `sessionStorageStore` function alongside the existing `localStorageStore` in `app/web_ui/src/lib/stores/local_storage_store.ts`. Same pattern — restore on create, auto-save via subscribe — just backed by `sessionStorage`.

```typescript
// Same file as localStorageStore: app/web_ui/src/lib/stores/local_storage_store.ts

export function sessionStorageStore<T>(key: string, initialValue: T) {
  const isBrowser = typeof window !== "undefined" && window.sessionStorage

  const storedValue = isBrowser
    ? JSON.parse(sessionStorage.getItem(key) || "null")
    : null
  const store = writable(storedValue !== null ? storedValue : initialValue)

  if (isBrowser) {
    store.subscribe((value) => {
      const stringified = JSON.stringify(value)
      if (stringified.length > 1 * 1024 * 1024) {
        console.error(
          "Skipping sessionStorage save for " + key + " as it's too large (>1MB)",
        )
      } else {
        sessionStorage.setItem(key, stringified)
      }
    })
  }

  return store
}
```

This is a general-purpose reusable utility, not chat-specific.

## Store Factory: `createChatSessionStore()`

Returns a `ChatSessionStore`. Uses `sessionStorageStore` for the persisted fields (messages, collapsedPartKeys) and layers action methods on top.

```typescript
// Persisted state (survives reload within same tab)
interface PersistedChatSession {
  messages: ChatMessage[]
  collapsedPartKeys: Record<string, boolean>
}

// Full runtime state (includes non-persisted fields)
interface ChatSessionState extends PersistedChatSession {
  status: "ready" | "submitted" | "streaming"
  abortController: AbortController | null
}

function createChatSessionStore(sessionStorageKey?: string): ChatSessionStore {
  // sessionStorageStore handles restore + auto-save for the persisted fields.
  // status and abortController always start fresh (not persisted).
  const persisted = sessionStorageKey
    ? sessionStorageStore<PersistedChatSession>(sessionStorageKey, {
        messages: [],
        collapsedPartKeys: {},
      })
    : writable<PersistedChatSession>({ messages: [], collapsedPartKeys: {} })

  // Runtime-only state (never persisted)
  let status: "ready" | "submitted" | "streaming" = "ready"
  let abortController: AbortController | null = null

  // Derive a combined readable for consumers
  // (implementation detail — could use a derived store or manual approach)

  return {
    subscribe: /* combined subscribe */,
    sendMessage(text) { /* ... */ },
    stop() { /* ... */ },
    retryLastRequest() { /* ... */ },
    reset() { /* ... */ },
    togglePartCollapsed(key, currentlyCollapsed) { /* ... */ },
  }
}
```

### Action methods

Each method calls `store.update(state => ...)` to mutate state. The streaming callback (`onAssistantMessage`, `onChatTrace`, etc.) also use `store.update`.

**`sendMessage(text)`**: Guards on `status === "ready"`. Creates user message + empty assistant message, sets status to `"submitted"`, creates AbortController, calls `streamChat()`. The `streamChat` callbacks update state via `store.update`.

**`stop()`**: Reads current `abortController` via `get(store)`, calls `.abort()`.

**`retryLastRequest()`**: Finds last user message, trims messages to before it, calls `sendMessage` with that text.

**`reset()`**: Sets state back to initial (empty messages, ready, null controller, empty collapsed keys). Also clears sessionStorage if key provided.

**`togglePartCollapsed(key, currentlyCollapsed)`**: Flips the boolean for that key in `collapsedPartKeys`.

## Global Instance

```typescript
export const chatSessionStore = createChatSessionStore({
  sessionStorageKey: SESSION_STORAGE_KEY,
})
```

Exported alongside the factory so consumers can create additional instances if needed.

## Modified Files

### `chat.svelte` — Major refactor

**Removals** (moved to store):
- `messages`, `status`, `abortController` local variables
- `handleSubmit()`, `stop()`, `retryLastRequest()`, `removeErrors()`, `updateLastAssistant()` functions
- `CHAT_API_URL` constant
- `streamChat` import and all streaming callback logic
- `collapsedPartKeys` variable and `togglePartCollapsed()` function

**Additions**:
- Import `chatSessionStore` (or accept as prop)
- `export let store: ChatSessionStore = chatSessionStore` — prop with default
- Subscribe via `$store` for reactive access to `messages`, `status`, `collapsedPartKeys`
- Call `store.sendMessage(text)`, `store.stop()`, `store.retryLastRequest()`, `store.togglePartCollapsed(key, collapsed)`

**Kept as-is** (component-local):
- DOM refs, scroll observer, auto-scroll logic
- `input` text binding
- `reasoningPartStartTimes`, `reasoningPartEndTimes`, `lastSeenLastPartKey` (timing is per-view)
- All formatting/helper functions (`formatToolName`, `hasToolInput`, `formatToolInput`, `formatToolOutput`, `getToolOutputError`, `durationLabel`, `reasoningDurationSeconds`)
- `partKey()` function (used by both store and component — could stay in component or move to `streaming_chat.ts`; keeping in component is simplest since store just stores the keys as strings)
- `shouldAutoCollapse()`, `isPartCollapsed()` — these reference `collapsedPartKeys` which now comes from `$store.collapsedPartKeys`
- All template markup and styles (unchanged)

### `chat_bar.svelte` — No changes

Does not manage chat state. Just renders `<Chat />`. Continues to work as-is.

### `+page.svelte` (chat route) — No changes

Just wraps `<Chat />` in `<AppPage>`.

### `streaming_chat.ts` — No changes

Already a clean utility. The store calls `streamChat()` the same way `chat.svelte` does today.

### `chat_ui_storage.ts` — No changes

Manages sidebar UI state (expand/width), unrelated to chat session state.

## Data Flow

```
User types → chat.svelte input → store.sendMessage(text)
                                      ↓
                               store.update(state => ...)
                                      ↓
                               streamChat() callbacks → store.update(state => ...)
                                      ↓
                               $store reactive → chat.svelte re-renders
                                      ↓
                               All subscribed Chat instances update simultaneously
```

## Testing

- Unit tests for the store in a new test file: `chat_session_store.test.ts`
- Test: create store, send message (mock fetch), verify state transitions
- Test: persistence round-trip (mock sessionStorage)
- Test: multiple instances are independent
- Test: reset clears state and storage
- Existing behavior is preserved — no new UI to test
