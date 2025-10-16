import { get, writable } from "svelte/store"

export type StepNumber = 1 | 2 | 3 | 4
export const step_numbers: StepNumber[] = [1, 2, 3, 4]
export const step_names: Record<StepNumber, string> = {
  1: "Select Documents",
  2: "Extraction",
  3: "Generate Q&A",
  4: "Save Data",
}

export const step_descriptions: Record<StepNumber, string> = {
  1: "Choose which documents to generate Q&A pairs from",
  2: "Extract text content from selected documents",
  3: "Generate question and answer pairs from extracted content",
  4: "Save generated Q&A pairs to dataset",
}

export const current_step = writable<StepNumber>(1)
export const max_available_step = writable<StepNumber>(1)

export function set_current_step(step: StepNumber) {
  current_step.set(step)

  max_available_step.set(Math.max(get(max_available_step), step) as StepNumber)
}

export function reset_ui_store() {
  current_step.set(1)
  max_available_step.set(1)
}
