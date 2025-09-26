import type { TaskRunConfig, RunConfigProperties } from "$lib/types"
import { writable } from "svelte/store"
import { client } from "$lib/api_client"
import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
import { load_current_task } from "$lib/stores"

type TaskCompositeId = string & { __brand: "TaskCompositeId" }

// Helper function to create composite keys for a task
export function get_task_composite_id(
  project_id: string,
  task_id: string,
): TaskCompositeId {
  return `${project_id}:${task_id}` as TaskCompositeId
}

export const run_configs_by_task_composite_id = writable<
  Record<TaskCompositeId, TaskRunConfig[]>
>({})

export const run_configs_errors_by_task_composite_id = writable<
  Record<TaskCompositeId, KilnError>
>({})

export const run_configs_loading_by_task_composite_id = writable<
  Record<TaskCompositeId, boolean>
>({})

// Promise map to avoid parallel requests for run configs per task
const loading_task_run_configs: Record<TaskCompositeId, Promise<void>> = {}

export async function load_task_run_configs(
  project_id: string,
  task_id: string,
  force_refresh: boolean = false,
): Promise<void> {
  const composite_key = get_task_composite_id(project_id, task_id)

  if (composite_key in loading_task_run_configs) {
    if (force_refresh) {
      // If forcing refresh and there's an existing request, wait for it to complete first
      await loading_task_run_configs[composite_key]
    } else {
      // Return existing promise if already loading this specific task
      return loading_task_run_configs[composite_key]
    }
  }

  // Create and store the promise
  const promise = (async () => {
    // Set loading state to true
    run_configs_loading_by_task_composite_id.update((loading) => ({
      ...loading,
      [composite_key]: true,
    }))

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

      // Clear any previous error for this task
      run_configs_errors_by_task_composite_id.update((errors) => {
        const new_errors = { ...errors }
        delete new_errors[composite_key]
        return new_errors
      })
    } catch (error) {
      console.error("Failed to load task run configs: ", error)

      // Store the error for this task
      run_configs_errors_by_task_composite_id.update((errors) => ({
        ...errors,
        [composite_key]: createKilnError(error),
      }))

      // Remove any existing data for this task since we have an error
      run_configs_by_task_composite_id.update((configs) => {
        const new_configs = { ...configs }
        delete new_configs[composite_key]
        return new_configs
      })

      throw error
    } finally {
      // Set loading state to false
      run_configs_loading_by_task_composite_id.update((loading) => ({
        ...loading,
        [composite_key]: false,
      }))

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
  name?: string,
  description?: string,
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
        name,
        description,
        run_config_properties,
      },
    },
  )

  if (error) {
    throw error
  }

  // Reload the run configs to include the new one (force refresh to get fresh data)
  try {
    await load_task_run_configs(project_id, task_id, true)
  } catch (reloadErr) {
    console.warn("Reload of task run configs after save failed:", reloadErr)
  }

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

  // Reload the current task to get the updated default_run_config_id
  await load_current_task(project_id)
}
