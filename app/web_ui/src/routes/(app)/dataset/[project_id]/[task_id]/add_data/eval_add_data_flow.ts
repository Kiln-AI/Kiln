import { get } from "svelte/store"
import { client } from "$lib/api_client"
import { available_tools, load_available_tools } from "$lib/stores"
import type { Eval, Spec } from "$lib/types"
import {
  plan_eval_add_data,
  type EvalAddDataPlan,
} from "$lib/utils/eval_add_data"

/**
 * Loads what the add-data plan needs from the eval alone: the eval, the spec that points
 * at it, its default judge and the project's tools. Throws the API error when the eval
 * can't be read; the spec, the judge and the tools only refine the plan, so a failure
 * there leaves them out.
 */
export async function load_eval_add_data_plan(
  project_id: string,
  task_id: string,
  eval_id: string,
): Promise<EvalAddDataPlan> {
  const [evaluator, spec, tool_sets] = await Promise.all([
    load_eval(project_id, task_id, eval_id),
    load_spec_for_eval(project_id, task_id, eval_id),
    load_tool_sets(project_id),
  ])
  const judge_properties = await load_judge_properties(
    project_id,
    task_id,
    evaluator,
  )
  return plan_eval_add_data({
    project_id,
    task_id,
    evaluator,
    spec,
    judge_properties,
    tool_sets,
  })
}

async function load_eval(
  project_id: string,
  task_id: string,
  eval_id: string,
): Promise<Eval> {
  const { data, error } = await client.GET(
    "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}",
    { params: { path: { project_id, task_id, eval_id } } },
  )
  if (error) {
    throw error
  }
  return data
}

async function load_spec_for_eval(
  project_id: string,
  task_id: string,
  eval_id: string,
): Promise<Spec | null> {
  const { data, error } = await client.GET(
    "/api/projects/{project_id}/tasks/{task_id}/specs",
    { params: { path: { project_id, task_id } } },
  )
  if (error || !data) {
    return null
  }
  return data.find((spec) => spec.eval_id === eval_id) ?? null
}

async function load_judge_properties(
  project_id: string,
  task_id: string,
  evaluator: Eval,
): Promise<Record<string, unknown> | null> {
  const eval_config_id = evaluator.current_config_id
  if (!evaluator.id || !eval_config_id) {
    return null
  }
  const { data, error } = await client.GET(
    "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/eval_config/{eval_config_id}",
    {
      params: {
        path: { project_id, task_id, eval_id: evaluator.id, eval_config_id },
      },
    },
  )
  if (error || !data?.properties) {
    return null
  }
  return data.properties as Record<string, unknown>
}

async function load_tool_sets(project_id: string) {
  await load_available_tools(project_id)
  return get(available_tools)[project_id] ?? []
}
