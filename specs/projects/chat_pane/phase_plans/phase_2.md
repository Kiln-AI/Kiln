---
status: draft
---

# Phase 2: Drag-to-Resize Sidebar

## Overview

Add drag-to-resize functionality to the chat sidebar. A drag handle on the left edge of the sidebar lets users adjust the width. The custom width is persisted to localStorage so it carries to future windows/tabs (last write wins). Min/max constraints are enforced.

## Steps

1. **Add width persistence to `chat_ui_storage.ts`**:
   - New storage key: `"chat_bar_width"`
   - `getChatBarWidth(): number | null` — reads from localStorage only (returns null if not set, so the component falls back to default Tailwind widths)
   - `setChatBarWidth(width: number): void` — writes to localStorage only
   - No sessionStorage for width (per spec: impacts future windows, not other currently-open windows)

2. **Add drag handle to `chat_bar.svelte`**:
   - Add a vertical drag handle div on the left edge of the sidebar (inside the sidebar wrapper, before the content)
   - Style: narrow strip (~6px), full height, `cursor: col-resize` on hover
   - Visual indicator: subtle vertical dots/line for discoverability
   - Only visible on `lg:+` screens when sidebar is expanded

3. **Implement drag logic in `chat_bar.svelte`**:
   - On `mousedown` on the drag handle: start tracking
   - Attach `mousemove` and `mouseup` listeners to `window` during drag
   - Calculate new width as `window.innerWidth - clientX` (since sidebar is on the right)
   - Account for the right margin/gap in the layout
   - Clamp width between 280px (min) and 50vw (max)
   - Apply width as inline `style="width: {customWidth}px"` on the sidebar
   - On `mouseup`: persist final width via `setChatBarWidth()`
   - Prevent text selection during drag (`user-select: none` on body)

4. **Initialize width from storage on mount**:
   - Read `getChatBarWidth()` on mount
   - If a value exists, use it as the sidebar width (overriding the Tailwind default)
   - If null, use the existing Tailwind class widths (320px / 380px at 2xl)

## Tests

- `chat_ui_storage.test.ts`: getChatBarWidth returns null when no storage set
- `chat_ui_storage.test.ts`: getChatBarWidth reads from localStorage
- `chat_ui_storage.test.ts`: getChatBarWidth returns null when storage throws
- `chat_ui_storage.test.ts`: getChatBarWidth returns null for non-numeric values
- `chat_ui_storage.test.ts`: setChatBarWidth writes to localStorage
- `chat_ui_storage.test.ts`: setChatBarWidth does not throw when storage is unavailable
