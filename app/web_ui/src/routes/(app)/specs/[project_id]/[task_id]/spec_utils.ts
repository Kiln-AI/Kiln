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
 * Which creation workflow the user picked on the Pro-vs-Manual screen, carried
 * to the spec builder as a `workflow` query param.
 *
 * Anything other than an explicit "pro" is treated as manual, so a missing or
 * malformed param can never surface Kiln Pro to someone who didn't choose it.
 */
export type SpecWorkflow = "manual" | "pro"

export function parseSpecWorkflow(value: string | null): SpecWorkflow {
  return value === "pro" ? "pro" : "manual"
}

/**
 * The judge each template implies. Programmatic judges are chosen directly on
 * the template picker (not via a template), so every template's judge is
 * implied: an LLM judge for the written-rubric templates, and the Tool Call
 * Check judge for tool call, which reads the trace directly and collects its
 * own tool list.
 */
export function implied_judge_for_spec_type(spec_type: SpecType): V2EvalType {
  switch (spec_type) {
    case "appropriate_tool_use":
      return "tool_call_check"
    default:
      return "llm_judge"
  }
}

/**
 * The EvalTemplateId recorded on evals created without a spec. Tool call is
 * the only template that still creates spec-less evals; the open-ended
 * behaviour mappings are kept for flows that record a template after the fact.
 * Mirrors the server's spec_eval_template.
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
 * Whether the Kiln Pro copilot could assist a spec of this type with this
 * judge. Mirrors the spec builder's own `copilot_enabled` gates that are
 * knowable from the route alone (the builder still applies runtime checks
 * like tool-enabled run configs and account availability).
 */
export function copilot_supported(
  spec_type: SpecType,
  judge: V2EvalType,
): boolean {
  return (
    judge === "llm_judge" &&
    spec_type !== "appropriate_tool_use" &&
    spec_type !== "reference_answer_accuracy"
  )
}

/**
 * The next screen after a template is picked: the Pro-vs-Manual workflow
 * screen when copilot could assist the template's implied judge, otherwise
 * straight to the spec builder in manual mode.
 */
export function next_page_after_template(
  project_id: string,
  task_id: string,
  spec_type: SpecType,
): string {
  return next_page_after_judge(
    project_id,
    task_id,
    spec_type,
    implied_judge_for_spec_type(spec_type),
  )
}

/**
 * The spec builder URL for a judge picked directly from the template screen's
 * programmatic checks section. No template is involved: the eval is created
 * spec-less and template-less, with just a name and the judge's own config.
 */
export function judge_only_builder_url(
  project_id: string,
  task_id: string,
  judge: V2EvalType,
): string {
  const params = new URLSearchParams({ judge, workflow: "manual" })
  return `/specs/${project_id}/${task_id}/spec_builder?${params.toString()}`
}

/**
 * The next screen once both template and judge are known: the Pro-vs-Manual
 * workflow screen when copilot could assist, otherwise straight to the spec
 * builder in manual mode. Asking Pro-vs-Manual any earlier would pose the
 * question to users picking judges Kiln Pro can't help with.
 */
export function next_page_after_judge(
  project_id: string,
  task_id: string,
  spec_type: SpecType,
  judge: V2EvalType,
): string {
  if (copilot_supported(spec_type, judge)) {
    const params = new URLSearchParams({ type: spec_type, judge })
    return `/specs/${project_id}/${task_id}/select_workflow?${params.toString()}`
  }
  return spec_builder_url(project_id, task_id, spec_type, "manual", judge)
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
