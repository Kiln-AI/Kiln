// Per-feature job creators. Each wraps `create_job` and attaches the
// appropriate `metadata.tag`, so producers can never forget the tag and the
// shape is enforced in one place. Add a sibling per new job kind as features
// come online (create_rag_job, create_finetune_job, …).

import { create_job } from "$lib/stores/jobs_api"
import { eval_tag } from "$lib/stores/job_tags"
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
  )
}
