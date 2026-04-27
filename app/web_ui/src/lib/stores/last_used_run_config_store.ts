import type { Writable } from "svelte/store"
import { get } from "svelte/store"
import { localStorageStore } from "./local_storage_store"
import type { TaskCompositeId } from "$lib/stores"

export const last_used_run_config_store: Writable<
  Record<TaskCompositeId, string>
> = localStorageStore("last_used_run_config_store", {})

export function get_last_used_run_config(
  task_composite_id: TaskCompositeId,
): string | null {
  return get(last_used_run_config_store)[task_composite_id] ?? null
}

export function set_last_used_run_config(
  task_composite_id: TaskCompositeId,
  run_config_id: string | null,
): void {
  last_used_run_config_store.update((current) => {
    if (run_config_id === null) {
      if (!(task_composite_id in current)) {
        return current
      }
      const next = { ...current }
      delete next[task_composite_id]
      return next
    }
    if (current[task_composite_id] === run_config_id) {
      return current
    }
    return { ...current, [task_composite_id]: run_config_id }
  })
}
