import { writable } from "svelte/store"
import type { KilnAgentRunConfigProperties } from "$lib/types"

// One-shot handoff: the saved-guide page (/data_guide) sets this when the user
// clicks "Test Data Guide" or submits the edit dialog, then navigates to
// /data_guide/refine. The refine page reads it on mount and clears it. Memory
// only — a hard refresh of /refine drops the seed and the page redirects back
// to /data_guide.
export type DataGuideRefineHandoff = {
  guide: string
  // The actually-saved-on-server guide text at handoff time. Used by the
  // refine page to detect whether the user has anything new to save (the
  // `guide` field above can be a pending edit that hasn't been persisted).
  saved_guide: string
  input_run_config: KilnAgentRunConfigProperties
  output_run_config: KilnAgentRunConfigProperties
}

export const pending_data_guide_refine_handoff =
  writable<DataGuideRefineHandoff | null>(null)
