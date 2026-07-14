import type { ComponentType } from "svelte"
import { assertNever } from "$lib/utils/exhaustive"
import { SHOW_REFERENCE_DATA_UI } from "$lib/utils/eval_types/reference_data_ui"
import type { V2EvalConfigProperties } from "$lib/api/v2_eval_api"
import type { components } from "$lib/api_schema"
import type { EvalConfig } from "$lib/types"

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
  "llm_judge",
  "code_eval",
  "tool_call_check",
  "exact_match",
  "pattern_match",
  "contains",
  "set_check",
  "step_count_check",
] as const

/**
 * Imperative API exposed by V2 eval-type form components via `export function`.
 * Used to retrieve form state from the parent page via `bind:this`.
 */
export interface EvalTypeFormApi {
  getProperties(): V2EvalConfigProperties
  validate?(): string | null
}

export type EvalTypeTag = { label: string; tone: "default" | "beta" }

/**
 * How a V2 eval type uses reference data in the Test Judge pane.
 *
 * - `"llm_judge"` — referenced via Jinja in the judge prompt
 * - `"reference_field"` — compared via a selected Reference Data Field
 * - `"code"` — passed as the `reference_data` argument to scoring code
 * - `"none"` — never read; the Reference Data field is hidden entirely
 */
export type ReferenceDataUsageMode =
  | "llm_judge"
  | "reference_field"
  | "code"
  | "none"

/**
 * Maps a V2 eval type to its reference-data usage mode.
 * Uses assertNever so adding a new V2EvalType forces a compile error
 * until its mode is declared here.
 *
 * While SHOW_REFERENCE_DATA_UI is off, every type reports "none", which hides
 * the Reference Data field from the Test Judge pane for all judge types.
 */
export function referenceDataUsageMode(
  type: V2EvalType,
): ReferenceDataUsageMode {
  if (!SHOW_REFERENCE_DATA_UI) {
    return "none"
  }
  switch (type) {
    case "llm_judge":
      return "llm_judge"
    case "exact_match":
    case "contains":
    case "set_check":
      return "reference_field"
    case "code_eval":
      return "code"
    case "pattern_match":
    case "tool_call_check":
    case "step_count_check":
      return "none"
    default:
      return assertNever(type)
  }
}

export interface ManualExampleSupport {
  /** Whether an input/output-only manual example can be used with this judge. */
  supported: boolean
  /** Tooltip reason when unsupported; null when supported. */
  reason: string | null
}

const MANUAL_EXAMPLE_TRACE_REASON =
  "Manual examples only provide an input and output. This judge can use the model's full execution trace, which a manual example doesn't include. Pick a dataset sample instead."

/**
 * Whether "add manual example" (input/output only, no trace) is offered for a
 * given judge type.
 *
 * - tool_call_check / step_count_check inherently operate on the trace and have
 *   no output-only mode, so manual examples are never useful for them.
 * - Every other type (the deterministic string judges, llm_judge, code_eval)
 *   can work from input/output alone. They *may* be configured to use the trace
 *   (e.g. a "trace" output expression, or a judge prompt / code that reads it),
 *   but a manual example is still allowed: if it turns out a trace is required,
 *   the test run degrades to a clear "skipped -- requires a trace" result.
 */
export function manualExampleSupport(type: V2EvalType): ManualExampleSupport {
  switch (type) {
    case "tool_call_check":
    case "step_count_check":
      return { supported: false, reason: MANUAL_EXAMPLE_TRACE_REASON }
    case "exact_match":
    case "pattern_match":
    case "contains":
    case "set_check":
    case "llm_judge":
    case "code_eval":
      return { supported: true, reason: null }
    default:
      return assertNever(type)
  }
}

export interface V2EvalTypeMetadata {
  label: string
  description: string
  requiresTrust: boolean
  recommended?: boolean
  tags: EvalTypeTag[]
  pageTitle: string
  pageSubtitle: string
  explainer?: string
  example?: string
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
        description: SHOW_REFERENCE_DATA_UI
          ? "Output field should exactly equal an expected value or a reference-data value."
          : "Output field should exactly equal an expected value.",

        requiresTrust: false,
        tags: [],
        pageTitle: "Add an Exact Match Check",
        pageSubtitle: "Pass when the output equals an expected value.",
        explainer: SHOW_REFERENCE_DATA_UI
          ? "Compares the model output (or a value extracted from it) against a fixed expected value or a value from your reference data. Useful for tasks with a single correct answer."
          : "Compares the model output (or a value extracted from it) against a fixed expected value. Useful for tasks with a single correct answer.",
        example:
          'If you expect the model to output "yes" or "no", Exact Match can verify the answer is correct.',
        createFormComponent: ExactMatchForm,
        resultRendererComponent: ExactMatchResult,
      }
    case "pattern_match":
      return {
        label: "Pattern Match",
        description: "Output field matches a regular expression.",

        requiresTrust: false,
        tags: [],
        pageTitle: "Add a Pattern Match Check",
        pageSubtitle: "Pass when the output matches a regular expression.",
        explainer:
          "Tests the model output against a regular expression pattern. Can require the pattern to match or not match.",
        createFormComponent: PatternMatchForm,
        resultRendererComponent: PatternMatchResult,
      }
    case "contains":
      return {
        label: "Contains",
        description: SHOW_REFERENCE_DATA_UI
          ? "Output contains (or doesn't contain) a string or reference value."
          : "Output contains (or doesn't contain) a string.",

        requiresTrust: false,
        tags: [],
        pageTitle: "Add a Contains Check",
        pageSubtitle: "Pass when the output contains (or omits) a substring.",
        explainer: SHOW_REFERENCE_DATA_UI
          ? "Checks whether the model output includes or excludes a specific substring. The substring can be a fixed value or pulled from your reference data."
          : "Checks whether the model output includes or excludes a specific substring.",
        createFormComponent: ContainsForm,
        resultRendererComponent: ContainsResult,
      }
    case "set_check":
      return {
        label: "Set Check",
        description:
          "Compare a set of values from the output against an expected set.",

        requiresTrust: false,
        tags: [],
        pageTitle: "Add a Set Check",
        pageSubtitle:
          "Compare a set of values from the output against an expected set.",
        explainer:
          "Parses a set of values from the model output and compares it against an expected set using subset, superset, or equality matching.",
        createFormComponent: SetCheckForm,
        resultRendererComponent: SetCheckResult,
      }
    case "tool_call_check":
      return {
        label: "Tool Call Check",
        description:
          "Check the agent called the right tools, in the right order, with the right arguments.",

        requiresTrust: false,
        tags: [],
        pageTitle: "Add a Tool Call Check",
        pageSubtitle:
          "Check the agent called the right tools, order, and arguments.",
        explainer:
          "Inspects the agent's tool-call trace to verify it called the expected tools, with the correct arguments, in the right order.",
        createFormComponent: ToolCallCheckForm,
        resultRendererComponent: ToolCallCheckResult,
      }
    case "step_count_check":
      return {
        label: "Step Count Check",
        description:
          "Count steps in the trace and check they're within bounds.",

        requiresTrust: false,
        tags: [],
        pageTitle: "Add a Step Count Check",
        pageSubtitle:
          "Check the number of steps in the trace is within bounds.",
        explainer:
          "Counts tool calls, model responses, or turns in the agent's trace and checks whether the count falls within specified bounds.",
        createFormComponent: StepCountCheckForm,
        resultRendererComponent: StepCountCheckResult,
      }
    case "llm_judge":
      return {
        label: "LLM as Judge",
        description:
          "A language model grades output against criteria you write.",

        requiresTrust: false,
        recommended: true,
        tags: [],
        pageTitle: "Add an LLM Judge",
        pageSubtitle: "Grade outputs with a model and rubric.",
        explainer:
          "Uses a language model to evaluate output quality against criteria you define in a prompt template.",
        createFormComponent: LlmJudgeForm,
        resultRendererComponent: LlmJudgeResult,
      }
    case "code_eval":
      return {
        label: "Code",
        description: "Write a custom Python scoring function.",

        requiresTrust: true,
        tags: [{ label: "Beta", tone: "beta" }],
        pageTitle: "Add a Code Judge",
        pageSubtitle: "Write a Python function that scores model outputs.",
        explainer: SHOW_REFERENCE_DATA_UI
          ? "Write a custom Python scoring function that can use the model's output, trace, and reference data. Faster and cheaper than LLM as a judge."
          : "Write a custom Python scoring function that can use the model's output and trace. Faster and cheaper than LLM as a judge.",
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
 * Returns the "... Judge" display label for a V2 eval type.
 * Appends "Judge" if the label does not already end with it.
 */
export function evalTypeJudgeLabel(type: V2EvalType): string {
  const label = getV2EvalTypeMetadata(type).label
  return label.endsWith("Judge") ? label : label + " Judge"
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

/**
 * Maps each V2 eval type discriminator to its generated schema properties type.
 */
export type V2PropsMap = {
  exact_match: components["schemas"]["ExactMatchProperties"]
  pattern_match: components["schemas"]["PatternMatchProperties"]
  contains: components["schemas"]["ContainsProperties"]
  set_check: components["schemas"]["SetCheckProperties"]
  tool_call_check: components["schemas"]["ToolCallCheckProperties"]
  step_count_check: components["schemas"]["StepCountCheckProperties"]
  llm_judge: components["schemas"]["LlmJudgeProperties"]
  code_eval: components["schemas"]["CodeEvalProperties"]
}

/**
 * Extract typed V2 properties from an EvalConfig, returning null if the config
 * is missing, has no properties, or the properties' type discriminator doesn't
 * match the expected type.
 */
export function extractV2Props<T extends V2EvalType>(
  eval_config: EvalConfig | null,
  expectedType: T,
): V2PropsMap[T] | null {
  if (
    !eval_config?.properties ||
    !("type" in eval_config.properties) ||
    eval_config.properties.type !== expectedType
  ) {
    return null
  }
  return eval_config.properties as V2PropsMap[T]
}
