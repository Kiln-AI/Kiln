import { writable } from "svelte/store"
import type { KilnAgentRunConfigProperties } from "$lib/types"

// One-shot handoff from the job spinner page (`[job_id]/`) back to the base
// copilot page once the draft job succeeds. The spinner fetches the draft
// result, stashes it here, then navigates to the base page which consumes it
// and generates preview inputs. Memory only — on a hard refresh that drops
// this, the base page falls back to re-fetching the result by job_id.
export type PendingDataGuideDraft = {
  job_id: string
  project_id: string
  task_id: string
  draft_guide: string
  run_config_properties: KilnAgentRunConfigProperties
}

export const pending_data_guide_draft = writable<PendingDataGuideDraft | null>(
  null,
)
