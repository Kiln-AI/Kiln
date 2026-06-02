// Per-feature job creators. Each wraps `create_job` and attaches the
// appropriate `metadata.tag`, so producers can never forget the tag and the
// shape is enforced in one place. Add a sibling per new job kind as features
// come online (create_rag_job, …).
//
// Note: eval jobs are spawned by the backend `run_comparison` endpoint, not
// from the frontend. No `create_eval_job` helper here — the UI calls
// `run_comparison` and gets back tracked job ids that the jobs store picks up.

import { create_job } from "$lib/stores/jobs_api"
import { finetune_tag } from "$lib/stores/job_tags"
import type { components } from "$lib/api_schema"

export type CreateJobResult =
  | components["schemas"]["CreateJobResponse"]
  | components["schemas"]["JobRecord"]

// Scaffolding for the finetune job type. The worker + endpoint are deferred to
// a follow-up PR; this declares the tag shape + creator so when that PR lands,
// it's purely additive (a new worker + endpoint registration).
export type FinetuneJobParams = {
  project_id: string
  task_id: string
  finetune_id: string
}

export async function create_finetune_job(
  params: FinetuneJobParams,
  // `secondary` may be one string or a list of lines — the jobs table renders
  // each list entry on its own row so multi-field details don't get truncated.
  display?: { primary?: string; secondary?: string | string[] },
): Promise<CreateJobResult> {
  return create_job(
    "finetune",
    { ...params },
    {
      tag: finetune_tag({
        task_id: params.task_id,
        finetune_id: params.finetune_id,
      }),
      ...(display ? { display } : {}),
    },
    params.project_id,
  )
}
