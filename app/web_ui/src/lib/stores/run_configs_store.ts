import type { TaskRunConfig } from "$lib/types"
import { get, writable } from "svelte/store"
import { client } from "$lib/api_client"
import { createKilnError } from "$lib/utils/error_handlers"

export const task_run_configs_by_task_id = writable<
  Record<string, TaskRunConfig[]>
>({})

// Lock to avoid parallel requests for task run configs per task
const loading_task_run_configs: Record<string, boolean> = {}

export async function load_task_run_configs(
  project_id: string,
  task_id: string,
) {
  try {
    // Return early if already loading this specific task
    if (loading_task_run_configs[task_id]) {
      return
    }
    loading_task_run_configs[task_id] = true
    const { data, error } = await client.GET(
      "/api/projects/{project_id}/tasks/{task_id}/task_run_configs",
      {
        params: {
          path: {
            project_id: project_id,
            task_id: task_id,
          },
        },
      },
    )
    if (error) {
      throw error
    }

    // Update the store with the new data for this specific task
    task_run_configs_by_task_id.update((configs) => ({
      ...configs,
      [task_id]: data || [],
    }))
  } catch (error) {
    console.error(
      "Failed to load task run configs:",
      createKilnError(error).getMessage(),
    )
    // Set empty array for this task on error
    task_run_configs_by_task_id.update((configs) => ({
      ...configs,
      [task_id]: [],
    }))
  } finally {
    loading_task_run_configs[task_id] = false
  }
}

export function run_config_from_id(
  config_id: string,
  task_id: string,
): TaskRunConfig | undefined {
  const task_run_configs = get(task_run_configs_by_task_id)[task_id]
  return task_run_configs?.find((config) => config.id === config_id)
}
