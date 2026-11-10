import type { LineageGraph, LineageNode } from "./lineage_graph"

export interface LayoutConfig {
  node: number
  col_gap: number
  row_height: number
  padding: number
  section_gap: number
  label_height: number
}

export const LAYOUT: Readonly<LayoutConfig> = {
  node: 14,
  col_gap: 4,
  row_height: 28,
  padding: 16,
  section_gap: 40,
  label_height: 16,
}

export interface LayoutEdge {
  id: string
  primary: boolean
  d: string // primary: an elbow; extra parent: an S-curve
}

export interface LineageLayout {
  positions: Map<string, { x: number; y: number }> // top-left of each node square, world px
  edges: LayoutEdge[]
  node_edges: Map<string, LayoutEdge[]> // each node's edges to its parents and children
  grid_label: { x: number; y: number } | null
  rows: string[][] // node ids grouped by y (top to bottom), each sorted by x
  width: number
  height: number
}

// The grid label's baseline sits this far above the first grid row.
const GRID_LABEL_BASELINE_OFFSET = 6

/**
 * Places the lineage graph in world pixels: a top-to-bottom tree whose columns
 * follow each node's primary parent, with nodes that have no recorded parent
 * in a grid below it.
 */
export function layout_lineage(
  graph: LineageGraph,
  config: Readonly<LayoutConfig> = LAYOUT,
): LineageLayout {
  const step = config.node + config.col_gap
  const positions = new Map<string, { x: number; y: number }>()

  const columns = tree_columns(graph)
  for (const [id, col] of columns) {
    const node = graph.nodes.get(id)
    if (node) {
      positions.set(id, {
        x: config.padding + col * step,
        y: config.padding + node.row * config.row_height,
      })
    }
  }

  const grid_label = place_grid(
    graph,
    positions,
    tree_extent(positions),
    config,
  )

  const edges: LayoutEdge[] = []
  const node_edges = new Map<string, LayoutEdge[]>()
  for (const edge of graph.edges) {
    const parent = positions.get(edge.parent_id)
    const child = positions.get(edge.child_id)
    if (!parent || !child) {
      continue
    }
    const layout_edge = layout_edge_between(
      edge.id,
      edge.primary,
      parent,
      child,
      config,
    )
    edges.push(layout_edge)
    for (const id of [edge.parent_id, edge.child_id]) {
      const touching = node_edges.get(id)
      if (touching) {
        touching.push(layout_edge)
      } else {
        node_edges.set(id, [layout_edge])
      }
    }
  }

  let width = 0
  let height = 0
  for (const { x, y } of positions.values()) {
    width = Math.max(width, x + config.node + config.padding)
    height = Math.max(height, y + config.node + config.padding)
  }

  return {
    positions,
    edges,
    node_edges,
    grid_label,
    rows: group_rows(positions),
    width,
    height,
  }
}

// From the parent's bottom center to the child's top center.
function layout_edge_between(
  id: string,
  primary: boolean,
  parent: { x: number; y: number },
  child: { x: number; y: number },
  config: Readonly<LayoutConfig>,
): LayoutEdge {
  const x1 = parent.x + config.node / 2
  const y1 = parent.y + config.node
  const x2 = child.x + config.node / 2
  const y2 = child.y
  if (primary) {
    const m = y2 - (config.row_height - config.node) / 2
    return { id, primary, d: `M${x1} ${y1}V${m}H${x2}V${y2}` }
  }
  // Handles of at most one row bend a long curve's vertical ends away from the
  // nodes stacked right below the parent and right above the child.
  const handle = Math.min((y2 - y1) / 2, config.row_height)
  return {
    id,
    primary,
    d: `M${x1} ${y1}C${x1} ${y1 + handle} ${x2} ${y2 - handle} ${x2} ${y2}`,
  }
}

// Post-order over the placement tree (each node under its primary parent). A
// leaf takes the next free column and a parent is centered over its first and
// last placement children. Roots share one counter, so trees sit side by side.
function tree_columns(graph: LineageGraph): Map<string, number> {
  const columns = new Map<string, number>()
  let next_col = 0
  for (const root_id of graph.tree_root_ids) {
    const root = graph.nodes.get(root_id)
    if (!root) {
      continue
    }
    const stack: { node: LineageNode; children: string[]; next: number }[] = [
      { node: root, children: placement_children(graph, root), next: 0 },
    ]
    while (stack.length > 0) {
      const frame = stack[stack.length - 1]
      if (frame.next < frame.children.length) {
        const child = graph.nodes.get(frame.children[frame.next++])
        if (child) {
          stack.push({
            node: child,
            children: placement_children(graph, child),
            next: 0,
          })
        }
        continue
      }
      stack.pop()
      const { children } = frame
      if (children.length === 0) {
        columns.set(frame.node.id, next_col++)
      } else {
        const first = columns.get(children[0]) ?? 0
        const last = columns.get(children[children.length - 1]) ?? 0
        columns.set(frame.node.id, (first + last) / 2)
      }
    }
  }
  return columns
}

function placement_children(graph: LineageGraph, node: LineageNode): string[] {
  return node.child_ids.filter(
    (id) => graph.nodes.get(id)?.parent_ids[0] === node.id,
  )
}

// The largest top-left corner among the tree's nodes.
interface TreeExtent {
  max_x: number
  max_y: number
}

function tree_extent(
  positions: Map<string, { x: number; y: number }>,
): TreeExtent | null {
  if (positions.size === 0) {
    return null
  }
  let max_x = -Infinity
  let max_y = -Infinity
  for (const { x, y } of positions.values()) {
    max_x = Math.max(max_x, x)
    max_y = Math.max(max_y, y)
  }
  return { max_x, max_y }
}

function place_grid(
  graph: LineageGraph,
  positions: Map<string, { x: number; y: number }>,
  tree: TreeExtent | null,
  config: Readonly<LayoutConfig>,
): { x: number; y: number } | null {
  const count = graph.no_parent_ids.length
  if (count === 0) {
    return null
  }
  const step = config.node + config.col_gap
  const tree_inner_width = tree ? tree.max_x + config.node - config.padding : 0
  const cols = Math.max(
    Math.floor((tree_inner_width + config.col_gap) / step),
    Math.ceil(Math.sqrt(count * 4)),
    1,
  )
  const grid_top =
    (tree ? tree.max_y + config.node + config.section_gap : config.padding) +
    config.label_height

  graph.no_parent_ids.forEach((id, index) => {
    positions.set(id, {
      x: config.padding + (index % cols) * step,
      y: grid_top + Math.floor(index / cols) * step,
    })
  })

  return { x: config.padding, y: grid_top - GRID_LABEL_BASELINE_OFFSET }
}

function group_rows(
  positions: Map<string, { x: number; y: number }>,
): string[][] {
  const by_y = new Map<number, string[]>()
  for (const [id, { y }] of positions) {
    const row = by_y.get(y)
    if (row) {
      row.push(id)
    } else {
      by_y.set(y, [id])
    }
  }
  return [...by_y.entries()]
    .sort(([a], [b]) => a - b)
    .map(([, ids]) =>
      ids.sort((a, b) => {
        const dx = (positions.get(a)?.x ?? 0) - (positions.get(b)?.x ?? 0)
        return dx !== 0 ? dx : a < b ? -1 : a > b ? 1 : 0
      }),
    )
}

/** Path data for a set of edges, joined into one string per way they're drawn. */
export interface EdgePaths {
  primary: string
  extra: string
}

/**
 * Joins the edges into one path per kind of edge, so the canvas draws a fixed
 * number of paths however many edges there are.
 */
export function join_edge_paths(edges: readonly LayoutEdge[]): EdgePaths {
  const primary: string[] = []
  const extra: string[] = []
  for (const edge of edges) {
    if (edge.primary) {
      primary.push(edge.d)
    } else {
      extra.push(edge.d)
    }
  }
  return { primary: primary.join(""), extra: extra.join("") }
}

/** Splits the edges into the ones at rest and the highlighted ones, each joined. */
export function edge_path_groups(
  edges: readonly LayoutEdge[],
  highlighted: ReadonlySet<string>,
): { resting: EdgePaths; highlighted: EdgePaths } {
  const resting: LayoutEdge[] = []
  const lit: LayoutEdge[] = []
  for (const edge of edges) {
    if (highlighted.has(edge.id)) {
      lit.push(edge)
    } else {
      resting.push(edge)
    }
  }
  return {
    resting: join_edge_paths(resting),
    highlighted: join_edge_paths(lit),
  }
}
