import type { LineageGraph } from "./lineage_graph"
import type { LineageLayout } from "./lineage_layout"

export type NavKey = "ArrowUp" | "ArrowDown" | "ArrowLeft" | "ArrowRight"

/**
 * The node an arrow key moves the selection to. In the tree, Up goes to the
 * primary parent and Down to the oldest child, or from a node with no children
 * to the nearest node in the grid's first row. In the grid, Up and Down go to
 * the nearest node in the layout row above or below, so Up from the grid's
 * first row reaches the tree's bottom row. Left and Right go to the neighbors
 * in the same layout row. Returns `current` when there is nowhere to go.
 */
export function next_selection(
  graph: LineageGraph,
  layout: LineageLayout,
  current: string | null,
  key: NavKey,
): string | null {
  const node = current === null ? undefined : graph.nodes.get(current)
  if (!node) {
    return first_selection(graph, layout)
  }
  const row_index = layout.rows.findIndex((ids) => ids.includes(node.id))
  const in_grid = node.status.type === "no_parent"
  switch (key) {
    case "ArrowUp":
      return in_grid
        ? nearest_in_row(layout, row_index - 1, node.id)
        : node.parent_ids[0] ?? node.id
    case "ArrowDown":
      if (in_grid) {
        return nearest_in_row(layout, row_index + 1, node.id)
      }
      return (
        node.child_ids[0] ??
        nearest_in_row(layout, first_grid_row(graph, layout), node.id)
      )
    case "ArrowLeft":
    case "ArrowRight": {
      const row = layout.rows[row_index] ?? []
      const index = row.indexOf(node.id)
      const offset = key === "ArrowLeft" ? -1 : 1
      return row[index + offset] ?? node.id
    }
  }
}

// Prefers the oldest starting point over the leftmost root, which can be a
// deleted placeholder. Falls back to the first node in the layout.
function first_selection(
  graph: LineageGraph,
  layout: LineageLayout,
): string | null {
  const starting_point = graph.tree_root_ids.find(
    (id) => graph.nodes.get(id)?.status.type === "starting_point",
  )
  return starting_point ?? layout.rows[0]?.[0] ?? null
}

// -1 when the graph has no grid.
function first_grid_row(graph: LineageGraph, layout: LineageLayout): number {
  const first_grid_id = graph.no_parent_ids[0]
  return first_grid_id === undefined
    ? -1
    : layout.rows.findIndex((ids) => ids.includes(first_grid_id))
}

// The node in `layout.rows[row_index]` closest in x to `from`, the leftmost on
// a tie. Returns `from` when there is no such row.
function nearest_in_row(
  layout: LineageLayout,
  row_index: number,
  from: string,
): string {
  const row = layout.rows[row_index]
  const from_x = layout.positions.get(from)?.x
  if (!row || from_x === undefined) {
    return from
  }
  let nearest = from
  let nearest_distance = Infinity
  for (const id of row) {
    const x = layout.positions.get(id)?.x
    if (x !== undefined && Math.abs(x - from_x) < nearest_distance) {
      nearest = id
      nearest_distance = Math.abs(x - from_x)
    }
  }
  return nearest
}
