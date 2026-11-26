import type { Eval, Spec, ToolSetApiDescription } from "$lib/types"
import { eval_split } from "$lib/utils/eval_splits"
import {
  build_eval_generation_splits,
  tag_from_filter_id,
} from "$lib/utils/eval_generation_splits"
import { encode_splits_for_url } from "$lib/utils/splits_util"

/**
 * The link to the "Add Data for your Eval" page. The page works out everything else (the
 * template, the splits, the tool, the link back) from the eval, so this is the only form
 * of the link any caller, the app or an agent, needs to build.
 */
export function eval_add_data_link(
  project_id: string,
  task_id: string,
  eval_id: string,
): string {
  const params = new URLSearchParams({ reason: "eval", eval_id })
  return `/dataset/${project_id}/${task_id}/add_data?${params.toString()}`
}

/**
 * The eval id an add-data link names. Accepts the plain id, and the full
 * `project_id::task_id::eval_id` form that older links carry. Undefined when the full form
 * names another task, or the param is empty.
 */
export function eval_id_from_param(
  param: string | null,
  project_id: string,
  task_id: string,
): string | undefined {
  if (!param) {
    return undefined
  }
  const parts = param.split("::")
  if (parts.length === 1) {
    return parts[0]
  }
  if (parts.length === 3 && parts[0] === project_id && parts[1] === task_id) {
    return parts[2] || undefined
  }
  return undefined
}

export type EvalAddDataInput = {
  project_id: string
  task_id: string
  evaluator: Eval
  // The spec that points at this eval, or null for an eval with no spec.
  spec: Spec | null
  // The properties of the eval's default judge, or null when it has none.
  judge_properties: Record<string, unknown> | null
  // The project's available tools, used to turn a tool-call judge's function name into a
  // tool id.
  tool_sets: ToolSetApiDescription[]
}

export type EvalAddDataPlan =
  | {
      kind: "ready"
      template_id: string | null
      // The `project_id::task_id::eval_id` form the synthetic data pages read.
      full_eval_id: string
      eval_link: string
      splits: Record<string, number>
      splits_param: string
      tool_id: string | null
    }
  | { kind: "refused"; message: string; eval_link: string }

export const EVAL_INPUT_TEST_SPLIT_MESSAGE =
  "This eval uses our new eval dataset format, which can't be generated from this UI."
export const MISSING_TAG_MESSAGE =
  "No test or golden dataset tag found. If you're using a custom filter, set up the dataset manually."

/**
 * How data is added to an eval: which tags generated or uploaded data goes to, and what the
 * add-data flow carries forward. Refused when the flow can't reach the eval's data: adding
 * data writes TaskRuns, so the test split must hold TaskRuns and name a tag, and every eval
 * but rag needs a golden tag.
 */
export function plan_eval_add_data(input: EvalAddDataInput): EvalAddDataPlan {
  const { project_id, task_id, evaluator, spec } = input
  const eval_id = evaluator.id ?? ""
  const eval_link = `/specs/${project_id}/${task_id}/${spec?.id ?? "legacy"}/${eval_id}`

  if (eval_split(evaluator, "test")?.source === "eval_input") {
    return {
      kind: "refused",
      message: EVAL_INPUT_TEST_SPLIT_MESSAGE,
      eval_link,
    }
  }
  const golden_tag = tag_from_filter_id(evaluator.eval_configs_filter_id)
  const splits = build_eval_generation_splits(evaluator)
  if (!splits || (evaluator.template !== "rag" && !golden_tag)) {
    return { kind: "refused", message: MISSING_TAG_MESSAGE, eval_link }
  }

  return {
    kind: "ready",
    template_id: evaluator.template ?? null,
    full_eval_id: `${project_id}::${task_id}::${eval_id}`,
    eval_link,
    splits,
    splits_param: encode_splits_for_url(splits),
    tool_id: eval_tool_id(input) ?? null,
  }
}

// The tool that generation should enable for a tool-call eval. Each kind of eval keeps it
// somewhere different: appropriate_tool_use specs store tool_id, tool_call-template evals
// store it in template_properties, and template-less tool evals name tool functions on
// their tool_call_check judge.
function eval_tool_id(input: EvalAddDataInput): string | undefined {
  const { evaluator, spec } = input
  if (evaluator.template === "tool_call") {
    const spec_properties = spec?.properties
    if (spec_properties?.spec_type === "appropriate_tool_use") {
      return spec_properties.tool_id ?? undefined
    }
    const template_tool_id = evaluator.template_properties?.tool_id
    return template_tool_id ? String(template_tool_id) : undefined
  }
  return tool_id_from_judge(input.judge_properties, input.tool_sets)
}

// The tool id for the first expected tool of a tool_call_check judge, resolved by function
// name. Undefined for other judges and unknown tools: the flow works without it, the tool
// just isn't pre-enabled.
function tool_id_from_judge(
  judge_properties: Record<string, unknown> | null,
  tool_sets: ToolSetApiDescription[],
): string | undefined {
  if (judge_properties?.["type"] !== "tool_call_check") {
    return undefined
  }
  const expected_tools = judge_properties["expected_tools"]
  if (!Array.isArray(expected_tools) || expected_tools.length === 0) {
    return undefined
  }
  const first = expected_tools[0]
  const function_name =
    first && typeof first === "object"
      ? (first as { tool_name?: unknown }).tool_name
      : undefined
  if (typeof function_name !== "string" || !function_name) {
    return undefined
  }
  for (const tool_set of tool_sets) {
    for (const tool of tool_set.tools) {
      if ((tool.function_name ?? tool.name) === function_name) {
        return tool.id
      }
    }
  }
  return undefined
}
