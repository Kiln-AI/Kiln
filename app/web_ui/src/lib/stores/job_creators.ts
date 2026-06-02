// Per-feature job creators. Each wraps `create_job` and attaches the
// appropriate `metadata.tag`, so producers can never forget the tag and the
// shape is enforced in one place. Add a sibling per new job kind as features
// come online (create_rag_job, create_finetune_job, …).

import { create_job } from "$lib/stores/jobs_api"
import { eval_tag, finetune_tag } from "$lib/stores/job_tags"
import type { components } from "$lib/api_schema"

export type EvalJobParams = {
  project_id: string
  task_id: string
  eval_id: string
  eval_config_id: string
  run_config_id: string
}

export type CreateJobResult =
  | components["schemas"]["CreateJobResponse"]
  | components["schemas"]["JobRecord"]

export async function create_eval_job(
  params: EvalJobParams,
): Promise<CreateJobResult> {
  return create_job(
    "eval",
    { ...params },
    {
      tag: eval_tag({
        task_id: params.task_id,
        // spec_id unavailable from this producer (Jobs-panel dialog);
        // back_url_for falls back to the task page.
        spec_id: null,
        eval_id: params.eval_id,
        eval_config_id: params.eval_config_id,
        run_config_id: params.run_config_id,
      }),
    },
    params.project_id,
    // Lifecycle identity: re-launching the same (eval, config, run_config)
    // triple supersedes the older row rather than stacking a new one. Must
    // match the backend producer in eval_jobs_api so both entry points share
    // the same dedup key.
    `${params.eval_id}:${params.eval_config_id}:${params.run_config_id}`,
  )
}

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
