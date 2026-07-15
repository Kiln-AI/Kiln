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

function example_value(
  type: ScoreType,
  bool_expr: string,
  rating_expr: string,
): string {
  switch (type) {
    case "pass_fail":
    case "pass_fail_critical":
    case "custom":
      return `KilnEvalHelpers.pass_fail(${bool_expr})`
    case "five_star":
      return `KilnEvalHelpers.five_star(${rating_expr})`
    default:
      return assertNever(type)
  }
}

function build_example_return(
  scores: { key: string; type: ScoreType }[],
  bool_expr: string,
  rating_expr: string,
): string {
  if (scores.length === 1) {
    const s = scores[0]
    return `return {"${s.key}": ${example_value(s.type, bool_expr, rating_expr)}}`
  }
  const lines = scores.map(
    (s) =>
      `        "${s.key}": ${example_value(s.type, bool_expr, rating_expr)},`,
  )
  return `return {  # Adjust each score's logic for your eval\n${lines.join("\n")}\n    }`
}

function build_example_error_return(
  scores: { key: string; type: ScoreType }[],
): string {
  const entries = scores.map((s) => {
    switch (s.type) {
      case "pass_fail":
      case "pass_fail_critical":
      case "custom":
        return `"${s.key}": 0.0`
      case "five_star":
        return `"${s.key}": 1.0`
      default:
        return assertNever(s.type)
    }
  })
  return `return {${entries.join(", ")}}`
}

function normalize_scores(
  output_scores?: EvalOutputScore[],
): { key: string; type: ScoreType }[] {
  return output_scores && output_scores.length > 0
    ? output_scores.map((s) => ({
        key: string_to_json_key(s.name),
        type: s.type,
      }))
    : [{ key: "quality", type: "pass_fail" as ScoreType }]
}

// IMPORTANT: The code strings produced by generate_default_code and generate_examples
// are the exact snippets users run. They are mirrored byte-for-byte and executed through
// the real sandbox in libs/core/kiln_ai/adapters/eval/test_code_eval_samples.py to prove
// they stay valid. Do NOT change these strings without updating those mirrored fixtures.
export function generate_default_code(
  output_scores?: EvalOutputScore[],
): string {
  const scores = normalize_scores(output_scores)

  const returns_doc = build_returns_docstring(scores)
  const low_dict = build_return_dict(scores, "low")
  const passing_dict = build_return_dict(scores, "passing")

  return `def score(output, trace, reference_data, task_input):
    """Score the model output.

    Parameters are optional and order-independent — declare only the ones you need.

    Args:
        output: The model's final output string.
        trace: List of message dicts from the conversation.
        reference_data: Dict of reference/expected data (if any).
        task_input: The original task input string.

    Returns:
        ${returns_doc}
    """
    if not output:
        return ${low_dict}
    return ${passing_dict}
`
}

// IMPORTANT: See the note on generate_default_code above. These example snippets are
// mirrored byte-for-byte and executed in test_code_eval_samples.py. Do NOT change them
// without updating those mirrored fixtures.
export function generate_examples(
  output_scores?: EvalOutputScore[],
): { label: string; code: string }[] {
  const scores = normalize_scores(output_scores)
  const parse_json_return = build_example_return(
    scores,
    "passed",
    "5 if passed else 1",
  )
  const parse_json_error = build_example_error_return(scores)
  const tool_return = build_example_return(
    scores,
    "used_search",
    "max(min(call_count, 5), 1)",
  )
  const domain_return = build_example_return(
    scores,
    "contains",
    "5 if word_count < 50 else 3 if word_count < 150 else 1",
  )

  return [
    {
      label: "Parse JSON",
      code: `import json
from kiln_ai.adapters.eval.eval_helpers import KilnEvalHelpers

def score(output):
    """Check if the output is valid JSON with required fields."""
    try:
        data = json.loads(output)
    except (json.JSONDecodeError, TypeError):
        ${parse_json_error}

    required = ["name", "description"]
    has_all = all(k in data for k in required)
    passed = isinstance(data, dict) and has_all
    ${parse_json_return}
`,
    },
    {
      label: "Check tool usage",
      code: `from kiln_ai.adapters.eval.eval_helpers import KilnEvalHelpers

def score(trace):
    """Verify the model used the expected tools."""
    tool_calls = KilnEvalHelpers.get_tool_calls(trace)
    used_search = KilnEvalHelpers.has_tool_call(tool_calls, "search")
    call_count = KilnEvalHelpers.count_tool_calls(tool_calls, "search")

    ${tool_return}
`,
    },
    {
      label: "Domain-specific grading",
      code: `from kiln_ai.adapters.eval.eval_helpers import KilnEvalHelpers

def score(output, reference_data):
    """Grade output against domain-specific criteria."""
    expected = (reference_data or {}).get("expected_answer", "")

    contains = KilnEvalHelpers.assert_contains(output, expected) if expected else True

    word_count = len(output.split())

    ${domain_return}
`,
    },
  ]
}
