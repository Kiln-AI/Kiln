import type { LineageGraph } from "./lineage_graph"
import type { LineageLayout } from "./lineage_layout"

export type NavKey = "ArrowUp" | "ArrowDown" | "ArrowLeft" | "ArrowRight"

/**
 * The node an arrow key moves the selection to. Up goes to the primary parent,
 * Down to the oldest child, and Left and Right to the neighbors in the same
 * layout row. Returns `current` when there is nowhere to go.
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
  switch (key) {
    case "ArrowUp":
      return node.parent_ids[0] ?? node.id
    case "ArrowDown":
      return node.child_ids[0] ?? node.id
    case "ArrowLeft":
    case "ArrowRight": {
      const row = layout.rows.find((ids) => ids.includes(node.id)) ?? []
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
