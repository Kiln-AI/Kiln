import { writable } from "svelte/store"
import type { ExternalToolApiDescription } from "$lib/types"

export const selected_tool_for_task =
  writable<ExternalToolApiDescription | null>(null)
