import { writable } from "svelte/store"
import { client } from "$lib/api_client"
import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
import {
  get_task_composite_id,
  load_available_prompts,
  type TaskCompositeId,
} from "$lib/stores"
import type { PromptResponse } from "$lib/types"

export const prompts_by_task_composite_id = writable<
  Record<TaskCompositeId, PromptResponse>
>({})

export const prompts_errors_by_task_composite_id = writable<
  Record<TaskCompositeId, KilnError>
>({})

export const prompts_loading_by_task_composite_id = writable<
  Record<TaskCompositeId, boolean>
>({})

// Promise map to avoid parallel requests for run configs per task
const loading_task_prompts: Record<TaskCompositeId, Promise<void>> = {}

// TODO: Remove load_task_prompts from store.ts
export async function load_task_prompts(
  project_id: string,
  task_id: string,
  force_refresh: boolean = false,
): Promise<void> {
  await load_available_prompts() // For the case task_id = current task id and other clients use load_available_prompts still

  const composite_key = get_task_composite_id(project_id, task_id)

  if (composite_key in loading_task_prompts) {
    if (force_refresh) {
      // If forcing refresh and there's an existing request, wait for it to complete first (still retry even on failure)
      try {
        await loading_task_prompts[composite_key]
      } catch (error) {
        console.warn(
          "Previous run config load failed; retrying due to force refresh: ",
          error,
        )
      }
    } else {
      // Return existing promise if already loading this specific task
      return loading_task_prompts[composite_key]
    }
  }

  // Create and store the promise
  const promise = (async () => {
    // Set loading state to true
    prompts_loading_by_task_composite_id.update((loading) => ({
      ...loading,
      [composite_key]: true,
    }))

    try {
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/task/{task_id}/prompts",
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
      prompts_by_task_composite_id.update((prompts) => ({
        ...prompts,
        [composite_key]: data || { generators: [], prompts: [] },
      }))

      // Clear any previous error for this task
      prompts_errors_by_task_composite_id.update((errors) => {
        const new_errors = { ...errors }
        delete new_errors[composite_key]
        return new_errors
      })
    } catch (error) {
      console.error("Failed to load task run configs: ", error)

      // Store the error for this task
      prompts_errors_by_task_composite_id.update((errors) => ({
        ...errors,
        [composite_key]: createKilnError(error),
      }))

      // Remove any existing data for this task since we have an error
      prompts_by_task_composite_id.update((configs) => {
        const new_configs = { ...configs }
        delete new_configs[composite_key]
        return new_configs
      })

      throw error
    } finally {
      // Set loading state to false
      prompts_loading_by_task_composite_id.update((loading) => ({
        ...loading,
        [composite_key]: false,
      }))

      // Clean up the promise from the map
      delete loading_task_prompts[composite_key]
    }
  })()

  loading_task_prompts[composite_key] = promise
  return promise
}
