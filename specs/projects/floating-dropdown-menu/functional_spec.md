---
status: complete
---

# Functional Spec: Floating Dropdown Menu

## Scope

Replace the 13 table-row action menu instances (Pattern A from the overview) with a floating-ui-powered component. The 5 toolbar dropdown instances (Pattern B) are out of scope — they work fine in their current context.

## Components

### 1. `FloatingMenu.svelte` (`$lib/ui/floating_menu.svelte`)

A menu component that renders a floating list of action items anchored to a trigger element.

**Props:**

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `items` | `FloatingMenuItem[]` | required | Menu items to display |
| `placement` | `Placement` | `"bottom-end"` | floating-ui placement |
| `width` | `string` | `"w-52"` | Tailwind width class for the menu |
| `hover` | `boolean` | `false` | Open on hover (in addition to click) |

**`FloatingMenuItem` type:**

```typescript
type FloatingMenuItem = {
  label: string
  href?: string          // renders as <a> link
  onclick?: () => void   // renders as <button>
  hidden?: boolean       // conditionally hide (simpler than {#if} at each call site)
}
```

Items with `href` render as `<a>` tags. Items with `onclick` render as `<button>` tags. Items with `hidden: true` are not rendered. At least one of `href` or `onclick` must be provided.

**Trigger:** A named slot (`trigger`) for the element that opens the menu. The component wraps it and handles show/hide.

**Behavior:**
- When `hover` is false: opens on click of trigger, closes on click outside or on item selection
- When `hover` is true: opens on mouseenter of trigger area, closes on mouseleave (with a small delay to allow moving to the menu). Also supports click for accessibility.
- Menu is positioned using `@floating-ui/dom` with `flip()` and `shift()` middleware, using `strategy: "fixed"` to escape overflow containers
- Menu closes after any item is clicked/activated
- Uses existing `Float.svelte` internally if suitable, or implements floating-ui directly

**Rendered HTML structure:**
```html
<!-- trigger wrapper -->
<div class="relative inline-block">
  <slot name="trigger" />
</div>

<!-- floating menu (positioned fixed via floating-ui) -->
<ul class="menu bg-base-100 rounded-box p-2 shadow {width}">
  {#each items as item}
    {#if !item.hidden}
      <li>
        <!-- <a> or <button> depending on item type -->
      </li>
    {/if}
  {/each}
</ul>
```

### 2. `TableActionMenu.svelte` (`$lib/ui/table_action_menu.svelte`)

A convenience wrapper for the most common pattern: ellipsis button + floating menu in a table row.

**Props:**

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `items` | `FloatingMenuItem[]` | required | Menu items to display |
| `width` | `string` | `"w-52"` | Tailwind width class |

**Behavior:**
- Renders the ellipsis "..." button (currently `TableButton`) as the trigger
- Sets `hover: true` and `placement: "bottom-end"` on `FloatingMenu`
- The ellipsis icon SVG is inlined (absorbed from current `table_button.svelte`)

**Usage at call sites (before → after):**

Before (current, ~15 lines):
```svelte
<div class="dropdown dropdown-end dropdown-hover">
  <TableButton />
  <!-- svelte-ignore a11y-no-noninteractive-tabindex -->
  <ul tabindex="0"
    class="dropdown-content menu bg-base-100 rounded-box z-[1] w-52 p-2 shadow">
    <li><button on:click={handleClone}>Clone</button></li>
    {#if !is_default}
      <li><button on:click={handleSetDefault}>Set as Default</button></li>
    {/if}
  </ul>
</div>
```

After (~6 lines):
```svelte
<TableActionMenu items={[
  { label: "Clone", onclick: handleClone },
  { label: "Set as Default", onclick: handleSetDefault, hidden: is_default },
]} />
```

## Migration Plan

All 13 table-row dropdown instances across 10 files will be migrated to `TableActionMenu`. The old `table_button.svelte` in the generate route will be deleted after migration.

### Files to migrate:
1. `tools/[project_id]/tool_servers/[tool_server_id]/+page.svelte` (1 instance, has Float)
2. `skills/[project_id]/+page.svelte` (1 instance, has Float)
3. `settings/providers/add_models/+page.svelte` (1 instance, no Float)
4. `settings/manage_projects/+page.svelte` (1 instance, no Float)
5. `prompts/[project_id]/[task_id]/+page.svelte` (1 instance, has Float)
6. `prompt_optimization/.../create_prompt_optimization_job/+page.svelte` (1 instance, no Float)
7. `optimize/[project_id]/[task_id]/+page.svelte` (1 instance, has Float)
8. `generate/.../qna/qna_document_node.svelte` (3 instances, no Float)
9. `generate/.../generated_data_node.svelte` (2 instances, no Float)
10. `docs/library/[project_id]/[document_id]/+page.svelte` (1 instance, no Float)

## Out of Scope

- Toolbar dropdowns (Pattern B) — working fine, different trigger pattern
- General-purpose floating content wrapper — `Float.svelte` already serves this role
- Keyboard navigation within the menu (not present in current implementation, can be added later)
- Nested/submenu support

## Edge Cases

- **Empty items list / all items hidden:** Render nothing (no trigger, no menu). The ellipsis button shouldn't appear if there are no actions.
- **Single item:** Still renders normally as a menu with one item.
- **Menu near viewport edge:** Handled by floating-ui's `flip()` and `shift()` middleware.
- **Menu inside scroll containers / dialogs / tables:** Handled by `strategy: "fixed"` — this is the whole point.
- **stopPropagation:** Several current call sites use `on:click|stopPropagation` on items. The component should call `stopPropagation` on item click events by default (table rows often have row-level click handlers).
