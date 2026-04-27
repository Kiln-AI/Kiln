---
status: complete
---

# Functional Spec: Chat Pane

## Overview

The chat feature is accessible in two modes: a full-screen page at `/chat`, and a sidebar panel on the right side of the app layout. This project focuses on the layout, visibility, and responsive behavior of the sidebar — not the chat UI itself (`chat.svelte` is out of scope).

## Scope

Files in scope: `(app)/+layout.svelte`, `chat_bar.svelte`, and new helpers (e.g., `chat_ui_storage.ts`). The `chat.svelte` component is owned by another developer and must not be modified.

## Chat Bar Visibility

### On `/chat` Page

The sidebar is hidden when the user is on the `/chat` route. It would be redundant since chat is already full-screen. The floating icon is also hidden on this page.

### Expand/Collapse Toggle

- The sidebar has an **X button** that collapses it.
- When collapsed, a **floating chat icon** appears in the bottom-right corner of the layout.
- Clicking the floating icon re-expands the sidebar.
- The floating icon is **not visible** on the `/chat` page (since chat is already full-screen there).

### Default State

On first visit (no storage set), the sidebar starts **expanded**.

### Persistence

The user's preferred state (expanded or collapsed) is persisted via a `chat_ui_storage.ts` helper:

- **Session storage**: preserves the state within the current browser tab across navigations and soft reloads.
- **Local storage**: preserves the "last decision" across new tabs/windows.
- **Priority on load**: session storage wins if set; otherwise fall back to local storage. This means: the current tab keeps its state, but a brand-new tab inherits the last decision made anywhere.
- Both storages are updated on every toggle.

## Responsive Behavior

### Small screens (below Tailwind `lg:` breakpoint)

The chat bar renders as a **full-screen dialog** using the existing `dialog.svelte` component (title bar, no action buttons). The screen is too narrow for side-by-side layout, but users can still access chat from any page without navigating away.

- The floating chat icon opens the dialog.
- The dialog has its own close mechanism (X / backdrop click).
- The sidebar panel itself is hidden at this breakpoint; only the dialog mode is available.

### Large screens (`lg:` and up)

The chat bar is a **sidebar** beside the main content area. It shares the row with the content pane in a flex layout (partially implemented).

**Vertical positioning:** The chat bar is pinned to the viewport height. When the main content area is taller than the viewport and the user scrolls up/down, the chat bar stays stationary — it does not scroll with the page. The chat bar's height is always based on the window/viewport, never on the document/content height.

### Extra-large screens (`2xl:` and up)

The sidebar gets a width boost for the larger viewport.

## Phase 2: Drag-to-Resize (Later)

Implemented separately after the core behavior is solid.

- A **drag handle** on the left edge of the sidebar allows the user to resize it.
- Cursor changes on hover for discoverability.
- The custom width is saved to **local storage only** — it affects future windows/tabs, not other currently-open windows. Last write wins.
- A reasonable min/max width should be enforced.
- Keyboard accessibility for resize is not required in V1.

## Phase 3: Transitions (Later)

- Add slide/transition animations for expand/collapse. Initial implementation uses instant show/hide.

## Out of Scope

- Shared state between multiple chat instances (separate project).
- Any changes to `chat.svelte` internals.
- Chat API or streaming behavior.
