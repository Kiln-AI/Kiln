// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from "vitest"
import { render, fireEvent, cleanup } from "@testing-library/svelte"
import ClaimCard from "./claim_card.svelte"
import type { Citation, Claim, ClaimVerdict } from "./claim_evidence"

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

function fresh_verdict(): ClaimVerdict {
  return { agrees: null, why: "" }
}

describe("ClaimCard — final judgement evidence", () => {
  it("renders clickable [n] chips for its evidence and no trace fallback", async () => {
    // With the server-guaranteed inline citation, the final card's evidence
    // sentence tokenizes to a clickable chip that opens the trace at the span.
    let cited: Citation | undefined
    const on_view_trace = vi.fn()
    const { getByTitle, queryByText } = render(ClaimCard, {
      props: {
        claim: claim({
          claim: "The bot resolved the issue.",
          evidence: "It confirmed the fix [1].",
          citations: [{ marker: 1, source: "output", from: "fix", to: "fix" }],
        }),
        verdict: fresh_verdict(),
        is_final_judgement: true,
        on_cite: (c: Citation) => (cited = c),
        on_view_trace,
      },
    })

    await fireEvent.click(getByTitle("View in trace"))

    expect(cited?.marker).toBe(1)
    // A resolvable chip is the trace path, so no fallback link is offered.
    expect(queryByText("View full trace")).toBeNull()
    expect(on_view_trace).not.toHaveBeenCalled()
  })

  it("renders both the reason and the evidence lines when they differ", () => {
    const { getByText } = render(ClaimCard, {
      props: {
        claim: claim({
          claim: "The bot resolved the issue.",
          evidence: "It confirmed the fix [1].",
          citations: [{ marker: 1, source: "output", from: "fix", to: "fix" }],
        }),
        verdict: fresh_verdict(),
        is_final_judgement: true,
      },
    })

    expect(getByText("The bot resolved the issue.")).toBeTruthy()
    // Evidence renders as its own line (text split around the [1] chip).
    expect(getByText(/It confirmed the fix/)).toBeTruthy()
  })

  it("dedupes when the reason and evidence are the same sentence", () => {
    // Same text in both slots must render once — through the tokenizer, so the
    // chip stays clickable — not printed twice.
    const same = "It confirmed the fix [1]."
    const { getAllByText } = render(ClaimCard, {
      props: {
        claim: claim({
          claim: same,
          evidence: same,
          citations: [{ marker: 1, source: "output", from: "fix", to: "fix" }],
        }),
        verdict: fresh_verdict(),
        is_final_judgement: true,
      },
    })

    // Only one rendering of the shared sentence's text.
    expect(getAllByText(/It confirmed the fix/)).toHaveLength(1)
  })

  it("offers a trace fallback when it has no resolvable citation", async () => {
    // Legacy pre-guarantee data: evidence without any [n]. The card surfaces a
    // quiet link that opens the trace via the caller's hook.
    const on_view_trace = vi.fn()
    const { getByText, queryByTitle } = render(ClaimCard, {
      props: {
        claim: claim({
          claim: "The bot failed.",
          evidence: "It gave the wrong return window.",
          citations: [],
        }),
        verdict: fresh_verdict(),
        is_final_judgement: true,
        on_view_trace,
      },
    })

    expect(queryByTitle("View in trace")).toBeNull()
    await fireEvent.click(getByText("View full trace"))
    expect(on_view_trace).toHaveBeenCalledTimes(1)
  })

  it("shows no trace fallback on non-final cards", () => {
    // The fallback is a final-judgement affordance only; a non-final card
    // never renders the link even without a resolvable citation.
    const { queryByText } = render(ClaimCard, {
      props: {
        claim: claim({ evidence: "No citation here.", citations: [] }),
        verdict: fresh_verdict(),
      },
    })

    expect(queryByText("View full trace")).toBeNull()
  })
})
