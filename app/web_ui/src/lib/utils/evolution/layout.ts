import type { EvoForest, EvoNode } from "./graph_assembly"
import { primary_parent_id } from "./graph_assembly"

export const NODE_W = 280
export const NODE_H = 84
// Horizontal gap between sibling cards inside one generation row
export const H_GAP_SIB = 24
// Vertical gap between generations (the graph flows top to bottom)
export const V_GAP_GEN = 70
// Vertical separation between two stacked components
export const COMPONENT_GAP = 120

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

// Deterministic layered layout, top to bottom: y is set purely by depth, so a
// generation is one horizontal row. Columns come from a post-order sweep of the
// placement tree (multi-parent nodes hang under their primary parent only),
// then a per-row collision pass pushes overlapping cards right. Components
// stack vertically, one below the other.
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

    // Post-order column assignment: a leaf takes the next free column; an
    // internal node sits at the mean of its placement children's columns.
    const cols = new Map<string, number>()
    let next_leaf_col = 0
    const assign_cols = (node: EvoNode) => {
      if (cols.has(node.id)) {
        return
      }
      const children = placement_children.get(node.id) ?? []
      if (children.length === 0) {
        cols.set(node.id, next_leaf_col++)
        return
      }
      for (const child of children) {
        assign_cols(child)
      }
      const child_cols = children.map((c) => cols.get(c.id) ?? 0)
      cols.set(
        node.id,
        child_cols.reduce((a, b) => a + b, 0) / child_cols.length,
      )
    }
    for (const root of roots) {
      assign_cols(root)
    }
    // Safety net for members unreachable through the placement tree
    for (const node of [...members].sort(created_asc)) {
      if (!cols.has(node.id)) {
        cols.set(node.id, next_leaf_col++)
      }
    }

    // Provisional coordinates within the component
    const component_positions = new Map<string, { x: number; y: number }>()
    for (const node of members) {
      component_positions.set(node.id, {
        x: (cols.get(node.id) ?? 0) * (NODE_W + H_GAP_SIB),
        y: node.depth * (NODE_H + V_GAP_GEN),
      })
    }

    // Collision pass per generation row: sweep in column order, pushing each
    // card right so it clears the previous card's right edge by H_GAP_SIB.
    const generations = new Map<number, EvoNode[]>()
    for (const node of members) {
      const generation = generations.get(node.depth) ?? []
      generation.push(node)
      generations.set(node.depth, generation)
    }
    for (const generation of generations.values()) {
      generation.sort((a, b) => {
        const xa = component_positions.get(a.id)?.x ?? 0
        const xb = component_positions.get(b.id)?.x ?? 0
        return xa - xb || created_asc(a, b)
      })
      let prev_right = -Infinity
      for (const node of generation) {
        const pos = component_positions.get(node.id)
        if (!pos) {
          continue
        }
        if (pos.x < prev_right + H_GAP_SIB) {
          pos.x = prev_right + H_GAP_SIB
        }
        prev_right = pos.x + NODE_W
      }
    }

    // Stack this component below the previous one, left-aligned at x = 0
    const min_x = Math.min(...[...component_positions.values()].map((p) => p.x))
    const min_y = Math.min(...[...component_positions.values()].map((p) => p.y))
    const start_y = first_component ? 0 : previous_bottom + COMPONENT_GAP
    const offset_x = -min_x
    const offset_y = start_y - min_y
    for (const [id, pos] of component_positions) {
      const final = { x: pos.x + offset_x, y: pos.y + offset_y }
      positions.set(id, final)
      previous_bottom = Math.max(previous_bottom, final.y + NODE_H)
    }
    first_component = false
  }

  // Edge paths: vertical S-curves between card mid-widths, leaving the parent's
  // bottom edge and arriving at the child's top edge, both control points at
  // the vertical midpoint. The chip anchor is the curve midpoint (which, for
  // this control-point choice, is the plain endpoint midpoint).
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
    const x1 = parent_pos.x + NODE_W / 2
    const y1 = parent_pos.y + NODE_H
    const x2 = child_pos.x + NODE_W / 2
    const y2 = child_pos.y
    const mid_y = (y1 + y2) / 2
    edgePaths.set(edge.id, {
      d: `M ${x1} ${y1} C ${x1} ${mid_y}, ${x2} ${mid_y}, ${x2} ${y2}`,
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
