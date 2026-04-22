import { writable, get } from "svelte/store"
import { ui_state } from "$lib/stores"

export interface AgentPageInfo {
  name: string
  description: string
}

export const agentInfo = writable<AgentPageInfo | null>(null)

export interface AppState {
  path: string
  pageName: string | null
  pageDescription: string | null
  currentProject: string | null
  currentTask: string | null
}

const FIELD_LABELS: Record<keyof AppState, string> = {
  path: "Path",
  pageName: "Page Name",
  pageDescription: "Page Description",
  currentProject: "Current Project",
  currentTask: "Current Task",
}

const FIELD_KEYS: (keyof AppState)[] = [
  "path",
  "pageName",
  "pageDescription",
  "currentProject",
  "currentTask",
]

export function getCurrentAppState(): AppState {
  const info = get(agentInfo)
  const uiState = get(ui_state)
  return {
    path:
      typeof window !== "undefined" && window.location
        ? window.location.pathname
        : "",
    pageName: info?.name ?? null,
    pageDescription: info?.description ?? null,
    currentProject: uiState.current_project_id,
    currentTask: uiState.current_task_id,
  }
}

export function buildContextHeader(
  current: AppState,
  lastSent: AppState | null,
): string | null {
  if (lastSent === null) {
    const header = formatHeader(current)
    return header || null
  }

  const changed: Record<string, string | null> = {}
  let hasChanges = false
  for (const key of FIELD_KEYS) {
    if (current[key] !== lastSent[key]) {
      changed[key] = current[key]
      hasChanges = true
    }
  }
  if (!hasChanges) return null
  return formatChangedHeader(changed)
}

export function formatHeader(state: AppState): string {
  const lines: string[] = []
  for (const key of FIELD_KEYS) {
    const value = state[key]
    if (value !== null && value !== undefined && value !== "") {
      lines.push(`${FIELD_LABELS[key]}: ${value}`)
    }
  }
  if (lines.length === 0) return ""
  return `<new_app_ui_context>\n${lines.join("\n")}\n</new_app_ui_context>`
}

export function formatChangedHeader(
  changed: Record<string, string | null>,
): string {
  const lines: string[] = []
  for (const key of FIELD_KEYS) {
    if (key in changed) {
      const value = changed[key]
      if (value !== null && value !== undefined && value !== "") {
        lines.push(`${FIELD_LABELS[key]}: ${value}`)
      } else {
        lines.push(`${FIELD_LABELS[key]}: (none)`)
      }
    }
  }
  return `<new_app_ui_context>\n${lines.join("\n")}\n</new_app_ui_context>`
}
