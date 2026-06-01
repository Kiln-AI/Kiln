// Shared identity convention for tracked jobs.
//
// A job's `metadata.tag` declares what feature-level thing the job is tracking,
// using a discriminated union by `kind`. Producers (the user-facing endpoint or
// frontend call that creates the job) attach the tag at create time; consumers
// (feature UIs like the Run Eval button) match on it without needing to know
// the worker's params schema.
//
// The job system itself stays oblivious — `metadata` is free-form pass-through
// stored verbatim. The contract lives here, in shared frontend types + tiny
// builders, plus a one-line dict literal at each backend create site.

import type { JobRecord } from "$lib/stores/jobs_api"

export type EvalTag = {
  kind: "eval"
  // task_id is required so back_url_for can build a useful URL even when the
  // producer doesn't know spec_id (e.g. the Jobs-panel run-eval dialog).
  task_id: string
  // spec_id is optional: route-bound producers (run_eval.svelte) pass it from
  // $page.params; the dialog and other contexts that don't have it leave it
  // null and back_url_for falls back to the task page.
  spec_id?: string | null
  eval_id: string
  eval_config_id: string
  // Singular: one job per run-config. "Run All Evals" spawns N jobs, one tag each.
  run_config_id: string
}

export type RagTag = {
  kind: "rag"
  rag_config_id: string
  // Populated only if RAG jobs end up being per-document; omit otherwise.
  doc_id?: string
}

export type FinetuneTag = {
  kind: "finetune"
  finetune_id: string
}

export type PromptOptimizationTag = {
  kind: "prompt_optimization"
  optimization_id: string
}

export type JobTag = EvalTag | RagTag | FinetuneTag | PromptOptimizationTag

// Read the tag off a record, safely narrowing the discriminated union for the
// caller. Returns null when the job has no tag (older job, untagged job type,
// or a malformed metadata shape).
export function get_tag(record: JobRecord): JobTag | null {
  const tag = (record.metadata as { tag?: unknown })?.tag
  if (
    tag &&
    typeof tag === "object" &&
    "kind" in tag &&
    typeof (tag as { kind: unknown }).kind === "string"
  ) {
    return tag as JobTag
  }
  return null
}

// Builders so producers don't open-code the tag shape. Add rag_tag /
// finetune_tag / prompt_optimization_tag siblings when those features start
// producing jobs.
export function eval_tag(parts: Omit<EvalTag, "kind">): EvalTag {
  return { kind: "eval", ...parts }
}

// Canonical "back to source" URL for a tracked job — the page in the UI that
// owns this job's context. Used by the jobs widget to make rows clickable.
// Returns null when no canonical URL is defined for the job's tag kind.
//
// Derivation lives here (frontend) rather than on the backend: producers don't
// need to know URL shapes, and renaming routes only requires updating this
// switch in one place.
export function back_url_for(record: JobRecord): string | null {
  const tag = get_tag(record)
  const project_id = record.project_id
  if (!tag || !project_id) return null
  switch (tag.kind) {
    case "eval":
      // The full "Run Eval" page is /specs/{project}/{task}/{spec}/{eval}/compare_run_configs.
      // Fall back to the task page when spec_id is unavailable (Jobs-panel dialog).
      if (tag.spec_id) {
        return `/specs/${project_id}/${tag.task_id}/${tag.spec_id}/${tag.eval_id}/compare_run_configs`
      }
      return `/specs/${project_id}/${tag.task_id}`
    case "rag":
    case "finetune":
    case "prompt_optimization":
      // Placeholders for when those features start producing jobs.
      return null
  }
}
