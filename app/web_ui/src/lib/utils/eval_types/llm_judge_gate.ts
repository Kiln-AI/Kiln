import type { Eval } from "$lib/types"

/**
 * Whether default judge steps can be derived for this eval.
 *
 * Mirrors the server's llm_judge_steps_derivable: a spec always derives;
 * without one, only a template with derivable data does. Evals with neither
 * (created with a programmatic judge) show the Evaluation Instructions steps
 * editor instead, whose text is bound to {{ judge_instructions }} in the
 * judge prompt.
 */
export function llm_judge_steps_derivable(
  evaluator: Eval | null | undefined,
  has_spec: boolean,
): boolean {
  if (has_spec) {
    return true
  }
  const template = evaluator?.template
  switch (template) {
    case "toxicity":
    case "bias":
    case "maliciousness":
    case "factual_correctness":
    case "jailbreak":
    case "kiln_requirements":
    case "rag":
      return true
    case "kiln_issue":
      return !!evaluator?.template_properties?.["issue_prompt"]
    case "tool_call":
      return !!evaluator?.template_properties?.["tool_function_name"]
    default:
      return false
  }
}
