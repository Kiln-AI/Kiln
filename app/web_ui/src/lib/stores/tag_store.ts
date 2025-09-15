import { writable } from "svelte/store"
import { client } from "$lib/api_client"
import { get } from "svelte/store"

export type TagCounts = Record<string, number> | null

export const tag_store_by_task_id = writable<Record<string, TagCounts>>({})

const loading_tags = writable<Record<string, boolean>>({})

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
      return {}
    }
    tag_store_by_task_id.set({ ...get(tag_store_by_task_id), [task_id]: data })
    return data
  } catch (error: unknown) {
    console.error("Error loading tags", error)
    return {}
  } finally {
    loading_tags.set({ ...get(loading_tags), [task_id]: false })
  }
}

export function increment_tag(task_id: string, tag: string): TagCounts {
  const tag_counts = get(tag_store_by_task_id)[task_id]
  if (!tag_counts) {
    return {}
  }

  if (tag_counts) {
    tag_counts[tag] = (tag_counts[tag] || 0) + 1
  }
  tag_store_by_task_id.set({
    ...get(tag_store_by_task_id),
    [task_id]: tag_counts,
  })
  return tag_counts
}
