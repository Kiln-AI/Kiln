import type { TaskRunConfig, RunConfigProperties } from "$lib/types"
import { writable } from "svelte/store"
import { client } from "$lib/api_client"
import { createKilnError } from "$lib/utils/error_handlers"

// Helper function to create composite keys for a task
export function get_task_composite_id(
  project_id: string,
  task_id: string,
): string {
  return `${project_id}:${task_id}`
}

export const run_configs_by_task_composite_id = writable<
  Record<string, TaskRunConfig[]>
>({})

// Promise map to avoid parallel requests for run configs per task
const loading_task_run_configs: Record<string, Promise<void>> = {}

export async function load_task_run_configs(
  project_id: string,
  task_id: string,
  force_refresh: boolean = false,
) {
  const composite_key = get_task_composite_id(project_id, task_id)

  // Return existing promise if already loading this specific task (unless forcing refresh)
  if (!force_refresh && composite_key in loading_task_run_configs) {
    return loading_task_run_configs[composite_key]
  }

  // Create and store the promise
  const promise = (async () => {
    try {
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

      // Update the store with the new data for this specific task using composite key
      run_configs_by_task_composite_id.update((configs) => ({
        ...configs,
        [composite_key]: data || [],
      }))
    } catch (error) {
      console.error(
        "Failed to load task run configs:",
        createKilnError(error).getMessage(),
      )
      // Set empty array for this task on error using composite key
      run_configs_by_task_composite_id.update((configs) => ({
        ...configs,
        [composite_key]: [],
      }))
      throw error
    } finally {
      // Clean up the promise from the map
      delete loading_task_run_configs[composite_key]
    }
  })()

  loading_task_run_configs[composite_key] = promise
  return promise
}

// Save a new task run configuration
export async function save_new_task_run_config(
  project_id: string,
  task_id: string,
  run_config_properties: RunConfigProperties,
): Promise<TaskRunConfig> {
  const { error, data } = await client.POST(
    "/api/projects/{project_id}/tasks/{task_id}/task_run_config",
    {
      params: {
        path: {
          project_id,
          task_id,
        },
      },
      body: {
        run_config_properties,
      },
    },
  )

  if (error) {
    throw error
  }

  // Reload the run configs to include the new one (force refresh to get fresh data)
  await load_task_run_configs(project_id, task_id, true)

  return data
}

// Update the default run config for a task
export async function update_task_default_run_config(
  project_id: string,
  task_id: string,
  default_run_config_id: string,
) {
  const { error } = await client.PATCH(
    "/api/projects/{project_id}/task/{task_id}",
    {
      params: {
        path: {
          project_id,
          task_id,
        },
      },
      body: {
        default_run_config_id,
      },
    },
  )

  if (error) {
    throw error
  }
}
