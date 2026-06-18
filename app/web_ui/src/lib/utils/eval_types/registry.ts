import type { ComponentType } from "svelte"
import { assertNever } from "$lib/utils/exhaustive"
import type { V2EvalConfigProperties } from "$lib/api/v2_eval_api"

import ExactMatchForm from "$lib/components/eval_types/exact_match_form.svelte"
import PatternMatchForm from "$lib/components/eval_types/pattern_match_form.svelte"
import ContainsForm from "$lib/components/eval_types/contains_form.svelte"
import SetCheckForm from "$lib/components/eval_types/set_check_form.svelte"
import ToolCallCheckForm from "$lib/components/eval_types/tool_call_check_form.svelte"
import StepCountCheckForm from "$lib/components/eval_types/step_count_check_form.svelte"
import LlmJudgeForm from "$lib/components/eval_types/llm_judge_form.svelte"
import CodeEvalForm from "$lib/components/eval_types/code_eval_form.svelte"

import ExactMatchResult from "$lib/components/eval_types/exact_match_result.svelte"
import PatternMatchResult from "$lib/components/eval_types/pattern_match_result.svelte"
import ContainsResult from "$lib/components/eval_types/contains_result.svelte"
import SetCheckResult from "$lib/components/eval_types/set_check_result.svelte"
import ToolCallCheckResult from "$lib/components/eval_types/tool_call_check_result.svelte"
import StepCountCheckResult from "$lib/components/eval_types/step_count_check_result.svelte"
import LlmJudgeResult from "$lib/components/eval_types/llm_judge_result.svelte"
import CodeEvalResult from "$lib/components/eval_types/code_eval_result.svelte"

/**
 * All V2 eval type discriminator values.
 * Mirrors the backend V2EvalType enum.
 */
export type V2EvalType =
  | "exact_match"
  | "pattern_match"
  | "contains"
  | "set_check"
  | "tool_call_check"
  | "step_count_check"
  | "llm_judge"
  | "code_eval"

export const ALL_V2_EVAL_TYPES: readonly V2EvalType[] = [
  "exact_match",
  "pattern_match",
  "contains",
  "set_check",
  "tool_call_check",
  "step_count_check",
  "llm_judge",
  "code_eval",
] as const

/**
 * Imperative API exposed by V2 eval-type form components via `export function`.
 * Used to retrieve form state from the parent page via `bind:this`.
 */
export interface EvalTypeFormApi {
  getProperties(): V2EvalConfigProperties
  validate?(): string | null
}

export interface V2EvalTypeMetadata {
  label: string
  description: string
  icon: string
  requiresTrust: boolean
  createFormComponent: ComponentType
  resultRendererComponent: ComponentType
}

/**
 * Get metadata for a single V2 eval type.
 * Uses assertNever for compile-time exhaustiveness.
 */
export function getV2EvalTypeMetadata(type: V2EvalType): V2EvalTypeMetadata {
  switch (type) {
    case "exact_match":
      return {
        label: "Exact Match",
        description:
          "Passes when the output exactly matches a fixed value or reference key.",
        icon: "bi bi-bullseye",
        requiresTrust: false,
        createFormComponent: ExactMatchForm,
        resultRendererComponent: ExactMatchResult,
      }
    case "pattern_match":
      return {
        label: "Pattern Match",
        description:
          "Passes when the output matches (or does not match) a regular expression.",
        icon: "bi bi-regex",
        requiresTrust: false,
        createFormComponent: PatternMatchForm,
        resultRendererComponent: PatternMatchResult,
      }
    case "contains":
      return {
        label: "Contains",
        description:
          "Passes when the output contains (or does not contain) a substring or reference value.",
        icon: "bi bi-search",
        requiresTrust: false,
        createFormComponent: ContainsForm,
        resultRendererComponent: ContainsResult,
      }
    case "set_check":
      return {
        label: "Set Check",
        description:
          "Compares the output (parsed as a set) against an expected set using subset, superset, or equality.",
        icon: "bi bi-collection",
        requiresTrust: false,
        createFormComponent: SetCheckForm,
        resultRendererComponent: SetCheckResult,
      }
    case "tool_call_check":
      return {
        label: "Tool Call Check",
        description:
          "Validates that the model made the expected tool calls with correct arguments.",
        icon: "bi bi-wrench",
        requiresTrust: false,
        createFormComponent: ToolCallCheckForm,
        resultRendererComponent: ToolCallCheckResult,
      }
    case "step_count_check":
      return {
        label: "Step Count Check",
        description:
          "Passes when the number of conversation steps (tool calls, model responses, or turns) falls within bounds.",
        icon: "bi bi-123",
        requiresTrust: false,
        createFormComponent: StepCountCheckForm,
        resultRendererComponent: StepCountCheckResult,
      }
    case "llm_judge":
      return {
        label: "LLM Judge",
        description:
          "Uses an LLM to evaluate output quality via a custom prompt template.",
        icon: "bi bi-robot",
        requiresTrust: false,
        createFormComponent: LlmJudgeForm,
        resultRendererComponent: LlmJudgeResult,
      }
    case "code_eval":
      return {
        label: "Code Eval",
        description:
          "Runs a custom Python scoring function against the output.",
        icon: "bi bi-code-slash",
        requiresTrust: true,
        createFormComponent: CodeEvalForm,
        resultRendererComponent: CodeEvalResult,
      }
    default:
      return assertNever(type)
  }
}

/**
 * Extract the V2 eval type from an EvalConfig's properties, if it is a V2 config.
 * Returns null for legacy (V1) configs or if properties are missing.
 */
export function getV2TypeFromEvalConfig(eval_config: {
  config_type: string
  properties?: { type?: string } | null
}): V2EvalType | null {
  if (eval_config.config_type !== "v2") return null
  const props = eval_config.properties
  if (!props || !("type" in props) || typeof props.type !== "string")
    return null
  const t = props.type as V2EvalType
  if (ALL_V2_EVAL_TYPES.includes(t)) return t
  return null
}

/**
 * Build the full registry map of all V2 eval types to their metadata.
 */
export function buildV2EvalTypeRegistry(): Map<V2EvalType, V2EvalTypeMetadata> {
  const map = new Map<V2EvalType, V2EvalTypeMetadata>()
  for (const t of ALL_V2_EVAL_TYPES) {
    map.set(t, getV2EvalTypeMetadata(t))
  }
  return map
}
