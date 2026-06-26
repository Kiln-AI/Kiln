import type { EvalConfig } from "$lib/types"
import {
  type V2EvalType,
  type V2PropsMap,
  getV2EvalTypeMetadata,
  getV2TypeFromEvalConfig,
} from "./registry"
import { assertNever } from "$lib/utils/exhaustive"

/**
 * Returns the "... Judge" display label for a V2 eval type.
 * Appends "Judge" if the label does not already end with it.
 * Reuses the same convention as eval_type_intro.svelte.
 */
export function evalTypeJudgeLabel(type: V2EvalType): string {
  const label = getV2EvalTypeMetadata(type).label
  return label.endsWith("Judge") ? label : label + " Judge"
}

/**
 * Returns the eval type column label for an EvalConfig.
 * V2 configs get their specific judge label; legacy configs
 * show their config_type UI name.
 */
export function evalConfigTypeLabel(eval_config: EvalConfig): string {
  const v2Type = getV2TypeFromEvalConfig(eval_config)
  if (v2Type) {
    return evalTypeJudgeLabel(v2Type)
  }
  if (eval_config.config_type === "g_eval") return "G-Eval"
  if (eval_config.config_type === "llm_as_judge") return "LLM as Judge"
  return eval_config.config_type
}

/**
 * Returns a concise text summary of an EvalConfig's properties,
 * suitable for the "Eval Details" column preview and the "see all" modal.
 *
 * Uses an exhaustive switch over V2EvalType so that adding a new type
 * without updating this function causes a compile-time type error.
 */
export function evalConfigDetailsSummary(eval_config: EvalConfig): string {
  const v2Type = getV2TypeFromEvalConfig(eval_config)
  if (!v2Type) {
    return legacyConfigSummary(eval_config)
  }
  return v2ConfigSummary(v2Type, eval_config)
}

function legacyConfigSummary(eval_config: EvalConfig): string {
  const props = eval_config.properties as Record<string, unknown> | null
  if (!props) return "No details available."
  const taskDesc = props["task_description"] as string | undefined
  const evalSteps = props["eval_steps"] as string[] | undefined
  const parts: string[] = []
  if (taskDesc) {
    parts.push(taskDesc)
  }
  if (evalSteps && evalSteps.length > 0) {
    const numbered = evalSteps
      .map((step, i) => `${i + 1}. ${step}`)
      .join("\n")
    parts.push("Steps:\n" + numbered)
  }
  return parts.length > 0 ? parts.join("\n\n") : "No details available."
}

function v2ConfigSummary(type: V2EvalType, eval_config: EvalConfig): string {
  // Exhaustive switch — adding a new V2EvalType without a case here
  // will cause a TypeScript compile error via assertNever.
  switch (type) {
    case "llm_judge":
      return llmJudgeSummary(eval_config)
    case "code_eval":
      return codeEvalSummary(eval_config)
    case "exact_match":
      return exactMatchSummary(eval_config)
    case "pattern_match":
      return patternMatchSummary(eval_config)
    case "contains":
      return containsSummary(eval_config)
    case "set_check":
      return setCheckSummary(eval_config)
    case "tool_call_check":
      return toolCallCheckSummary(eval_config)
    case "step_count_check":
      return stepCountCheckSummary(eval_config)
    default:
      return assertNever(type)
  }
}

function llmJudgeSummary(eval_config: EvalConfig): string {
  const props = eval_config.properties as V2PropsMap["llm_judge"] | null
  if (!props) return "No details available."
  const parts: string[] = []
  if (props.prompt_template) {
    parts.push(props.prompt_template)
  }
  if (props.system_prompt) {
    parts.push("System prompt: " + props.system_prompt)
  }
  return parts.length > 0 ? parts.join("\n\n") : "No details available."
}

function codeEvalSummary(eval_config: EvalConfig): string {
  const props = eval_config.properties as V2PropsMap["code_eval"] | null
  if (!props?.code) return "No code provided."
  return props.code
}

function valueExpressionLabel(expr: string | null | undefined): string {
  if (!expr) return "output"
  return expr
}

function exactMatchSummary(eval_config: EvalConfig): string {
  const props = eval_config.properties as V2PropsMap["exact_match"] | null
  if (!props) return "No details available."
  const source = valueExpressionLabel(props.value_expression)
  const casePart = props.case_sensitive ? "" : " (case-insensitive)"
  if (props.expected_value != null) {
    return `Compare ${source} to expected value "${props.expected_value}"${casePart}`
  }
  if (props.reference_key) {
    return `Compare ${source} to reference_data.${props.reference_key}${casePart}`
  }
  return `Exact match on ${source}${casePart}`
}

function patternMatchSummary(eval_config: EvalConfig): string {
  const props = eval_config.properties as V2PropsMap["pattern_match"] | null
  if (!props) return "No details available."
  const source = valueExpressionLabel(props.value_expression)
  const modeLabel =
    props.mode === "must_not_match" ? "must not match" : "must match"
  return `${source} ${modeLabel} pattern /${props.pattern}/`
}

function containsSummary(eval_config: EvalConfig): string {
  const props = eval_config.properties as V2PropsMap["contains"] | null
  if (!props) return "No details available."
  const source = valueExpressionLabel(props.value_expression)
  const modeLabel =
    props.mode === "must_not_contain" ? "must not contain" : "must contain"
  const casePart = props.case_sensitive ? "" : " (case-insensitive)"
  if (props.substring != null) {
    return `${source} ${modeLabel} "${props.substring}"${casePart}`
  }
  if (props.reference_key) {
    return `${source} ${modeLabel} reference_data.${props.reference_key}${casePart}`
  }
  return `${source} ${modeLabel} a value${casePart}`
}

function setCheckSummary(eval_config: EvalConfig): string {
  const props = eval_config.properties as V2PropsMap["set_check"] | null
  if (!props) return "No details available."
  const source = valueExpressionLabel(props.value_expression)
  const modeLabels: Record<string, string> = {
    subset: "is a subset of",
    superset: "is a superset of",
    equal: "equals",
  }
  const modeLabel = modeLabels[props.mode] || props.mode
  if (props.expected_set && props.expected_set.length > 0) {
    return `${source} ${modeLabel} {${props.expected_set.join(", ")}}`
  }
  if (props.reference_key) {
    return `${source} ${modeLabel} reference_data.${props.reference_key}`
  }
  return `Set check on ${source} (${props.mode})`
}

function toolCallCheckSummary(eval_config: EvalConfig): string {
  const props = eval_config.properties as V2PropsMap["tool_call_check"] | null
  if (!props) return "No details available."
  const toolNames = props.expected_tools.map((t) => t.tool_name)
  const modeLabels: Record<string, string> = {
    any: "any of",
    all: "all of",
    ordered: "in order",
    never: "never call",
  }
  const modeLabel = modeLabels[props.match_mode] || props.match_mode
  let summary = `Expect ${modeLabel}: ${toolNames.join(", ")}`
  if (props.on_unexpected_tools === "fail") {
    summary += " (fail on unexpected tools)"
  }
  return summary
}

function stepCountCheckSummary(eval_config: EvalConfig): string {
  const props = eval_config.properties as V2PropsMap["step_count_check"] | null
  if (!props) return "No details available."
  const typeLabels: Record<string, string> = {
    tool_calls: "tool calls",
    model_responses: "model responses",
    turns: "turns",
  }
  const countLabel = typeLabels[props.count_type] || props.count_type
  const bounds: string[] = []
  if (props.min_count != null) {
    bounds.push(`min ${props.min_count}`)
  }
  if (props.max_count != null) {
    bounds.push(`max ${props.max_count}`)
  }
  if (bounds.length > 0) {
    return `Count ${countLabel}: ${bounds.join(", ")}`
  }
  return `Count ${countLabel}`
}
