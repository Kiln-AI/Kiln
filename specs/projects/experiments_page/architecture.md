---
status: draft
---

# Architecture: Experiment Lineage Page

Web UI only (`app/web_ui`). No backend, API or schema changes. No new npm dependency. The graph is drawn as SVG in Svelte, with our own layout and zoom and pan code. Behavior is defined in `functional_spec.md` and look in `ui_design.md`. This doc defines the code.

## Why Own SVG (Decided)

Mike's prototype added no npm packages either. It used inline SVG, a hand-written layout, and hand-written pointer and wheel handlers. echarts was rejected:

- Its tree series takes one root and one parent per node, so it can't draw merges.
- Its graph series has no elbow edges and gives one color per node.
- Its default roam zooms on a plain scroll.
- It draws to a canvas, which rules out per-node focus and DOM tests.

Graph libraries were rejected too. Cytoscape and Svelte Flow are too heavy, dagre and elk give a different layout look, and d3-zoom gains little for a desktop browser. SVG keeps theme tokens, reactive classes and testable DOM. The worst case, 1,000 nodes, is about 7,000 elements, and pan and zoom change one transform.

## File Inventory

```
app/web_ui/src/lib/utils/
  chart_palette.ts                      NEW   CHART_PALETTE (shared with Compare charts)
  chart_palette.test.ts                 NEW
  link_builder.ts                       EDIT  + experiment_lineage_link, compare_run_configs_link
  link_builder.test.ts                  EDIT
  lineage/
    lineage_graph.ts      (+ .test.ts)  NEW   graph model, statuses, summary, filters, ancestors
    lineage_changes.ts    (+ .test.ts)  NEW   change detection between two run configs
    lineage_glyph.ts      (+ .test.ts)  NEW   kind colors and labels, glyph rectangles
    lineage_layout.ts     (+ .test.ts)  NEW   tree + grid layout, edge paths, rows
    lineage_viewport.ts   (+ .test.ts)  NEW   zoom and pan math
    lineage_navigation.ts (+ .test.ts)  NEW   arrow-key selection
    lineage_display.ts    (+ .test.ts)  NEW   display strings for tooltip, panel, diff rows
    __tests__/lineage_fixtures.ts       NEW   run config builders for tests (test support only)
app/web_ui/src/lib/components/
  compare_chart.svelte                  EDIT  color: CHART_PALETTE
  compare_radar_chart.svelte            EDIT  color: CHART_PALETTE
app/web_ui/src/routes/(app)/optimize/[project_id]/[task_id]/
  +page.svelte                          EDIT  header button + row menu item
  experiment_lineage/
    +page.ts                            NEW   export const prerender = false
    +page.svelte                        NEW   loading, state, URL sync, layout of the page
    lineage_canvas.svelte  (+ test)     NEW   SVG graph, toolbar, zoom/pan, hover, keyboard
    lineage_glyph.svelte                NEW   <svelte:options namespace="svg" />, glyph rects
    lineage_swatch.svelte               NEW   glyph in a standalone <svg> for HTML contexts
    lineage_filter_chips.svelte (+ test) NEW  chips row
    lineage_panel.svelte   (+ test)     NEW   detail panel
app/web_ui/src/routes/(app)/specs/[project_id]/[task_id]/compare/+page.svelte
                                        EDIT  AppPage action button
```

The `lib/utils/lineage/` modules are pure TypeScript: no stores, no DOM and no Svelte. Components and the page own all store reads. The Svelte components are used by this route only, so they live beside the page (web_ui.md: move to `lib/` only when a second route needs one).

## Shared Chart Palette

```ts
// lib/utils/chart_palette.ts
// The series colors for every Kiln chart. Equal to echarts 6's built-in default
// palette, which the Compare charts used before it was named here.
export const CHART_PALETTE = [
  "#5070dd", "#b6d634", "#505372", "#ff994d", "#0ca8df",
  "#ffd10a", "#fb628b", "#785db0", "#3fbe95",
] as const
```

`compare_chart.svelte` and `compare_radar_chart.svelte` add `color: [...CHART_PALETTE]` at the root of the options object they pass to `chartInstance.setOption(...)`. This doesn't change how they look. `chart_palette.test.ts` pins the nine values, so a change is deliberate.

## Graph Model: `lineage_graph.ts`

```ts
export type ChangeKind = "prompt" | "tools" | "skills" | "model" | "settings"
export const CHANGE_KINDS: readonly ChangeKind[] = ["prompt", "tools", "skills", "model", "settings"]

export type LineageStatus =
  | { type: "starting_point" }
  | { type: "changed"; kinds: ChangeKind[] } // non-empty, in CHANGE_KINDS order
  | { type: "copy" }
  | { type: "parent_deleted" }
  | { type: "no_parent" }
  | { type: "deleted" } // the placeholder for a missing parent id

export interface LineageNode {
  id: string
  config: TaskRunConfig | null // null only for "deleted"
  parent_ids: string[] // primary first; cleaned and cycle-free
  child_ids: string[] // oldest first
  status: LineageStatus
  row: number // longest path from a root; 0 for roots and grid nodes
  sort_key: string // created_at; a placeholder uses its oldest child's
}

export interface LineageEdge { id: string; parent_id: string; child_id: string; primary: boolean }

export interface LineageGraph {
  nodes: Map<string, LineageNode>
  edges: LineageEdge[]
  tree_root_ids: string[] // roots that have children, by sort_key then id
  no_parent_ids: string[] // grid nodes, by sort_key then id
}

export function build_lineage_graph(configs: TaskRunConfig[]): LineageGraph
export function ancestor_edge_ids(graph: LineageGraph, id: string): Set<string>

export type FilterKey = ChangeKind | "copy"
export const FILTER_KEYS: readonly FilterKey[] = [...CHANGE_KINDS, "copy"]
export function node_matches_filters(status: LineageStatus, filters: ReadonlySet<FilterKey>): boolean

export interface LineageSummary {
  run_config_count: number
  model_count: number
  filter_counts: Record<FilterKey, number>
}
export function summarize_lineage(graph: LineageGraph): LineageSummary
```

`build_lineage_graph` runs these steps in order. It never throws.

1. **Nodes.** Make one node per config with a non-empty `id`. The first config wins for a duplicate id. `sort_key` is `created_at ?? ""`.
2. **Parent lists.** Read `provenance?.derived_from_ids ?? []`. Skip `null` and empty entries, the node's own id, and repeats. For an id with no config, create one `deleted` placeholder per distinct missing id, with `config: null`.
3. **Cycle breaking.** Visit nodes by `(sort_key, id)` ascending with a white, grey and black DFS over `parent_ids`. A parent that is grey (on the stack) closes a cycle. Remove it from the child's `parent_ids`. Do this before any child lists are built.
4. **Edges and child lists.** Build one edge per remaining (parent, child) pair, with `primary = index === 0` and id `` `${parent_id}->${child_id}` ``. Sort each `child_ids` by `(sort_key, id)`. A placeholder's `sort_key` is the smallest `sort_key` of its children.
5. **Rows.** `row = max(row(parent) + 1)` over all parents, memoized, with 0 for no parents.
6. **Statuses.**
   - A placeholder is `deleted`.
   - No parents: `starting_point` if it has children, else `no_parent`.
   - A primary parent that is a placeholder: `parent_deleted`.
   - Otherwise: `detect_changes(primary.config, node.config)`. An empty result is `copy`, anything else is `changed`.
7. **Roots and grid.**
   - `tree_root_ids`: nodes with no parents and at least one child. That includes placeholders.
   - `no_parent_ids`: nodes with status `no_parent`.
   - Both are sorted by `(sort_key, id)`.

`ancestor_edge_ids` does a breadth-first walk up all `parent_ids` from `id` and collects every edge it crosses.

`node_matches_filters`:

- An empty set matches everything.
- `changed` matches if any of its kinds is in the set.
- `copy` matches if the set has `"copy"`.
- Every other status never matches.

`summarize_lineage`:

- `run_config_count` counts the nodes whose status isn't `deleted`.
- `model_count` is the number of distinct `` `${model_provider_name}::${model_name}` `` keys over `kiln_agent` configs.
- `filter_counts` counts each kind once per `changed` node that contains it, and `copy` once per `copy` node.

## Change Detection: `lineage_changes.ts`

```ts
export type SettingField = "temperature" | "top_p" | "thinking_level" | "structured_output_mode" | "input_transform"
export const SETTING_FIELDS: readonly SettingField[] = [...]
export function detect_changes(parent: TaskRunConfig, child: TaskRunConfig): ChangeKind[]
export function changed_setting_fields(parent: KilnAgentRunConfigProperties, child: KilnAgentRunConfigProperties): SettingField[]
```

`detect_changes` compares `run_config_properties` (call them `a` and `b`) and returns kinds in `CHANGE_KINDS` order:

- **Different `type`**: `["model"]`.
- **Both `mcp`**: `[]` if `a.tool_reference.tool_id === b.tool_reference.tool_id`, else `["model"]`.
- **Both `kiln_agent`**:
  - prompt: `a.prompt_id !== b.prompt_id`.
  - tools and skills: split each side's `tools_config?.tools ?? []` with `split_tool_and_skill_ids`. Compare `tool_ids` as sets, and `skill_ids` as sets.
  - model: `model_name` or `model_provider_name` differs.
  - settings: `changed_setting_fields(a, b).length > 0`.

`changed_setting_fields` compares `temperature` and `top_p` with `!==`, `thinking_level ?? null`, and `structured_output_mode`. Input transforms are compared with `!inputTransformsEqual(a.input_transform, b.input_transform)`, the existing helper in `run_config_formatters.ts`.

## Glyph: `lineage_glyph.ts`, `lineage_glyph.svelte`, `lineage_swatch.svelte`

```ts
export const CHANGE_KIND_COLORS: Record<ChangeKind, string> = {
  prompt: CHART_PALETTE[0], tools: CHART_PALETTE[7], skills: CHART_PALETTE[4],
  model: CHART_PALETTE[3], settings: CHART_PALETTE[5],
}
export const CHANGE_KIND_LABELS: Record<ChangeKind, string> = {
  prompt: "Prompt", tools: "Tools", skills: "Skills", model: "Model", settings: "Settings",
}
export const FILTER_LABELS: Record<FilterKey, string> = { ...CHANGE_KIND_LABELS, copy: "Copy or re-run" }
export interface GlyphRect { x: number; y: number; w: number; h: number; kind: ChangeKind; overlay: boolean }
export function glyph_rects(kinds: ChangeKind[], size: number, gap: number): GlyphRect[]
export const GLYPH = { graph: { size: 14, gap: 1 }, panel: { size: 40, gap: 2 }, swatch: { size: 12, gap: 1 } } as const
```

`glyph_rects` ports `nodeRects()` from `design_reference/lineage.js`. The unit shapes are:

| Kinds | Unit rectangles |
|---|---|
| 1 | `[0,0,1,1]` |
| 2 | `[0,0,.5,1]`, `[.5,0,.5,1]` |
| 3 | `[0,0,.5,1]`, `[.5,0,.5,.5]`, `[.5,.5,.5,.5]` |
| 4 | the four quadrants: top left, top right, bottom left, bottom right |
| 5 | the four quadrants, plus the overlay `[.3,.3,.4,.4]` |

Scale each by `size`. Inset only the internal edges by `gap / 2`. An edge is internal when its unit coordinate is strictly between 0 and 1. The overlay is not inset. Kinds take the rectangles in order. Fewer than one kind or more than five returns `[]`.

`lineage_glyph.svelte` declares `<svelte:options namespace="svg" />` and takes `status`, `size` and `gap`. It renders SVG only, at the origin:

- `changed`: one `<rect>` per `GlyphRect`, with `fill` from `CHANGE_KIND_COLORS`. The overlay is drawn after a white rect inflated by `gap` on every side, which gives the white outline.
- `copy`: a full square, `class="fill-base-300"`.
- `starting_point`: a full square, `class="fill-secondary"`.
- `parent_deleted` and `no_parent`: a rect inset by 0.5, `class="fill-base-100 stroke-base-300"`, `stroke-width="1"`.
- `deleted`: the same as the previous row, plus `stroke-dasharray="2 1.5"`.

Rounded corners:

- **In the canvas:** every node's glyph sits in a `<g clip-path="url(#lineage-node-clip)">`. The canvas defines that clip path once in its `<defs>`: `clipPathUnits="objectBoundingBox"` with a `<rect width="1" height="1" rx="0.143" ry="0.143"/>`. That's 2px on 14px.
- **In HTML:** `lineage_swatch.svelte` wraps the glyph in `<svg width={size} height={size} viewBox="0 0 {size} {size}" aria-hidden="true" class="shrink-0 overflow-hidden {size >= 32 ? 'rounded' : 'rounded-sm'}">`.

## Layout: `lineage_layout.ts`

```ts
export const LAYOUT = { node: 14, col_gap: 4, row_height: 28, padding: 16, section_gap: 40, label_height: 16 } as const
export interface LineageLayout {
  positions: Map<string, { x: number; y: number }> // top-left of each node square, world px
  edges: { id: string; primary: boolean; d: string }[]
  grid_label: { x: number; y: number } | null
  rows: string[][] // node ids grouped by y (top to bottom), each sorted by x
  width: number
  height: number
}
export function layout_lineage(graph: LineageGraph, config = LAYOUT): LineageLayout
```

1. **Placement tree.** Each tree node hangs under `parent_ids[0]`. Placement children are sorted by `(sort_key, id)`.
2. **Columns.** Walk the roots in order, post-order. A placement leaf takes `next_col++`. An internal node takes the mean of its first and last placement children's columns. Roots continue the same counter, so trees sit side by side. Two nodes in one row never overlap: each node sits inside its own subtree's column range, and those ranges don't overlap.
3. **Tree positions.** `x = padding + col * (node + col_gap)` and `y = padding + row * row_height`.
4. **Grid.** Grid nodes are laid out in the order of `no_parent_ids`.
   - Columns: `cols = max(floor((tree_inner_width + col_gap) / (node + col_gap)), ceil(sqrt(n * 4)), 1)`, where `tree_inner_width` is 0 when there is no tree.
   - Top: `grid_top = (tree ? tree_bottom + section_gap : padding) + label_height`.
   - Positions: node `i` goes to column `i % cols` and row `floor(i / cols)`, with `node + col_gap` spacing in both directions.
   - `grid_label` is at `{ x: padding, y: grid_top - 6 }`. It is `null` when there are no grid nodes.
5. **Edges.** For each graph edge: `x1 = parent.x + node/2`, `y1 = parent.y + node`, `x2 = child.x + node/2`, `y2 = child.y`, `m = y2 - (row_height - node) / 2`. The path is `` `M${x1} ${y1}V${m}H${x2}V${y2}` ``.
6. **Size.** `width` and `height` are the maximum node extent plus `padding`. An empty graph gives `0`.
7. **Rows.** Group all positioned nodes by `y` and sort each group by `x`.

## Viewport: `lineage_viewport.ts`

The world maps to the screen as `screen = world * k + t`. View coordinates are relative to the canvas element.

```ts
export interface Viewport { k: number; tx: number; ty: number }
export interface Size { width: number; height: number }
export const ZOOM_MAX = 2, ZOOM_FLOOR = 0.5, ZOOM_STEP = 1.25, FIT_MARGIN = 24, PAN_KEEP = 40
export function fit_zoom(world: Size, view: Size): number // min((vw-2m)/w, (vh-2m)/h, 1); 1 for an empty world
export function min_zoom(world: Size, view: Size): number // min(ZOOM_FLOOR, fit_zoom)
export function fit(world: Size, view: Size): Viewport // fit_zoom, centered
export function zoom_at(vp: Viewport, point: { x: number; y: number }, k: number, world: Size, view: Size): Viewport
export function zoom_step(vp: Viewport, direction: 1 | -1, world: Size, view: Size): Viewport // about the view center
export function pan_by(vp: Viewport, dx: number, dy: number, world: Size, view: Size): Viewport
export function center_on(point: { x: number; y: number }, k: number, world: Size, view: Size): Viewport
export function ensure_visible(vp: Viewport, rect: { x: number; y: number; w: number; h: number }, world: Size, view: Size, margin?: number): Viewport
export function resize_keep_center(vp: Viewport, old_view: Size, new_view: Size): Viewport
export function wheel_delta_px(delta: number, delta_mode: number, view_height: number): number // 0 → px, 1 → ×16, 2 → ×view_height
export function wheel_zoom_factor(delta_y_px: number): number // Math.exp(-delta_y_px / 200)
```

Every function that returns a viewport clamps it:

- `k` to `[min_zoom, ZOOM_MAX]`.
- `tx` and `ty` so that at least `PAN_KEEP` px of the world stays inside the view on each axis.
- `zoom_at` keeps the world point under `point` fixed.
- `resize_keep_center` shifts `t` by half the change in view size. It is the only function that doesn't clamp, because the next interaction clamps.

## Navigation: `lineage_navigation.ts`

```ts
export type NavKey = "ArrowUp" | "ArrowDown" | "ArrowLeft" | "ArrowRight"
export function next_selection(graph: LineageGraph, layout: LineageLayout, current: string | null, key: NavKey): string | null
```

- With no current selection, any key picks `layout.rows[0][0]`, or `null` for an empty graph.
- Up picks `parent_ids[0]`. Down picks `child_ids[0]`.
- Left and Right pick the neighbor in the current node's `rows` entry.
- With no target, it returns `current` unchanged.

## Display Strings: `lineage_display.ts`

```ts
export interface DisplayContext {
  model_info: ProviderModels | null
  task_prompts: PromptResponse | null
  project_tools: ToolSetApiDescription[] | null // available_tools[project_id] ?? null
}
export interface ChangeRow { kind: ChangeKind; value: string; previous: string; provider_id: string | null }
export function node_title(node: LineageNode): string // config.name, or "Deleted run config"
export function status_text(status: LineageStatus): string
export function node_model_text(node: LineageNode, model_info: ProviderModels | null): string
export function children_text(count: number): string // "No children", "1 child", "N children"
export function change_rows(parent: TaskRunConfig, child: TaskRunConfig, kinds: ChangeKind[], ctx: DisplayContext): ChangeRow[]
```

- **`status_text`** returns the functional spec's tooltip line 2 for each status. For `changed`, it's the kinds' labels joined by ", ".
- **`node_model_text`** returns `getRunConfigModelDisplayName(...)` for `kiln_agent`, `"MCP: " + tool_name` for MCP, and `""` for placeholders.
- **`change_rows`** returns one row per kind:
  - prompt: `getRunConfigPromptDisplayName(...) ?? prompt_id`.
  - tools and skills: `get_tool_names_from_ids(ids, project_tools)` joined by ", ". It falls back to the raw ids when `project_tools` is `null`, and shows `"None"` when the list is empty.
  - model: `node_model_text`. `provider_id` is set for `kiln_agent`, for the logo.
  - settings: only the changed fields, each as `"{Label} {value}"`, joined by " · ".
    - Labels: "Temperature", "Top P", "Thinking", "Output", "Input transform".
    - Values: `thinking_level` shows `getThinkingLevelDisplayName(...)`, or "Default" when it is `null`. Output mode shows `structuredOutputModeToString(...)`. The input transform shows `getInputTransformDisplay(...).valueLabel`, or "None".
  - A kind that can't apply returns `"—"`, for example a prompt on an MCP side.

## Links: `link_builder.ts`

```ts
export function experiment_lineage_link(project_id: string, task_id: string, selected_id?: string | null): string
// /optimize/{p}/{t}/experiment_lineage[?selected={id}]
export function compare_run_configs_link(project_id: string, task_id: string, run_config_ids: (string | null)[]): string
// /specs/{p}/{t}/compare?from=optimize&columns={n}&models={ids joined by ",", null as ""}
```

Both build their query strings with `URLSearchParams`. Compare reads them back with `searchParams.get` and then splits on ",", so the encoding survives the round trip.

## Components

### `+page.svelte`

- **Load.** The load is reactive on `project_id` and `task_id`, with the same stale-request guard as the Optimize page. It calls `load_available_tools(project_id)` without waiting, then `await Promise.all([load_model_info(), load_task_prompts(p, t), load_task_run_configs(p, t, true)])`. Errors go through `createKilnError` into an `error` state. The page reads `$run_configs_by_task_composite_id[get_task_composite_id(p, t)] ?? []`.
- **Derived state:**
  - `graph = build_lineage_graph(configs)`
  - `layout = layout_lineage(graph)`
  - `summary = summarize_lineage(graph)`
  - `ctx: DisplayContext`
- **Local state:** `filters: Set<FilterKey>`, `selected_id: string | null`.
- **URL sync.** After the first load completes, read `selected` once from `$page.url.searchParams`. Keep it only if `graph.nodes.has(id)`, and pass it as `initial_center_id`. Later selection changes call `goto(experiment_lineage_link(p, t, selected_id), { replaceState: true, noScroll: true, keepFocus: true })`.
- **Body height.** At `lg` and up (`window.matchMedia("(min-width: 1024px)")`), the height is `max(420, innerHeight - body_el.getBoundingClientRect().top - 64)`. The 64 is AppPage's `mb-12` plus the layout's `mb-4`. It's recomputed on mount, after the first load, and on `svelte:window` resize. Below `lg`, the graph frame is 480px tall.
- **Layout order:**
  1. `AppPage`: title, subtitle and breadcrumb.
  2. Loading spinner, error block, or `Intro` for zero configs.
  3. Stats row.
  4. An info `Warning` when `graph.edges.length === 0 && graph.no_parent_ids.length > 0`.
  5. `LineageFilterChips bind:active={filters} counts={summary.filter_counts}`.
  6. Body: `LineageCanvas` and, when `selected_id` is set, `LineagePanel`.

### `lineage_canvas.svelte`

- **Props:** `graph`, `layout`, `filters`, `selected_id`, `initial_center_id`, `model_info`.
- **Events:** `select` (detail: id) and `close`.
- **DOM:** a toolbar row, then a canvas `div`. It is `relative overflow-hidden`, has `tabindex="0"` and `aria-label="Run config lineage graph"`, and carries `bind:this`, `bind:clientWidth` and `bind:clientHeight`. Inside it:
  - One `<svg>` (100% by 100%, `aria-hidden="true"`), with `<defs>` holding the clip path.
  - `<g transform="translate(tx ty) scale(k)">` holding:
    - Four edge `<path>`s: normal primary, normal extra, highlighted primary and highlighted extra. Each joins its edges' `d` strings into one path. All use `fill="none"` and `vector-effect="non-scaling-stroke"`. Extra edges use `stroke-dasharray="3 3"`. Normal edges are `stroke-base-300` at 1px, highlighted are `stroke-secondary` at 1.5px. Highlighted means `ancestor_edge_ids(graph, selected_id)`, memoized on `(graph, selected_id)`.
    - The grid label as `<text class="text-xs fill-gray-500">`.
    - The nodes, as `{#each [...graph.nodes.values()] as node (node.id)}`. Each is `<g transform="translate(x y)" data-node-id={node.id} opacity={dim ? 0.15 : 1} class="cursor-pointer">` with the clipped `LineageGlyph` inside. Dimming applies when `!node_matches_filters(node.status, filters) && node.id !== selected_id`.
    - The selection ring, drawn last. It's two rects: one at `x-1, y-1, 16, 16` with `stroke-base-100` width 2, and one at `x-2.75, y-2.75, 19.5, 19.5` with `stroke-secondary` width 1.5. Both use `fill="none"`.
  - The tooltip anchor, an absolutely positioned `div` covering the hovered node's screen rect. Inside it, `{#key hover_id}<Float placement="right" offset_px={8} role="tooltip">`, holding a `div` with `InfoTooltip`'s popover classes (`px-3 py-2 text-sm text-base-content bg-stone-200 rounded-md shadow-lg`, left aligned, `max-w-72`). It shows `node_title`, `status_text` and `node_model_text`.
  - An `aria-live="polite"` visually hidden `div` that announces `"{title}. {status_text}."` for the selected node.
- **Input**, delegated from the canvas `div`. Node ids come from `(event.target as Element).closest("[data-node-id]")`.
  - `pointerdown` (button 0): call `setPointerCapture` and record the start point and the node id under the pointer.
  - `pointermove`: once the pointer has moved more than 4px, set `dragging`, hide the tooltip, and `pan_by` the movement.
  - `pointerup`: release capture. If it wasn't a drag and a node was under the pointer at `pointerdown`, dispatch `select`.
  - Hover: `pointerover` and `pointerout` with a 100ms show delay. Suppressed while dragging.
  - `wheel` is bound with `on:wheel|nonpassive` and always calls `preventDefault()`. With `ctrlKey` or `metaKey`, it calls `zoom_at(cursor, k * wheel_zoom_factor(dy))`. Without, it calls `pan_by(-dx, -dy)`. Deltas go through `wheel_delta_px`.
  - Safari pinch: `gesturestart` stores `k`. `gesturechange` calls `preventDefault()` and `zoom_at(cursor, start_k * event.scale)`. These events aren't in the DOM typings, so read `scale` through a narrow local type.
  - `dblclick` on empty space calls `fit`.
  - `keydown`:
    - Arrow keys call `next_selection`, dispatch `select`, then `ensure_visible`.
    - `Escape` dispatches `close`.
    - `+` or `=` zooms in, `-` zooms out, and `0` fits.
    - Arrow keys and the zoom keys call `preventDefault()`.
- **Toolbar.** The hint text, then a `join` of `btn btn-sm`: "−" (`aria-label="Zoom out"`), the zoom as `Math.round(k * 100)%` in a non-interactive `span`, "+" (`aria-label="Zoom in"`), and "Fit" (`aria-label="Fit graph"`).
- **Viewport lifecycle:**
  - Once the view and `layout.width` are both non-zero, it initializes once. With `initial_center_id`, it calls `center_on` at k=1 on that node's center. Otherwise it calls `fit`.
  - When the view size changes (a reactive comparison with the previous size), it calls `resize_keep_center`.
  - When `layout` changes after initialization, it keeps the viewport and re-clamps it.

### `lineage_filter_chips.svelte`

- **Props:** `counts: Record<FilterKey, number>` and `active: Set<FilterKey>` (two-way bound).
- **Each chip:**
  - Element: a `<button type="button" aria-pressed={on}>`.
  - Class: `btn btn-sm gap-2` plus `btn-outline` when off, or `btn-secondary` when on.
  - Contents: a `LineageSwatch` (a one-kind `changed` status, or `copy`), the label, and the count (`text-gray-500` when off, `opacity-70` when on).
- **Toggling:** assigns a new `Set`, so Svelte sees the change.
- **Label:** "Changed from parent", `text-sm font-medium`, with `InfoTooltip` holding the spec text.
- **Clear:** shown while the set is non-empty. `<button class="link text-sm text-gray-500">Clear</button>`.

### `lineage_panel.svelte`

- **Props:** `project_id`, `task_id`, `node`, `graph`, `ctx: DisplayContext`, `available_tools: Record<string, ToolSetApiDescription[]>`.
- **Events:** `select` (detail: id) and `close`.
- **Header:** `LineageSwatch` at `GLYPH.panel`, the name, and the lineage line. Parent names are `<button class="link">` elements that dispatch `select`. Children use `children_text`. The close button uses `Dialog`'s classes and `CloseIcon`, with `aria-label="Close details"`.
- **Sections**, per the functional spec, each under a `SettingsHeader`. "Changed from Parent" uses `change_rows` when `status.type === "changed"`, with the logo from `get_provider_image(provider_id)`. "Notes" uses `Output raw_output={notes}`. "Run Configuration" uses `PropertyList` with `getRunConfigUiProperties(project_id, task_id, config, ctx.model_info, ctx.task_prompts, available_tools, () => input_transform_modal?.show())`. `InputTransformModal` is mounted when the config has a transform, as on the detail page.
- **Actions:**
  - "Compare" goes to `compare_run_configs_link(p, t, [node.id, null])`.
  - "Compare to Parent" goes to `compare_run_configs_link(p, t, [parent_ids[0], node.id])`, only when that parent's status isn't `deleted`.
  - Both use `goto`.

## Entry Points

- **Optimize `+page.svelte`:**
  - In the not-select-mode branch, before "Compare": `<button class="btn btn-mid" on:click={() => goto(experiment_lineage_link(project_id, task_id))}>Experiment Lineage</button>`.
  - Row `TableActionMenu`: add `{ label: "Show in Experiment Lineage", onclick: () => goto(experiment_lineage_link(project_id, task_id, config.id)) }` after "Set as Task Default".
- **Compare `+page.svelte`:** pass `action_buttons={[{ label: "Experiment Lineage", href: experiment_lineage_link(project_id, task_id) }]}` to `AppPage`.

## Error Handling

- **Load failures** show the page's error state. The page doesn't render partial data.
- **Graph building never throws on bad data.** Bad ids, unknown parents and cycles are cleaned up as described above.
- **Display helpers never throw on missing lookups.** Before prompts, tools or model info have loaded, they fall back to ids, as the existing formatters do.
- **A `selected` id that isn't in the graph** is dropped without a message.
- **Store reloads** rebuild the graph. If the selected id disappears, `selected_id` becomes `null`.
- There's no logging, the same as the sibling pages.

## Testing Strategy

Vitest. Pure modules get unit tests beside them. Components get `@vitest-environment jsdom` tests with `@testing-library/svelte`, following `routes/(app)/sidebar_rail_item.test.ts`. Fixtures come from `lib/utils/lineage/__tests__/lineage_fixtures.ts`: `make_agent_config(overrides)`, `make_mcp_config(overrides)`, and `make_chain(n)`.

- **`lineage_graph`**:
  - A primary and an extra parent make two edges, and only the first is primary.
  - A missing parent makes one shared placeholder for two children, and both children are `parent_deleted`.
  - Self-references, repeats, `null` and empty ids are dropped.
  - In a two-node cycle, the newer node's edge is the one dropped.
  - Rows use the longest path, including merges.
  - Each status is assigned correctly.
  - Roots and the grid are ordered by `sort_key`.
  - A placeholder's `sort_key` is its oldest child's.
  - `ancestor_edge_ids` includes extra-parent paths.
  - Filter matching: an empty set matches everything, matches combine with OR, and copies match only with the "copy" key.
  - The summary's overlapping counts and model count, with MCP configs excluded.
- **`lineage_changes`**:
  - Each kind is detected alone.
  - Several kinds come back in order.
  - Tool order is ignored, and a skill-only change isn't reported as tools.
  - Thinking level `null` versus `"medium"`.
  - Input transform `null` versus a transform, and two equal transforms.
  - MCP with the same tool, MCP with a different tool, and mixed types.
- **`lineage_glyph`**:
  - Rectangles for 1 to 5 kinds, at 14 by 1 and 40 by 2, against the values from the design reference.
  - Outer edges stay flush.
  - The overlay isn't inset.
  - 0 or 6 kinds return `[]`.
  - Colors map to the palette indices.
- **`lineage_layout`**:
  - A chain is one column.
  - A parent is centered over its children.
  - Two trees sit side by side.
  - No two nodes in a row overlap, on a 200-node random fixture with a fixed seed.
  - The grid's columns and its top, with and without a tree.
  - A sample edge path string.
  - Rows are grouped and sorted.
  - An empty graph.
  - A 1,000-node fixture lays out without error.
- **`lineage_viewport`**:
  - Fit of a world larger and smaller than the view (capped at 1).
  - `min_zoom` below 0.5 for huge worlds.
  - `zoom_at` keeps the cursor's world point fixed.
  - Clamping of `k` and of the pan.
  - `zoom_step` stays centered.
  - `ensure_visible` doesn't move when the node is already visible.
  - `resize_keep_center`.
  - `wheel_delta_px` modes.
- **`lineage_navigation`**: each key, edges of rows, no selection, and an empty graph.
- **`lineage_display`**:
  - `status_text` for each status.
  - `change_rows` for each kind, including settings with two fields changed, unloaded tools, and MCP.
  - `children_text`.
- **`link_builder`**: both new links, with and without selection, and a `null` column.
- **`lineage_canvas.test.ts`**:
  - It renders one `[data-node-id]` per node.
  - A pointerdown and pointerup on a node dispatches `select`. A 10px drag doesn't.
  - Filters dim non-matching nodes, but not the selected node.
  - The zoom buttons change the label.
  - `Escape` dispatches `close`, and arrow keys dispatch `select`.
  - In jsdom, set `clientWidth` and `clientHeight` through `Object.defineProperty` on the element prototype in the test.
- **`lineage_filter_chips.test.ts`**: a chip toggles `aria-pressed` and the bound set, Clear appears and resets it, and counts render.
- **`lineage_panel.test.ts`**:
  - Diff rows render for a changed node.
  - Copy text and parent-deleted text render.
  - Parent links dispatch `select`.
  - "Compare to Parent" is hidden when the parent is deleted.
  - The "Compare" href is correct.
  - Notes appear only when present.
- **Compare charts:** no new tests. `chart_palette.test.ts` pins the values.
- **Visual check** (kiln-ui handback):
  - Run the dev server.
  - Seed a task with a lineage fixture (about 180 run configs, created through the API with `provenance.derived_from_ids`), using a script kept outside the repo.
  - Screenshot the page next to the run config detail page, at the same width.
  - Check that panning and zooming stay smooth with 1,000 nodes.

The project's standard checks (`uv run ./checks.sh --agent-mode`), the `kiln-ui` gate and the `kiln-conventions` gate must pass.

## Known Risks

- **Clip paths at scale.** 1,000 clipped groups is the most expensive part of the SVG. If the 1,000-node check stutters while panning, drop the clip in the canvas (glyphs become square-cornered at graph size) before trying anything else. Record the result in the phase plan.
- **Screen readers.** The graph SVG is `aria-hidden`. Screen-reader users get keyboard selection, the live-region announcement and the panel. The Optimize table stays the full accessible list of run configs.
