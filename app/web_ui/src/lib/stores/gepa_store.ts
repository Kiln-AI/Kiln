import { writable } from "svelte/store"
import { client } from "$lib/api_client"
import type { GepaJob } from "$lib/types"

export const gepa_jobs = writable<GepaJob[]>([])
export const gepa_jobs_loading = writable<boolean>(false)
export const gepa_jobs_error = writable<Error | null>(null)

export async function load_gepa_jobs(
  _project_id: string,
  _task_id: string,
): Promise<GepaJob[]> {
  gepa_jobs_loading.set(true)
  gepa_jobs_error.set(null)

  try {
    const { data, error } = await client.GET(
      "/api/projects/{project_id}/tasks/{task_id}/gepa_jobs",
      {
        params: {
          path: { project_id: _project_id, task_id: _task_id },
          query: { update_status: true },
        },
      },
    )
    if (error) throw error
    const sorted = (data || []).sort(
      (a, b) =>
        new Date(b.created_at || "").getTime() -
        new Date(a.created_at || "").getTime(),
    )
    gepa_jobs.set(sorted)
    return sorted
  } catch (e) {
    const err = e instanceof Error ? e : new Error(String(e))
    gepa_jobs_error.set(err)
    throw err
  } finally {
    gepa_jobs_loading.set(false)
  }
}

export async function load_gepa_job(
  _project_id: string,
  _task_id: string,
  gepa_job_id: string,
): Promise<GepaJob> {
  const { data, error } = await client.GET(
    "/api/projects/{project_id}/tasks/{task_id}/gepa_jobs/{gepa_job_id}",
    {
      params: {
        path: {
          project_id: _project_id,
          task_id: _task_id,
          gepa_job_id,
        },
      },
    },
  )
  if (error) throw error
  return data
}
