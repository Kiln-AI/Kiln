import type { components } from "$lib/api_schema"

export type SessionListItem = components["schemas"]["ChatSessionListItem"]

/**
 * Split session rows into the auto-active group ("Working now") and the rest,
 * preserving the server's ordering within each group. The Chat History dialog
 * renders the active group above a divider so a running conversation is the
 * first thing the user sees (ui_design §4).
 */
export function splitSessionRows(rows: SessionListItem[]): {
  active: SessionListItem[]
  recent: SessionListItem[]
} {
  const active: SessionListItem[] = []
  const recent: SessionListItem[] = []
  for (const row of rows) {
    if (row.auto_active) {
      active.push(row)
    } else {
      recent.push(row)
    }
  }
  return { active, recent }
}

/** A top-level session row plus any sub-agent sessions nested under it. */
export interface SessionRowNode {
  row: SessionListItem
  children: SessionListItem[]
}

/**
 * Nest sub-agent sessions under their parent conversation's row (matched by
 * ``parent_root_id`` → ``root_id``), preserving the server's ordering for both
 * the top-level rows and each parent's children. A sub-agent row whose parent
 * is not visible in the list renders as a normal top-level row.
 */
export function nestSessionRows(rows: SessionListItem[]): SessionRowNode[] {
  const parentRootIds = new Set<string>()
  for (const row of rows) {
    if (!row.is_subagent && row.root_id) {
      parentRootIds.add(row.root_id)
    }
  }

  const isNestedChild = (row: SessionListItem): boolean =>
    row.is_subagent === true &&
    !!row.parent_root_id &&
    parentRootIds.has(row.parent_root_id)

  const nodes: SessionRowNode[] = []
  const nodeByRootId = new Map<string, SessionRowNode>()
  for (const row of rows) {
    if (isNestedChild(row)) continue
    const node: SessionRowNode = { row, children: [] }
    nodes.push(node)
    if (!row.is_subagent && row.root_id && !nodeByRootId.has(row.root_id)) {
      nodeByRootId.set(row.root_id, node)
    }
  }
  for (const row of rows) {
    if (!isNestedChild(row)) continue
    nodeByRootId.get(row.parent_root_id ?? "")?.children.push(row)
  }
  return nodes
}

/**
 * ``splitSessionRows`` over nested nodes: children follow their parent into
 * whichever group the parent's ``auto_active`` puts it in.
 */
export function splitSessionNodes(nodes: SessionRowNode[]): {
  active: SessionRowNode[]
  recent: SessionRowNode[]
} {
  const active: SessionRowNode[] = []
  const recent: SessionRowNode[] = []
  for (const node of nodes) {
    if (node.row.auto_active) {
      active.push(node)
    } else {
      recent.push(node)
    }
  }
  return { active, recent }
}
