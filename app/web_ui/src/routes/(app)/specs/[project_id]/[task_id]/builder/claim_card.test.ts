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

function fresh_verdict(): ClaimVerdict {
  return { agrees: null, why: "" }
}

describe("ClaimCard — the Disagree toggle", () => {
  it("flags a claim and opens the reason, then clears both on a second click", async () => {
    const verdict = fresh_verdict()
    const { container, getByText, queryByText } = render(ClaimCard, {
      props: { claim: claim(), verdict },
    })

    // There is no positive answer to give: an agreed claim carries no signal
    // downstream, so the card offers the flag alone.
    expect(queryByText("Correct")).toBeNull()
    expect(queryByText("Incorrect")).toBeNull()

    await fireEvent.click(getByText("Disagree"))
    expect(verdict.agrees).toBe(false)
    // The word holds still; only the selection styling moves.
    expect(getByText("Disagree").className).toContain("btn-error")
    const why = container.querySelector("textarea") as HTMLTextAreaElement
    expect(why).not.toBeNull()
    await fireEvent.input(why, { target: { value: "The window is real." } })
    expect(verdict.why).toBe("The window is real.")

    // Clicking again clears the flag and the reason under it, so the claim
    // goes back to carrying no signal at all rather than a stale one.
    await fireEvent.click(getByText("Disagree"))
    expect(verdict.agrees).toBeNull()
    expect(verdict.why).toBe("")
    expect(container.querySelector("textarea")).toBeNull()
    expect(getByText("Disagree").className).toContain("btn-outline")
  })
})

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
    expect(queryByText("View Full Trace")).toBeNull()
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
    await fireEvent.click(getByText("View Full Trace"))
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

    expect(queryByText("View Full Trace")).toBeNull()
  })
})

describe("ClaimCard — the blind final judgement", () => {
  it("records the label as agreement with the judge, inverting on a pass call", async () => {
    // The judge passed this one, so "Pass" is the agreeing label and "Fail"
    // is the contradiction — the mirror of a failed call. Agreement is
    // computed, never asked, so the card writes the same verdict either way.
    const verdict = fresh_verdict()
    const { container, getByText, queryByText } = render(ClaimCard, {
      props: {
        claim: claim({
          claim: "The bot answered from the policy page.",
          expected_result: "pass",
          evidence: "It linked the page [1].",
          citations: [
            { marker: 1, source: "output", from: "page", to: "page" },
          ],
        }),
        verdict,
        is_final_judgement: true,
        blind: true,
        judged_noun: "conversation",
      },
    })

    expect(getByText("Does this conversation pass?")).toBeTruthy()
    expect(queryByText("Correct")).toBeNull()

    await fireEvent.click(getByText("Pass"))
    expect(verdict.agrees).toBe(true)
    expect(container.querySelector("textarea")).toBeNull()

    await fireEvent.click(getByText("Fail"))
    expect(verdict.agrees).toBe(false)
    // The reveal names the judge's call, which is the opposite of the label
    // just given.
    expect(
      getByText("The judge disagrees. It scored this as a pass."),
    ).toBeTruthy()
    expect(
      (container.querySelector("textarea") as HTMLTextAreaElement).placeholder,
    ).toBe(
      "Describe why this fails. Detailed explanations will improve the judge.",
    )
  })
})

describe("ClaimCard — display only", () => {
  it("renders the claim as reading material, with no way to grade it", () => {
    // A disagreeing verdict is the state that renders both controls, so it is
    // the one that proves display_only drops them. The claim and its evidence
    // still render: this is the card as reading material for a surface that
    // takes the grade somewhere else.
    const verdict: ClaimVerdict = { agrees: false, why: "The window is real." }
    const { container, getByText, queryByText, queryByTitle } = render(
      ClaimCard,
      {
        props: { claim: claim(), verdict, display_only: true },
      },
    )

    expect(getByText("The agent stated a return window as fact.")).toBeTruthy()
    expect(queryByTitle("View in trace")).toBeTruthy()
    expect(queryByText("Disagree")).toBeNull()
    expect(container.querySelector("textarea")).toBeNull()
  })
})
