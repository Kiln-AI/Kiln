/**
 * Static prompt builder: a human-readable description of what a programmatic
 * (deterministic) judge config checks, extrapolated from its typed properties.
 *
 * Used to prefill synthetic data generation guidance for judge-only evals,
 * which have no spec or template to derive a prompt from — the judge config
 * is the eval's entire definition. Mirrors the per-type summaries the eval
 * config page renders, as plain text an LLM planner can read.
 *
 * Returns null for LLM judges (their prompt/instructions are the guidance
 * source) and for unrecognized or malformed properties.
 */
export function judge_check_description(properties: unknown): string | null {
  const props = properties as Record<string, unknown> | null | undefined
  if (!props || typeof props !== "object") {
    return null
  }
  switch (props["type"]) {
    case "exact_match":
      return exact_match_description(props)
    case "pattern_match":
      return pattern_match_description(props)
    case "contains":
      return contains_description(props)
    case "set_check":
      return set_check_description(props)
    case "step_count_check":
      return step_count_description(props)
    case "tool_call_check":
      return tool_call_check_description(props)
    case "code_eval":
      return code_eval_description(props)
    default:
      return null
  }
}

/** The judged value: the final response, or a custom Jinja expression. */
function source_label(props: Record<string, unknown>): string {
  const expr = props["value_expression"]
  if (typeof expr === "string" && expr.trim()) {
    return `the value of \`${expr}\` (a Jinja expression over the model's output)`
  }
  return "the model's final response"
}

function case_part(props: Record<string, unknown>): string {
  return props["case_sensitive"] === false ? ", case-insensitively" : ""
}

function exact_match_description(props: Record<string, unknown>): string {
  const expected =
    typeof props["expected_value"] === "string"
      ? `"${props["expected_value"]}"`
      : typeof props["reference_key"] === "string" && props["reference_key"]
        ? `the expected value stored in each dataset item's reference data ("${props["reference_key"]}")`
        : "an expected value"
  return `This eval's judge checks that ${source_label(props)} exactly matches ${expected}${case_part(props)}.`
}

function pattern_match_description(props: Record<string, unknown>): string {
  const mode = props["mode"] === "must_not_match" ? "does not match" : "matches"
  return `This eval's judge checks that ${source_label(props)} ${mode} the regular expression /${String(props["pattern"] ?? "")}/.`
}

function contains_description(props: Record<string, unknown>): string {
  const mode =
    props["mode"] === "must_not_contain" ? "does not contain" : "contains"
  const target =
    typeof props["substring"] === "string"
      ? `"${props["substring"]}"`
      : typeof props["reference_key"] === "string" && props["reference_key"]
        ? `the value stored in each dataset item's reference data ("${props["reference_key"]}")`
        : "a value"
  return `This eval's judge checks that ${source_label(props)} ${mode} ${target}${case_part(props)}.`
}

function set_check_description(props: Record<string, unknown>): string {
  const mode_labels: Record<string, string> = {
    subset: "is a subset of",
    superset: "is a superset of",
    equal: "is exactly equal to",
  }
  const mode = mode_labels[String(props["mode"])] ?? "is compared against"
  const expected = Array.isArray(props["expected_set"])
    ? props["expected_set"].map((v) => `"${String(v)}"`).join(", ")
    : typeof props["reference_key"] === "string" && props["reference_key"]
      ? `the expected set stored in each dataset item's reference data ("${props["reference_key"]}")`
      : "an expected set"
  return `This eval's judge parses ${source_label(props)} as a set of values and checks that it ${mode} ${expected}.`
}

function step_count_description(props: Record<string, unknown>): string {
  const kind_labels: Record<string, string> = {
    tool_calls: "tool calls",
    model_responses: "model responses",
    turns: "conversation turns",
  }
  const kind = kind_labels[String(props["count_type"])] ?? "steps"
  const min = typeof props["min_count"] === "number" ? props["min_count"] : null
  const max = typeof props["max_count"] === "number" ? props["max_count"] : null
  let bound = "a bounded number of"
  if (min !== null && max !== null) {
    bound = `between ${min} and ${max}`
  } else if (min !== null) {
    bound = `at least ${min}`
  } else if (max !== null) {
    bound = `at most ${max}`
  }
  return `This eval's judge checks that the run used ${bound} ${kind}.`
}

function tool_call_check_description(props: Record<string, unknown>): string {
  const expected = Array.isArray(props["expected_tools"])
    ? props["expected_tools"]
        .map((t) =>
          t && typeof t === "object"
            ? (t as { tool_name?: unknown }).tool_name
            : undefined,
        )
        .filter((n): n is string => typeof n === "string" && n.length > 0)
        .map((n) => `"${n}"`)
        .join(", ")
    : ""
  const tools = expected || "the expected tools"
  const mode_sentences: Record<string, string> = {
    all: `This eval's judge checks that the run called all of these tools: ${tools}.`,
    any: `This eval's judge checks that the run called at least one of these tools: ${tools}.`,
    ordered: `This eval's judge checks that the run called these tools in order: ${tools}.`,
    never: `This eval's judge checks that the run called none of these tools: ${tools}.`,
  }
  let description =
    mode_sentences[String(props["match_mode"])] ?? mode_sentences["all"]
  if (props["on_unexpected_tools"] === "fail") {
    description += " Calls to any other tool fail the eval."
  }
  return description
}

function code_eval_description(props: Record<string, unknown>): string {
  const code = typeof props["code"] === "string" ? props["code"].trim() : ""
  if (!code) {
    return "This eval's judge scores each run with a custom Python function."
  }
  return `This eval's judge scores each run with the custom Python function below:

\`\`\`python
${code}
\`\`\``
}
