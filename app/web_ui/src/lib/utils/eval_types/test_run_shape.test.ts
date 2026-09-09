import { describe, it, expect } from "vitest"
import { validate_result_shape } from "./test_run_shape"
import type { EvalOutputScore } from "$lib/types"

function score(name: string): EvalOutputScore {
  return { name, type: "pass_fail", instruction: null } as EvalOutputScore
}

describe("validate_result_shape", () => {
  it("passes when returned keys exactly match", () => {
    expect(
      validate_result_shape({ accuracy: 1.0 }, [score("Accuracy")]),
    ).toEqual({ valid: true, message: null })
  })

  it("reports missing keys", () => {
    const result = validate_result_shape({ other: 1.0 }, [score("Accuracy")])
    expect(result.valid).toBe(false)
    expect(result.message).toContain("Missing expected scores: accuracy")
  })

  it("reports unexpected extra keys, even when the expected key is present", () => {
    // e.g. code returning both the placeholder and the right key.
    const result = validate_result_shape(
      { accuracy: 1.0, score_name_placeholder: 1.0 },
      [score("Accuracy")],
    )
    expect(result.valid).toBe(false)
    expect(result.message).toContain(
      "Unexpected scores: score_name_placeholder",
    )
  })

  it("is permissive when there are no scores or no expected scores", () => {
    expect(validate_result_shape(undefined, [score("A")]).valid).toBe(true)
    expect(validate_result_shape({ a: 1 }, []).valid).toBe(true)
    expect(validate_result_shape({ a: 1 }, undefined).valid).toBe(true)
  })
})
