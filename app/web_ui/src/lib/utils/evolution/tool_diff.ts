import type { ToolSetApiDescription } from "$lib/types"
import {
  get_tool_names_from_ids,
  split_tool_and_skill_ids,
} from "$lib/stores/tools_store"

// Set diff of a tools-axis value (the comma-joined, sorted id string emitted
// by get_axis_values), resolved to display names and split into tools vs
// skills so the UI can summarize each group separately.
export interface ToolAxisDiff {
  tools_added: string[]
  tools_removed: string[]
  skills_added: string[]
  skills_removed: string[]
}

export function split_axis_ids(value: string): string[] {
  return value.split(", ").filter((id) => id.length > 0)
}

export function diff_tool_axis(
  from: string,
  to: string,
  project_tools: ToolSetApiDescription[] | undefined,
): ToolAxisDiff {
  const from_ids = new Set(split_axis_ids(from))
  const to_ids = new Set(split_axis_ids(to))
  const added_ids = [...to_ids].filter((id) => !from_ids.has(id))
  const removed_ids = [...from_ids].filter((id) => !to_ids.has(id))
  const added = split_tool_and_skill_ids(added_ids)
  const removed = split_tool_and_skill_ids(removed_ids)
  const resolve = (ids: string[]) =>
    project_tools ? get_tool_names_from_ids(ids, project_tools) : ids
  return {
    tools_added: resolve(added.tool_ids),
    tools_removed: resolve(removed.tool_ids),
    skills_added: resolve(added.skill_ids),
    skills_removed: resolve(removed.skill_ids),
  }
}
