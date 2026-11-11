---
status: complete
---

# Phase 1: Shared Chart Palette and Lineage Logic

## Overview

This phase builds everything the Experiment Lineage page needs that has no UI of its own. It names the chart palette the Compare charts already use and sets it on both charts, so the lineage page can take its change colors from the same constant. It adds two link helpers. It adds the pure TypeScript modules under `lib/utils/lineage/`: the graph model, change detection, the glyph encoding, the layout, the zoom and pan math, arrow-key navigation, and the display strings. Each module gets unit tests, built on a shared fixtures file. No page, route or component is added; that is phase 2.

All paths below are relative to `app/web_ui/src/`.

## Steps

1. **`lib/utils/chart_palette.ts`** (new). Export `CHART_PALETTE`, the nine echarts 6 default series colors, `as const`. Verified against `node_modules/echarts/lib/visual/tokens.js` (`tokens.color.theme`) in echarts 6.1.0.

2. **`lib/components/compare_chart.svelte`** and **`lib/components/compare_radar_chart.svelte`** (edit). Import `CHART_PALETTE` and add `color: [...CHART_PALETTE]` at the root of the options object passed to `chartInstance.setOption(...)`. Colors don't change. This is a shared-component change and is committed on its own, separate from the rest of the phase.

3. **`lib/utils/link_builder.ts`** (edit). Add:

   ```ts
   export function experiment_lineage_link(project_id: string, task_id: string, selected_id?: string | null): string
   // /optimize/{p}/{t}/experiment_lineage[?selected={id}]
   export function compare_run_configs_link(project_id: string, task_id: string, run_config_ids: (string | null)[]): string
   // /specs/{p}/{t}/compare?from=optimize&columns={n}&models={ids joined by ",", null as ""}
   ```

   Query strings are built with `URLSearchParams`.

4. **`lib/utils/lineage/lineage_graph.ts`** (new). Types `ChangeKind`, `CHANGE_KINDS`, `LineageStatus`, `LineageNode`, `LineageEdge`, `LineageGraph`, `FilterKey`, `FILTER_KEYS`, `LineageSummary`, exactly as in the architecture. Functions:

   ```ts
   export function build_lineage_graph(configs: TaskRunConfig[]): LineageGraph
   export function ancestor_edge_ids(graph: LineageGraph, id: string): Set<string>
   export function node_matches_filters(status: LineageStatus, filters: ReadonlySet<FilterKey>): boolean
   export function summarize_lineage(graph: LineageGraph): LineageSummary
   ```

   `build_lineage_graph` follows the architecture's seven steps: nodes (first config wins on a duplicate id), cleaned parent lists with one shared `deleted` placeholder per missing id, cycle breaking with an iterative white/grey/black DFS in `(sort_key, id)` order, edges and sorted child lists (a placeholder's `sort_key` is its oldest child's), rows by longest path (Kahn's algorithm over the cycle-free graph, so deep chains can't overflow the stack), statuses, then `tree_root_ids` and `no_parent_ids`. `ancestor_edge_ids` walks every parent breadth-first. `lineage_changes.ts` is imported for `detect_changes`; it imports only the `ChangeKind` type back, so there is no runtime import cycle.

5. **`lib/utils/lineage/lineage_changes.ts`** (new).

   ```ts
   export type SettingField = "temperature" | "top_p" | "thinking_level" | "structured_output_mode" | "input_transform"
   export const SETTING_FIELDS: readonly SettingField[]
   export function detect_changes(parent: TaskRunConfig, child: TaskRunConfig): ChangeKind[]
   export function changed_setting_fields(parent: KilnAgentRunConfigProperties, child: KilnAgentRunConfigProperties): SettingField[]
   ```

   Mixed types return `["model"]`. Two MCP configs compare `tool_reference.tool_id`. Two agent configs compare prompt id, tool and skill id sets (`split_tool_and_skill_ids`, then `sets_equal` from `lib/utils/collections.ts`), model name and provider, and settings. `changed_setting_fields` builds a `Record<SettingField, boolean>` so a new field is a compile error until it is handled, and compares input transforms with `inputTransformsEqual`.

6. **`lib/utils/lineage/lineage_glyph.ts`** (new). `CHANGE_KIND_COLORS` (palette indices 0, 7, 4, 3, 5), `CHANGE_KIND_LABELS`, `FILTER_LABELS`, `GlyphRect`, `GLYPH` sizes, and `glyph_rects(kinds, size, gap)`. A table of unit rectangles per kind count (1 to 5, the fifth an overlay) is scaled by `size`, with only internal edges inset by `gap / 2`. Kinds take rectangles in the order given. Fewer than one or more than five kinds return `[]`.

7. **`lib/utils/lineage/lineage_layout.ts`** (new). `LayoutConfig`, `LAYOUT`, `LineageLayout`, and `layout_lineage(graph, config = LAYOUT)`. Placement tree under `parent_ids[0]`, post-order columns (iterative), tree positions, the grid below with the architecture's column and top formulas and its label, elbow edge paths, overall size, and rows grouped by `y` and sorted by `x`.

8. **`lib/utils/lineage/lineage_viewport.ts`** (new). `Viewport`, `Size`, the zoom constants, and `fit_zoom`, `min_zoom`, `fit`, `zoom_at`, `zoom_step`, `pan_by`, `center_on`, `ensure_visible`, `resize_keep_center`, `wheel_delta_px`, `wheel_zoom_factor`. Also export `clamp_viewport(vp, world, view)`, the clamp every other function applies, because the canvas needs it to re-clamp after a layout change. The pan clamp keeps `min(PAN_KEEP, world on screen, view)` px of the world in view on each axis, so a world smaller than `PAN_KEEP` still has a valid range. `fit_zoom` treats a view smaller than its margins as 1px wide, so it never returns zero or a negative zoom.

9. **`lib/utils/lineage/lineage_navigation.ts`** (new). `NavKey` and `next_selection(graph, layout, current, key)`. Up picks the primary parent, Down the oldest child, Left and Right the neighbor in the node's layout row. With no target it returns `current`. With no current selection (or one not in the graph), it picks the oldest starting point, falling back to `layout.rows[0][0]` and then `null`.

10. **`lib/utils/lineage/lineage_display.ts`** (new). `DisplayContext`, `ChangeRow`, `node_title`, `status_text`, `node_model_text`, `children_text`, and `change_rows(parent, child, kinds, ctx)`, with the strings and fallbacks listed in the architecture.

11. **`lib/utils/lineage/__tests__/lineage_fixtures.ts`** (new, test support only). `make_agent_config(overrides)`, `make_mcp_config(overrides)`, `make_chain(n)`, a `created_at_for(index)` helper for ordered timestamps, and `make_random_lineage(n, seed)` for the 200-node and 1,000-node layout tests (a seeded generator with roots, extra parents, missing parents and grid nodes).

## Tests

- `chart_palette.test.ts`: pins the nine palette values in order.
- `link_builder.test.ts`:
  - `experiment_lineage_link` without a selection, with a selection, with `null`, and with an id that needs encoding.
  - `compare_run_configs_link` with two ids, with a `null` second column (trailing empty entry), and the `models` value read back by `URLSearchParams` and split on ",".
- `lineage_graph.test.ts`:
  - A primary and an extra parent make two edges, and only the first is primary.
  - A missing parent makes one shared placeholder for two children; both children are `parent_deleted`, and the placeholder is a tree root.
  - Self-references, repeats, `null` and empty ids are dropped; a config without an id is skipped; the first config wins on a duplicate id.
  - In a two-node cycle, the newer node's edge is the one dropped. A three-node cycle still renders.
  - Rows use the longest path, including merges.
  - Each status is assigned (starting point, changed with kinds, copy, parent deleted, no parent, deleted).
  - Roots and the grid are ordered by `sort_key`, then id; child lists are sorted the same way.
  - A placeholder's `sort_key` is its oldest child's.
  - `ancestor_edge_ids` includes extra-parent paths and excludes unrelated edges; an unknown id gives an empty set.
  - Filter matching: an empty set matches everything, matches combine with OR, copies match only with "copy", other statuses never match.
  - Summary: overlapping counts, the run config count excludes placeholders, and the model count dedupes by provider and name and excludes MCP configs.
  - A 1,000-node chain builds without a stack overflow.
- `lineage_changes.test.ts`:
  - Each kind is detected alone (prompt, tools, skills, model name, model provider, each setting field).
  - Several kinds come back in `CHANGE_KINDS` order.
  - Tool order is ignored, and a skill-only change isn't reported as tools.
  - Missing `tools_config` equals an empty tool list.
  - Thinking level `null` versus `"medium"`, and `undefined` versus `null`.
  - Input transform `null` versus a transform, and two equal transforms.
  - MCP with the same tool, MCP with a different tool, and mixed types in both directions.
  - `changed_setting_fields` returns several fields in `SETTING_FIELDS` order.
- `lineage_glyph.test.ts`:
  - Rectangles for 1 to 5 kinds at 14/1 and 40/2, against the values the design reference's `nodeRects()` produces.
  - Outer edges stay flush; the overlay isn't inset and is flagged.
  - 0 or 6 kinds return `[]`.
  - Colors map to the palette indices; labels and filter labels.
- `lineage_layout.test.ts`:
  - A chain is one column.
  - A parent is centered over its first and last children.
  - Two trees sit side by side, oldest root first.
  - No two nodes in a row overlap, on a 200-node seeded random fixture.
  - Grid columns and top, with and without a tree, and the grid label position; no label without grid nodes.
  - A sample edge path string, for a primary and an extra edge.
  - Rows are grouped by `y` and sorted by `x`.
  - Width and height; an empty graph gives zero size and no rows.
  - A 1,000-node fixture lays out without error, every node positioned.
- `lineage_viewport.test.ts`:
  - `fit_zoom` for a world larger and smaller than the view (capped at 1), an empty world, and a view smaller than its margins.
  - `min_zoom` is 0.5 normally and below 0.5 for huge worlds.
  - `fit` centers the world.
  - `zoom_at` keeps the cursor's world point fixed, and clamps `k` at both ends.
  - Pan clamping on both axes, including a world smaller than `PAN_KEEP`.
  - `zoom_step` in and out stays centered on the view.
  - `center_on` puts the point at the view center.
  - `ensure_visible` doesn't move a visible node, and scrolls a node off each edge back in.
  - `resize_keep_center` keeps the center and doesn't clamp.
  - `wheel_delta_px` for each mode, and `wheel_zoom_factor` direction and identity.
- `lineage_navigation.test.ts`: each key, the ends of a row, a node without a parent or child, no selection (oldest starting point, and the grid fallback), and an empty graph.
- `lineage_display.test.ts`:
  - `node_title` for a config and a placeholder.
  - `status_text` for each status.
  - `node_model_text` for an agent, MCP and a placeholder.
  - `change_rows` for each kind, including settings with two fields changed, thinking level and input transform values, unloaded tools (raw ids), an empty tool list ("None"), unloaded prompts, and an MCP side ("—").
  - `children_text` for 0, 1 and many.
