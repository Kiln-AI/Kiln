import { string_to_json_key } from "$lib/utils/json_schema_editor/json_schema_templates"
import type { EvalOutputScore } from "$lib/types"
import { assertNever } from "$lib/utils/exhaustive"

type ScoreType = EvalOutputScore["type"]

function score_description(type: ScoreType, key: string): string {
  switch (type) {
    case "pass_fail":
      return `${key}: return 0.0 for Fail or 1.0 for Pass`
    case "pass_fail_critical":
      return `${key}: return -1.0 for a critical failure, 0.0 for Fail, or 1.0 for Pass`
    case "five_star":
      return `${key}: return a 1-5 star rating (1.0, 2.0, 3.0, 4.0, or 5.0)`
    case "custom":
      return `${key}: return 0.0 for Fail or 1.0 for Pass`
    default:
      return assertNever(type)
  }
}

function passing_value(type: ScoreType): string {
  switch (type) {
    case "five_star":
      return "5.0"
    case "pass_fail":
    case "pass_fail_critical":
    case "custom":
      return "1.0"
    default:
      return assertNever(type)
  }
}

function low_value(type: ScoreType): string {
  switch (type) {
    case "five_star":
      return "1.0"
    case "pass_fail":
    case "pass_fail_critical":
    case "custom":
      return "0.0"
    default:
      return assertNever(type)
  }
}

function build_returns_docstring(
  scores: { key: string; type: ScoreType }[],
): string {
  if (scores.length === 1) {
    const s = scores[0]
    return score_description(s.type, s.key)
  }
  const lines = scores.map((s) => `      - ${score_description(s.type, s.key)}`)
  return `A dictionary of score names to scores:\n${lines.join("\n")}`
}

function build_return_dict(
  scores: { key: string; type: ScoreType }[],
  variant: "passing" | "low",
): string {
  const fn = variant === "passing" ? passing_value : low_value
  const entries = scores.map((s) => `"${s.key}": ${fn(s.type)}`)
  return `{${entries.join(", ")}}`
}

export function generate_default_code(
  output_scores?: EvalOutputScore[],
): string {
  const scores =
    output_scores && output_scores.length > 0
      ? output_scores.map((s) => ({
          key: string_to_json_key(s.name),
          type: s.type,
        }))
      : [{ key: "quality", type: "pass_fail" as ScoreType }]

  const returns_doc = build_returns_docstring(scores)
  const low_dict = build_return_dict(scores, "low")
  const passing_dict = build_return_dict(scores, "passing")

  return `def score(output, trace, reference_data, task_input, kiln):
    """Score the model output.

    Args:
        output: The model's final output string.
        trace: List of message dicts from the conversation.
        reference_data: Dict of reference/expected data (if any).
        task_input: The original task input string.
        kiln: KilnEvalHelpers with utility methods.

    Returns:
        ${returns_doc}
    """
    if not output:
        return ${low_dict}
    return ${passing_dict}
`
}
