import type { TaskRunConfig, RunConfigProperties } from "$lib/types"
import { client } from "$lib/api_client"
import { load_current_task } from "$lib/stores"
import { create_task_store, type TaskStoreConfig } from "./task_store_factory"

// Create singleton store instance that's shared across all pages
const run_configs_store_config: TaskStoreConfig<TaskRunConfig[]> = {
  api_endpoint: "/api/projects/{project_id}/tasks/{task_id}/task_run_configs",
  default_value: [],
  store_name: "task_run_configs",
}

const run_configs_store = create_task_store(run_configs_store_config)

export const load_task_run_configs = run_configs_store.load
export const get_task_run_configs = run_configs_store.get
export const get_task_run_configs_store = run_configs_store.get_task_store

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
