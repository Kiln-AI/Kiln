import { writable } from "svelte/store"
import { client } from "$lib/api_client"
import { get } from "svelte/store"
import { createKilnError, type KilnError } from "$lib/utils/error_handlers"

export type TagCounts = Record<string, number>

export const tag_store_by_task_id = writable<Record<string, TagCounts>>({})

const loading_tags = writable<Record<string, boolean>>({})

export const tags_errors_by_task_id = writable<Record<string, KilnError>>({})

export async function load_tags(
  project_id: string,
  task_id: string,
): Promise<TagCounts> {
  try {
    // Return early if already loading
    if (get(loading_tags)[task_id]) {
      return {}
    }
    loading_tags.set({ ...get(loading_tags), [task_id]: true })

    // Check if tags are already loaded
    const existing_tag_counts = get(tag_store_by_task_id)[task_id]
    if (existing_tag_counts) {
      return existing_tag_counts
    }
    const { data, error } = await client.GET(
      "/api/projects/{project_id}/tasks/{task_id}/tags",
      {
        params: {
          path: { project_id, task_id },
        },
      },
    )
    if (error) {
      console.error("Error loading tags", error)
      tags_errors_by_task_id.set({
        ...get(tags_errors_by_task_id),
        [task_id]: createKilnError(error),
      })
      return {}
    }
    tag_store_by_task_id.set({ ...get(tag_store_by_task_id), [task_id]: data })
    return data
  } catch (error: unknown) {
    console.error("Error loading tags", error)
    tags_errors_by_task_id.set({
      ...get(tags_errors_by_task_id),
      [task_id]: createKilnError(error),
    })
    return {}
  } finally {
    loading_tags.set({ ...get(loading_tags), [task_id]: false })
  }
}

export function increment_tag(task_id: string, tag: string): TagCounts {
  const tag_counts = get(tag_store_by_task_id)[task_id]
  if (!tag_counts) {
    console.error(
      "Attempted to increment a tag, but no tag counts found for task",
      task_id,
    )
    return {}
  }

  const updated_counts = {
    ...tag_counts,
    [tag]: (tag_counts[tag] || 0) + 1,
  }
  tag_store_by_task_id.set({
    ...get(tag_store_by_task_id),
    [task_id]: updated_counts,
  })
  return updated_counts
}
