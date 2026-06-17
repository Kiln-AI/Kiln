import type { BackgroundJobStatus, JobProgress, JobRecord } from "./jobs_api"

export const ACTIVE_STATUSES: readonly BackgroundJobStatus[] = [
  "pending",
  "running",
  "paused",
]

export const TERMINAL_STATUSES: readonly BackgroundJobStatus[] = [
  "succeeded",
  "failed",
  "cancelled",
]

export function is_active(status: BackgroundJobStatus): boolean {
  return ACTIVE_STATUSES.includes(status)
}

export function is_terminal(status: BackgroundJobStatus): boolean {
  return TERMINAL_STATUSES.includes(status)
}

export function job_status_display(status: BackgroundJobStatus): string {
  switch (status) {
    case "pending":
      return "Pending"
    case "running":
      return "Running"
    case "paused":
      return "Paused"
    case "succeeded":
      return "Succeeded"
    case "failed":
      return "Failed"
    case "cancelled":
      return "Cancelled"
    default: {
      const exhaustive: never = status
      return exhaustive
    }
  }
}

export function job_status_badge_class(status: BackgroundJobStatus): string {
  switch (status) {
    case "running":
      return "badge-outline badge-success"
    case "succeeded":
      return "badge-outline badge-primary"
    case "failed":
      return "badge-outline badge-error"
    case "paused":
      return "badge-outline badge-warning"
    case "pending":
      return "badge-outline"
    case "cancelled":
      return "badge-outline"
    default: {
      const exhaustive: never = status
      return exhaustive
    }
  }
}

// A job that finished successfully but logged one or more non-fatal per-item
// errors. Like RAG's `completed_with_errors`, this is a frontend-derived display
// state only — the backend status stays `succeeded` and the error detail lives
// in the per-run error log. No worker/backend change is needed.
export function job_completed_with_errors(job: JobRecord): boolean {
  return job.status === "succeeded" && (job.progress?.error ?? 0) > 0
}

export function job_status_display_label(job: JobRecord): string {
  if (job_completed_with_errors(job)) {
    return "Completed with errors"
  }
  return job_status_display(job.status)
}

export function job_status_display_badge_class(job: JobRecord): string {
  if (job_completed_with_errors(job)) {
    return "badge-outline badge-error"
  }
  return job_status_badge_class(job.status)
}

export type JobAction = "pause" | "resume" | "cancel" | "delete"

// The set of lifecycle actions valid for a job given its status and whether
// its worker supports pause. Mirrors the state machine (functional_spec §3) and
// the delete policy (architecture open item #7: delete only on terminal state).
export function available_actions(job: JobRecord): JobAction[] {
  switch (job.status) {
    case "running": {
      const actions: JobAction[] = ["cancel"]
      if (job.supports_pause) {
        actions.unshift("pause")
      }
      return actions
    }
    case "paused":
      return ["resume", "cancel"]
    case "pending":
      return ["cancel"]
    case "succeeded":
    case "failed":
    case "cancelled":
      return ["delete"]
    default: {
      const exhaustive: never = job.status
      return exhaustive
    }
  }
}

export function progress_label(progress: JobProgress | undefined): string {
  const success = progress?.success ?? 0
  const total = progress?.total
  const base = total == null ? `${success}` : `${success} / ${total}`
  const error = progress?.error ?? 0
  return error > 0 ? `${base} (${error} errored)` : base
}

export function progress_percent(progress: JobProgress | undefined): number {
  const total = progress?.total
  if (!total || total <= 0) {
    return 0
  }
  const processed = (progress?.success ?? 0) + (progress?.error ?? 0)
  return Math.max(0, Math.min(100, Math.round((processed / total) * 100)))
}

// The jobs that "Clear completed" removes: every job in a terminal state.
export function completed_jobs(jobs: JobRecord[]): JobRecord[] {
  return jobs.filter((job) => is_terminal(job.status))
}

// What the sidebar Jobs indicator should render, derived purely from the live
// counts so it can be unit-tested without mounting the component:
//   - "spinner": at least one active job; show a subtle spinner + active count.
//   - "static": no active jobs but some still exist; show a muted total count.
//   - "hidden": no jobs at all; show no indicator.
export type JobsIndicator =
  | { kind: "spinner"; count: number }
  | { kind: "static"; count: number }
  | { kind: "hidden" }

export function jobs_indicator(
  active_count: number,
  total_count: number,
): JobsIndicator {
  if (active_count > 0) {
    return { kind: "spinner", count: active_count }
  }
  if (total_count > 0) {
    return { kind: "static", count: total_count }
  }
  return { kind: "hidden" }
}
