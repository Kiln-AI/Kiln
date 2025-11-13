import type { Writable } from "svelte/store"
import { localStorageStore } from "./local_storage_store"

export type ProgressUIState = {
  title: string
  body: string
  cta: string | null
  link: string
  /**
   * Number between 0 and 1
   */
  progress: number | null
  step_count: number | null
  current_step: number | null
}

export const progress_ui_state: Writable<ProgressUIState | null> =
  localStorageStore("progress_ui_state", null)
