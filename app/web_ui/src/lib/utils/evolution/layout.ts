import type { EvoForest, EvoNode } from "./graph_assembly"
import { primary_parent_id } from "./graph_assembly"

export const NODE_W = 200
export const NODE_H = 76
export const H_GAP = 90
export const V_GAP = 24

export interface EvolutionLayout {
  positions: Map<string, { x: number; y: number }>
  edgePaths: Map<string, { d: string; chipAt: { x: number; y: number } }>
  world: { width: number; height: number }
}

// Sort helper: created_at ascending, nulls (ghosts) first, id as tiebreaker.
function created_asc(a: EvoNode, b: EvoNode): number {
  const ca = a.created_at ?? ""
  const cb = b.created_at ?? ""
  if (ca !== cb) {
    return ca < cb ? -1 : 1
  }
  return a.id < b.id ? -1 : a.id > b.id ? 1 : 0
}

// Deterministic layered layout. x is set purely by depth; rows come from a
// post-order sweep of the placement tree (multi-parent nodes hang under their
// primary parent only), then a per-column collision pass pushes overlapping
// cards down. Components stack vertically with a 3*V_GAP separator.
export function layout_forest(forest: EvoForest): EvolutionLayout {
  const positions = new Map<string, { x: number; y: number }>()
  let previous_bottom = 0
  let first_component = true

  for (const component of forest.components) {
    const members = component.nodeIds
      .map((id) => forest.nodes.get(id))
      .filter((n): n is EvoNode => !!n)
    if (members.length === 0) {
      continue
    }
    const member_set = new Set(component.nodeIds)

    // Placement tree: each node hangs under its primary parent only.
    const placement_children = new Map<string, EvoNode[]>()
    for (const node of members) {
      const parent_id = primary_parent_id(node)
      if (parent_id && member_set.has(parent_id)) {
        const list = placement_children.get(parent_id) ?? []
        list.push(node)
        placement_children.set(parent_id, list)
      }
    }
    for (const list of placement_children.values()) {
      list.sort(created_asc)
    }

    const roots = component.rootIds
      .map((id) => forest.nodes.get(id))
      .filter((n): n is EvoNode => !!n)
      .sort(created_asc)

    // Post-order row assignment: a leaf takes the next free row; an internal
    // node sits at the mean of its placement children's rows.
    const rows = new Map<string, number>()
    let next_leaf_row = 0
    const assign_rows = (node: EvoNode) => {
      if (rows.has(node.id)) {
        return
      }
      const children = placement_children.get(node.id) ?? []
      if (children.length === 0) {
        rows.set(node.id, next_leaf_row++)
        return
      }
      for (const child of children) {
        assign_rows(child)
      }
      const child_rows = children.map((c) => rows.get(c.id) ?? 0)
      rows.set(
        node.id,
        child_rows.reduce((a, b) => a + b, 0) / child_rows.length,
      )
    }
    for (const root of roots) {
      assign_rows(root)
    }
    // Safety net for members unreachable through the placement tree
    for (const node of [...members].sort(created_asc)) {
      if (!rows.has(node.id)) {
        rows.set(node.id, next_leaf_row++)
      }
    }

    // Provisional coordinates within the component
    const component_positions = new Map<string, { x: number; y: number }>()
    for (const node of members) {
      component_positions.set(node.id, {
        x: node.depth * (NODE_W + H_GAP),
        y: (rows.get(node.id) ?? 0) * (NODE_H + V_GAP),
      })
    }

    // Collision pass per depth column: sweep in row order, pushing each card
    // down so it clears the previous card's bottom edge by V_GAP.
    const columns = new Map<number, EvoNode[]>()
    for (const node of members) {
      const column = columns.get(node.depth) ?? []
      column.push(node)
      columns.set(node.depth, column)
    }
    for (const column of columns.values()) {
      column.sort((a, b) => {
        const ya = component_positions.get(a.id)?.y ?? 0
        const yb = component_positions.get(b.id)?.y ?? 0
        return ya - yb || created_asc(a, b)
      })
      let prev_bottom = -Infinity
      for (const node of column) {
        const pos = component_positions.get(node.id)
        if (!pos) {
          continue
        }
        if (pos.y < prev_bottom + V_GAP) {
          pos.y = prev_bottom + V_GAP
        }
        prev_bottom = pos.y + NODE_H
      }
    }

    // Stack this component below the previous one
    const min_y = Math.min(...[...component_positions.values()].map((p) => p.y))
    const start_y = first_component ? 0 : previous_bottom + 3 * V_GAP
    const offset_y = start_y - min_y
    for (const [id, pos] of component_positions) {
      const final = { x: pos.x, y: pos.y + offset_y }
      positions.set(id, final)
      previous_bottom = Math.max(previous_bottom, final.y + NODE_H)
    }
    first_component = false
  }

  // Edge paths: cubic beziers between card mid-heights, both control points
  // at the horizontal midpoint. The chip anchor is the curve midpoint (which,
  // for this control-point choice, is the plain endpoint midpoint).
  const edgePaths = new Map<
    string,
    { d: string; chipAt: { x: number; y: number } }
  >()
  for (const edge of forest.edges) {
    const parent_pos = positions.get(edge.parentId)
    const child_pos = positions.get(edge.childId)
    if (!parent_pos || !child_pos) {
      continue
    }
    const x1 = parent_pos.x + NODE_W
    const y1 = parent_pos.y + NODE_H / 2
    const x2 = child_pos.x
    const y2 = child_pos.y + NODE_H / 2
    const mid_x = (x1 + x2) / 2
    edgePaths.set(edge.id, {
      d: `M ${x1} ${y1} C ${mid_x} ${y1}, ${mid_x} ${y2}, ${x2} ${y2}`,
      chipAt: { x: (x1 + x2) / 2, y: (y1 + y2) / 2 },
    })
  }

  let width = 0
  let height = 0
  for (const pos of positions.values()) {
    width = Math.max(width, pos.x + NODE_W)
    height = Math.max(height, pos.y + NODE_H)
  }

  return { positions, edgePaths, world: { width, height } }
}
