import type { EvoEdge, EvoForest, EvoNode } from "./graph_assembly"
import type { EvolutionLayout, LayoutSizes } from "./layout"
import { created_asc, layout_forest } from "./layout"

// The map view shows every run config of the task at once, as small blocks:
// the lineage tree on top (the same layered layout as the detail view, on
// blocks instead of cards), and the run configs with no recorded parent in a
// grid below it. It answers "how much was tried, and what kind of change"
// before a reader zooms into the cards.

export const MAP_SIZES: LayoutSizes = {
  nodeW: 36,
  nodeH: 36,
  hGap: 8,
  vGap: 28,
  componentGap: 56,
}

// Space between the lineage tree and the grid of unlinked run configs. The
// grid's label is drawn in this gap.
export const MAP_UNLINKED_GAP = 120

// With this many run configs or more, the page opens on the map view
export const MAP_DEFAULT_MIN_NODES = 40

export interface MapLayout extends EvolutionLayout {
  // World position of the label over the unlinked grid (null with no grid)
  unlinkedLabelAt: { x: number; y: number } | null
}

export function layout_map(forest: EvoForest): MapLayout {
  const tree = layout_forest(forest, MAP_SIZES)
  const unlinked = forest.unlinkedIds
    .map((id) => forest.nodes.get(id))
    .filter((n): n is EvoNode => !!n)
    .sort(created_asc)
  if (unlinked.length === 0) {
    return { ...tree, unlinkedLabelAt: null }
  }

  const { nodeW, nodeH, hGap } = MAP_SIZES
  const step = nodeW + hGap
  // The grid takes the tree's width, so the map stays one block. A narrow (or
  // empty) tree falls back to a grid about four times wider than tall.
  const cols = Math.max(
    Math.floor((tree.world.width + hGap) / step),
    Math.ceil(Math.sqrt(unlinked.length * 4)),
    1,
  )
  const top = tree.world.height > 0 ? tree.world.height + MAP_UNLINKED_GAP : 0
  const positions = new Map(tree.positions)
  unlinked.forEach((node, index) => {
    positions.set(node.id, {
      x: (index % cols) * step,
      y: top + Math.floor(index / cols) * (nodeH + hGap),
    })
  })
  const rows = Math.ceil(unlinked.length / cols)
  const grid_width = Math.min(cols, unlinked.length) * step - hGap
  return {
    positions,
    edgePaths: tree.edgePaths,
    world: {
      width: Math.max(tree.world.width, grid_width),
      height: top + rows * (nodeH + hGap) - hGap,
    },
    unlinkedLabelAt: { x: 0, y: top },
  }
}

// What a run config changed against its primary parent, by the generation
// axes (graph_assembly.diff_axes). Skills are tools, so they count as "tools".
export type MapKind =
  | "start"
  | "prompt_tools"
  | "model_settings"
  | "same"
  | "unlinked"
  | "deleted"

export const MAP_KINDS: MapKind[] = [
  "prompt_tools",
  "model_settings",
  "same",
  "start",
  "unlinked",
  "deleted",
]

export const MAP_KIND_LABELS: Record<MapKind, string> = {
  prompt_tools: "Changed the prompt, tools or skills",
  model_settings: "Changed the model or its settings",
  same: "Same settings: a copy or re-run",
  start: "Starting point",
  unlinked: "No parent recorded",
  deleted: "Deleted",
}

// Fill and stroke per kind. The two change kinds differ in lightness as well
// as hue, and the kinds without a change are grey.
export const MAP_KIND_STYLES: Record<
  MapKind,
  { fill: string; stroke: string; dashed?: boolean }
> = {
  prompt_tools: { fill: "#2a78d6", stroke: "#1d5aa3" },
  model_settings: { fill: "#f5a25d", stroke: "#d9772a" },
  same: { fill: "#d1d5db", stroke: "#9ca3af" },
  start: { fill: "#111827", stroke: "#111827" },
  unlinked: { fill: "#f3f4f6", stroke: "#9ca3af" },
  deleted: { fill: "#f9fafb", stroke: "#d1d5db", dashed: true },
}

const PROMPT_TOOL_AXES = new Set(["prompt", "tools"])

export function primary_edges_by_child(
  forest: EvoForest,
): Map<string, EvoEdge> {
  const by_child = new Map<string, EvoEdge>()
  for (const edge of forest.edges) {
    const current = by_child.get(edge.childId)
    if (!current || (edge.primary && !current.primary)) {
      by_child.set(edge.childId, edge)
    }
  }
  return by_child
}

export function map_kind(
  node: EvoNode,
  primary_edge: EvoEdge | undefined,
  unlinked: Set<string>,
): MapKind {
  if (node.ghost) {
    return "deleted"
  }
  if (unlinked.has(node.id)) {
    return "unlinked"
  }
  if (!primary_edge) {
    return "start"
  }
  const axes = primary_edge.changedAxes.map((change) => change.axis)
  if (axes.some((axis) => PROMPT_TOOL_AXES.has(axis))) {
    return "prompt_tools"
  }
  if (axes.length > 0) {
    return "model_settings"
  }
  return "same"
}

export function map_kinds(forest: EvoForest): Map<string, MapKind> {
  const edges = primary_edges_by_child(forest)
  const unlinked = new Set(forest.unlinkedIds)
  const kinds = new Map<string, MapKind>()
  for (const node of forest.nodes.values()) {
    kinds.set(node.id, map_kind(node, edges.get(node.id), unlinked))
  }
  return kinds
}

export interface MapSummary {
  // Run configs that exist (deleted parents are not counted)
  runConfigs: number
  models: number
  providers: number
  kindCounts: Map<MapKind, number>
}

export function map_summary(
  forest: EvoForest,
  kinds: Map<string, MapKind>,
): MapSummary {
  const models = new Set<string>()
  const providers = new Set<string>()
  let run_configs = 0
  for (const node of forest.nodes.values()) {
    if (node.ghost) {
      continue
    }
    run_configs++
    const props = node.config?.run_config_properties
    if (props && "model_name" in props) {
      models.add(props.model_name)
      providers.add(String(props.model_provider_name))
    }
  }
  const kind_counts = new Map<MapKind, number>()
  for (const kind of kinds.values()) {
    kind_counts.set(kind, (kind_counts.get(kind) ?? 0) + 1)
  }
  return {
    runConfigs: run_configs,
    models: models.size,
    providers: providers.size,
    kindCounts: kind_counts,
  }
}
