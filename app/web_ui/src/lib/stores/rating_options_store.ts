import { writable } from "svelte/store"
import { client } from "$lib/api_client"
import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
import { get_task_composite_id, type TaskCompositeId } from "$lib/stores"
import type { RatingOptionResponse } from "$lib/types"

export const rating_options_by_task_composite_id = writable<
  Record<TaskCompositeId, RatingOptionResponse>
>({})

export const rating_options_errors_by_task_composite_id = writable<
  Record<TaskCompositeId, KilnError>
>({})

export const rating_options_loading_by_task_composite_id = writable<
  Record<TaskCompositeId, boolean>
>({})

// Promise map to dedup parallel requests for the same task
const loading_rating_options: Record<TaskCompositeId, Promise<void>> = {}

export async function load_rating_options(
  project_id: string,
  task_id: string,
  force_refresh: boolean = false,
): Promise<void> {
  const composite_key = get_task_composite_id(project_id, task_id)

  if (composite_key in loading_rating_options) {
    if (force_refresh) {
      try {
        await loading_rating_options[composite_key]
      } catch (error) {
        console.warn(
          "Previous rating options load failed; retrying due to force refresh: ",
          error,
        )
      }
    } else {
      return loading_rating_options[composite_key]
    }
  }

  const promise = (async () => {
    rating_options_loading_by_task_composite_id.update((loading) => ({
      ...loading,
      [composite_key]: true,
    }))

    try {
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/rating_options",
        {
          params: {
            path: {
              project_id,
              task_id,
            },
          },
        },
      )
      if (error) {
        throw error
      }

      rating_options_by_task_composite_id.update((options) => ({
        ...options,
        [composite_key]: data,
      }))

      rating_options_errors_by_task_composite_id.update((errors) => {
        const next = { ...errors }
        delete next[composite_key]
        return next
      })
    } catch (error) {
      console.error("Failed to load rating options: ", error)

      rating_options_errors_by_task_composite_id.update((errors) => ({
        ...errors,
        [composite_key]: createKilnError(error),
      }))

      rating_options_by_task_composite_id.update((options) => {
        const next = { ...options }
        delete next[composite_key]
        return next
      })

      throw error
    } finally {
      rating_options_loading_by_task_composite_id.update((loading) => ({
        ...loading,
        [composite_key]: false,
      }))

      delete loading_rating_options[composite_key]
    }
  })()

  loading_rating_options[composite_key] = promise
  return promise
}
