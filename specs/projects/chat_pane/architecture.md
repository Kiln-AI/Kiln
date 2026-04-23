---
status: complete
---

# Architecture: Chat Pane

This is a small, frontend-only layout project. No new data models, APIs, or backend changes. Single architecture doc — no component designs needed.

## File Structure

```
(app)/+layout.svelte          — layout changes: flex row, conditional sidebar vs dialog
(app)/chat_bar.svelte          — sidebar wrapper: X button, Chat embed, responsive logic
lib/chat/chat_ui_storage.ts    — expand/collapse persistence helper
```

`chat.svelte` is not modified.

## Component Breakdown

### `chat_ui_storage.ts`

A small helper module for persisting the expanded/collapsed state.

```typescript
const STORAGE_KEY = "chat_bar_expanded"

// Read: sessionStorage ?? localStorage ?? true (default expanded)
export function getChatBarExpanded(): boolean

// Write: sets both sessionStorage and localStorage
export function setChatBarExpanded(expanded: boolean): void
```

No reactive store needed — `chat_bar.svelte` reads on mount and writes on toggle, managing its own Svelte reactive state.

### `chat_bar.svelte`

This component owns all chat-bar presentation logic. The layout delegates to it.

**State:**
- `expanded: boolean` — initialized from `getChatBarExpanded()` on mount
- `section` — passed as prop from layout to know if we're on `/chat`

**Responsibilities:**
- Renders the sidebar content (header with title + X button, `<Chat />` embed) when expanded on `lg:+` screens
- Renders the floating chat-bubble icon when collapsed on `lg:+` screens
- On small screens (`< lg`): renders only the floating chat-bubble icon, which opens a `dialog.svelte` containing `<Chat />`
- Hides entirely (no sidebar, no icon) when `section === Section.Chat`

**Structure (lg:+ expanded):**
```
┌─────────────────────┐
│ Chat            [X]  │  ← header row
│                      │
│   <Chat />           │  ← embedded chat component
│                      │
└─────────────────────┘
```

**Floating icon (collapsed or small screen):**
- Fixed position, bottom-right corner
- Chat-bubble SVG icon
- `on:click` → toggle expanded (lg:+) or open dialog (< lg)

**Dialog (small screens):**
- Uses existing `dialog.svelte` with `title="Chat"`, no action buttons
- Contains `<Chat />` as slot content
- Opened programmatically via `dialog.show()`

### `+layout.svelte` Changes

Minimal changes to layout:

- Import `ChatBar` (already done)
- Pass `section` prop to `ChatBar`
- The flex row wrapper (already partially implemented) contains the main content slot and the `ChatBar`
- `ChatBar` handles its own visibility — layout just places it in the DOM

**Layout structure:**
```svelte
<div class="flex flex-grow flex-row gap-4">
  <div class="flex-1 min-w-0 ...">
    <slot />
  </div>
  <ChatBar {section} />
</div>
```

The `ChatBar` component handles all conditional rendering internally (hidden on `/chat`, responsive breakpoints, expanded/collapsed). The layout doesn't need `{section == Section.Chat ? 'hidden' : ''}` logic — that moves into `ChatBar`.

**Viewport-pinned positioning:** The chat bar uses `position: sticky; top: 0` with a height based on viewport (`h-screen` or `100vh`). This keeps it anchored to the viewport while the main content scrolls independently. The sticky approach works because the chat bar is a flex sibling of the main content — it stays in the normal document flow for layout purposes (no overlap, no absolute positioning hacks) but doesn't scroll with the page. The chat bar manages its own internal scrolling if its content overflows.

## Responsive Breakpoints

Using Tailwind's responsive approach:

| Breakpoint | Behavior |
|---|---|
| `< lg` (< 1024px) | No sidebar. Floating icon → opens dialog with Chat |
| `lg` - `2xl` (1024-1535px) | Sidebar at `w-[320px]` |
| `2xl` (≥ 1536px) | Sidebar at `w-[380px]` |

## Sidebar Sizing (Phase 2: Resize)

Not implemented in Phase 1. Architecture note for later:

- Add a drag handle div on the left edge of the sidebar
- Track drag via `mousedown`/`mousemove`/`mouseup` on `window`
- Clamp width between min (280px) and max (50vw)
- Persist to localStorage only via a new function in `chat_ui_storage.ts`
- Apply as inline `style="width: {customWidth}px"` overriding the Tailwind class

## Testing Strategy

- `chat_ui_storage.ts`: unit tests for read/write logic, priority behavior (session over local), default value. Mock `sessionStorage` and `localStorage`.
- `chat_bar.svelte`: no component tests planned (visual/layout behavior is best verified manually for this scope).
- Manual QA: test all breakpoints, toggle persistence across tabs, dialog on small screens.
