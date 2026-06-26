import { client } from "$lib/api_client"
import type { components } from "$lib/api_schema"

/**
 * Extract a human-readable message from an openapi-fetch error object.
 * Kiln's backend returns `{ message: ... }` via connect_custom_errors,
 * but some paths may still use `{ detail: ... }`.
 */
function extractErrorMessage(error: unknown): string {
  const obj = error as Record<string, unknown> | undefined
  return String(obj?.message ?? obj?.detail ?? JSON.stringify(error))
}

/**
 * Re-export schema types so callers can import from this module.
 */
export type V2EvalConfigProperties = NonNullable<
  components["schemas"]["TestV2EvalRequest"]["properties"]
>
export type EvalTaskInput = components["schemas"]["EvalTaskInput"]
export type TestV2EvalRequest = components["schemas"]["TestV2EvalRequest"]
export type TestV2EvalResponse = components["schemas"]["TestV2EvalResponse"]
export type CreateEvalConfigRequest =
  components["schemas"]["CreateEvalConfigRequest"]
export type CreateLlmJudgeConfigRequest =
  components["schemas"]["CreateLlmJudgeConfigRequest"]
export type LlmJudgeBuilderInput = components["schemas"]["LlmJudgeBuilderInput"]

/**
 * Run a V2 eval config test without persisting.
 */
export async function testV2Eval(
  projectId: string,
  taskId: string,
  evalId: string,
  request: TestV2EvalRequest,
  signal?: AbortSignal,
): Promise<TestV2EvalResponse> {
  const { data, error } = await client.POST(
    "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/test_v2_eval",
    {
      params: {
        path: {
          project_id: projectId,
          task_id: taskId,
          eval_id: evalId,
        },
      },
      body: request,
      signal,
    },
  )
  if (error) {
    throw new Error(`test_v2_eval failed: ${extractErrorMessage(error)}`)
  }
  return data
}

/**
 * Create an eval config, returning the created EvalConfig.
 */
export async function createEvalConfig(
  projectId: string,
  taskId: string,
  evalId: string,
  request: CreateEvalConfigRequest,
): Promise<components["schemas"]["EvalConfig"]> {
  const { data, error } = await client.POST(
    "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/create_eval_config",
    {
      params: {
        path: {
          project_id: projectId,
          task_id: taskId,
          eval_id: evalId,
        },
      },
      body: request,
    },
  )
  if (error) {
    throw new Error(`create_eval_config failed: ${extractErrorMessage(error)}`)
  }
  return data
}

/**
 * Create a V2 llm_judge eval config with server-baked template.
 */
export async function createLlmJudgeConfig(
  projectId: string,
  taskId: string,
  evalId: string,
  request: CreateLlmJudgeConfigRequest,
): Promise<components["schemas"]["EvalConfig"]> {
  const { data, error } = await client.POST(
    "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/create_llm_judge_config",
    {
      params: {
        path: {
          project_id: projectId,
          task_id: taskId,
          eval_id: evalId,
        },
      },
      body: request,
    },
  )
  if (error) {
    throw new Error(
      `create_llm_judge_config failed: ${extractErrorMessage(error)}`,
    )
  }
  return data
}

/**
 * Run a V2 llm_judge eval test using the builder input (server bakes the properties).
 */
export async function testV2EvalLlmJudge(
  projectId: string,
  taskId: string,
  evalId: string,
  builderInput: LlmJudgeBuilderInput,
  evalInput: EvalTaskInput,
  signal?: AbortSignal,
): Promise<TestV2EvalResponse> {
  return testV2Eval(
    projectId,
    taskId,
    evalId,
    {
      eval_input: evalInput,
      llm_judge_builder_input: builderInput,
    },
    signal,
  )
}

/**
 * Fetch task runs for a task, sorted most recent first.
 */
export async function fetchTaskRuns(
  projectId: string,
  taskId: string,
): Promise<components["schemas"]["TaskRun-Output"][]> {
  const { data, error } = await client.GET(
    "/api/projects/{project_id}/tasks/{task_id}/runs",
    {
      params: {
        path: { project_id: projectId, task_id: taskId },
      },
    },
  )
  if (error) {
    throw new Error(`Failed to fetch task runs: ${extractErrorMessage(error)}`)
  }
  if (!data) return []
  return [...data].sort((a, b) => {
    const aDate = a.created_at ? new Date(a.created_at).getTime() : 0
    const bDate = b.created_at ? new Date(b.created_at).getTime() : 0
    return bDate - aDate
  })
}

/**
 * Check whether the current session has granted code_eval trust for a project.
 */
export async function checkCodeEvalTrust(
  projectId: string,
): Promise<{ trusted: boolean }> {
  const { data, error } = await client.GET(
    "/api/projects/{project_id}/code_eval_trust",
    {
      params: {
        path: {
          project_id: projectId,
        },
      },
    },
  )
  if (error) {
    throw new Error(
      `code_eval_trust check failed: ${extractErrorMessage(error)}`,
    )
  }
  return data
}

/**
 * Grant code_eval trust for a project in the current session.
 */
export async function grantCodeEvalTrust(
  projectId: string,
): Promise<{ trusted: boolean }> {
  const { data, error } = await client.POST(
    "/api/projects/{project_id}/grant_code_eval_trust",
    {
      params: {
        path: {
          project_id: projectId,
        },
      },
    },
  )
  if (error) {
    throw new Error(
      `grant_code_eval_trust failed: ${extractErrorMessage(error)}`,
    )
  }
  return data
}
