import type {
  ExternalToolApiDescription,
  ToolSetApiDescription,
  ToolSetType,
} from "$lib/types"
import { writable } from "svelte/store"
import { tool_link } from "$lib/utils/link_builder"
import { indexedDBStore } from "./index_db_store"
import { LLM_JUDGE_TOOL_ID } from "$lib/utils/built_in_tool_ids"

type ToolsStore = {
  selected_tool_ids_by_task_id: Record<string, string[]>
}

// Which sandboxed-code allowlist a tool picker is editing, if any. "none" is every
// picker that selects agent tools.
export type SandboxCodeContext = "none" | "code_tool" | "code_eval"

// Tools the server marks as needing a code judge's score schema. `llm_judge` errors
// without one, so it is offered in the code-eval picker alone — a narrowing within
// the sandbox_code set that the set type cannot express on its own.
// Module-private on purpose: pickers must go through
// is_tool_selectable_in_context() rather than matching ids themselves.
const CODE_EVAL_ONLY_TOOL_IDS = [LLM_JUDGE_TOOL_ID]

// Whether a picker in `context` may offer a tool, given the set that carries it.
//
// The coarse rule is the server's: a "sandbox_code" set holds tools that only
// user-authored sandboxed code can call, so no agent picker may offer them. Keying
// on the set type rather than on tool ids means renaming a KilnBuiltInToolId cannot
// silently leak these back into every picker.
export function is_tool_selectable_in_context(
  tool_id: string,
  tool_set_type: ToolSetType,
  context: SandboxCodeContext,
): boolean {
  if (tool_set_type !== "sandbox_code") {
    return true
  }
  if (context === "none") {
    return false
  }
  if (CODE_EVAL_ONLY_TOOL_IDS.includes(tool_id)) {
    return context === "code_eval"
  }
  return true
}

const tools_store_key = "tools_store"
export const { store: tools_store, initialized: tools_store_initialized } =
  indexedDBStore<ToolsStore>(tools_store_key, {
    selected_tool_ids_by_task_id: {},
  })

export const selected_tool_for_task =
  writable<ExternalToolApiDescription | null>(null)

export function get_tools_property_info(
  tool_ids: string[],
  project_id: string,
  available_tools: Record<string, ToolSetApiDescription[]>,
): { value: string | string[]; links: (string | null)[] | undefined } {
  const project_tools = available_tools[project_id]
  if (!project_tools) {
    return { value: "Loading...", links: undefined }
  }
  if (tool_ids.length > 0) {
    const tool_names = get_tool_names_from_ids(tool_ids, project_tools)
    return {
      value: tool_names,
      links: tool_ids.map((id) => tool_link(project_id, id)),
    }
  } else {
    return { value: "None", links: undefined }
  }
}

export function get_tool_server_name(
  available_tools: Record<string, ToolSetApiDescription[]>,
  project_id: string,
  tool_id: string | null | undefined,
): string | null {
  if (!tool_id) {
    return null
  }
  const project_tools = available_tools[project_id]
  if (!project_tools) {
    return null
  }
  for (const tool_set of project_tools) {
    if (tool_set.tools.some((tool) => tool.id === tool_id)) {
      return tool_set.set_name
    }
  }
  return null
}

export function get_tool_names_from_ids(
  tool_ids: string[],
  project_tools: ToolSetApiDescription[],
): string[] {
  if (!project_tools) {
    return tool_ids // Return IDs if we don't have the tools loaded for some reason
  }

  const all_tools = project_tools.flatMap((tool_set) => tool_set.tools)
  const tool_map = new Map(all_tools.map((tool) => [tool.id, tool.name]))

  return tool_ids.map((id) => tool_map.get(id) || id) // Fall back to ID if name not found
}

const SKILL_TOOL_ID_PREFIX = "kiln_tool::skill::"

export function is_skill_tool_id(id: string): boolean {
  return id.startsWith(SKILL_TOOL_ID_PREFIX)
}

export function split_tool_and_skill_ids(ids: string[]): {
  tool_ids: string[]
  skill_ids: string[]
} {
  return {
    tool_ids: ids.filter((id) => !is_skill_tool_id(id)),
    skill_ids: ids.filter((id) => is_skill_tool_id(id)),
  }
}
