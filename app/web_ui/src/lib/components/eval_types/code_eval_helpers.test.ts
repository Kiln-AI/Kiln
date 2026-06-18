import { describe, it, expect } from "vitest"
import type { EvalOutputScore } from "$lib/types"
import { generate_default_code } from "./code_eval_helpers"

function make_score(
  name: string,
  type: EvalOutputScore["type"],
): EvalOutputScore {
  return { name, type, instruction: null }
}

describe("generate_default_code", () => {
  it("produces a fallback template when output_scores is undefined", () => {
    const code = generate_default_code(undefined)
    expect(code).toContain('"quality"')
    expect(code).toContain("def score(")
    expect(code).toContain('return {"quality": 0.0}')
    expect(code).toContain('return {"quality": 1.0}')
  })

  it("produces a fallback template when output_scores is empty", () => {
    const code = generate_default_code([])
    expect(code).toContain('"quality"')
  })

  describe("single pass_fail score", () => {
    const scores = [make_score("Accuracy", "pass_fail")]

    it("uses json_key for the score name", () => {
      const code = generate_default_code(scores)
      expect(code).toContain('"accuracy"')
      expect(code).not.toContain('"quality"')
    })

    it("documents return 0.0 for Fail or 1.0 for Pass", () => {
      const code = generate_default_code(scores)
      expect(code).toContain("return 0.0 for Fail or 1.0 for Pass")
    })

    it("returns 0.0 for low and 1.0 for passing", () => {
      const code = generate_default_code(scores)
      expect(code).toContain('{"accuracy": 0.0}')
      expect(code).toContain('{"accuracy": 1.0}')
    })
  })

  describe("single pass_fail_critical score", () => {
    const scores = [make_score("Safety", "pass_fail_critical")]

    it("documents the -1.0/0.0/1.0 range", () => {
      const code = generate_default_code(scores)
      expect(code).toContain(
        "return -1.0 for a critical failure, 0.0 for Fail, or 1.0 for Pass",
      )
    })

    it("returns 0.0 for low and 1.0 for passing", () => {
      const code = generate_default_code(scores)
      expect(code).toContain('{"safety": 0.0}')
      expect(code).toContain('{"safety": 1.0}')
    })
  })

  describe("single five_star score", () => {
    const scores = [make_score("Quality", "five_star")]

    it("documents the 1-5 star range", () => {
      const code = generate_default_code(scores)
      expect(code).toContain(
        "return a 1-5 star rating (1.0, 2.0, 3.0, 4.0, or 5.0)",
      )
    })

    it("uses 1.0 for low (NOT 0.0 which is invalid for five_star)", () => {
      const code = generate_default_code(scores)
      expect(code).toContain('{"quality": 1.0}')
      expect(code).not.toContain('"quality": 0.0')
    })

    it("uses 5.0 for passing", () => {
      const code = generate_default_code(scores)
      expect(code).toContain('{"quality": 5.0}')
    })
  })

  describe("multi-output scores", () => {
    const scores = [
      make_score("Accuracy", "pass_fail"),
      make_score("Overall Rating", "five_star"),
      make_score("Safety Check", "pass_fail_critical"),
    ]

    it("builds a bulleted Returns docstring for multiple scores", () => {
      const code = generate_default_code(scores)
      expect(code).toContain("A dictionary of score names to scores:")
      expect(code).toContain("- accuracy: return 0.0 for Fail or 1.0 for Pass")
      expect(code).toContain(
        "- overall_rating: return a 1-5 star rating (1.0, 2.0, 3.0, 4.0, or 5.0)",
      )
      expect(code).toContain(
        "- safety_check: return -1.0 for a critical failure, 0.0 for Fail, or 1.0 for Pass",
      )
    })

    it("uses correct per-type low values in the dict", () => {
      const code = generate_default_code(scores)
      expect(code).toContain(
        '{"accuracy": 0.0, "overall_rating": 1.0, "safety_check": 0.0}',
      )
    })

    it("uses correct per-type passing values in the dict", () => {
      const code = generate_default_code(scores)
      expect(code).toContain(
        '{"accuracy": 1.0, "overall_rating": 5.0, "safety_check": 1.0}',
      )
    })

    it("contains all json_keys in the return dicts", () => {
      const code = generate_default_code(scores)
      expect(code).toContain('"accuracy"')
      expect(code).toContain('"overall_rating"')
      expect(code).toContain('"safety_check"')
    })
  })

  it("preserves the function signature and Args docstring", () => {
    const scores = [make_score("Test", "pass_fail")]
    const code = generate_default_code(scores)
    expect(code).toContain(
      "def score(output, trace, reference_data, task_input, kiln):",
    )
    expect(code).toContain("Args:")
    expect(code).toContain("output: The model's final output string.")
    expect(code).toContain("kiln: KilnEvalHelpers with utility methods.")
  })

  describe("custom score type", () => {
    it("treats custom like pass_fail (custom is rejected by the backend for evals but handled gracefully)", () => {
      const scores = [make_score("Custom Score", "custom")]
      const code = generate_default_code(scores)
      expect(code).toContain('"custom_score": 0.0')
      expect(code).toContain('"custom_score": 1.0')
      expect(code).toContain("return 0.0 for Fail or 1.0 for Pass")
    })
  })
})
