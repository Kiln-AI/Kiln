import { client } from "$lib/api_client"
import type { components } from "$lib/api_schema"

export type JobRecord = components["schemas"]["JobRecord"]
export type JobProgress = components["schemas"]["JobProgress"]
export type JobError = components["schemas"]["JobError"]
export type BackgroundJobStatus = components["schemas"]["BackgroundJobStatus"]

export type JobErrorEntry = {
  error_message?: string
} & Record<string, unknown>

// Mirror of the backend EvalJobWorker.EvalJobProperties model. JobRecord
// carries worker-published properties as an untyped dict on the wire (so the
// core stays worker-agnostic); the frontend casts it per job type.
export type EvalJobProperties = {
  eval_name: string
  run_config_name: string
  run_config_model_name: string
  run_config_model_provider: string
  run_config_prompt_name: string
  run_config_tools_count: number
  run_config_skills_count: number
  judge_name: string
  judge_algorithm: string
  judge_model_name: string
  judge_model_provider: string
}

export function eval_job_properties(job: JobRecord): EvalJobProperties | null {
  if (job.type !== "eval" || !job.properties) {
    return null
  }
  return job.properties as EvalJobProperties
}

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
