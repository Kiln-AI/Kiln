import { describe, it, expect } from "vitest"
import { judge_reasoning } from "./judge_reasoning"

describe("judge_reasoning", () => {
  it("reads the reasoning key", () => {
    expect(judge_reasoning({ reasoning: "Clear and correct." })).toBe(
      "Clear and correct.",
    )
  })

  it("falls back to the chain_of_thought key", () => {
    expect(judge_reasoning({ chain_of_thought: "Step by step." })).toBe(
      "Step by step.",
    )
  })

  it("prefers reasoning when both keys are present", () => {
    expect(
      judge_reasoning({ reasoning: "Reasoning.", chain_of_thought: "Steps." }),
    ).toBe("Reasoning.")
  })

  it("is null when the run saved no reasoning", () => {
    const no_reasoning: Array<Record<string, string> | null | undefined> = [
      null,
      undefined,
      {},
      { other: "x" },
      { reasoning: "" },
    ]
    for (const outputs of no_reasoning) {
      expect(judge_reasoning(outputs)).toBeNull()
    }
  })
})
