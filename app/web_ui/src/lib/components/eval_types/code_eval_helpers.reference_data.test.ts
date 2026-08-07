import { describe, it, expect, vi } from "vitest"
// Pins the behavior restored by flipping SHOW_REFERENCE_DATA_UI back on, so the
// gated code paths don't rot while reference data is hidden from the UI.
vi.mock("$lib/utils/eval_types/reference_data_ui", () => ({
  SHOW_REFERENCE_DATA_UI: true,
}))

import type { EvalOutputScore } from "$lib/types"
import { generate_default_code, generate_examples } from "./code_eval_helpers"

function make_score(
  name: string,
  type: EvalOutputScore["type"],
): EvalOutputScore {
  return { name, type, instruction: null }
}

describe("generate_default_code (reference data shown)", () => {
  it("preserves the function signature and Args docstring", () => {
    const scores = [make_score("Test", "pass_fail")]
    const code = generate_default_code(scores)
    expect(code).toContain(
      "def score(output, trace, reference_data, task_input):",
    )
    expect(code).toContain("Args:")
    expect(code).toContain("output: The model's final output string.")
    expect(code).not.toContain("kiln:")
  })

  it("documents the reference_data parameter", () => {
    const code = generate_default_code(undefined)
    expect(code).toContain(
      "reference_data: Dict of reference/expected data (if any).",
    )
  })

  it("still builds the score dicts from output_scores", () => {
    const scores = [make_score("Accuracy", "pass_fail")]
    const code = generate_default_code(scores)
    expect(code).toContain('{"accuracy": 0.0}')
    expect(code).toContain('{"accuracy": 1.0}')
  })
})

describe("generate_examples Domain-specific grading (reference data shown)", () => {
  it("reads expected_answer from reference_data", () => {
    const examples = generate_examples(undefined)
    expect(examples[2].label).toBe("Domain-specific grading")
    expect(examples[2].code).toContain("def score(output, reference_data):")
    expect(examples[2].code).toContain(
      'expected = (reference_data or {}).get("expected_answer", "")',
    )
  })

  it("guards assert_contains with if expected else True", () => {
    const examples = generate_examples(undefined)
    expect(examples[2].code).toContain("if expected else True")
  })

  it("uses contains as the bool expression", () => {
    const examples = generate_examples(undefined)
    expect(examples[2].code).toContain("KilnEvalHelpers.pass_fail(contains)")
  })

  it("uses word_count-based rating expression for five_star", () => {
    const scores = [make_score("R", "five_star")]
    const examples = generate_examples(scores)
    expect(examples[2].code).toContain(
      "KilnEvalHelpers.five_star(5 if word_count < 50 else 3 if word_count < 150 else 1)",
    )
  })

  it("leaves the other two examples free of reference data", () => {
    const examples = generate_examples(undefined)
    expect(examples[0].code).not.toContain("reference_data")
    expect(examples[1].code).not.toContain("reference_data")
  })
})
