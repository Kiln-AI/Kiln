---
status: complete
---

# Phase 1: Foundation stores

## Overview

Add the two shared Svelte stores that later phases will consume to decide when to render the sidebar rail:

- `app/web_ui/src/lib/stores/viewport.ts` — reactive viewport width plus `isLg` (≥1024px) and `isBelow2000` (<2000px) derived booleans. SSR-safe: `browser` guard, initial width 0 on the server, `window`-resize listener attached only in the browser.
- `app/web_ui/src/lib/stores/chat_ui_state.ts` — shared `chatBarExpanded` writable store, initialized from `getChatBarExpanded()` in `chat_ui_storage`, with a `setChatBarExpanded(expanded)` function that updates the store and persists via the existing storage layer.

Then migrate `app/web_ui/src/routes/(app)/chat_bar.svelte` from its local `expanded` variable to the shared store (subscribing via `$chatBarExpanded`, writing via `setChatBarExpanded` imported from the new store). The existing animation state machine (`animState`, `toggle`, `sidebarVisible`, `iconHidden`) stays intact — only the source of `expanded` changes.

This phase is foundation-only. No visual changes, no rail rendering yet. Unit tests cover both stores and the migrated persistence flow.

> **Note:** In Phase 2 the narrow-viewport threshold was tuned to `< 1550px` and the derived store was renamed `isBelow2000 → isNarrowViewport`. Occurrences of `isBelow2000` / `2000` below are preserved as the original Phase 1 plan; the live code reflects the updated names/threshold.

## Steps

1. **Create `app/web_ui/src/lib/stores/viewport.ts`**
   - Export `viewportWidth: Readable<number>` built from `readable(browser ? window.innerWidth : 0, ...)` that subscribes to `window.resize` only when `browser` is true.
   - Export `isLg: Readable<boolean>` = `derived(viewportWidth, (w) => w >= 1024)`.
   - Export `isBelow2000: Readable<boolean>` = `derived(viewportWidth, (w) => w < 2000)`.

   Signature reference:
   ```ts
   export const viewportWidth: Readable<number>
   export const isLg: Readable<boolean>
   export const isBelow2000: Readable<boolean>
   ```

2. **Create `app/web_ui/src/lib/stores/chat_ui_state.ts`**
   - Import `getChatBarExpanded` and `setChatBarExpanded as persistChatBarExpanded` from `$lib/chat/chat_ui_storage`.
   - Initialize `const initial = browser ? getChatBarExpanded() : true`.
   - Export `chatBarExpanded = writable<boolean>(initial)`.
   - Export `function setChatBarExpanded(expanded: boolean): void` that calls `chatBarExpanded.set(expanded)` and, when `browser`, calls `persistChatBarExpanded(expanded)`.

3. **Migrate `app/web_ui/src/routes/(app)/chat_bar.svelte`**
   - Remove the direct imports of `getChatBarExpanded` / `setChatBarExpanded` from `$lib/chat/chat_ui_storage` (keep `getChatBarWidth` / `setChatBarWidth` — width persistence is out of scope for this phase).
   - Import `chatBarExpanded` and `setChatBarExpanded` from `$lib/stores/chat_ui_state`.
   - Replace `let expanded = browser ? getChatBarExpanded() : true` with a reactive `$: expanded = $chatBarExpanded` and write `expanded` through `setChatBarExpanded(...)` from the new module.
   - The `toggle` function updates via `setChatBarExpanded(...)` only — no local `expanded = ...` assignment.
   - Keep all animation, drag, and dialog behavior unchanged.

## Tests

- `app/web_ui/src/lib/stores/viewport.test.ts`
  - `isLg` is `true` when width ≥ 1024 and `false` when < 1024 (use a manual `writable` overriding `viewportWidth` via module re-import, or assert with `get` after simulating `resize`).
  - `isBelow2000` is `true` when width < 2000 and `false` when ≥ 2000.
  - `viewportWidth` updates when `window` dispatches a `resize` event.
  - Unsubscribing the last subscriber removes the resize listener (`window.removeEventListener` called).
  - SSR safety: when `browser` is false the module still exports usable stores whose value is the fallback `0` (and `isLg` is `false`, `isBelow2000` is `true`).

- `app/web_ui/src/lib/stores/chat_ui_state.test.ts`
  - Store initializes from `getChatBarExpanded()` (mock storage → verify store value).
  - `setChatBarExpanded(true)` updates the store and calls the persistence layer with `true`.
  - `setChatBarExpanded(false)` updates the store and persists `false`.
  - Multiple subscribers receive the new value after `setChatBarExpanded`.
