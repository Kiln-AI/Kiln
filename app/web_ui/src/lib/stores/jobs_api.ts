import { client } from "$lib/api_client"
import type { components } from "$lib/api_schema"

export type JobRecord = components["schemas"]["JobRecord"]
export type JobProgress = components["schemas"]["JobProgress"]
export type JobError = components["schemas"]["JobError"]
export type BackgroundJobStatus = components["schemas"]["BackgroundJobStatus"]

export type JobErrorEntry = {
  error_message?: string
} & Record<string, unknown>

export type ListJobsQuery = {
  status?: BackgroundJobStatus
  type?: string
  project_id?: string
  since?: string
  limit?: number
}

export async function list_jobs(
  query: ListJobsQuery = {},
): Promise<JobRecord[]> {
  const { data, error } = await client.GET("/api/jobs", {
    params: { query },
  })
  if (error) {
    throw error
  }
  return data
}

export async function get_job(id: string): Promise<JobRecord> {
  const { data, error } = await client.GET("/api/jobs/{id}", {
    params: { path: { id } },
  })
  if (error) {
    throw error
  }
  return data
}

export async function create_job(
  type: string,
  params: Record<string, unknown> = {},
  metadata: Record<string, unknown> | null = null,
  project_id: string | null = null,
  idempotency_key: string | null = null,
): Promise<
  | components["schemas"]["CreateJobResponse"]
  | components["schemas"]["JobRecord"]
> {
  const { data, error } = await client.POST("/api/jobs/{type}", {
    params: { path: { type } },
    body: { params, metadata, project_id, idempotency_key },
  })
  if (error) {
    throw error
  }
  return data
}

export async function get_job_result(
  id: string,
): Promise<Record<string, unknown>> {
  const { data, error } = await client.GET("/api/jobs/{id}/result", {
    params: { path: { id } },
  })
  if (error) {
    throw error
  }
  return data
}

export async function get_job_errors(
  id: string,
  run_id?: string,
): Promise<JobErrorEntry[]> {
  const { data, error } = await client.GET("/api/jobs/{id}/errors", {
    params: { path: { id }, query: run_id ? { run_id } : {} },
  })
  if (error) {
    throw error
  }
  return data as JobErrorEntry[]
}

export async function pause_job(id: string): Promise<void> {
  const { error } = await client.POST("/api/jobs/{id}/pause", {
    params: { path: { id } },
  })
  if (error) {
    throw error
  }
}

export async function resume_job(id: string): Promise<void> {
  const { error } = await client.POST("/api/jobs/{id}/resume", {
    params: { path: { id } },
  })
  if (error) {
    throw error
  }
}

export async function cancel_job(id: string): Promise<void> {
  const { error } = await client.POST("/api/jobs/{id}/cancel", {
    params: { path: { id } },
  })
  if (error) {
    throw error
  }
}

export async function delete_job(id: string): Promise<void> {
  const { error } = await client.DELETE("/api/jobs/{id}", {
    params: { path: { id } },
  })
  if (error) {
    throw error
  }
}
