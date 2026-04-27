---
status: complete
---

# Functional Spec: Chat App State

## Overview

When a user sends a chat message, the system prepends an invisible `<new_app_ui_context>` block to the message if the app state has changed since the last message. This gives the chat agent awareness of where the user is in the app and what they're looking at.

## App State Data Model

App state is composed of fields from two sources:

| Field | Source | Example |
|-------|--------|---------|
| `Path` | Browser URL path (`window.location.pathname`) | `/tools/189194447825/add_tools` |
| `Page Name` | `agentInfo` store | `Settings Home` |
| `Page Description` | `agentInfo` store | `A page for managing user settings...` |
| `Current Project` | UIState store | `12345` |
| `Current Task` | UIState store | `123456` |

## `agentInfo` Store

A new Svelte writable store in `$lib/agent.ts`:

```ts
export interface AgentPageInfo {
  name: string;
  description: string;
}

export const agentInfo = writable<AgentPageInfo | null>(null);
```

Every `+page.svelte` must call `agentInfo.set(...)` with a name and description. Descriptions should be:
- **Static** for simple pages: `"A page for managing user settings. General selection screen with many options."`
- **Dynamic** where useful: `"Tool detail page for tool ID 100945512896 in project 1234545, named 'Memory by Anthropic'"`

Descriptions should include key contextual data (selected entity names, active filters, relevant IDs with labels like "project ID X") but not exhaustively list all page data.

## Context Header Format

```
<new_app_ui_context>
Path: /tools/189194447825/add_tools
Page Name: Settings Home
Page Description: A page for managing user settings.
Current Project: 12345
Current Task: 123456
</new_app_ui_context>
```

### Only Changed Fields

The header only includes fields whose values have changed since the last sent state. For example, if only the path and page name changed but the project/task stayed the same, those are omitted:

```
<new_app_ui_context>
Path: /tools/189194447825/add_tools
Page Name: Tool Detail
Page Description: Tool detail page for tool 100945512896, named 'Memory by Anthropic'
</new_app_ui_context>
```

### Null Handling

If `agentInfo` is null (page hasn't set it), omit the `Page Name` and `Page Description` fields — send only the fields that are available (at minimum, `Path`). The CI test ensures this shouldn't happen in practice.

## Send Logic

Located in the chat session store's `sendMessage` / `beginStreaming` flow:

1. Collect current app state: read `agentInfo`, UIState (project/task), and `window.location.pathname`.
2. Read `lastSentAppState` from the chat session store (null for new sessions).
3. Compare field-by-field against `lastSentAppState`.
4. If any field changed (or `lastSentAppState` is null — first message):
   - Build the `<new_app_ui_context>` block with only the changed fields (all fields on first message).
   - Prepend to the message text sent to the backend API.
   - Update `lastSentAppState` with the full current state.
5. If nothing changed: send the message as-is, no header.

### UI Visibility

The context header is **not visible** in the chat UI. It is prepended to the message content sent to the API, but the displayed user message shows only what the user typed.

This means:
- The `ChatMessage` stored in the persisted session keeps the original user text (no header).
- The header is added at send time only, in the payload to `streamChat`.

## `lastSentAppState` Storage

Added as a persisted field on `PersistedChatSession` (stored in session storage alongside messages). It resets to `null` on new sessions and on `reset()`, ensuring the first message in any session always includes full context.

If a user loads an old conversation into a new tab, `lastSentAppState` will be null, so full context is re-sent — this is fine and expected.

## CI Test: agentInfo Coverage

A Vitest test that scans all `+page.svelte` files under `src/routes/` and asserts each one contains an `agentInfo.set(` or `agentInfo.update(` call. This catches new pages added without agent context.

## Phases

- **Phase 1**: Core infrastructure — `agentInfo` store, `lastSentAppState` tracking, context header prepend logic, tests.
- **Phase 2**: Backfill all existing pages with `agentInfo.set()` calls + add the CI coverage test.
