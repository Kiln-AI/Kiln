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
