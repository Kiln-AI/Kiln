// @vitest-environment jsdom
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest"
import { render, fireEvent, cleanup } from "@testing-library/svelte"
import { tick } from "svelte"
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
      props: { claim: claim(), index: 2, verdict },
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
      props: { claim: claim(), index: 0, verdict },
    })

    await fireEvent.click(by_id(container, "claim-disagree-0"))
    expect(verdict.agrees).toBe(false)
    expect(by_id(container, "claim-disagree-0").className).toContain(
      "btn-error",
    )
    const why = by_id<HTMLTextAreaElement>(container, "claim-why-0")
    expect(why.placeholder).toBe("This is wrong because…")
    // Required: flagged as an error until a reason is typed.
    expect(why.className).toContain("textarea-error")
    // Under 20 characters, so the card flags it as likely too short, and it
    // is still accepted: only an empty reason is ever held back.
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

describe("ClaimCard — the disagree reason hint", () => {
  const TOO_SHORT =
    "Likely too short to help improve the judge. What did it get wrong?"
  const MORE_DETAIL = "More details here would help the judge improve faster."

  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  async function open_disagree() {
    const verdict = fresh_verdict()
    const rendered = render(ClaimCard, {
      props: { claim: claim(), index: 0, verdict },
    })
    await fireEvent.click(by_id(rendered.container, "claim-disagree-0"))
    return { ...rendered, verdict }
  }

  async function type_reason(container: HTMLElement, value: string) {
    await fireEvent.input(by_id(container, "claim-why-0"), {
      target: { value },
    })
  }

  // Let `ms` of the pause pass, then let Svelte render whatever that changed.
  async function wait(ms: number) {
    vi.advanceTimersByTime(ms)
    await tick()
  }

  function hint(container: HTMLElement): string {
    return by_id(container, "claim-why-hint-0").textContent?.trim() ?? ""
  }

  it("labels the reason box and points it at the hint slot", async () => {
    const { container } = await open_disagree()

    const label = container.querySelector('label[for="claim-why-0"]')
    expect(label?.textContent?.trim()).toBe(
      "What do you disagree with? What should the judge have done instead?",
    )

    const slot = by_id(container, "claim-why-hint-0")
    expect(
      by_id(container, "claim-why-0").getAttribute("aria-describedby"),
    ).toBe("claim-why-hint-0")
    expect(slot.getAttribute("aria-live")).toBe("polite")
    // Fixed height so an appearing hint never moves the card.
    expect(slot.className).toContain("h-5")
  })

  it("warns when the trimmed reason is under 20 characters", async () => {
    const { container } = await open_disagree()

    // 21 characters typed, 13 once trimmed: the tier reads the trimmed length.
    await type_reason(container, "  Wrong window.      ")
    await wait(500)
    expect(hint(container)).toBe(TOO_SHORT)
  })

  it("asks for more detail from 20 through 59 characters", async () => {
    const { container } = await open_disagree()

    await type_reason(container, "a".repeat(20))
    await wait(500)
    expect(hint(container)).toBe(MORE_DETAIL)

    await type_reason(container, "a".repeat(59))
    await wait(500)
    expect(hint(container)).toBe(MORE_DETAIL)
  })

  it("says nothing for an empty, blank, or long enough reason", async () => {
    const { container } = await open_disagree()
    await wait(500)
    expect(hint(container)).toBe("")

    await type_reason(container, "     ")
    await wait(500)
    expect(hint(container)).toBe("")

    await type_reason(container, "a".repeat(60))
    await wait(500)
    expect(hint(container)).toBe("")
  })

  it("holds the hint back until typing pauses", async () => {
    const { container } = await open_disagree()

    await type_reason(container, "Too short.")
    await wait(499)
    expect(hint(container)).toBe("")
    await wait(1)
    expect(hint(container)).toBe(TOO_SHORT)
  })

  it("restarts the pause on the next keystroke", async () => {
    const { container } = await open_disagree()

    await type_reason(container, "Too")
    await wait(400)
    await type_reason(container, "Too short.")
    await wait(400)
    expect(hint(container)).toBe("")
    await wait(100)
    expect(hint(container)).toBe(TOO_SHORT)
  })

  it("waits out the pause when the reason shrinks into the short tier", async () => {
    const { container } = await open_disagree()

    await type_reason(container, "a".repeat(30))
    await wait(500)
    expect(hint(container)).toBe(MORE_DETAIL)

    await type_reason(container, "Too short.")
    await wait(499)
    expect(hint(container)).toBe(MORE_DETAIL)
    await wait(1)
    expect(hint(container)).toBe(TOO_SHORT)
  })

  it("clears the hint the moment the reason gets long enough", async () => {
    const { container } = await open_disagree()

    await type_reason(container, "a".repeat(30))
    await wait(500)
    expect(hint(container)).toBe(MORE_DETAIL)

    await type_reason(container, "a".repeat(60))
    await tick()
    expect(hint(container)).toBe("")
  })

  it("drops the hint at once when the card moves to another verdict", async () => {
    const { container, component } = render(ClaimCard, {
      props: {
        claim: claim(),
        index: 0,
        verdict: { agrees: false, why: "Too short." },
      },
    })
    await wait(500)
    expect(hint(container)).toBe(TOO_SHORT)

    // The review reuses these cards by position, so a new verdict object is
    // how a different claim arrives. Its reason gets the usual pause.
    component.$set({ verdict: { agrees: false, why: "a".repeat(30) } })
    await tick()
    expect(hint(container)).toBe("")
    await wait(500)
    expect(hint(container)).toBe(MORE_DETAIL)
  })

  it("keeps the pause running when the parent re-sets the same verdict", async () => {
    const { container, component, verdict } = await open_disagree()

    await type_reason(container, "Too short.")
    await wait(400)
    // A writeback or an unrelated parent render: the same verdict object with
    // the same reason, so the pause must run out on schedule, not start over.
    component.$set({ verdict })
    await tick()
    await wait(100)
    expect(hint(container)).toBe(TOO_SHORT)
  })

  it("drops a pending hint when the card goes away", async () => {
    const { container, unmount } = await open_disagree()
    // Counted as a delta so the card's own focus timer, and anything the test
    // environment keeps running, stay out of it.
    const idle_timers = vi.getTimerCount()

    await type_reason(container, "Too short.")
    expect(vi.getTimerCount()).toBe(idle_timers + 1)
    unmount()
    expect(vi.getTimerCount()).toBe(idle_timers)
  })

  it("clears the hint the moment the reason is emptied", async () => {
    const { container } = await open_disagree()

    await type_reason(container, "Too short.")
    await wait(500)
    expect(hint(container)).toBe(TOO_SHORT)

    await type_reason(container, "")
    await tick()
    expect(hint(container)).toBe("")
  })
})
