// Generic selectors over the project-scoped jobs store. Designed to be reused
// by any "Run X" feature: take a JobRecord array (typically `$jobs`), narrow by
// tag, derive status slices, and aggregate progress.
//
// These are pure functions on arrays rather than Readable<...> store
// transformers, because real consumers' predicates depend on reactive
// component props — feeding them through a `$:` reactive in the component is
// the simplest correct shape with Svelte 4.

import type { JobRecord } from "$lib/stores/jobs_api"
import { get_tag, type JobTag } from "$lib/stores/job_tags"

export type AggregateProgress = {
  progress: number
  total: number
  errors: number
}

// Narrow to records carrying a tag of the given `kind`, optionally refined by
// the tag fields and/or the full record.
export function filter_by_tag<K extends JobTag["kind"]>(
  records: JobRecord[],
  kind: K,
  refine?: (tag: Extract<JobTag, { kind: K }>, job: JobRecord) => boolean,
): JobRecord[] {
  return records.filter((j) => {
    const t = get_tag(j)
    if (t?.kind !== kind) return false
    return refine ? refine(t as Extract<JobTag, { kind: K }>, j) : true
  })
}

// "Ongoing" = pending or running. Paused is deliberately excluded — for the
// Run-X-button UX, a paused job is "not running" and the button should return
// to its idle state. Terminal statuses (succeeded/failed/cancelled) are also
// excluded.
export function ongoing(records: JobRecord[]): JobRecord[] {
  return records.filter((j) => j.status === "pending" || j.status === "running")
}

export function is_ongoing(records: JobRecord[]): boolean {
  return records.some((j) => j.status === "pending" || j.status === "running")
}

export function aggregate(records: JobRecord[]): AggregateProgress {
  return records.reduce<AggregateProgress>(
    (acc, j) => ({
      progress: acc.progress + (j.progress?.success ?? 0),
      total: acc.total + (j.progress?.total ?? 0),
      errors: acc.errors + (j.progress?.error ?? 0),
    }),
    { progress: 0, total: 0, errors: 0 },
  )
}

// Effective "Run X" button state, with the store as the source of truth for
// "is it running". A stuck local `"running"` (e.g. an SSE that never received
// its terminal sentinel because the user paused the job via the widget) is
// overridden — if the store says nothing's ongoing, the button is idle and a
// fresh click triggers an idempotent re-run. Local terminal states still show
// when no jobs are ongoing, so the user sees the result of a just-finished run.
//
// `initiating` smooths the brief click-to-store-update window so the button
// doesn't flicker between "click" and "store has seen the new jobs".
export type LocalRunState =
  | "not_started"
  | "running"
  | "complete"
  | "complete_with_errors"

export function compute_run_state(
  store_running: boolean,
  initiating: boolean,
  local: LocalRunState,
): LocalRunState {
  if (store_running || initiating) return "running"
  if (local === "complete" || local === "complete_with_errors") return local
  return "not_started"
}
