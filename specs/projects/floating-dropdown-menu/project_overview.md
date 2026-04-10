---
status: complete
---

# Floating Dropdown Menu Component

## Problem

We use DaisyUI's `dropdown-content` CSS class for dropdown menus throughout the app. Being pure CSS, it uses `position: absolute` which breaks inside tables, dialogs, scroll areas, and other constrained containers — content gets clipped or mispositioned. We've already adopted `@floating-ui/dom` in several places (info_tooltip.svelte, float.svelte, fancy_select.svelte) to solve this. Some dropdown menus already wrap their content in our `<Float>` component as a partial fix, but the pattern is inconsistent and verbose.

## Goal

Create a reusable floating dropdown menu component that replaces the current `dropdown-content menu` pattern. This should eliminate the CSS positioning bugs while reducing the boilerplate at each call site.

## Current Usage Analysis

**18 instances across 13 files**, falling into two patterns:

### Pattern A: Table Row Action Menus (13 instances, 10 files)
- Trigger: `<TableButton />` (horizontal ellipsis "..." icon) inside a `div.dropdown.dropdown-hover`
- Content: `<ul class="dropdown-content menu">` with 1-5 `<li>` items
- Items are buttons with `on:click` handlers, or occasionally `<a>` links
- Many have conditional items via `{#if}`
- All are inside `<td>` elements (the primary source of positioning bugs)
- 5 already use `<Float>`, 5 do not

### Pattern B: Toolbar Dropdowns (5 instances, 3 files)
- Trigger: Custom icon buttons (tags, filter) — click-triggered, no hover
- Content: Same `<ul class="dropdown-content menu">` structure with 2-3 items
- Used in table toolbars, not inside table rows

### Shared characteristics
- All items are simple: a label + an action (click handler or link)
- No complex/custom content inside any dropdown (no forms, no nested components)
- All use `dropdown-end` positioning
- Menu widths vary: w-40 through w-64

## Design Considerations from User

- Should the component be menu-specific (structured data) or general-purpose (slot for any content)?
- Should it include the trigger button, or just the floating content?
- TableButton is reused everywhere — should it be part of the component or remain separate?
- Should hover-trigger behavior be built in?
- Current `TableButton` lives in an odd location (generate route) — should be relocated to `$lib/ui/`
