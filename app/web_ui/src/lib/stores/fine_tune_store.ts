import type { FinetuneProvider } from "$lib/types"
import { writable } from "svelte/store"
import { client } from "$lib/api_client"
import { createKilnError, KilnError } from "$lib/utils/error_handlers"
import { create_retrying_loader } from "./retrying_loader"

export const available_tuning_models = writable<FinetuneProvider[] | null>(null)
export const available_models_error = writable<KilnError | null>(null)
export const available_models_loading = writable<boolean>(false)

const tuning_models_loader = create_retrying_loader({
  fetch: async () => {
    const { data: available_models_response, error: get_error } =
      await client.GET("/api/finetune_providers", {})
    if (get_error) {
      throw get_error
    }
    if (!available_models_response) {
      throw new Error("Invalid response from server")
    }
    return available_models_response
  },
  on_start: () => {
    available_models_loading.set(true)
    available_models_error.set(null)
  },
  on_loaded: (data) => {
    available_tuning_models.set(data)
    available_models_loading.set(false)
  },
  on_error: (e) => {
    if (e instanceof Error && e.message.includes("Load failed")) {
      available_models_error.set(
        new KilnError("Could not load available models for fine-tuning.", null),
      )
    } else {
      available_models_error.set(createKilnError(e))
    }
    available_models_loading.set(false)
  },
})

export function get_available_models(): Promise<void> {
  return tuning_models_loader.load()
}

export function reset_available_tuning_models() {
  tuning_models_loader.reset()
  available_tuning_models.set(null)
  available_models_error.set(null)
  available_models_loading.set(false)
}
