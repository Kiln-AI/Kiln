import type { Writable } from "svelte/store"
import { localStorageStore } from "./local_storage_store"

export type RecentModel = {
  model_id: string
  model_provider: string
}

export const recent_model_store: Writable<RecentModel[]> = localStorageStore(
  "recent_model_store",
  [],
)

/**
 * Add a model to the recent models list, maintaining MRU order, uniqueness and max length
 * @param model_id - The model identifier
 * @param model_provider - The model provider
 */
export function addRecentModel(
  model_id: string | null,
  model_provider: string | null,
): void {
  if (!model_id || !model_provider) {
    return
  }

  recent_model_store.update((current_models) => {
    // Remove any existing entry with the same model_id and model_provider
    const filtered_models = current_models.filter(
      (model) =>
        !(
          model.model_id === model_id && model.model_provider === model_provider
        ),
    )

    // Add the new model to the front of the list
    const updated_models = [{ model_id, model_provider }, ...filtered_models]

    // Keep only the first 5 items (most recent)
    return updated_models.slice(0, 5)
  })
}
