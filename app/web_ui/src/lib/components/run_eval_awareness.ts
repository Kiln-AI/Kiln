import type { JobRecord } from "$lib/stores/jobs_api"
import { get_tag } from "$lib/stores/job_tags"

// Eval jobs that are currently "ongoing" for this (eval, eval_config, run_config*)
// triple — i.e. pending or running. Paused and terminal statuses are intentionally
// excluded so the button shows "Run Eval" again and a fresh idempotent click can
// pick up where the previous (paused) run left off.
//
// Matches by `metadata.tag` (the job-tags convention) rather than the worker's
// params shape, so consumers stay decoupled from worker internals and the same
// pattern can be reused for RAG / fine-tune / other "Run X" buttons.
export function match_ongoing_jobs(
  all_jobs: JobRecord[],
  eval_id: string,
  eval_config_id: string,
  run_config_ids: string[],
  run_all: boolean,
): JobRecord[] {
  return all_jobs.filter((j) => {
    if (j.status !== "pending" && j.status !== "running") return false
    const tag = get_tag(j)
    if (tag?.kind !== "eval") return false
    if (tag.eval_id !== eval_id) return false
    if (tag.eval_config_id !== eval_config_id) return false
    if (run_all) return true
    return run_config_ids.includes(tag.run_config_id)
  })
}

export type AggregateProgress = {
  progress: number
  total: number
  errors: number
}

export function aggregate_progress(jobs: JobRecord[]): AggregateProgress {
  return jobs.reduce<AggregateProgress>(
    (acc, j) => ({
      progress: acc.progress + (j.progress?.success ?? 0),
      total: acc.total + (j.progress?.total ?? 0),
      errors: acc.errors + (j.progress?.error ?? 0),
    }),
    { progress: 0, total: 0, errors: 0 },
  )
}
