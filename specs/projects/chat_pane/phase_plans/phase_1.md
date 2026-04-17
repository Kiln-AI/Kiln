---
status: draft
---

# Phase 1: Core Sidebar Layout, Expand/Collapse, Persistence, Responsive Dialog

## Overview

Implement the core chat sidebar with expand/collapse toggle, localStorage/sessionStorage persistence, responsive behavior (sidebar on large screens, dialog on small screens), and the floating chat icon. The sidebar is hidden on the `/chat` route.

## Steps

1. **Create `chat_ui_storage.ts`** at `app/web_ui/src/lib/chat/chat_ui_storage.ts`:
   - `getChatBarExpanded(): boolean` — reads sessionStorage first, then localStorage, defaults to `true`
   - `setChatBarExpanded(expanded: boolean): void` — writes to both sessionStorage and localStorage
   - Storage key: `"chat_bar_expanded"`

2. **Rewrite `chat_bar.svelte`** at `app/web_ui/src/routes/(app)/chat_bar.svelte`:
   - Accept `section` prop (the Section enum)
   - Initialize `expanded` from `getChatBarExpanded()` on mount
   - On `lg:+` expanded: render sidebar with header ("Chat" title + X close button) and `<Chat />`
   - On `lg:+` collapsed: render floating chat-bubble icon (fixed, bottom-right)
   - On `< lg`: render floating chat-bubble icon that opens a `dialog.svelte` containing `<Chat />`
   - Hide entirely when `section === Section.Chat`
   - Sidebar uses `sticky top-0 h-screen` for viewport-pinned positioning
   - Width: `w-[320px] 2xl:w-[380px]`

3. **Update `+layout.svelte`**:
   - Pass `section` prop to `<ChatBar />`
   - Remove the outer wrapper div that currently handles sidebar sizing/visibility
   - Let `ChatBar` handle its own conditional rendering

## Tests

- `chat_ui_storage.test.ts`: getChatBarExpanded returns true when no storage set (default)
- `chat_ui_storage.test.ts`: getChatBarExpanded reads from sessionStorage first
- `chat_ui_storage.test.ts`: getChatBarExpanded falls back to localStorage when sessionStorage is empty
- `chat_ui_storage.test.ts`: setChatBarExpanded writes to both storages
- `chat_ui_storage.test.ts`: handles invalid/non-boolean storage values gracefully
