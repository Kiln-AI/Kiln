---
status: draft
---

# Phase 4: Move tool approval state into store and fix streaming re-render

## Overview

Three bug fixes for shared-state correctness and performance:
1. Tool approval state (`toolApprovalWaiter`, `toolApprovalPicks`) is component-local, so only one view sees approval UI. Move into the store.
2. `onToolCallsPending` handler is captured as a stale closure. Make the store own tool approval logic internally.
3. `setRuntimeState("streaming", controller)` is called on every assistant message update. Guard to only call when status transitions.

## Steps

1. **Add tool approval fields to `ChatSessionState`** in `chat_session_store.ts`:
   - `toolApprovalWaiter: { payload: ToolCallsPendingPayload } | null`
   - `toolApprovalPicks: Record<string, boolean | undefined>`

2. **Add `applyToolApprovalRun` and `applyToolApprovalSkip`** to `ChatSessionStore` interface and implement them. Each sets the pick for the given toolCallId, then checks if all picks are decided. If so, resolves the internal promise and clears approval state.

3. **Implement internal `onToolCallsPending`** in `beginStreaming`: Create a Promise whose resolver is stored in a closure variable. When called, filter to approval-only items, set `toolApprovalWaiter` and `toolApprovalPicks` in the combined store. The resolver is called by the approval methods.

4. **Remove `setOnToolCallsPending`** from the public API and the `ChatSessionStore` interface.

5. **Fix `onAssistantMessage` guard**: Change from always calling `setRuntimeState("streaming", controller)` to `if (status !== "streaming") { setRuntimeState("streaming", controller) }`.

6. **Update `chat.svelte`**:
   - Remove local `toolApprovalWaiter` and `toolApprovalPicks`
   - Read from `$store.toolApprovalWaiter` and `$store.toolApprovalPicks`
   - Replace `applyToolApprovalRun`/`applyToolApprovalSkip` with `store.applyToolApprovalRun(id)` / `store.applyToolApprovalSkip(id)`
   - Remove `handleToolCallsPending`, the `onMount`/`onDestroy` calls for it
   - Remove `ToolCallsPendingPayload` import

7. **Update tests**: Remove `setOnToolCallsPending` tests, add tests for approval state and methods, add test for streaming guard.

## Tests

- `has correct initial state`: verify `toolApprovalWaiter` is null and `toolApprovalPicks` is empty
- `internal onToolCallsPending sets approval state`: trigger the captured handler, verify store state
- `applyToolApprovalRun resolves approval for a tool call`: run one approval, verify pick is set
- `applyToolApprovalSkip resolves approval for a tool call`: skip one approval, verify pick is set
- `completing all approvals clears waiter and resolves promise`: approve all, verify waiter cleared
- `onAssistantMessage only transitions to streaming once`: call onAssistantMessage multiple times, verify setRuntimeState called only once for the streaming transition
- `auto-skip non-approval items`: verify items without requiresApproval are auto-approved
- `reset clears tool approval state`: verify reset clears waiter and picks
