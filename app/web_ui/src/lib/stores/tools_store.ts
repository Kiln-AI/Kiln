import type {
  ExternalToolApiDescription,
  ToolSetApiDescription,
} from "$lib/types"
import { writable } from "svelte/store"
import { tool_link } from "$lib/utils/link_builder"
import { indexedDBStore } from "./index_db_store"
import { client } from "$lib/api_client"

type ToolsStore = {
  selected_tool_ids_by_task_id: Record<string, string[]>
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

function get_tool_names_from_ids(
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

// Fetches OpenAI-compatible tool definition's function name for a given tool ID
export async function tool_id_to_function_name(
  tool_id: string,
  project_id: string,
  task_id: string,
): Promise<string> {
  const { data, error } = await client.GET(
    "/api/projects/{project_id}/tasks/{task_id}/tools/{tool_id}/definition",
    {
      params: {
        path: {
          project_id,
          task_id,
          tool_id,
        },
      },
    },
  )

  if (error) {
    throw error
  }

  return data.function_name
}
