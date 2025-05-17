import type { FinetuneProvider } from "$lib/types"
import { writable, get } from "svelte/store"
import { client } from "$lib/api_client"
import { createKilnError, KilnError } from "$lib/utils/error_handlers"

export const available_tuning_models = writable<FinetuneProvider[] | null>(null)
export const available_models_error = writable<KilnError | null>(null)
export const available_models_loading = writable<boolean>(false)

export async function get_available_models() {
  try {
    if (get(available_tuning_models)) {
      // Already loaded
      return
    }
    available_models_loading.set(true)
    available_models_error.set(null)
    const { data: available_models_response, error: get_error } =
      await client.GET("/api/finetune_providers", {})
    if (get_error) {
      throw get_error
    }
    if (!available_models_response) {
      throw new Error("Invalid response from server")
    }
    available_tuning_models.set(available_models_response)
  } catch (e) {
    if (e instanceof Error && e.message.includes("Load failed")) {
      available_models_error.set(
        new KilnError("Could not load available models for fine-tuning.", null),
      )
    } else {
      available_models_error.set(createKilnError(e))
    }
  } finally {
    available_models_loading.set(false)
  }
}
