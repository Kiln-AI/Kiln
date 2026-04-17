---
status: complete
---

# Phase 2: Sidebar rail + layout wiring

## Overview

Build the icon-rail version of the left nav and wire it into `+layout.svelte` behind an `isRailEligible` derived store (`isLg && isNarrowViewport && chatBarExpanded`), with an additional `section !== Chat` guard (the chat bar hides itself on the chat page, so there's no width pressure there).

New component tree:

- `sidebar_rail.svelte` — top-level rail container, consumes `section` + `openTaskDialog`.
- `sidebar_rail_tooltip.svelte` — shared tooltip primitive wrapping `$lib/ui/float.svelte`.
- `sidebar_rail_item.svelte` — single icon row with tooltip + active state.
- `sidebar_rail_task_chip.svelte` — task letter chip, multi-line tooltip (task name + project).
- `sidebar_rail_optimize_group.svelte` — divider + "OPTIMIZE" link + flat children.
- `sidebar_rail_progress.svelte` — rail trigger with `<Float>`-wrapped `ProgressWidget`.
- `sidebar_rail_settings.svelte` — settings icon with update-dot overlay.

Wiring in `+layout.svelte`:
- Compute `showRail = $isLg && $isNarrowViewport && $chatBarExpanded && section !== Section.Chat`.
- When `showRail`, replace the full `<ul>` contents with `<SidebarRail ... />`.
- Track `prevRailActive` + `justExitedRail` for one-shot 250ms slide-in animation on rail→full transitions.

**Tooltip decision:** DaisyUI's `tooltip tooltip-right` was rejected during implementation (the `::before`/`data-tip` pattern couldn't render the task chip's two-line structured content cleanly). Instead we ship a shared `sidebar_rail_tooltip.svelte` component built on `$lib/ui/float.svelte` (portaled). All four rail components (`sidebar_rail_item`, `sidebar_rail_optimize_group`, `sidebar_rail_settings`, `sidebar_rail_task_chip`) use it — originally the consolidation was deferred to Phase 4, but since all four ended up with identical hover/focus state and the same tooltip component, we folded the cleanup into Phase 2. Phase 4 (tooltip cleanup) therefore collapses to a no-op.

Rail appears/disappears instantly. The full sidebar's interior gets a one-shot `sidebar-slide-in` CSS animation when we transition rail→full.

## Steps

1. **`app/web_ui/src/routes/(app)/sidebar_rail_item.svelte`** — icon-link row with a `SidebarRailTooltip` (shared component). Props: `href: string`, `active?: boolean`, `label: string`. Default slot named `icon`. Tracks local `hovered`/`focused` booleans (mouseenter/leave, focus/blur) and shows the tooltip when either is true. Sets `aria-label={label}`, `aria-current={active ? 'page' : undefined}`. Active bg `bg-base-300`, hover `bg-base-300/50`, rounded `rounded-md`.

2. **`app/web_ui/src/routes/(app)/sidebar_rail_task_chip.svelte`** — 32×32 rounded square button with an uppercase first letter of `$current_task?.name`. Click dispatches `open` event. Tooltip via `SidebarRailTooltip variant="multi" role="tooltip"` with task name (`font-medium`) and project name (`text-gray-500`). No tooltip rendered if both name and project are empty. Aria-label falls back to "Select task".

3. **`app/web_ui/src/routes/(app)/sidebar_rail_optimize_group.svelte`** — renders top/bottom 1px divider (`h-px bg-base-300`), the `OPTIMIZE` link (small text `text-[9px] font-semibold tracking-wider text-gray-500`; tooltip "Optimize"), and the seven child items (Prompts, Models, Tools, Skills, Docs & Search, Fine Tune, Synthetic Data). Props: `section: Section`. Imports icons from `$lib/ui/icons/*`.

4. **`app/web_ui/src/routes/(app)/sidebar_rail_progress.svelte`** — conditional on `$progress_ui_state` non-null. Renders a `<div>` with a small 12px primary pip and a `<Float placement="right-start" offset_px={12}>` containing the unchanged `ProgressWidget`. `<Float>` anchors to its parent, so we make the `<div>` the reference by wrapping the pip in it.

5. **`app/web_ui/src/routes/(app)/sidebar_rail_settings.svelte`** — settings icon link with optional primary dot overlay. Props: `active: boolean`. Subscribes to `$update_info` directly (no `hasUpdate` prop — keeps a single source of truth, matching `SidebarRailProgress`). Tooltip "Settings" or "Settings — Update Available". Reuses the same SVG as the full sidebar.

6. **`app/web_ui/src/routes/(app)/sidebar_rail.svelte`** — top-level rail `<nav aria-label="Primary" class="bg-base-200 text-base-content w-[56px] ...">`. Assembly:
    - Logo `<div>` (non-interactive).
    - `<SidebarRailTaskChip on:open={openTaskDialog} />`
    - Run / Chat / Dataset / Specs & Evals rail items (icons copied from current +layout.svelte).
    - `<SidebarRailOptimizeGroup {section} />` (Synthetic Data is rendered inside this group).
    - Spacer `<div class="flex-1"></div>`.
    - `<SidebarRailProgress />`
    - `<SidebarRailSettings active={section === Section.Settings} />`.
   Props: `section: Section`, `openTaskDialog: () => void`.

7. **Modify `app/web_ui/src/routes/(app)/+layout.svelte`**:
    - Import `isLg`, `isNarrowViewport` from `$lib/stores/viewport`, `chatBarExpanded` from `$lib/stores/chat_ui_state`, `SidebarRail`.
    - Derive `isRailEligible` via `derived([isLg, isNarrowViewport, chatBarExpanded], ...)`, then gate with `section !== Section.Chat` for `showRail`.
    - Reactive `justExitedRail` block (250ms timeout) watching rail→full transitions.
    - In `.drawer-side`, wrap current `<ul>` contents in `{#if showRail} <SidebarRail .../> {:else} ...existing full sidebar markup with class:sidebar-slide-in={justExitedRail}... {/if}`.
    - Add `.sidebar-slide-in` CSS keyframe (250ms linear translateX(-20px) + opacity 0→1).

## Tests

- `app/web_ui/src/routes/(app)/sidebar_rail_item.test.ts`
  - Renders link with correct `href` and `aria-label`.
  - Applies `aria-current="page"` when `active=true`, none when `active=false`.
  - Active class `bg-base-300` present when active.
  - On hover the shared tooltip element (`data-testid="rail-tooltip"`) appears containing the label; disappears on mouseleave.

- `app/web_ui/src/routes/(app)/sidebar_rail_task_chip.test.ts`
  - Renders uppercase first letter when `current_task` is set.
  - Empty chip when no task.
  - Dispatches `open` event on click.
  - Hovering the button reveals a `[role="tooltip"]` element containing both task name and project name when both are set.
  - Tooltip is absent (not rendered) when both task name and project name are empty.

- `app/web_ui/src/routes/(app)/sidebar_rail_settings.test.ts`
  - Dot rendered when `hasUpdate=true`.
  - Dot absent when `hasUpdate=false`.
  - Tooltip text is "Settings — Update Available" when `hasUpdate=true`.
  - Tooltip text is "Settings" when `hasUpdate=false`.
  - `aria-current="page"` when `active=true`.
