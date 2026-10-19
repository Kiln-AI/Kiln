import { describe, it, expect } from "vitest"
import { judge_check_description } from "./judge_check_description"

describe("judge_check_description", () => {
  it("returns null for LLM judges, malformed, and unknown properties", () => {
    expect(judge_check_description(null)).toBe(null)
    expect(judge_check_description(undefined)).toBe(null)
    expect(judge_check_description("not an object")).toBe(null)
    expect(judge_check_description({})).toBe(null)
    expect(
      judge_check_description({ type: "llm_judge", prompt_template: "x" }),
    ).toBe(null)
    expect(judge_check_description({ type: "g_eval" })).toBe(null)
  })

  it("describes exact match against a static value", () => {
    const desc = judge_check_description({
      type: "exact_match",
      expected_value: "XYZ",
      case_sensitive: true,
    })
    expect(desc).toBe(
      "This eval's judge checks that the model's final response exactly matches \"XYZ\".",
    )
  })

  it("describes case-insensitive exact match against reference data", () => {
    const desc = judge_check_description({
      type: "exact_match",
      reference_key: "answer",
      case_sensitive: false,
    })
    expect(desc).toContain('reference data ("answer")')
    expect(desc).toContain("case-insensitively")
  })

  it("uses the Jinja expression as the source when set", () => {
    const desc = judge_check_description({
      type: "exact_match",
      expected_value: "42",
      value_expression: "(final_message | fromjson).count",
      case_sensitive: true,
    })
    expect(desc).toContain("the value of `(final_message | fromjson).count`")
    expect(desc).not.toContain("final response exactly")
  })

  it("describes pattern match in both modes", () => {
    expect(
      judge_check_description({
        type: "pattern_match",
        pattern: "^[A-Z]+$",
        mode: "must_match",
      }),
    ).toContain("matches the regular expression /^[A-Z]+$/")
    expect(
      judge_check_description({
        type: "pattern_match",
        pattern: "DRAFT",
        mode: "must_not_match",
      }),
    ).toContain("does not match the regular expression /DRAFT/")
  })

  it("describes contains in both modes", () => {
    expect(
      judge_check_description({
        type: "contains",
        substring: "thanks",
        mode: "must_contain",
        case_sensitive: false,
      }),
    ).toBe(
      "This eval's judge checks that the model's final response contains \"thanks\", case-insensitively.",
    )
    expect(
      judge_check_description({
        type: "contains",
        substring: "sorry",
        mode: "must_not_contain",
        case_sensitive: true,
      }),
    ).toContain('does not contain "sorry"')
  })

  it("describes set check with an inline expected set", () => {
    const desc = judge_check_description({
      type: "set_check",
      expected_set: ["a", "b"],
      mode: "equal",
    })
    expect(desc).toContain('is exactly equal to "a", "b"')
  })

  it("describes step count bounds", () => {
    expect(
      judge_check_description({
        type: "step_count_check",
        count_type: "tool_calls",
        min_count: 1,
        max_count: 3,
      }),
    ).toContain("between 1 and 3 tool calls")
    expect(
      judge_check_description({
        type: "step_count_check",
        count_type: "turns",
        min_count: 2,
      }),
    ).toContain("at least 2 conversation turns")
  })

  it("describes tool call check modes and unexpected-tool failure", () => {
    expect(
      judge_check_description({
        type: "tool_call_check",
        expected_tools: [{ tool_name: "search" }, { tool_name: "lookup" }],
        match_mode: "ordered",
        on_unexpected_tools: "fail",
      }),
    ).toBe(
      'This eval\'s judge checks that the run called these tools in order: "search", "lookup". Calls to any other tool fail the eval.',
    )
    expect(
      judge_check_description({
        type: "tool_call_check",
        expected_tools: [{ tool_name: "search" }],
        match_mode: "never",
        on_unexpected_tools: "ignore",
      }),
    ).toContain('called none of these tools: "search"')
  })

  it("embeds the code for code evals", () => {
    const desc = judge_check_description({
      type: "code_eval",
      code: 'def score(output):\n    return {"quality": 1.0}',
    })
    expect(desc).toContain("custom Python function below")
    expect(desc).toContain("```python")
    expect(desc).toContain('return {"quality": 1.0}')
  })
})
