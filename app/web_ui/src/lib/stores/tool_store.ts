import { writable } from "svelte/store"
import type { components } from "$lib/api_schema"

export type ExternalToolApiDescription =
  components["schemas"]["ExternalToolApiDescription"]

export const selected_tool_for_task =
  writable<ExternalToolApiDescription | null>(null)
