import { client } from "$lib/api_client"
import type {
  Eval,
  EvalStatus,
  SpecType,
  Task,
  TaskRunConfig,
} from "$lib/types"
import type { components } from "$lib/api_schema"
import { isKilnAgentRunConfig } from "$lib/types"
import type { V2EvalType } from "$lib/utils/eval_types/registry"
import { spec_field_configs } from "./select_template/spec_templates"
import {
  load_task_run_configs,
  run_configs_by_task_composite_id,
} from "$lib/stores/run_configs_store"
import { get_task_composite_id } from "$lib/stores"
import { get } from "svelte/store"
import posthog from "posthog-js"

export type SuggestedEdit = {
  proposed_value: string
  reason_for_edit: string
}

/**
 * Which creation workflow the user picked on the first screen. Threaded through
 * the flow as a `workflow` query param.
 *
 * Anything other than an explicit "pro" is treated as manual, so a missing or
 * malformed param can never surface Kiln Pro to someone who didn't choose it.
 */
export type SpecWorkflow = "manual" | "pro"

export function parseSpecWorkflow(value: string | null): SpecWorkflow {
  return value === "pro" ? "pro" : "manual"
}

/**
 * Templates that skip the judge picker, and the judge they imply.
 *
 * Only the two open-ended behaviour templates (desired behaviour, issue) offer
 * a judge choice. Every other template describes a written rubric only an LLM
 * judge can grade, except tool call, where the Tool Call Check judge reads the
 * trace directly and collects its own tool list.
 */
export function implied_judge_for_spec_type(
  spec_type: SpecType,
): V2EvalType | null {
  switch (spec_type) {
    case "desired_behaviour":
    case "issue":
      return null
    case "appropriate_tool_use":
      return "tool_call_check"
    default:
      return "llm_judge"
  }
}

/**
 * The EvalTemplateId recorded on evals created without a spec. Only templates
 * that can reach a non-LLM judge need a mapping: the two open-ended behaviour
 * templates and tool call. Mirrors the server's spec_eval_template.
 */
export function eval_template_for_spec_type(
  spec_type: SpecType,
): components["schemas"]["EvalTemplateId"] | null {
  switch (spec_type) {
    case "desired_behaviour":
      return "desired_behaviour"
    case "issue":
      return "kiln_issue"
    case "appropriate_tool_use":
      return "tool_call"
    default:
      return null
  }
}

/**
 * The next screen after a template is picked: either straight to the spec
 * builder (for templates whose judge is implied) or the judge picker.
 */
export function next_page_after_template(
  project_id: string,
  task_id: string,
  spec_type: SpecType,
  workflow: SpecWorkflow,
): string {
  const base = `/specs/${project_id}/${task_id}`
  const implied = implied_judge_for_spec_type(spec_type)
  if (implied) {
    return spec_builder_url(project_id, task_id, spec_type, workflow, implied)
  }
  return `${base}/select_judge?type=${spec_type}&workflow=${workflow}`
}

export function spec_builder_url(
  project_id: string,
  task_id: string,
  spec_type: SpecType,
  workflow: SpecWorkflow,
  judge: V2EvalType,
): string {
  const params = new URLSearchParams({
    type: spec_type,
    workflow,
    judge,
  })
  return `/specs/${project_id}/${task_id}/spec_builder?${params.toString()}`
}

/**
 * A reviewed example from the spec review process.
 * These examples form the golden dataset for the spec's eval.
 * user_says_meets_spec is optional in the UI (not yet reviewed) but required when sent to backend.
 */
export type ReviewRow = {
  input: string
  output: string
  model_says_meets_spec: boolean
  user_says_meets_spec?: boolean
  feedback: string
  row_id: string
}

/**
 * Build a definition string from properties
 * @param specType - The type of spec
 * @param properties - The properties of the spec
 * @returns The definition string
 */
export function buildSpecDefinition(
  specType: SpecType,
  properties: Record<string, string | null>,
): string {
  const fieldConfigs = spec_field_configs[specType]
  const parts: string[] = []

  for (const field of fieldConfigs) {
    const value = properties[field.key]
    if (value && value.trim()) {
      parts.push(`## ${field.label}\n${value}`)
    }
  }

  return parts.join("\n\n")
}

/**
 * Check if the task's default run config has any tools configured
 * @param project_id - The project ID
 * @param task - The task to check
 * @returns true if the default run config has tools, false otherwise
 */
export async function checkDefaultRunConfigHasTools(
  project_id: string,
  task: Task,
): Promise<boolean> {
  if (!task.id) {
    throw new Error("Task ID is required")
  }

  if (!task.default_run_config_id) {
    return false
  }

  await load_task_run_configs(project_id, task.id)
  const run_configs =
    get(run_configs_by_task_composite_id)[
      get_task_composite_id(project_id, task.id)
    ] ?? []

  const default_config = run_configs.find(
    (config: TaskRunConfig) => config.id === task.default_run_config_id,
  )

  if (!default_config) {
    return false
  }

  const tools = isKilnAgentRunConfig(default_config.run_config_properties)
    ? default_config.run_config_properties.tools_config?.tools ?? []
    : []
  return tools.length > 0
}

/**
 * Update an eval's priority via the API. Priority lives on the eval (spec-backed
 * or not); the server resolves legacy files through their spec on read.
 * @returns The updated eval
 * @throws Error if the API call fails
 */
export async function updateEvalPriority(
  project_id: string,
  task_id: string,
  evaluator: Eval,
  newPriority: number,
): Promise<Eval> {
  if (!evaluator.id) {
    throw new Error("Eval ID is required")
  }

  const { data, error } = await client.PATCH(
    "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}",
    {
      params: {
        path: { project_id, task_id, eval_id: evaluator.id },
      },
      body: {
        priority: newPriority as 0 | 1 | 2 | 3,
      },
    },
  )

  if (error) {
    throw error
  }

  posthog.capture("update_eval_priority", {
    old_priority: evaluator.priority,
    new_priority: newPriority,
  })

  return data
}

/**
 * Update an eval's status via the API. Status lives on the eval (spec-backed
 * or not); the server resolves legacy files through their spec on read.
 * @returns The updated eval
 * @throws Error if the API call fails
 */
export async function updateEvalStatus(
  project_id: string,
  task_id: string,
  evaluator: Eval,
  newStatus: EvalStatus,
): Promise<Eval> {
  if (!evaluator.id) {
    throw new Error("Eval ID is required")
  }

  const { data, error } = await client.PATCH(
    "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}",
    {
      params: {
        path: { project_id, task_id, eval_id: evaluator.id },
      },
      body: {
        status: newStatus,
      },
    },
  )

  if (error) {
    throw error
  }

  posthog.capture("update_eval_status", {
    old_status: evaluator.status,
    new_status: newStatus,
  })

  return data
}

/**
 * Extract a tag from a filter_id string (e.g., "tag::my_tag" -> "my_tag")
 * @param filter_id - The filter ID to extract the tag from
 * @returns The tag if the filter_id is a tag filter, undefined otherwise
 */
export function tagFromFilterId(filter_id: string): string | undefined {
  if (filter_id.startsWith("tag::")) {
    return filter_id.replace("tag::", "")
  }
  return undefined
}

/**
 * Generate a dataset link from a filter_id
 * @param project_id - The project ID
 * @param task_id - The task ID
 * @param filter_id - The filter ID to generate a link from
 * @returns The dataset URL if the filter_id is a tag filter, undefined otherwise
 */
export function linkFromFilterId(
  project_id: string,
  task_id: string,
  filter_id: string | null | undefined,
): string | undefined {
  if (!filter_id) {
    return undefined
  }
  const tag = tagFromFilterId(filter_id)
  if (tag) {
    return `/dataset/${project_id}/${task_id}?tags=${tag}`
  }
  return undefined
}
