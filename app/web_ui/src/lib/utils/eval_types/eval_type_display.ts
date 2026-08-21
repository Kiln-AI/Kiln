import type { Eval, Spec } from "$lib/types"
import { formatSpecType } from "$lib/utils/formatters"
import {
  ALL_V2_EVAL_TYPES,
  getV2EvalTypeMetadata,
  type V2EvalType,
} from "$lib/utils/eval_types/registry"

/** Judge type discriminators that mean "an LLM scores this eval". */
const LLM_JUDGE_TYPES = new Set(["llm_judge", "g_eval", "llm_as_judge"])

/** V1 config types — only the pre-spec eval system created these. */
const LEGACY_JUDGE_TYPES = new Set(["g_eval", "llm_as_judge"])

/** Human names for the eval template recorded on spec-less evals. */
const TEMPLATE_FLAVORS: Record<string, string> = {
  desired_behaviour: "Desired Behaviour",
  kiln_issue: "Issue",
  // The V1 name for the tool_call template; only legacy evals carry it (new
  // tool evals are the template-less Tool Call Check programmatic judge).
  tool_call: "Appropriate Tool Use",
  toxicity: "Toxicity",
  bias: "Bias",
  maliciousness: "Maliciousness",
  factual_correctness: "Factual Correctness",
  jailbreak: "Jailbreak",
  kiln_requirements: "Requirements",
  rag: "RAG",
}

/**
 * The judge type discriminator for an eval config: V2 configs report their
 * properties type ("code_eval", "llm_judge", ...), legacy configs their
 * config_type ("g_eval", "llm_as_judge"). Mirrors the server's
 * eval_default_judge_types endpoint.
 */
export function judge_type_from_config(
  config: { config_type?: string; properties?: unknown } | null | undefined,
): string | null {
  if (!config) return null
  const props = config.properties
  if (
    props &&
    typeof props === "object" &&
    "type" in props &&
    typeof (props as { type: unknown }).type === "string"
  ) {
    return (props as { type: string }).type
  }
  return config.config_type ?? null
}

/**
 * Display string for an eval's type: the judge that scores it, flavored with
 * what it checks.
 *
 * - Programmatic default judge: its label ("Code", "Exact Match", ...)
 * - LLM default judge: "LLM (Toxicity)" from the spec/template, or "LLM"
 * - No default judge yet: what the spec/template implies, else "None"
 *
 * True legacy evals (created before specs existed) get a "Legacy" prefix:
 * they have no spec, and either a V1 judge config or a template with no
 * default judge at all — states the current system never creates.
 */
export function eval_type_display(
  spec: Spec | null | undefined,
  eval_data: Eval | null | undefined,
  default_judge_type: string | null | undefined,
): string {
  if (default_judge_type && !LLM_JUDGE_TYPES.has(default_judge_type)) {
    if (ALL_V2_EVAL_TYPES.includes(default_judge_type as V2EvalType)) {
      return getV2EvalTypeMetadata(default_judge_type as V2EvalType).label
    }
    return default_judge_type
  }

  const spec_type = spec?.properties?.spec_type
  const flavor = spec_type
    ? formatSpecType(spec_type)
    : eval_data?.template
      ? TEMPLATE_FLAVORS[eval_data.template]
      : null

  const is_legacy =
    !spec &&
    (LEGACY_JUDGE_TYPES.has(default_judge_type ?? "") ||
      (!default_judge_type && !!eval_data?.template))
  const llm_label = is_legacy ? "Legacy LLM" : "LLM"

  if (default_judge_type) {
    return flavor ? `${llm_label} (${flavor})` : llm_label
  }

  // No default judge configured yet: report what the spec/template implies.
  if (spec_type === "appropriate_tool_use") {
    return getV2EvalTypeMetadata("tool_call_check").label
  }
  if (flavor) {
    return `${llm_label} (${flavor})`
  }
  return "None"
}
