---
status: complete
---

# Architecture: Floating Dropdown Menu

## Component Breakdown

This is a small, frontend-only project with two Svelte components and one TypeScript type definition.

### Types (`$lib/ui/floating_menu_types.ts`)

```typescript
export type FloatingMenuItem = {
  label: string
  href?: string
  onclick?: () => void
  hidden?: boolean
}
```

### `FloatingMenu.svelte` (`$lib/ui/floating_menu.svelte`)

**Responsibilities:**
- Accept a trigger slot and an `items` array
- Manage open/close state (click and optional hover)
- Position the menu using `@floating-ui/dom` (strategy: fixed, with flip + shift + offset middleware)
- Render menu items as `<button>` or `<a>` based on item type
- Call `stopPropagation()` on item click events
- Close menu on item activation or click-outside
- Render nothing if all items are hidden

**Implementation approach:**
- Reuse the existing `Float.svelte` component for positioning (it already wraps `@floating-ui/dom` with `autoUpdate`, `flip`, `shift`, `offset`)
- Visibility controlled by a reactive `isOpen` boolean
- Hover mode: `mouseenter`/`mouseleave` on the wrapper div with a small debounce (~100ms on leave) to allow cursor movement to the menu
- Click mode: toggle on trigger click, close on click-outside via document listener (same pattern as `fancy_select.svelte`)
- Click-outside listener should check for modal context (same `dialog[open]` pattern as `fancy_select.svelte`)

**Key detail:** The trigger slot wrapper and the menu `<ul>` must be siblings so `Float.svelte` can find its parent reference element. The Float component uses `contentElement.parentElement` as the reference.

### `TableActionMenu.svelte` (`$lib/ui/table_action_menu.svelte`)

**Responsibilities:**
- Render the ellipsis "..." SVG button as the trigger
- Pass through `items` and optional `width` to `FloatingMenu`
- Set `hover: true`

**Implementation:** Thin wrapper, ~20 lines. Inlines the SVG from current `table_button.svelte`.

## Testing Strategy

- **Unit test for `FloatingMenu`:** Test that items render correctly, hidden items are excluded, href vs onclick rendering, empty state (all hidden) renders nothing
- **Unit test for `TableActionMenu`:** Test that it renders the ellipsis button and passes items through
- Use vitest + @testing-library/svelte (existing test setup)

## Migration

Each file migration is mechanical:
1. Replace `TableButton` import with `TableActionMenu` import
2. Replace the `div.dropdown > TableButton + ul.dropdown-content` block with `<TableActionMenu items={[...]} />`
3. Convert conditional `{#if}` blocks to `hidden` properties on items
4. Remove any `Float` import if it was only used for this dropdown
5. Remove `TableButton` import

After all migrations, delete `app/web_ui/src/routes/(app)/generate/[project_id]/[task_id]/table_button.svelte`.
