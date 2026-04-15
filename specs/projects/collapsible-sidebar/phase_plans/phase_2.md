---
status: draft
---

# Phase 2: Sidebar rail + layout wiring

## Overview

Build the icon-rail version of the left nav and wire it into `+layout.svelte` behind an `isRailActive` derived store (`isLg && isBelow2000 && chatBarExpanded`).

New component tree:

- `sidebar_rail.svelte` — top-level rail container, consumes `section` + `openTaskDialog` and `hasUpdate`.
- `sidebar_rail_item.svelte` — single icon row with tooltip + active state.
- `sidebar_rail_task_chip.svelte` — task letter chip, multi-line tooltip (task name + project).
- `sidebar_rail_optimize_group.svelte` — divider + "OPTIMIZE" link + flat children.
- `sidebar_rail_progress.svelte` — rail trigger with `<Float>`-wrapped `ProgressWidget`.
- `sidebar_rail_settings.svelte` — settings icon with update-dot overlay.

Wiring in `+layout.svelte`:
- Compute `isRailActive = $isLg && $isBelow2000 && $chatBarExpanded`.
- When `isRailActive`, replace the full `<ul>` contents with `<SidebarRail ... />`.
- Track `prevRailActive` + `justExitedRail` for one-shot 250ms slide-in animation on rail→full transitions.

**Tooltip decision** (architecture flags this as the key validation point): we ship DaisyUI `tooltip tooltip-right` for single-line items (nav, settings, optimize label). For the task chip's two-line tooltip, DaisyUI's `data-tip`/`::before` renders pseudo-element content that is difficult to style reliably across themes and breaks with line wraps (multi-line `white-space: pre-line` hack is fragile — `::before` sizing interacts badly with the DaisyUI pointer arrow, and there is no programmatic test surface). For the single chip that needs structured two-line content with distinct typography (medium task name + gray project name), ship a small hand-rolled tooltip inside `sidebar_rail_task_chip.svelte`. Other rail items keep DaisyUI tooltips — less surface area, cheap to refactor later. This means Phase 4 (tooltip cleanup) is a no-op and can be skipped.

Rail appears/disappears instantly. The full sidebar's interior gets a one-shot `sidebar-slide-in` CSS animation when we transition rail→full.

## Steps

1. **`app/web_ui/src/routes/(app)/sidebar_rail_item.svelte`** — icon-link list item with DaisyUI `tooltip tooltip-right`. Props: `href: string`, `active?: boolean`, `label: string`, `narrow?: boolean` (for the OPTIMIZE label variant: shorter pill). Default slot named `icon`. Sets `aria-label={label}`, `aria-current={active ? 'page' : undefined}`, `data-tip={label}`. Active bg `bg-base-300`, hover `bg-base-300/50`, rounded `rounded-md`.

2. **`app/web_ui/src/routes/(app)/sidebar_rail_task_chip.svelte`** — 32×32 rounded square button with an uppercase first letter of `$current_task?.name`. Click dispatches `open` event. Custom hover tooltip: an absolute-positioned `<span>` (hidden by default, shown on `group-hover` using Tailwind) with two lines — task name in `font-medium` and project name in `text-gray-500`. No tooltip if both name and project are empty. Use `pointer-events-none` so hover state doesn't flicker. Aria-label falls back to "Select task".

3. **`app/web_ui/src/routes/(app)/sidebar_rail_optimize_group.svelte`** — renders top/bottom 1px divider (`h-px bg-base-300 mx-2 my-2`), the `OPTIMIZE` link (reusing `SidebarRailItem` pattern but with small text instead of an icon — use a dedicated small-text variant directly; tooltip "Optimize"), and the six child items (Prompts, Models, Tools, Skills, Docs & Search, Fine Tune). Props: `section: Section`. Imports icons from `$lib/ui/icons/*`.

4. **`app/web_ui/src/routes/(app)/sidebar_rail_progress.svelte`** — conditional on `$progress_ui_state` non-null. Renders a `<li>` with a small 12px primary pip and a `<Float placement="right-start" offset_px={12}>` containing the unchanged `ProgressWidget`. `<Float>` anchors to its parent, so we make the `<li>` the reference by wrapping the pip in it.

5. **`app/web_ui/src/routes/(app)/sidebar_rail_settings.svelte`** — settings icon link with optional primary dot overlay. Props: `active: boolean`, `hasUpdate: boolean`. Tooltip "Settings" or "Settings — Update Available". Reuses the same SVG as the full sidebar.

6. **`app/web_ui/src/routes/(app)/sidebar_rail.svelte`** — top-level rail `<ul class="sidebar-menu menu bg-base-200 w-[56px] ...">`. Assembly:
    - Logo li (non-interactive).
    - `<SidebarRailTaskChip on:open={openTaskDialog} />`
    - Run / Chat / Dataset / Specs & Evals rail items (icons copied from current +layout.svelte).
    - `<SidebarRailOptimizeGroup {section} />`
    - Synthetic Data rail item.
    - Spacer `<li class="flex-1"></li>`.
    - `<SidebarRailProgress />`
    - `<SidebarRailSettings active={section === Section.Settings} hasUpdate={hasUpdate} />`.
   Props: `section: Section`, `openTaskDialog: () => void`, `hasUpdate: boolean`.

7. **Modify `app/web_ui/src/routes/(app)/+layout.svelte`**:
    - Import `isLg`, `isBelow2000` from `$lib/stores/viewport`, `chatBarExpanded` from `$lib/stores/chat_ui_state`, `SidebarRail`.
    - Derive `isRailActive` via `derived([isLg, isBelow2000, chatBarExpanded], ...)`.
    - Reactive `justExitedRail` block (250ms timeout) watching rail→full transitions.
    - In `.drawer-side`, wrap current `<ul>` contents in `{#if $isRailActive} <SidebarRail .../> {:else} ...existing full sidebar markup with class:sidebar-slide-in={justExitedRail}... {/if}`.
    - Add `.sidebar-slide-in` CSS keyframe (250ms linear translateX(-20px) + opacity 0→1).

## Tests

- `app/web_ui/src/routes/(app)/sidebar_rail_item.test.ts`
  - Renders link with correct `href` and `aria-label`.
  - Applies `aria-current="page"` when `active=true`, none when `active=false`.
  - Active class `bg-base-300` present when active.
  - `data-tip` equals label.

- `app/web_ui/src/routes/(app)/sidebar_rail_task_chip.test.ts`
  - Renders uppercase first letter when `current_task` is set.
  - Empty chip when no task.
  - Dispatches `open` event on click.
  - Tooltip content contains task name + project name when both are set.
  - Tooltip is absent (not rendered) when both task name and project name are empty.

- `app/web_ui/src/routes/(app)/sidebar_rail_settings.test.ts`
  - Dot rendered when `hasUpdate=true`.
  - Dot absent when `hasUpdate=false`.
  - Tooltip text is "Settings — Update Available" when `hasUpdate=true`.
  - Tooltip text is "Settings" when `hasUpdate=false`.
  - `aria-current="page"` when `active=true`.
