import { client } from "$lib/api_client"
import type { components } from "$lib/api_schema"
import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
import { writable, type Readable } from "svelte/store"

// Drives the Kiln Pro batch generation flow: start an in-process job on the
// local server, then poll its status until it finishes. The server fans the N
// LLM calls out in parallel — the browser just polls one endpoint.

export type InputsBatchStatus = components["schemas"]["InputsBatchStatusOutput"]
export type OutputsBatchStatus =
  components["schemas"]["OutputsBatchStatusOutput"]
type InputsBatchBody = components["schemas"]["GenerateInputsBatchInput"]
type OutputsBatchBody = components["schemas"]["GenerateOutputsBatchInput"]

const POLL_INTERVAL_MS = 1000

export type BatchRun<T> = {
  status: Readable<T | null>
  error: Readable<KilnError | null>
  cancel: () => void
}

function poll_job<T extends { status: string }>(
  fetch_status: () => Promise<{ data?: T; error?: unknown }>,
  status: ReturnType<typeof writable<T | null>>,
  error: ReturnType<typeof writable<KilnError | null>>,
  is_cancelled: () => boolean,
): () => void {
  let timer: ReturnType<typeof setInterval> | null = null
  const stop = () => {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  const tick = async () => {
    if (is_cancelled()) {
      stop()
      return
    }
    try {
      const { data, error: e } = await fetch_status()
      if (e) throw e
      if (!data) throw new Error("No status returned")
      status.set(data)
      if (data.status !== "running") {
        stop()
      }
    } catch (err) {
      error.set(createKilnError(err))
      stop()
    }
  }

  timer = setInterval(tick, POLL_INTERVAL_MS)
  // Kick off an immediate poll so the UI updates without waiting a full tick.
  tick()
  return stop
}

export function runInputsBatch(
  project_id: string,
  task_id: string,
  body: InputsBatchBody,
): BatchRun<InputsBatchStatus> {
  const status = writable<InputsBatchStatus | null>(null)
  const error = writable<KilnError | null>(null)
  let cancelled = false
  let stop_polling: (() => void) | null = null

  const cancel = () => {
    cancelled = true
    stop_polling?.()
  }

  ;(async () => {
    try {
      const { data, error: start_error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/generate_inputs_batch",
        { params: { path: { project_id, task_id } }, body },
      )
      if (start_error) throw start_error
      if (!data) throw new Error("No job id returned")
      if (cancelled) return
      const job_id = data.job_id
      stop_polling = poll_job(
        () =>
          client.GET(
            "/api/projects/{project_id}/tasks/{task_id}/generate_inputs_batch/{job_id}",
            { params: { path: { project_id, task_id, job_id } } },
          ),
        status,
        error,
        () => cancelled,
      )
    } catch (err) {
      error.set(createKilnError(err))
    }
  })()

  return { status, error, cancel }
}

export function runOutputsBatch(
  project_id: string,
  task_id: string,
  body: OutputsBatchBody,
): BatchRun<OutputsBatchStatus> {
  const status = writable<OutputsBatchStatus | null>(null)
  const error = writable<KilnError | null>(null)
  let cancelled = false
  let stop_polling: (() => void) | null = null

  const cancel = () => {
    cancelled = true
    stop_polling?.()
  }

  ;(async () => {
    try {
      const { data, error: start_error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/generate_outputs_batch",
        { params: { path: { project_id, task_id } }, body },
      )
      if (start_error) throw start_error
      if (!data) throw new Error("No job id returned")
      if (cancelled) return
      const job_id = data.job_id
      stop_polling = poll_job(
        () =>
          client.GET(
            "/api/projects/{project_id}/tasks/{task_id}/generate_outputs_batch/{job_id}",
            { params: { path: { project_id, task_id, job_id } } },
          ),
        status,
        error,
        () => cancelled,
      )
    } catch (err) {
      error.set(createKilnError(err))
    }
  })()

  return { status, error, cancel }
}
