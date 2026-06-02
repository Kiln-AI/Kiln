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
      return "badge-info"
    case "succeeded":
      return "badge-success"
    case "failed":
      return "badge-error"
    case "paused":
      return "badge-warning"
    case "pending":
      return "badge-ghost"
    case "cancelled":
      return "badge-ghost"
    default: {
      const exhaustive: never = status
      return exhaustive
    }
  }
}

export type JobAction = "pause" | "resume" | "cancel" | "delete"

// The set of lifecycle actions valid for a job given its status and whether
// its worker supports pause/cancel. Mirrors the state machine (functional_spec
// §3) and the delete policy (architecture open item #7: delete only on
// terminal state). `supports_cancel === false` hides cancel entirely (e.g.
// finetune watcher: nothing local to interrupt).
export function available_actions(job: JobRecord): JobAction[] {
  const cancel: JobAction[] = job.supports_cancel ? ["cancel"] : []
  switch (job.status) {
    case "running": {
      const actions: JobAction[] = [...cancel]
      if (job.supports_pause) {
        actions.unshift("pause")
      }
      return actions
    }
    case "paused":
      return ["resume", ...cancel]
    case "pending":
      return [...cancel]
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
//   - "spinner": at least one job is *running*; show a spinner + open-job count.
//     Paused jobs don't trigger the spinner — they're open but not doing work.
//   - "static": no running jobs but some still exist; show a static count.
//   - "hidden": no jobs at all; show no indicator.
export type JobsIndicator =
  | { kind: "spinner"; count: number }
  | { kind: "static"; count: number }
  | { kind: "hidden" }

export function jobs_indicator(
  running_count: number,
  active_count: number,
  total_count: number,
): JobsIndicator {
  if (running_count > 0) {
    return { kind: "spinner", count: active_count }
  }
  if (total_count > 0) {
    return { kind: "static", count: total_count }
  }
  return { kind: "hidden" }
}
