---
status: complete
---

# Phase 2: The Experiment Lineage Page

## Overview

This phase builds the page itself on top of the phase 1 logic. It adds the route `/optimize/[project_id]/[task_id]/experiment_lineage`, the glyph and swatch components, the canvas (toolbar, zoom and pan, hover, keyboard, selection), the filter chips, the stats row, the detail panel, and the loading, error and empty states. It adds component tests for the canvas, the chips and the panel, and unit tests for the few pure helpers the components need. Then it does the visual check and the 1,000-node pan and zoom check in a real browser. Entry points from the Optimize and Compare pages are phase 3, so nothing links to the page yet.

All paths below are relative to `app/web_ui/src/`. The route directory `routes/(app)/optimize/[project_id]/[task_id]/experiment_lineage/` is called `ROUTE/`.

## Steps

1. **`lib/utils/lineage/lineage_glyph.ts`** (edit). Add `radius` to each `GLYPH` entry: graph 2, panel 4, swatch 2. Export `type GlyphSize = { size: number; gap: number; radius: number }`. The glyph needs the radius to round its outline statuses, and the swatch and the canvas clip path read it from here so the value lives in one place.

2. **`lib/utils/lineage/lineage_layout.ts`** (edit). Add a pure helper for the canvas's four edge paths:

   ```ts
   export interface EdgePathGroups { primary: string; extra: string; highlighted_primary: string; highlighted_extra: string }
   export function edge_path_groups(edges: LineageLayout["edges"], highlighted: ReadonlySet<string>): EdgePathGroups
   ```

   Each group joins its edges' `d` strings with no separator (each starts with `M`).

3. **`lib/utils/lineage/lineage_display.ts`** (edit). Add two pure helpers for the panel:

   ```ts
   export type LineagePart = { type: "text"; text: string } | { type: "link"; node_id: string; text: string }
   export function lineage_line_parts(node: LineageNode, graph: LineageGraph): LineagePart[]
   // "Starting point · N children", "Derived from {A} and {B}, {C} · N children",
   // "No recorded parent", "This run config was deleted · N children"
   export function origin_text(origin: string | null | undefined): string | null
   // "agent" → "Created by an agent", "human" → "Created by a person", else null
   ```

4. **`ROUTE/+page.ts`** (new). `export const prerender = false`.

5. **`ROUTE/lineage_glyph.svelte`** (new). `<svelte:options namespace="svg" />`. Props `status: LineageStatus` and `glyph: GlyphSize`. Renders at the origin:
   - `changed`: one `<rect>` per `glyph_rects(kinds, size, gap)`, filled from `CHANGE_KIND_COLORS`. The overlay is preceded by a `fill-base-100` rect inflated by `gap` on every side.
   - `copy`: full square, `fill-base-300`. `starting_point`: full square, `fill-secondary`.
   - `parent_deleted`, `no_parent`: rect inset by 0.5 with `rx = radius - 0.5`, `fill-base-100 stroke-base-300`, width 1. `deleted` adds `stroke-dasharray="2 1.5"`.

6. **`ROUTE/lineage_swatch.svelte`** (new). Props `status` and `glyph: GlyphSize`. `<svg width height viewBox aria-hidden="true" class="shrink-0 overflow-hidden {radius >= 4 ? 'rounded' : 'rounded-sm'}">` around `LineageGlyph`.

7. **`ROUTE/lineage_canvas.svelte`** (new). Props `graph`, `layout`, `filters`, `selected_id`, `initial_center_id`, `model_info`. Events `select` (detail: id) and `close`.
   - Root is the graph frame: `rounded-lg border flex flex-col overflow-hidden h-full`.
   - Toolbar: hint text, then a `join` of `btn btn-sm`: "−", the zoom percentage (non-interactive `span`), "+", "Fit", with the architecture's `aria-label`s.
   - Canvas `div`: `tabindex="0"`, `role="application"`, `aria-label="Run config lineage graph"`, `bind:clientWidth`, `bind:clientHeight`, `cursor-grab` or `cursor-grabbing`, `select-none`.
   - SVG with `<defs><clipPath id="lineage-node-clip" clipPathUnits="userSpaceOnUse"><rect width height rx /></clipPath></defs>` sized from `GLYPH.graph`. The architecture's `objectBoundingBox` clip would cut the outer half of the outline statuses' stroke, because their bounding box is inset by 0.5.
   - One `<g transform="translate(tx ty) scale(k)">` with the four edge paths from `edge_path_groups` (non-scaling stroke, extra edges dashed `3 3`), the grid label, the nodes, then the selection ring (two rects with rounded corners).
   - Each node: `<g transform="translate(x y)" data-node-id opacity class="cursor-pointer">`, holding `<g clip-path="url(#lineage-node-clip)"><LineageGlyph/></g>` and a transparent full-size hit rect on top, so the gaps between segments don't flicker the hover.
   - Hover tooltip: an absolutely positioned, `pointer-events-none` anchor over the hovered node's screen rect, with `{#key hover_id}<Float placement="right" offset_px={8} role="tooltip">` holding the three tooltip lines in InfoTooltip's popover classes. 100ms show delay. Hidden while dragging and on any pan or zoom.
   - `sr-only` `aria-live="polite"` region: `"{title}. {status_text}."` for the selected node.
   - Input as in the architecture: pointerdown/move/up/cancel with a 4px drag threshold and pointer capture; pointerover/out for hover; `on:wheel|nonpassive` (Ctrl/⌘ zooms at the cursor, otherwise pans); Safari `gesturestart`/`gesturechange` attached in `onMount`; `dblclick` fits when the last pointerdown was on empty space; keydown for arrows (`next_selection`, dispatch, `ensure_visible`), Escape, `+`/`=`, `-` and `0`, ignoring keys with Ctrl, ⌘ or Alt held.
   - Viewport lifecycle in one function run reactively on `(layout, view_width, view_height)`: initialize once (center on `initial_center_id` at 100%, else fit), `resize_keep_center` on a view size change, `clamp_viewport` on a layout change.

8. **`ROUTE/lineage_filter_chips.svelte`** (new). Props `counts: Record<FilterKey, number>` and `active: Set<FilterKey>` (two-way bound). The label "Changed from parent" (`text-sm font-medium`) with `InfoTooltip`, six `<button type="button" aria-pressed>` chips (`btn btn-sm gap-2`, `btn-outline` off, `btn-secondary` on) each with a swatch, label and count, then a "Clear" `button.link text-sm text-gray-500` while any chip is on. Toggling assigns a new `Set`.

9. **`ROUTE/lineage_panel.svelte`** (new). Props `project_id`, `task_id`, `node`, `graph`, `ctx: DisplayContext`, `available_tools`. Events `select` and `close`.
   - Header: 40px swatch, the name (`text-lg font-medium truncate`, `title`), the lineage line from `lineage_line_parts` (links are `<button class="link">` that dispatch `select`), and the close button with Dialog's close classes, `CloseIcon` and `aria-label="Close details"`.
   - "Changed from Parent" (`SettingsHeader`) for `changed`, `copy` and `parent_deleted`: the diff grid from `change_rows` with a provider logo on the Model row, or "Same settings as parent.", or the parent-deleted sentence.
   - "Notes" when `provenance.notes` is set: `Output` plus `origin_text`.
   - "Run Configuration": `PropertyList` with `getRunConfigUiProperties(...)`; tools show "Loading..." until the project's tools load. `InputTransformModal` is mounted when the config has a transform. Hidden for the placeholder.
   - Actions: a two-column grid of `btn btn-mid`: "Compare" (hidden for the placeholder) and "Compare to Parent" (only when the primary parent is live), both through `goto(compare_run_configs_link(...))`.
   - Sections are a `flex flex-col gap-6` stack; each section is `flex flex-col gap-4`.

10. **`ROUTE/+page.svelte`** (new).
    - `AppPage` with the title, subtitle and "Optimize" breadcrumb. `agentInfo` set as on sibling pages.
    - Load reactive on `project_id` and `task_id` with the stale-request guard: `load_available_tools(p)` without waiting, then `await Promise.all([load_model_info(), load_task_prompts(p, t), load_task_run_configs(p, t, true)])`. Errors through `createKilnError`.
    - Derived `graph`, `layout`, `summary`, `ctx`, `selected_node`.
    - After a successful load, `await tick()`, then read `selected` from the URL once; keep it if the graph has it, and pass it as `initial_center_id`.
    - `select(id)` sets `selected_id` and calls `goto(experiment_lineage_link(p, t, id), { replaceState: true, noScroll: true, keepFocus: true })`. A store reload that drops the selected node calls `select(null)`.
    - States: spinner (as Optimize), error block (as Compare), `Intro` "No Run Configurations Yet" with a primary "Create Run Config" link to `run_config/create`, else the content stack `flex flex-col gap-6`: stats row (`flex gap-10`, number `text-xl font-medium tabular-nums`, label `text-sm text-gray-500`, singular for 1), the info `Warning` when there are no edges but there are grid nodes, the chips, and the body.
    - Body: `flex flex-col lg:flex-row gap-6`. At `lg` and up its height is `max(420, innerHeight − document top − 96)`, measured on mount, after load and on window resize. 96 is AppPage's `mb-12` plus the app layout's `pb-8` and `mb-4`; the architecture says 64, which leaves out the layout's `pb-8` and makes the page scroll by 32px. Below `lg` the graph is 480px tall and the panel stacks under it. The panel column is 360px and scrolls on its own.

## Tests

- `lineage_glyph.test.ts`: update the `GLYPH` pin for the new radii.
- `lineage_layout.test.ts`, `edge_path_groups`:
  - Splits edges into primary and extra, and moves highlighted ones into the highlighted groups.
  - An empty highlight set leaves the highlighted groups empty; no edges gives four empty strings.
- `lineage_display.test.ts`:
  - `lineage_line_parts` for a starting point, one parent, several parents ("and" then ", "), no recorded parent, the placeholder, and a node whose primary parent is a placeholder ("Deleted run config" link).
  - `origin_text` for "agent", "human", null and an unknown value.
- `ROUTE/lineage_canvas.test.ts` (jsdom, `clientWidth`/`clientHeight` defined on the prototype):
  - Renders one `[data-node-id]` per node, and the grid label with its count.
  - Pointerdown then pointerup on a node dispatches `select` with its id; a 10px drag doesn't; a click on empty space doesn't.
  - Filters dim non-matching nodes to 0.15, but not the selected node; no filters dims nothing.
  - The selected node's ancestor edges are in the highlighted path, and the selection ring renders.
  - Zoom buttons change the label; Fit resets it; `+`, `-` and `0` keys do the same.
  - `Escape` dispatches `close`; arrow keys dispatch `select` (first selection with none, then Up to the parent); a key with ⌘ held is ignored.
  - Starts centered at 100% on `initial_center_id`.
  - Hovering a node shows the tooltip lines after the delay (fake timers).
  - The live region announces the selected node.
- `ROUTE/lineage_filter_chips.test.ts`: six chips with labels and counts in order; a click toggles `aria-pressed` and the bound set; two chips can be on; Clear appears only while a chip is on and resets the set.
- `ROUTE/lineage_panel.test.ts`:
  - Diff rows render for a changed node, with the new and struck-through old values.
  - Copy text and parent-deleted text render; the section is hidden for a starting point and the placeholder.
  - Parent links dispatch `select`; the close button dispatches `close`.
  - "Compare" calls `goto` with the compare link and an empty second column; "Compare to Parent" puts the parent first; it is hidden when the parent is deleted and for a starting point; the placeholder shows neither button and no property list.
  - Notes and the origin line appear only when present.
- Visual check: run the web app against a mocked API in Chromium with a seeded lineage of about 180 run configs, screenshot the page next to the run config detail page at the same width, and pan and zoom a 1,000-node lineage to confirm it stays smooth. The seeding script lives outside the repo.
