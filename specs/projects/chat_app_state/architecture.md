---
status: complete
---

# Architecture: Chat App State

This is a small, frontend-only feature. Single architecture doc — no component designs needed.

## New Files

### `app/web_ui/src/lib/agent.ts`

The `agentInfo` store and the context-building logic.

```ts
import { writable, get } from 'svelte/store';
import { ui_state } from '$lib/stores';

export interface AgentPageInfo {
  name: string;
  description: string;
}

export const agentInfo = writable<AgentPageInfo | null>(null);

export interface AppState {
  path: string;
  pageName: string | null;
  pageDescription: string | null;
  currentProject: string | null;
  currentTask: string | null;
}

export function getCurrentAppState(): AppState {
  const info = get(agentInfo);
  const uiState = get(ui_state);
  return {
    path: typeof window !== 'undefined' ? window.location.pathname : '',
    pageName: info?.name ?? null,
    pageDescription: info?.description ?? null,
    currentProject: uiState.current_project_id,
    currentTask: uiState.current_task_id,
  };
}

export function buildContextHeader(
  current: AppState,
  lastSent: AppState | null,
): string | null {
  if (lastSent === null) {
    // First message — include all non-null fields
    return formatHeader(current);
  }

  // Build header with only changed fields
  const changed: Partial<AppState> = {};
  let hasChanges = false;
  for (const key of Object.keys(current) as (keyof AppState)[]) {
    if (current[key] !== lastSent[key]) {
      changed[key] = current[key];
      hasChanges = true;
    }
  }
  if (!hasChanges) return null;
  return formatChangedHeader(changed);
}
```

`formatHeader` builds the full `<new_app_ui_context>` block. `formatChangedHeader` builds it with only the provided fields. Both skip null values.

Field mapping:
- `path` → `Path`
- `pageName` → `Page Name`
- `pageDescription` → `Page Description`
- `currentProject` → `Current Project`
- `currentTask` → `Current Task`

### `app/web_ui/src/lib/agent.test.ts`

Tests for `buildContextHeader` and `getCurrentAppState`:

- First message (lastSent=null): returns full header with all non-null fields.
- No changes: returns null.
- Partial changes: returns header with only changed fields.
- Null fields omitted from output.
- Path always included when it changes (even if other fields are null).

## Modified Files

### `app/web_ui/src/lib/chat/chat_session_store.ts`

**`PersistedChatSession`** — add `lastSentAppState`:

```ts
export interface PersistedChatSession {
  messages: ChatMessage[];
  collapsedPartKeys: Record<string, boolean>;
  lastSentAppState: AppState | null;  // new
}
```

Update `EMPTY_PERSISTED` to include `lastSentAppState: null`.

**`beginStreaming`** — after constructing `userMessage`, before calling `streamChat`:

1. Call `getCurrentAppState()`.
2. Call `buildContextHeader(currentState, get(persisted).lastSentAppState)`.
3. If header is non-null, create a modified copy of the user message with `content: header + "\n" + text` for sending to the API. The original `userMessage` (without header) is what gets stored in messages.
4. Update `lastSentAppState` in persisted store.

The key point: `updateMessages` stores the clean user text. The `streamChat` call receives the message with the prepended header.

**`reset()`** — `lastSentAppState` is already reset because `persisted.set(...)` uses `EMPTY_PERSISTED` which has `lastSentAppState: null`.

**`retryLastRequest`** — no changes needed. It re-calls `beginStreaming` which re-evaluates current app state. The retried message will get fresh context, which is the desired behavior.

## Testing Strategy

All tests in Vitest.

### Unit Tests (`agent.test.ts`)

- `buildContextHeader` — the cases listed above.
- `formatHeader` / `formatChangedHeader` — correct XML output format.

### Integration Test (Phase 2: `agent_coverage.test.ts`)

- Scan all `+page.svelte` files in `src/routes/`.
- Assert each contains `agentInfo.set(` or `agentInfo.update(`.
- This is a static analysis test (reads file contents), not a runtime test.

## Edge Cases

- **SSR**: `window.location.pathname` is guarded with `typeof window !== 'undefined'`. In practice, this code only runs client-side when the user sends a message.
- **Rapid navigation**: If the user navigates quickly and sends a message, they get whichever `agentInfo` was last set. This is correct — it reflects what they're currently looking at.
- **agentInfo null**: If a page hasn't set it, `pageName` and `pageDescription` are null and omitted from the header. Path is always available.
