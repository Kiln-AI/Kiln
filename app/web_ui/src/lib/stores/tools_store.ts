import type { ToolSetApiDescription } from "$lib/types"
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

  return data.function_name as string
}
