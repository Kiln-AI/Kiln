import type { TaskRunConfig } from "$lib/types"
import {
  CHANGE_KINDS,
  detect_changes,
  type ChangeKind,
} from "./lineage_changes"

export { CHANGE_KINDS }
export type { ChangeKind }

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

export interface LineageEdge {
  id: string
  parent_id: string
  child_id: string
  primary: boolean
}

export interface LineageGraph {
  nodes: Map<string, LineageNode>
  edges: LineageEdge[]
  tree_root_ids: string[] // roots that have children, by sort_key then id
  no_parent_ids: string[] // grid nodes, by sort_key then id
}

export type FilterKey = ChangeKind | "copy"
export const FILTER_KEYS: readonly FilterKey[] = [...CHANGE_KINDS, "copy"]

export interface LineageSummary {
  run_config_count: number
  model_count: number
  filter_counts: Record<FilterKey, number>
}

/**
 * Builds the lineage graph for a task's run configs. Never throws: duplicate
 * and empty ids, self-references and cycles are dropped, and each missing
 * parent id becomes one shared "deleted" placeholder node.
 */
export function build_lineage_graph(configs: TaskRunConfig[]): LineageGraph {
  const nodes = new Map<string, LineageNode>()
  for (const config of configs) {
    if (!config.id || nodes.has(config.id)) {
      continue
    }
    nodes.set(config.id, {
      id: config.id,
      config,
      parent_ids: [],
      child_ids: [],
      status: { type: "no_parent" },
      row: 0,
      sort_key: config.created_at ?? "",
    })
  }

  for (const node of [...nodes.values()]) {
    node.parent_ids = clean_parent_ids(node)
    for (const parent_id of node.parent_ids) {
      if (!nodes.has(parent_id)) {
        nodes.set(parent_id, make_placeholder(parent_id))
      }
    }
  }

  const ordered = [...nodes.values()].sort(compare_nodes)
  break_cycles(nodes, ordered)
  const edges = link_children(nodes, ordered)
  assign_rows(nodes, ordered)
  for (const node of nodes.values()) {
    node.status = node_status(node, nodes)
  }

  const by_order = [...nodes.values()].sort(compare_nodes)
  return {
    nodes,
    edges,
    tree_root_ids: by_order
      .filter((n) => n.parent_ids.length === 0 && n.child_ids.length > 0)
      .map((n) => n.id),
    no_parent_ids: by_order
      .filter((n) => n.status.type === "no_parent")
      .map((n) => n.id),
  }
}

/** Every edge on any path from a root down to `id`, extra parents included. */
export function ancestor_edge_ids(
  graph: LineageGraph,
  id: string,
): Set<string> {
  const edge_ids = new Set<string>()
  const visited = new Set<string>([id])
  const queue = [id]
  for (let i = 0; i < queue.length; i++) {
    const child_id = queue[i]
    const child = graph.nodes.get(child_id)
    if (!child) {
      continue
    }
    for (const parent_id of child.parent_ids) {
      edge_ids.add(edge_id(parent_id, child_id))
      if (!visited.has(parent_id)) {
        visited.add(parent_id)
        queue.push(parent_id)
      }
    }
  }
  return edge_ids
}

/** An empty filter set matches every node; otherwise any active key matches. */
export function node_matches_filters(
  status: LineageStatus,
  filters: ReadonlySet<FilterKey>,
): boolean {
  if (filters.size === 0) {
    return true
  }
  switch (status.type) {
    case "changed":
      return status.kinds.some((kind) => filters.has(kind))
    case "copy":
      return filters.has("copy")
    default:
      return false
  }
}

export function summarize_lineage(graph: LineageGraph): LineageSummary {
  const filter_counts = Object.fromEntries(
    FILTER_KEYS.map((key) => [key, 0]),
  ) as Record<FilterKey, number>
  const model_keys = new Set<string>()
  let run_config_count = 0

  for (const node of graph.nodes.values()) {
    if (node.status.type !== "deleted") {
      run_config_count++
    }
    if (node.status.type === "changed") {
      for (const kind of node.status.kinds) {
        filter_counts[kind]++
      }
    } else if (node.status.type === "copy") {
      filter_counts.copy++
    }
    const properties = node.config?.run_config_properties
    if (properties?.type === "kiln_agent") {
      model_keys.add(
        `${properties.model_provider_name}::${properties.model_name}`,
      )
    }
  }

  return { run_config_count, model_count: model_keys.size, filter_counts }
}

function edge_id(parent_id: string, child_id: string): string {
  return `${parent_id}->${child_id}`
}

function compare_nodes(a: LineageNode, b: LineageNode): number {
  if (a.sort_key !== b.sort_key) {
    return a.sort_key < b.sort_key ? -1 : 1
  }
  if (a.id !== b.id) {
    return a.id < b.id ? -1 : 1
  }
  return 0
}

function oldest_sort_key(
  ids: string[],
  nodes: Map<string, LineageNode>,
): string {
  let oldest: string | null = null
  for (const id of ids) {
    const key = nodes.get(id)?.sort_key ?? ""
    if (oldest === null || key < oldest) {
      oldest = key
    }
  }
  return oldest ?? ""
}

function make_placeholder(id: string): LineageNode {
  return {
    id,
    config: null,
    parent_ids: [],
    child_ids: [],
    status: { type: "deleted" },
    row: 0,
    sort_key: "",
  }
}

function clean_parent_ids(node: LineageNode): string[] {
  const parent_ids: string[] = []
  for (const parent_id of node.config?.provenance?.derived_from_ids ?? []) {
    if (parent_id && parent_id !== node.id && !parent_ids.includes(parent_id)) {
      parent_ids.push(parent_id)
    }
  }
  return parent_ids
}

// Iterative DFS over parent links, so a long chain can't overflow the stack.
// A parent still on the stack closes a cycle, and that link is removed.
function break_cycles(
  nodes: Map<string, LineageNode>,
  ordered: LineageNode[],
): void {
  const state = new Map<string, "on_stack" | "done">()
  for (const start of ordered) {
    if (state.has(start.id)) {
      continue
    }
    state.set(start.id, "on_stack")
    const stack: { node: LineageNode; next: number }[] = [
      { node: start, next: 0 },
    ]
    while (stack.length > 0) {
      const frame = stack[stack.length - 1]
      const parent_ids = frame.node.parent_ids
      if (frame.next >= parent_ids.length) {
        state.set(frame.node.id, "done")
        stack.pop()
        continue
      }
      const parent_id = parent_ids[frame.next]
      const parent_state = state.get(parent_id)
      if (parent_state === "on_stack") {
        parent_ids.splice(frame.next, 1)
        continue
      }
      frame.next++
      const parent = nodes.get(parent_id)
      if (parent_state === undefined && parent) {
        state.set(parent_id, "on_stack")
        stack.push({ node: parent, next: 0 })
      }
    }
  }
}

function link_children(
  nodes: Map<string, LineageNode>,
  ordered: LineageNode[],
): LineageEdge[] {
  const edges: LineageEdge[] = []
  for (const child of ordered) {
    child.parent_ids.forEach((parent_id, index) => {
      nodes.get(parent_id)?.child_ids.push(child.id)
      edges.push({
        id: edge_id(parent_id, child.id),
        parent_id,
        child_id: child.id,
        primary: index === 0,
      })
    })
  }
  for (const node of nodes.values()) {
    if (node.config === null) {
      node.sort_key = oldest_sort_key(node.child_ids, nodes)
    }
  }
  for (const node of nodes.values()) {
    node.child_ids = node.child_ids
      .map((id) => nodes.get(id))
      .filter((child): child is LineageNode => child !== undefined)
      .sort(compare_nodes)
      .map((child) => child.id)
  }
  return edges
}

// Kahn's algorithm over the cycle-free graph: a node's row is final once
// every one of its parents has been visited.
function assign_rows(
  nodes: Map<string, LineageNode>,
  ordered: LineageNode[],
): void {
  const waiting_on = new Map<string, number>()
  const ready: LineageNode[] = []
  for (const node of ordered) {
    node.row = 0
    waiting_on.set(node.id, node.parent_ids.length)
    if (node.parent_ids.length === 0) {
      ready.push(node)
    }
  }
  for (let i = 0; i < ready.length; i++) {
    const parent = ready[i]
    for (const child_id of parent.child_ids) {
      const child = nodes.get(child_id)
      if (!child) {
        continue
      }
      child.row = Math.max(child.row, parent.row + 1)
      const remaining = (waiting_on.get(child_id) ?? 1) - 1
      waiting_on.set(child_id, remaining)
      if (remaining === 0) {
        ready.push(child)
      }
    }
  }
}

function node_status(
  node: LineageNode,
  nodes: Map<string, LineageNode>,
): LineageStatus {
  if (node.config === null) {
    return { type: "deleted" }
  }
  if (node.parent_ids.length === 0) {
    return node.child_ids.length > 0
      ? { type: "starting_point" }
      : { type: "no_parent" }
  }
  const primary = nodes.get(node.parent_ids[0])
  if (!primary?.config) {
    return { type: "parent_deleted" }
  }
  const kinds = detect_changes(primary.config, node.config)
  return kinds.length > 0 ? { type: "changed", kinds } : { type: "copy" }
}
