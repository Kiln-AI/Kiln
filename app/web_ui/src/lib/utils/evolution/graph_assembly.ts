import type { TaskRunConfig } from "$lib/types"

// The comparable generation axes of a run config. Diffs between parent and
// child are expressed per-axis so edges can summarize "what changed".
export type AxisKey =
  | "prompt"
  | "model"
  | "provider"
  | "tools"
  | "temperature"
  | "top_p"
  | "thinking"
  | "output_mode"

export const AXIS_KEYS: AxisKey[] = [
  "prompt",
  "model",
  "provider",
  "tools",
  "temperature",
  "top_p",
  "thinking",
  "output_mode",
]

export const AXIS_LABELS: Record<AxisKey, string> = {
  prompt: "Prompt",
  model: "Model",
  provider: "Provider",
  tools: "Tools",
  temperature: "Temperature",
  top_p: "Top P",
  thinking: "Thinking",
  output_mode: "Output Mode",
}

export interface AxisChange {
  axis: AxisKey
  from: string
  to: string
}

export interface EvoNode {
  id: string
  config: TaskRunConfig | null
  ghost: boolean
  name: string
  created_at: string | null
  starred: boolean
  origin: "human" | "agent" | null
  noteSummary: string | null
  noteFull: string | null
  parents: { parentId: string; primary: boolean }[]
  children: string[]
  depth: number
  componentId: string
}

export interface EvoEdge {
  id: string
  parentId: string
  childId: string
  primary: boolean
  changedAxes: AxisChange[]
  noteSummary: string | null
  cycleBroken?: boolean
}

export interface EvoForest {
  nodes: Map<string, EvoNode>
  edges: EvoEdge[]
  components: { rootIds: string[]; nodeIds: string[] }[]
  unlinkedIds: string[]
}

function first_line(notes: string | null | undefined): string | null {
  if (!notes) {
    return null
  }
  const line = notes.split("\n")[0].trim()
  return line.length > 0 ? line : null
}

function parse_origin(
  origin: string | null | undefined,
): "human" | "agent" | null {
  return origin === "human" || origin === "agent" ? origin : null
}

// Raw (string-normalized) axis values for a config. MCP configs have no
// comparable generation axes, so they return null (as do ghosts).
export function get_axis_values(
  config: TaskRunConfig | null,
): Record<AxisKey, string> | null {
  const props = config?.run_config_properties
  // run_config_properties is a union type - only kiln_agent configs carry axes
  if (!props || !("model_name" in props)) {
    return null
  }
  return {
    prompt: props.prompt_id ?? "",
    model: props.model_name ?? "",
    provider: String(props.model_provider_name ?? ""),
    tools: [...(props.tools_config?.tools ?? [])].sort().join(", "),
    temperature: String(props.temperature ?? ""),
    top_p: String(props.top_p ?? ""),
    thinking: props.thinking_level ?? "none",
    output_mode: String(props.structured_output_mode ?? ""),
  }
}

export function diff_axes(
  parent: TaskRunConfig | null,
  child: TaskRunConfig | null,
): AxisChange[] {
  const parent_values = get_axis_values(parent)
  const child_values = get_axis_values(child)
  if (!parent_values || !child_values) {
    return []
  }
  const changes: AxisChange[] = []
  for (const axis of AXIS_KEYS) {
    if (parent_values[axis] !== child_values[axis]) {
      changes.push({
        axis,
        from: parent_values[axis],
        to: child_values[axis],
      })
    }
  }
  return changes
}

// The primary parent is derived_from_ids[0]; falls back to the first parent
// if the primary edge was dropped by cycle-breaking.
export function primary_parent_id(node: EvoNode): string | null {
  if (node.parents.length === 0) {
    return null
  }
  return (node.parents.find((p) => p.primary) ?? node.parents[0]).parentId
}

function make_ghost(id: string): EvoNode {
  return {
    id,
    config: null,
    ghost: true,
    name: "Deleted config",
    created_at: null,
    starred: false,
    origin: null,
    noteSummary: null,
    noteFull: null,
    parents: [],
    children: [],
    depth: 0,
    componentId: "",
  }
}

// Sort helper: created_at descending, nulls last, id as tiebreaker.
function created_desc(a: EvoNode, b: EvoNode): number {
  const ca = a.created_at ?? ""
  const cb = b.created_at ?? ""
  if (ca !== cb) {
    return ca > cb ? -1 : 1
  }
  return a.id < b.id ? -1 : a.id > b.id ? 1 : 0
}

export function build_forest(configs: TaskRunConfig[]): EvoForest {
  const nodes = new Map<string, EvoNode>()
  for (const config of configs) {
    if (!config.id) {
      continue
    }
    nodes.set(config.id, {
      id: config.id,
      config,
      ghost: false,
      name: config.name,
      created_at: config.created_at ?? null,
      starred: !!config.starred,
      origin: parse_origin(config.provenance?.origin),
      noteSummary: first_line(config.provenance?.notes),
      noteFull: config.provenance?.notes ?? null,
      parents: [],
      children: [],
      depth: 0,
      componentId: "",
    })
  }

  // Edges from provenance. Ordered: first non-null entry = primary parent.
  // Dangling parent ids materialize as ghost nodes.
  const edges: EvoEdge[] = []
  for (const node of [...nodes.values()]) {
    if (node.ghost || !node.config) {
      continue
    }
    const derived = node.config.provenance?.derived_from_ids ?? []
    let parent_index = 0
    for (const parent_id of derived) {
      if (!parent_id || parent_id === node.id) {
        continue
      }
      if (node.parents.some((p) => p.parentId === parent_id)) {
        continue
      }
      const primary = parent_index === 0
      parent_index++
      let parent = nodes.get(parent_id)
      if (!parent) {
        parent = make_ghost(parent_id)
        nodes.set(parent_id, parent)
      }
      node.parents.push({ parentId: parent_id, primary })
      parent.children.push(node.id)
      edges.push({
        id: `${parent_id}->${node.id}`,
        parentId: parent_id,
        childId: node.id,
        primary,
        changedAxes: parent.ghost ? [] : diff_axes(parent.config, node.config),
        noteSummary: first_line(node.config.provenance?.notes),
      })
    }
  }

  // Cycle-breaking: DFS over parent links with a visiting set. A parent
  // already on the current stack closes a cycle - drop that parent edge from
  // the graph (so depth/layout terminate) and mark the edge cycleBroken.
  const edge_by_id = new Map(edges.map((e) => [e.id, e]))
  const visiting = new Set<string>()
  const visited = new Set<string>()
  const break_cycles = (node_id: string) => {
    if (visited.has(node_id)) {
      return
    }
    visiting.add(node_id)
    const node = nodes.get(node_id)
    if (node) {
      for (const parent_ref of [...node.parents]) {
        if (visiting.has(parent_ref.parentId)) {
          node.parents = node.parents.filter(
            (p) => p.parentId !== parent_ref.parentId,
          )
          const parent = nodes.get(parent_ref.parentId)
          if (parent) {
            parent.children = parent.children.filter((c) => c !== node_id)
          }
          const edge = edge_by_id.get(`${parent_ref.parentId}->${node_id}`)
          if (edge) {
            edge.cycleBroken = true
          }
          continue
        }
        break_cycles(parent_ref.parentId)
      }
    }
    visiting.delete(node_id)
    visited.add(node_id)
  }
  for (const id of nodes.keys()) {
    break_cycles(id)
  }

  // Depth: memoized longest path from roots (safe post cycle-breaking).
  const depth_memo = new Map<string, number>()
  const depth_of = (node_id: string): number => {
    const memo = depth_memo.get(node_id)
    if (memo !== undefined) {
      return memo
    }
    // Seed before recursing as a defensive stop for any residual cycle
    depth_memo.set(node_id, 0)
    const node = nodes.get(node_id)
    let depth = 0
    for (const parent_ref of node?.parents ?? []) {
      depth = Math.max(depth, depth_of(parent_ref.parentId) + 1)
    }
    depth_memo.set(node_id, depth)
    return depth
  }
  for (const node of nodes.values()) {
    node.depth = depth_of(node.id)
  }

  // Unlinked: no parents and no children, newest first.
  const unlinkedIds = [...nodes.values()]
    .filter((n) => n.parents.length === 0 && n.children.length === 0)
    .sort(created_desc)
    .map((n) => n.id)
  const unlinked_set = new Set(unlinkedIds)

  // Connected components (undirected), sorted by earliest created_at.
  const component_visited = new Set<string>()
  const raw_components: {
    rootIds: string[]
    nodeIds: string[]
    earliest: string
  }[] = []
  for (const seed of nodes.values()) {
    if (unlinked_set.has(seed.id) || component_visited.has(seed.id)) {
      continue
    }
    const stack = [seed.id]
    component_visited.add(seed.id)
    const members: string[] = []
    while (stack.length > 0) {
      const id = stack.pop()
      if (!id) {
        continue
      }
      members.push(id)
      const node = nodes.get(id)
      if (!node) {
        continue
      }
      const neighbors = [
        ...node.parents.map((p) => p.parentId),
        ...node.children,
      ]
      for (const neighbor of neighbors) {
        if (!component_visited.has(neighbor)) {
          component_visited.add(neighbor)
          stack.push(neighbor)
        }
      }
    }
    members.sort()
    const rootIds = members.filter(
      (id) => (nodes.get(id)?.parents.length ?? 0) === 0,
    )
    const earliest =
      members
        .map((id) => nodes.get(id)?.created_at)
        .filter((c): c is string => !!c)
        .sort()[0] ?? "9999"
    raw_components.push({ rootIds, nodeIds: members, earliest })
  }
  raw_components.sort(
    (a, b) =>
      a.earliest.localeCompare(b.earliest) ||
      (a.nodeIds[0] ?? "").localeCompare(b.nodeIds[0] ?? ""),
  )
  const components = raw_components.map(({ rootIds, nodeIds }) => ({
    rootIds,
    nodeIds,
  }))
  components.forEach((component, index) => {
    for (const id of component.nodeIds) {
      const node = nodes.get(id)
      if (node) {
        node.componentId = `c${index}`
      }
    }
  })

  return { nodes, edges, components, unlinkedIds }
}
