// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest"
import { render, fireEvent, cleanup } from "@testing-library/svelte"
import ClaimCard from "./claim_card.svelte"
import type { Citation, Claim, ClaimVerdict } from "./claim_evidence"

afterEach(() => {
  cleanup()
})

function claim(overrides: Partial<Claim> = {}): Claim {
  return {
    text: "The agent stated a return window as fact [1]. Disagree if the window is documented.",
    citations: [
      { marker: 1, source: "output", from: "30 days", to: "30 days" },
    ],
    is_verdict: false,
    ...overrides,
  }
}

function fresh_verdict(): ClaimVerdict {
  return { agrees: null, why: "" }
}

function by_id<T extends HTMLElement>(container: HTMLElement, id: string): T {
  const found = container.querySelector<T>(`#${id}`)
  if (!found) throw new Error(`no element with id ${id}`)
  return found
}

describe("ClaimCard — Agree / Disagree", () => {
  it("numbers the claim and records Agree without a reason box", async () => {
    const verdict = fresh_verdict()
    const { container } = render(ClaimCard, {
      props: { claim: claim(), index: 2, verdict, triggers_refine: false },
    })

    // The number is the one the builder's own cross-references use.
    expect(by_id(container, "claim-card-2").textContent).toContain("#3")

    await fireEvent.click(by_id(container, "claim-agree-2"))
    expect(verdict.agrees).toBe(true)
    expect(by_id(container, "claim-agree-2").className).toContain("btn-success")
    expect(container.querySelector("#claim-why-2")).toBeNull()
  })

  it("Disagree opens the required reason box, and Agree drops the reason again", async () => {
    const verdict = fresh_verdict()
    const { container } = render(ClaimCard, {
      props: { claim: claim(), index: 0, verdict, triggers_refine: false },
    })

    await fireEvent.click(by_id(container, "claim-disagree-0"))
    expect(verdict.agrees).toBe(false)
    expect(by_id(container, "claim-disagree-0").className).toContain(
      "btn-error",
    )
    const why = by_id<HTMLTextAreaElement>(container, "claim-why-0")
    expect(why.placeholder).toBe(
      "Why is this wrong? Your reason helps improve the eval.",
    )
    // Required: flagged as an error until a reason is typed.
    expect(why.className).toContain("textarea-error")
    await fireEvent.input(why, { target: { value: "The window is real." } })
    expect(verdict.why).toBe("The window is real.")
    expect(why.className).not.toContain("textarea-error")

    // Switching to Agree hides the box and clears the reason typed under
    // Disagree, so nothing stale rides the agree grade into the record.
    await fireEvent.click(by_id(container, "claim-agree-0"))
    expect(verdict).toEqual({ agrees: true, why: "" })
    expect(container.querySelector("#claim-why-0")).toBeNull()
  })
})

describe("ClaimCard — what a disagreement will do", () => {
  // The rule is stated on the card because it decides what the reviewer's
  // click is worth: only a verdict (or a claim the builder tagged as a
  // possible judge error) refines the judge, and everything else is a note.
  const REFINES = "This will refine the judge."
  const NOTE = "Saved as a note. This does not refine the judge."

  function note_line(container: HTMLElement): string | null {
    const found = container.querySelector("[data-refine-consequence]")
    return found?.textContent?.trim() ?? null
  }

  it("promises a note on an ordinary claim's disagreement", async () => {
    const { container } = render(ClaimCard, {
      props: {
        claim: claim(),
        index: 0,
        verdict: fresh_verdict(),
        triggers_refine: false,
      },
    })
    await fireEvent.click(by_id(container, "claim-disagree-0"))
    expect(note_line(container)).toBe(NOTE)
  })

  it("promises a refine on a trigger claim's disagreement", async () => {
    const { container } = render(ClaimCard, {
      props: {
        claim: claim(),
        index: 0,
        verdict: fresh_verdict(),
        triggers_refine: true,
      },
    })
    await fireEvent.click(by_id(container, "claim-disagree-0"))
    expect(note_line(container)).toBe(REFINES)
  })

  it("says nothing on agreement, or before the claim is graded", async () => {
    // Agreeing changes nothing about the judge, so there is nothing to
    // acknowledge; an ungraded claim has no consequence to state yet.
    const { container } = render(ClaimCard, {
      props: {
        claim: claim(),
        index: 0,
        verdict: fresh_verdict(),
        triggers_refine: false,
      },
    })
    expect(note_line(container)).toBeNull()
    await fireEvent.click(by_id(container, "claim-agree-0"))
    expect(note_line(container)).toBeNull()
  })
})

describe("ClaimCard — the claim text", () => {
  it("chips a [n] that has a citation and leaves one without as plain text", async () => {
    let cited: Citation | undefined
    const { container, getAllByTitle } = render(ClaimCard, {
      props: {
        claim: claim({
          text: "The reply gives 30 days [1] and cites item [2] of the policy.",
        }),
        index: 0,
        verdict: fresh_verdict(),
        triggers_refine: false,
        on_cite: (c: Citation) => (cited = c),
      },
    })

    // Exactly one chip: [1] resolves, [2] is a number the model quoted out
    // of the trace and must not become a dead button.
    const chips = getAllByTitle("View in trace")
    expect(chips.map((c) => c.textContent)).toEqual(["[1]"])
    expect(container.textContent).toContain("cites item [2] of the policy")

    await fireEvent.click(chips[0])
    expect(cited?.marker).toBe(1)
  })

  it("renders the Note paragraph apart and muted, with We suggest inline", () => {
    const { container } = render(ClaimCard, {
      props: {
        claim: claim({
          text: "The joke retells a known one [1]. We suggest 'Agree', keeping this eval focused on safety.\n\nNote: the rubric never mentions originality.",
        }),
        index: 0,
        verdict: fresh_verdict(),
        triggers_refine: false,
      },
    })

    const note = container.querySelector("[data-claim-note]")
    expect(note?.textContent?.trim()).toBe(
      "Note: the rubric never mentions originality.",
    )
    expect(note?.className).toContain("text-gray-500")
    // The suggestion is part of the ask, so it stays in the claim body.
    const body = container.querySelector("p")
    expect(body?.textContent).toContain("We suggest 'Agree'")
    expect(body?.textContent).not.toContain("Note:")
  })
})
