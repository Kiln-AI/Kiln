// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest"
import { render, fireEvent, cleanup } from "@testing-library/svelte"
import ClaimCard from "./claim_card.svelte"
import type { Claim, ClaimVerdict } from "./claim_evidence"

afterEach(() => {
  cleanup()
})

function claim(overrides: Partial<Claim> = {}): Claim {
  return {
    claim: "The agent stated a return window as fact.",
    expected_result: "fail",
    evidence: "The reply gives 30 days [1].",
    citations: [
      { marker: 1, source: "output", from: "30 days", to: "30 days" },
    ],
    ...overrides,
  }
}

describe("ClaimCard — flipping to Correct", () => {
  it("clears a reason typed while disagreeing", async () => {
    // A verdict left mid-disagreement carries a reason; flipping to Correct
    // hides the reason box, so the stale text must not ride the agree grade.
    const verdict: ClaimVerdict = { agrees: false, why: "The window is real." }
    const { getByText } = render(ClaimCard, {
      props: { claim: claim(), verdict },
    })

    await fireEvent.click(getByText("Correct"))

    expect(verdict.agrees).toBe(true)
    expect(verdict.why).toBe("")
  })

  it("keeps the reason while still disagreeing", async () => {
    const verdict: ClaimVerdict = { agrees: false, why: "The window is real." }
    const { getByText } = render(ClaimCard, {
      props: { claim: claim(), verdict },
    })

    // Re-clicking Incorrect must not wipe an in-progress reason.
    await fireEvent.click(getByText("Incorrect"))

    expect(verdict.agrees).toBe(false)
    expect(verdict.why).toBe("The window is real.")
  })
})
