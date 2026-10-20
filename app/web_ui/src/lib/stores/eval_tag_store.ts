import { writable, get } from "svelte/store"
import { client } from "$lib/api_client"
import type { Eval, Spec } from "$lib/types"
import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
import { resolved_status } from "$lib/utils/spec_status"
import type { TagCounts } from "./tag_store"

export const eval_tag_store_by_task_id = writable<Record<string, TagCounts>>({})

const loading_eval_tags = writable<Record<string, boolean>>({})

export const eval_tags_errors_by_task_id = writable<Record<string, KilnError>>(
  {},
)

/** How many of the task's evals use each tag. Archived evals are left out. */
export function count_eval_tags(specs: Spec[], evals: Eval[]): TagCounts {
  const evals_by_id = new Map(
    evals.flatMap((e) => (e.id ? [[e.id, e] as const] : [])),
  )
  const counts: TagCounts = {}
  for (const spec of specs) {
    if (resolved_status(spec, evals_by_id) === "archived") continue
    for (const tag of spec.tags ?? []) {
      counts[tag] = (counts[tag] || 0) + 1
    }
  }
  return counts
}

export async function load_eval_tags(
  project_id: string,
  task_id: string,
): Promise<TagCounts> {
  const existing = get(eval_tag_store_by_task_id)[task_id]
  if (existing) {
    return existing
  }
  if (get(loading_eval_tags)[task_id]) {
    return {}
  }
  loading_eval_tags.set({ ...get(loading_eval_tags), [task_id]: true })
  try {
    const params = { params: { path: { project_id, task_id } } }
    const [specs_response, evals_response] = await Promise.all([
      client.GET("/api/projects/{project_id}/tasks/{task_id}/specs", params),
      client.GET("/api/projects/{project_id}/tasks/{task_id}/evals", params),
    ])
    if (specs_response.error) {
      throw specs_response.error
    }
    if (evals_response.error) {
      throw evals_response.error
    }
    const counts = count_eval_tags(
      specs_response.data,
      evals_response.data.evals,
    )
    eval_tag_store_by_task_id.set({
      ...get(eval_tag_store_by_task_id),
      [task_id]: counts,
    })
    return counts
  } catch (error: unknown) {
    console.error("Error loading eval tags", error)
    eval_tags_errors_by_task_id.set({
      ...get(eval_tags_errors_by_task_id),
      [task_id]: createKilnError(error),
    })
    return {}
  } finally {
    loading_eval_tags.set({ ...get(loading_eval_tags), [task_id]: false })
  }
}

// Keeps a just-added tag in the suggestions without refetching every spec.
export function increment_eval_tag(task_id: string, tag: string): void {
  const counts = get(eval_tag_store_by_task_id)[task_id]
  if (!counts) {
    return
  }
  eval_tag_store_by_task_id.set({
    ...get(eval_tag_store_by_task_id),
    [task_id]: { ...counts, [tag]: (counts[tag] || 0) + 1 },
  })
}
