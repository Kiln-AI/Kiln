// @vitest-environment jsdom
import { describe, it, expect, afterAll, afterEach, beforeAll } from "vitest"
import { render, fireEvent, cleanup } from "@testing-library/svelte"
import { tick } from "svelte"
import ClaimEvidenceReview from "./claim_evidence_review.svelte"
import {
  build_claim_review_payload,
  build_trace_reviews,
  CHAR_CUTOFF,
  is_trace_reviewed,
  type Citation,
  type TraceClaims,
} from "./claim_evidence"
import type { TraceMessage } from "$lib/types"

// jsdom does not implement HTMLDialogElement.showModal/close. The Dialog
// component behind View Claims calls them, so polyfill with no-ops that just
// track the open state.
const original_show_modal = HTMLDialogElement.prototype.showModal
const original_close = HTMLDialogElement.prototype.close
const original_scroll_into_view = Element.prototype.scrollIntoView
beforeAll(() => {
  if (!HTMLDialogElement.prototype.showModal) {
    HTMLDialogElement.prototype.showModal = function () {
      this.open = true
    }
  }
  if (!HTMLDialogElement.prototype.close) {
    HTMLDialogElement.prototype.close = function () {
      this.open = false
    }
  }
  // Nor scrollIntoView, which the trace modal calls on the citation's <mark>
  // once it has rendered.
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = function () {}
  }
})

afterAll(() => {
  HTMLDialogElement.prototype.showModal = original_show_modal
  HTMLDialogElement.prototype.close = original_close
  Element.prototype.scrollIntoView = original_scroll_into_view
})

afterEach(() => {
  cleanup()
})

// The first suites render the CLAIMS-FIRST arm, so each render declares
// is_multi_turn — the review shape is gated on it (is_trace_first_review).
// The trace-first suite at the bottom renders the other arm.

function errored_trace(): TraceClaims {
  return {
    trace_id: "batch1_case_0",
    leaf_run_id: "run_0",
    raw_input: "What's the return window?",
    raw_output: "Our return window is 30 days.",
    judge_score: "fail",
    judge_reasoning: "Fabricated the window.",
    claims: null,
    final_judgement: null,
    claims_state: "error",
    claims_error: "Copilot request failed.",
  }
}

// A built trace with an EMPTY claims list — only the blind final-judgement
// card renders, so answering it (one Pass/Fail click) reviews the whole
// trace, and no claims disclosure is drawn at all.
function built_trace(id: string): TraceClaims {
  return {
    trace_id: id,
    leaf_run_id: null,
    raw_input: "in",
    raw_output: "out",
    judge_score: "pass",
    judge_reasoning: "reason",
    claims: [],
    final_judgement: {
      claim: "reason",
      expected_result: "pass",
      evidence: "",
      citations: [],
    },
    claims_state: "built",
    claims_error: null,
  }
}

describe("ClaimEvidenceReview — failed claims build", () => {
  it("renders a gradable blind verdict card so the save gate stays reachable", async () => {
    const traces = [errored_trace()]
    const verdicts = build_trace_reviews(traces)
    const { getByText, container } = render(ClaimEvidenceReview, {
      props: {
        traces,
        verdicts,
        selected_indices: [0],
        judged_noun: "conversation",
        is_multi_turn: true,
      },
    })

    // The error surfaces, but the blind verdict is still gradable.
    expect(container.textContent).toContain("Copilot request failed.")
    expect(container.textContent).toContain("Overall, this conversation")

    // Grading the blind verdict marks the trace reviewed — the only recovery
    // short of a paid re-drive.
    expect(is_trace_reviewed(traces[0], verdicts[0])).toBe(false)
    await fireEvent.click(getByText("Correct"))
    expect(verdicts[0].final_judgement_verdict.agrees).toBe(true)
    expect(is_trace_reviewed(traces[0], verdicts[0])).toBe(true)
  })
})

describe("ClaimEvidenceReview — Next gating", () => {
  it("disables Next until the current conversation is answered", async () => {
    const traces = [built_trace("t0"), built_trace("t1")]
    const verdicts = build_trace_reviews(traces)
    const { getByText, queryByText } = render(ClaimEvidenceReview, {
      props: {
        traces,
        verdicts,
        selected_indices: [0, 1],
        judged_noun: "conversation",
        is_multi_turn: true,
      },
    })

    // On the first (unanswered) conversation: Next is present but disabled,
    // and Save is nowhere (not the last conversation).
    const next = getByText("Next") as HTMLButtonElement
    expect(next.disabled).toBe(true)
    expect(queryByText("Save")).toBeNull()
    // Next carries the step-4 forward spec (wide primary) but no keyboard
    // hint: on this screen the shortcut fires Save, never Next.
    expect(next.className).toContain("min-w-64")
    expect(next.className).not.toContain("btn-sm")

    // Answering the current conversation enables Next.
    await fireEvent.click(getByText("Pass"))
    expect((getByText("Next") as HTMLButtonElement).disabled).toBe(false)
  })
})

describe("ClaimEvidenceReview — Save slot on the last conversation", () => {
  it("holds the Save slot disabled until the gate is met, never a dead Next", async () => {
    const traces = [built_trace("only")]
    const verdicts = build_trace_reviews(traces)

    // Gate not met: the same Save button holds the slot, disabled and
    // explaining itself. No Next — there's nothing left to advance to.
    const gated = render(ClaimEvidenceReview, {
      props: {
        traces,
        verdicts,
        selected_indices: [0],
        judged_noun: "conversation",
        is_multi_turn: true,
        save_disabled: true,
      },
    })
    const blocked = gated.getByText("Save") as HTMLButtonElement
    expect(blocked.disabled).toBe(true)
    expect(gated.queryByText("Next")).toBeNull()
    expect(
      gated.container.querySelector(".tooltip")?.getAttribute("data-tip"),
    ).toContain("Finish grading")
    cleanup()

    // Gate met on the last conversation: the same slot, now enabled.
    const open = render(ClaimEvidenceReview, {
      props: {
        traces,
        verdicts: build_trace_reviews(traces),
        selected_indices: [0],
        judged_noun: "conversation",
        is_multi_turn: true,
        save_disabled: false,
      },
    })
    const live = open.getByText("Save") as HTMLButtonElement
    expect(live.disabled).toBe(false)
    expect(open.queryByText("Next")).toBeNull()
    // The slot keeps one width across that flip, so it doesn't resize as the
    // gate completes.
    expect(live.className).toContain("min-w-64")
    expect(blocked.className).toContain("min-w-64")
  })

  it("renders the parent-owned refine label and its tooltip", () => {
    // The parent flips these props when graded disagreements exist (see
    // review_cta_refines in the wizard); the component just renders them.
    const traces = [built_trace("only")]
    const tip =
      "You disagreed with the judge on 1 conversation. Kiln will improve the judge from your feedback and re-check your eval data, then you'll review once more."
    const { getByText, queryByText, container } = render(ClaimEvidenceReview, {
      props: {
        traces,
        verdicts: build_trace_reviews(traces),
        selected_indices: [0],
        judged_noun: "conversation",
        is_multi_turn: true,
        save_disabled: false,
        save_label: "Refine Judge",
        save_tooltip: tip,
      },
    })
    expect(getByText("Refine Judge")).toBeTruthy()
    expect(queryByText("Save")).toBeNull()
    const tooltip = container.querySelector(".tooltip")
    expect(tooltip?.getAttribute("data-tip")).toBe(tip)
  })
})

// A short single-turn trace: the shape the gate sends trace-first. Its
// claims are built and sit behind View Claims.
function short_single_turn_trace(
  judge_score: "pass" | "fail" = "fail",
): TraceClaims {
  return {
    trace_id: "st_0",
    leaf_run_id: "run_st_0",
    raw_input: "What's the return window?",
    raw_output: "Our return window is 30 days.",
    judge_score,
    judge_reasoning: "The window was asserted with no source.",
    claims: [
      {
        claim: "The agent stated a return window as fact.",
        expected_result: "fail",
        evidence: "The reply gives 30 days.",
        citations: [],
      },
    ],
    final_judgement: {
      claim: "Fails Eval: fabricated policy.",
      expected_result: judge_score,
      evidence: "",
      citations: [],
    },
    claims_state: "built",
    claims_error: null,
    trace: null,
  }
}

function render_trace_first(
  traces: TraceClaims[],
  verdicts = build_trace_reviews(traces),
) {
  return {
    verdicts,
    ...render(ClaimEvidenceReview, {
      props: {
        traces,
        verdicts,
        selected_indices: traces.map((_, i) => i),
        judged_noun: "example",
      },
    }),
  }
}

// The component mounts two dialogs (the trace modal, then the claim stack);
// pick the one View Claims opens by its title.
function claims_dialog(container: HTMLElement): HTMLDialogElement {
  const found = [...container.querySelectorAll("dialog")].find((d) =>
    d.textContent?.includes("Claims"),
  )
  if (!found) throw new Error("no claims dialog rendered")
  return found
}

// The span the trace modal highlighted for the citation just clicked — only
// that view renders a <mark>, so its text identifies both which view opened
// and where in the trace it landed.
function cited_text(container: HTMLElement): string | null {
  return container.querySelector("mark")?.textContent ?? null
}

describe("ClaimEvidenceReview — trace-first arm", () => {
  it("shows the trace and one blind question, with the judge off screen", () => {
    const traces = [short_single_turn_trace()]
    const { container, getByText, queryByText } = render_trace_first(traces)

    // The trace itself, echoed from the raws the run recorded no trace for.
    expect(container.textContent).toContain("What's the return window?")
    expect(container.textContent).toContain("Our return window is 30 days.")
    expect(getByText("Does this example pass?")).toBeTruthy()

    // Nothing states the judge's call, or the claims that argue it, before
    // the reviewer answers.
    expect(container.textContent).not.toContain("The window was asserted")
    expect(container.textContent).not.toContain("Overall, this example")
    expect(container.textContent).not.toContain("Fails Eval")
    expect(container.textContent).not.toContain("The judge disagrees")

    // The inverse escape hatch: claims are one click away, the trace is not
    // behind a button any more.
    expect(getByText("View Claims")).toBeTruthy()
    expect(queryByText("View Full Trace")).toBeNull()
  })

  it("a label contradicting the judge reveals it and demands a reason", async () => {
    const traces = [short_single_turn_trace("fail")]
    const { container, getByText, verdicts } = render_trace_first(traces)

    // Judge said fail, reviewer says the response passes: a mismatch.
    await fireEvent.click(getByText("Pass"))
    expect(verdicts[0].final_judgement_verdict.agrees).toBe(false)
    // One sentence: the disagreement, the judge's own verdict word, and the
    // explanation it introduces.
    expect(
      getByText("The judge disagrees. It scored this as a fail."),
    ).toBeTruthy()
    expect(container.textContent).toContain("Fails Eval: fabricated policy.")
    // The Teach the Judge label. Its description names the mismatch; the ask
    // itself stays in the placeholder, keyed to the REVIEWER's label.
    expect(getByText("Teach the Judge")).toBeTruthy()
    expect(container.textContent).not.toContain("Detailed explanations")

    // The reason is required while the mismatch stands.
    const why = container.querySelector("textarea") as HTMLTextAreaElement
    expect(why.className).toContain("textarea-error")
    expect(why.placeholder).toBe(
      "Describe why this passes. Detailed explanations will improve the judge.",
    )
    expect(is_trace_reviewed(traces[0], verdicts[0])).toBe(false)

    await fireEvent.input(why, {
      target: { value: "The window is documented." },
    })
    expect(why.className).not.toContain("textarea-error")
    expect(verdicts[0].final_judgement_verdict.why).toBe(
      "The window is documented.",
    )
    expect(is_trace_reviewed(traces[0], verdicts[0])).toBe(true)
  })

  it("a label matching the judge finishes the trace with no interruption", async () => {
    const traces = [short_single_turn_trace("fail")]
    const { container, getByText, verdicts } = render_trace_first(traces)

    await fireEvent.click(getByText("Fail"))
    expect(verdicts[0].final_judgement_verdict.agrees).toBe(true)
    expect(container.textContent).not.toContain("The judge disagrees")
    expect(container.querySelector("textarea")).toBeNull()
    expect(is_trace_reviewed(traces[0], verdicts[0])).toBe(true)
  })

  it("inverts on a judge-pass trace", async () => {
    const traces = [short_single_turn_trace("pass")]
    const { container, getByText, verdicts } = render_trace_first(traces)

    // Agreeing with a passing judge is the Pass label here.
    await fireEvent.click(getByText("Pass"))
    expect(verdicts[0].final_judgement_verdict.agrees).toBe(true)
    expect(container.textContent).not.toContain("The judge disagrees")
    // The grade is readable off the row: the chosen side takes the verdict
    // color rather than the neutral outline.
    expect(getByText("Pass").className).toContain("btn-success")

    await fireEvent.click(getByText("Fail"))
    expect(verdicts[0].final_judgement_verdict.agrees).toBe(false)
    // And the color moves with the label, so only one side reads as chosen.
    expect(getByText("Fail").className).toContain("btn-error")
    expect(getByText("Pass").className).not.toContain("btn-success")
    // The verdict word follows the judge, the placeholder follows the
    // reviewer, so the two point opposite ways here.
    expect(
      getByText("The judge disagrees. It scored this as a pass."),
    ).toBeTruthy()
    expect(
      (container.querySelector("textarea") as HTMLTextAreaElement).placeholder,
    ).toBe(
      "Describe why this fails. Detailed explanations will improve the judge.",
    )
  })

  it("flipping back to agreement clears the reveal and the reason", async () => {
    const traces = [short_single_turn_trace("fail")]
    const { container, getByText, verdicts } = render_trace_first(traces)

    await fireEvent.click(getByText("Pass"))
    const why = container.querySelector("textarea") as HTMLTextAreaElement
    await fireEvent.input(why, {
      target: { value: "The window is documented." },
    })

    await fireEvent.click(getByText("Fail"))
    expect(container.textContent).not.toContain("The judge disagrees")
    expect(container.querySelector("textarea")).toBeNull()
    // The reason went with the reveal: an agreeing grade never ships text the
    // reviewer can no longer see.
    expect(verdicts[0].final_judgement_verdict.why).toBe("")
  })

  it("View Claims opens a display-only claim stack, with no verdict controls", async () => {
    const traces = [short_single_turn_trace()]
    const { container, getByText, getAllByText, verdicts } =
      render_trace_first(traces)

    // Before the click nothing of the claims is mounted, so the judge's call
    // isn't sitting in a closed dialog on a blind screen.
    expect(container.textContent).not.toContain("Overall, this example")

    // Label first, so the shared verdict reads "disagree" while the claims are
    // open — the state that would put a second reason box in the dialog.
    await fireEvent.click(getByText("Pass"))
    await fireEvent.click(getByText("View Claims"))
    const dialog = claims_dialog(container)
    expect(dialog.open).toBe(true)
    expect(dialog.textContent).toContain(
      "The agent stated a return window as fact.",
    )
    expect(dialog.textContent).toContain("Overall, this example")

    // The blind row stays the one grading control: its Pass/Fail pair renders
    // once, and the dialog's cards carry no Correct/Incorrect of their own and
    // no reason box.
    expect(getAllByText("Pass")).toHaveLength(1)
    expect(getAllByText("Fail")).toHaveLength(1)
    expect(dialog.textContent).not.toContain("Correct")
    expect(dialog.querySelector("textarea")).toBeNull()
    // So no sub-claim grade can appear here and quietly demand a reason the
    // trace-first screen never shows.
    expect(verdicts[0].claim_verdicts.every((v) => v.agrees === null)).toBe(
      true,
    )
  })

  it("keeps the judgement out of the claims dialog until the call is made", async () => {
    // The dialog is reachable at any time, so it is a second way to read the
    // verdict this arm withholds. The claims are reading material and stay;
    // the overall judgement joins them only once the answer is in.
    const traces = [short_single_turn_trace()]
    const { container, getByText } = render_trace_first(traces)

    await fireEvent.click(getByText("View Claims"))
    const dialog = claims_dialog(container)
    expect(dialog.textContent).toContain(
      "The agent stated a return window as fact.",
    )
    expect(dialog.textContent).not.toContain("Overall, this example")
    expect(dialog.textContent).not.toContain("Fails Eval")

    // Answered, so the call is no longer anything to protect.
    await fireEvent.click(getByText("Pass"))
    expect(claims_dialog(container).textContent).toContain(
      "Overall, this example",
    )
  })

  it("holds the judgement's reason back until the reviewer has answered", async () => {
    // The trace is on screen here, so the reviewer has what they need without
    // the eval's reasoning, which would only telegraph the call. Answering
    // either way releases it.
    const traces = [short_single_turn_trace()]
    const { container, getByText } = render_trace_first(traces)
    expect(container.textContent).not.toContain("Fails Eval")

    // Agreeing releases it too: the conclusion can no longer anchor anyone.
    await fireEvent.click(getByText("Fail"))
    expect(container.textContent).toContain("Fails Eval: fabricated policy.")
    expect(container.textContent).not.toContain("The judge disagrees")
  })

  it("offers Retry Analysis in the dialog when the claims build failed", async () => {
    const traces = [
      {
        ...short_single_turn_trace(),
        claims: null,
        final_judgement: null,
        claims_state: "error" as const,
        claims_error: "Copilot request failed.",
      },
    ]
    const opened: number[] = []
    const verdicts = build_trace_reviews(traces)
    const { container, getByText } = render(ClaimEvidenceReview, {
      props: {
        traces,
        verdicts,
        selected_indices: [0],
        judged_noun: "example",
        on_open_trace: (i: number) => opened.push(i),
      },
    })

    // The blind label still grades a trace whose claims failed: the reveal
    // reads the judge's own verdict and reasoning, not the claims.
    await fireEvent.click(getByText("Fail"))
    expect(is_trace_reviewed(traces[0], verdicts[0])).toBe(true)

    await fireEvent.click(getByText("View Claims"))
    expect(claims_dialog(container).textContent).toContain(
      "Copilot request failed.",
    )
    // Landing on the trace already reported it open once, so the retry has to
    // show up as another report, not merely as a report.
    const before = opened.filter((i) => i === 0).length
    await fireEvent.click(getByText("Retry Analysis"))
    expect(opened.filter((i) => i === 0)).toHaveLength(before + 1)
  })

  it("carries each trace's label and reason across Next and Previous", async () => {
    const traces = [short_single_turn_trace(), short_single_turn_trace()]
    traces[1].trace_id = "st_1"
    const { container, getByText, verdicts } = render_trace_first(traces)
    await fireEvent.click(getByText("Pass"))
    await fireEvent.input(container.querySelector("textarea")!, {
      target: { value: "The window is documented." },
    })
    await fireEvent.click(getByText("View Claims"))
    expect(claims_dialog(container).textContent).toContain(
      "Overall, this example",
    )

    await fireEvent.click(getByText("Next"))
    // A fresh trace starts unlabelled: no reveal, no reason carried over.
    expect(container.textContent).not.toContain("The judge disagrees")
    expect(container.querySelector("textarea")).toBeNull()
    expect(verdicts[1].final_judgement_verdict).toEqual({
      agrees: null,
      why: "",
    })
    // And its claims are its own to ask for: the previous trace's opt-in did
    // not follow the reviewer here.
    expect(claims_dialog(container).textContent).not.toContain(
      "Overall, this example",
    )

    await fireEvent.click(getByText("Previous"))
    expect(
      getByText("The judge disagrees. It scored this as a fail."),
    ).toBeTruthy()
    expect(
      (container.querySelector("textarea") as HTMLTextAreaElement).value,
    ).toBe("The window is documented.")
    // The grade came back; the claims stay closed until asked for again.
    expect(claims_dialog(container).textContent).not.toContain(
      "Overall, this example",
    )
  })

  it("keeps the claims-first review for multi-turn", () => {
    // Same short trace, the other gate arm: the claim stack, not the
    // question, and the trace back behind its button.
    const traces = [short_single_turn_trace()]
    const multi = render(ClaimEvidenceReview, {
      props: {
        traces,
        verdicts: build_trace_reviews(traces),
        selected_indices: [0],
        judged_noun: "conversation",
        is_multi_turn: true,
      },
    })
    // The same blind question in the arm's own noun, and the trace back
    // behind its button with the claims folded under the call.
    expect(multi.getByText("Does this conversation pass?")).toBeTruthy()
    expect(multi.queryAllByText("View Full Trace").length).toBeGreaterThan(0)
    expect(multi.queryByText("View Claims")).toBeNull()
    expect(multi.getByRole("button", { name: "Show claims" })).toBeTruthy()
    expect(
      multi.container.querySelector("[data-testid='review-input']"),
    ).toBeNull()
  })

  it("reviews a short structured output trace-first", () => {
    // The shape a schema'd single-turn task produces. It reviews on the
    // trace like any other short output, and the Output section renders the
    // JSON.
    const raw_output = JSON.stringify({
      window_days: 30,
      answer: "Our return window is 30 days.",
    })
    const traces = [{ ...short_single_turn_trace(), raw_output }]
    const { container, getByText } = render_trace_first(traces)

    expect(getByText("Does this example pass?")).toBeTruthy()
    expect(container.textContent).toContain("window_days")
    expect(container.textContent).toContain("Our return window is 30 days.")
  })

  it("keeps the claims-first review for a structured output over the cutoff", () => {
    // Length is what decides, for JSON as for prose.
    const raw_output = JSON.stringify({ answer: "x".repeat(CHAR_CUTOFF) })
    const traces = [{ ...short_single_turn_trace(), raw_output }]
    const { container, getByRole, queryByText } = render_trace_first(traces)

    // Claims-first: the trace is behind its button, not rendered inline.
    expect(queryByText("View Claims")).toBeNull()
    expect(getByRole("button", { name: "Show claims" })).toBeTruthy()
    expect(container.querySelector("[data-testid='review-input']")).toBeNull()
  })

  it("fails loud when a trace has neither a transcript nor raws", () => {
    const traces = [
      { ...short_single_turn_trace(), raw_input: "", raw_output: "" },
    ]
    const { container, queryByText } = render_trace_first(traces)
    expect(container.textContent).toContain("no transcript and no raw input")
    // Nothing to read means nothing to label.
    expect(queryByText("Does this example pass?")).toBeNull()
  })
})

// What the server writes into judge_reasoning when the judge model emits no
// reasoning trace: honest, and about nothing in this trace.
const PLACEHOLDER_REASONING =
  "The judge returned a FAIL verdict without an explicit reasoning trace."

// A trace whose judge_reasoning is that placeholder, so the reveal has a real
// explanation only if it reads the final judgement. It carries the structured
// trace a real single-turn run records — the assistant message IS raw_output —
// so a citation click goes through the chat view, not the raw-text panel.
function trace_with_placeholder_reasoning(): TraceClaims {
  const base = short_single_turn_trace("fail")
  return {
    ...base,
    judge_reasoning: PLACEHOLDER_REASONING,
    final_judgement: {
      claim: "The agent stated a 30 day window it has no source for.",
      expected_result: "fail",
      evidence: "The reply asserts the window [1].",
      citations: [
        { marker: 1, source: "output", from: "30 days", to: "30 days" },
      ],
    },
    trace: [
      { role: "system", content: "You are a support agent." },
      { role: "user", content: base.raw_input },
      { role: "assistant", content: base.raw_output },
    ],
  }
}

describe("ClaimEvidenceReview — what the mismatch reveal explains", () => {
  it("reads out the final judgement, not the judge's reasoning field", async () => {
    const { container, getByText } = render_trace_first([
      trace_with_placeholder_reasoning(),
    ])

    await fireEvent.click(getByText("Pass"))
    expect(container.textContent).toContain(
      "The agent stated a 30 day window it has no source for.",
    )
    expect(container.textContent).not.toContain(PLACEHOLDER_REASONING)
  })

  it("falls back to judge_reasoning when no final judgement was built", async () => {
    // The claims build failed, so there is no distilled judgement to read —
    // the judge's own field is all this trace carries.
    const { container, getByText } = render_trace_first([
      {
        ...trace_with_placeholder_reasoning(),
        claims: null,
        final_judgement: null,
        claims_state: "error" as const,
        claims_error: "Copilot request failed.",
      },
    ])

    await fireEvent.click(getByText("Pass"))
    expect(container.textContent).toContain(PLACEHOLDER_REASONING)
  })

  it("falls back to judge_reasoning when the final judgement's text is empty", async () => {
    // The judgement still carries citations: they belong to the sentence that
    // was dropped, so they must go with it rather than chip the judge's
    // placeholder with evidence for text nobody is reading.
    const { container, getByText } = render_trace_first([
      {
        ...trace_with_placeholder_reasoning(),
        final_judgement: {
          claim: "   ",
          expected_result: "fail" as const,
          evidence: "",
          citations: [
            { marker: 1, source: "output" as const, from: "30", to: "days" },
          ],
        },
      },
    ])

    await fireEvent.click(getByText("Pass"))
    expect(container.textContent).toContain(PLACEHOLDER_REASONING)
    expect(container.querySelector('[title="View in trace"]')).toBeNull()
  })

  it("closes the headline on a period when there is nothing to explain", async () => {
    // Neither a final judgement nor a reasoning field, so the reveal carries
    // no sentence: the headline has to end rather than trail into "because:".
    const { getByText } = render_trace_first([
      {
        ...trace_with_placeholder_reasoning(),
        judge_reasoning: "",
        claims: null,
        final_judgement: null,
        claims_state: "error" as const,
        claims_error: "Copilot request failed.",
      },
    ])

    await fireEvent.click(getByText("Pass"))
    expect(
      getByText("The judge disagrees. It scored this as a fail."),
    ).toBeTruthy()
  })

  it("chips the final judgement's citations into the same trace view the claim cards open", async () => {
    // The reveal's chip. The trace is structured, so the click lands in the
    // chat view and the mark proves the output span mapped onto the assistant
    // message — the single-turn path through map_output_span_to_trace.
    const revealed = render_trace_first([trace_with_placeholder_reasoning()])
    await fireEvent.click(revealed.getByText("Pass"))
    const chip = revealed.getByTitle("View in trace")
    expect(chip.textContent).toBe("[1]")
    await fireEvent.click(chip)
    const from_reveal = cited_text(revealed.container)
    expect(from_reveal).toBe("30 days")
    cleanup()

    // The claims-first arm's final-judgement card, citing the same span
    // through on_cite. Both land on the same highlighted trace, so the reveal
    // reuses that plumbing rather than opening a view of its own.
    const traces = [trace_with_placeholder_reasoning()]
    const carded = render(ClaimEvidenceReview, {
      props: {
        traces,
        verdicts: build_trace_reviews(traces),
        selected_indices: [0],
        judged_noun: "conversation",
        is_multi_turn: true,
      },
    })
    await fireEvent.click(carded.getByTitle("View in trace"))
    expect(cited_text(carded.container)).toBe(from_reveal)
  })
})

// A single-turn trace whose structured trace ECHOES the raws: its user turn IS
// raw_input and its assistant turn IS raw_output. This is what a single-turn
// run records, and it is the shape the duplicate-input pin leans on: any panel
// rendered above the conversation would print the opening message twice.
function echoing_trace(citations: Citation[] = []): TraceClaims {
  const raw_input = "What is the return window on a mattress?"
  const raw_output = "Our return window is 30 days."
  return {
    trace_id: "echo_0",
    leaf_run_id: "run_echo_0",
    raw_input,
    raw_output,
    judge_score: "fail",
    judge_reasoning: "The window was asserted with no source.",
    claims: [
      {
        claim: "The agent stated a return window as fact.",
        expected_result: "fail",
        evidence:
          citations.length > 0
            ? "The reply answers the question [1]."
            : "The reply gives 30 days.",
        citations,
      },
    ],
    final_judgement: {
      claim: "Fails Eval: fabricated policy.",
      expected_result: "fail",
      evidence: "",
      citations: [],
    },
    claims_state: "built",
    claims_error: null,
    trace: [
      { role: "system", content: "You are a support agent." },
      { role: "user", content: raw_input },
      { role: "assistant", content: raw_output },
    ],
  }
}

// The MULTI-TURN arm: the claim stack, with the conversation behind View Full
// Trace and the claim cards carrying the [n] chips that open it on a citation.
function render_multi_turn(traces: TraceClaims[]) {
  return render(ClaimEvidenceReview, {
    props: {
      traces,
      verdicts: build_trace_reviews(traces),
      selected_indices: [0],
      judged_noun: "conversation",
      is_multi_turn: true,
    },
  })
}

// The claims sit behind a collapsed Claims disclosure on the claims-first
// arm, so anything rendered by a claim card needs it opened first.
function claims_toggle(container: HTMLElement): HTMLButtonElement {
  const found = [...container.querySelectorAll("button")].find((b) =>
    b.textContent?.trim().startsWith("Claims"),
  )
  if (!found) throw new Error("no claims disclosure rendered")
  return found as HTMLButtonElement
}

async function expand_claims(container: HTMLElement) {
  const toggle = claims_toggle(container)
  if (toggle.getAttribute("aria-expanded") === "true") return
  await fireEvent.click(toggle)
}

// The trace modal, picked out of the mounted dialogs by its title.
function trace_dialog(container: HTMLElement): HTMLDialogElement {
  const found = [...container.querySelectorAll("dialog")].find(
    (d) => d.querySelector("h3")?.textContent?.trim() === "Trace",
  )
  if (!found) throw new Error("no trace dialog rendered")
  return found
}

function occurrences(haystack: string, needle: string): number {
  return haystack.split(needle).length - 1
}

// ── The single-turn anatomy ──────────────────────────────────────────────
// Two sections, on both surfaces that show a single-turn trace: a labelled
// Input field and a labelled Output section. No chat bubbles, no system row.

function section(root: ParentNode, name: "input" | "output"): HTMLElement {
  const found = root.querySelector<HTMLElement>(
    `[data-testid='review-${name}']`,
  )
  if (!found) throw new Error(`no ${name} section rendered`)
  return found
}

// The tint a section's field is painted with. The two are the review's whole
// visual grammar (input neutral, output primary), so a test that only read
// text would pass on a surface that had lost them.
function tinted(root: ParentNode, tint: string): Element | null {
  return root.querySelector(`[class*='${tint}']`)
}

// The linear trace renders one collapsible block per row; the chat renders
// bubbles with data-testids. Either predicate alone would pass on a surface
// showing both, so each test checks the pair.
function linear_role_labels(root: ParentNode): string[] {
  return [...root.querySelectorAll(".collapse-title > span")].map(
    (span) => span.textContent?.trim() ?? "",
  )
}

function chat_bubbles(root: ParentNode): Element[] {
  return [...root.querySelectorAll("[data-testid^='chat-msg-']")]
}

// Everything the expanded rows really rendered, through Output's <pre>. A
// collapsed row prints its preview as plain text, so this is what separates
// "on screen" from "one click away".
function rendered_pre_text(root: ParentNode): string {
  return [...root.querySelectorAll("pre")]
    .map((pre) => pre.textContent ?? "")
    .join("\n")
}

// The rows that started OPEN. A collapsed row still prints a one-line preview
// of its content, so reading text off the page proves nothing about
// expansion — the checked toggle is what does.
function expanded_rows(root: ParentNode): boolean[] {
  return [...root.querySelectorAll(".collapse")].map(
    (block) =>
      !!block.querySelector<HTMLInputElement>("input[type=checkbox]")?.checked,
  )
}

// A run whose stored trace is a tool loop: the model called a tool, read the
// result, then answered. Two assistant messages, so "the assistant rows" and
// "the final assistant row" are different answers.
function tool_loop_trace(
  overrides: Partial<TraceClaims> = {},
  citations: Citation[] = [],
): TraceClaims {
  const base = short_single_turn_trace("fail")
  return {
    ...base,
    trace_id: "tool_0",
    claims: [
      {
        claim: "The agent stated a return window as fact.",
        expected_result: "fail",
        evidence:
          citations.length > 0
            ? "The reply asserts the window [1]."
            : "The reply gives 30 days.",
        citations,
      },
    ],
    trace: [
      { role: "system", content: "You are a support agent." },
      { role: "user", content: base.raw_input },
      { role: "assistant", content: "Let me look up the policy." },
      {
        role: "assistant",
        content: null,
        tool_calls: [
          {
            id: "call_1",
            type: "function",
            function: {
              name: "lookup_policy",
              arguments: '{"topic": "returns"}',
            },
          },
        ],
      },
      {
        role: "tool",
        content: '{"output": "Returns accepted within 30 days."}',
        tool_call_id: "call_1",
      },
      { role: "assistant", content: base.raw_output },
    ] as TraceMessage[],
    ...overrides,
  }
}

// A multi-turn trace with claims to fold under the call. Its final judgement
// follows the builder's contract: a reason carrying no verdict phrasing, plus
// an evidence sentence with a clickable [n] — the substance the blind question
// is answered from once the trace and the claims are both off screen.
function claims_first_trace(
  judge_score: "pass" | "fail" = "fail",
): TraceClaims {
  return {
    trace_id: "mt_0",
    leaf_run_id: "run_mt_0",
    raw_input: "What is the return window on a mattress?",
    raw_output: "Our return window is 30 days.",
    judge_score,
    judge_reasoning: "The window was asserted with no source.",
    claims: [
      {
        claim: "The agent stated a return window as fact.",
        expected_result: "fail",
        evidence: "The reply gives 30 days [1].",
        citations: [
          { marker: 1, source: "output", from: "30 days", to: "30 days" },
        ],
      },
      {
        claim: "The agent named no policy page.",
        expected_result: "fail",
        evidence: "No source appears in the reply.",
        citations: [],
      },
    ],
    final_judgement: {
      claim: "The window was given without a source.",
      expected_result: judge_score,
      evidence: "The reply asserts 30 days with no citation [1].",
      citations: [
        { marker: 1, source: "output", from: "30 days", to: "30 days" },
      ],
    },
    claims_state: "built",
    claims_error: null,
    trace: null,
  }
}

describe("ClaimEvidenceReview — the claims-first arm asks the call first", () => {
  it("leads with the overall question and the reason it is answered from", async () => {
    const { container, getByText, getByTitle } = render_multi_turn([
      claims_first_trace(),
    ])

    // The call comes before the claims, not after them.
    const text = container.textContent ?? ""
    expect(text).toContain("Does this conversation pass?")
    expect(text.indexOf("Does this conversation pass?")).toBeLessThan(
      text.indexOf("Claims"),
    )

    // The trace is behind a button and the claims are folded, so the reason
    // and its cited evidence have to be on the card for the question to be
    // answerable at all.
    expect(getByText("The window was given without a source.")).toBeTruthy()
    expect(text).toContain("The reply asserts 30 days with no citation")
    await fireEvent.click(getByTitle("View in trace"))
    expect(cited_text(container)).toBe("30 days")
  })

  it("states no verdict before the reviewer answers, on either call", () => {
    // Both directions: the tint that would give a fail away is amber, the one
    // that would give a pass away is green, so a single fixture can only ever
    // prove half of this.
    for (const judge_score of ["fail", "pass"] as const) {
      const { container, getByText } = render_multi_turn([
        claims_first_trace(judge_score),
      ])

      expect(container.textContent).not.toContain("Overall, this conversation")
      expect(container.textContent).not.toContain("The judge disagrees")
      // Neither side of the pair reads as chosen yet.
      expect(getByText("Pass").className).toContain("btn-outline")
      expect(getByText("Fail").className).toContain("btn-outline")
      expect(container.querySelector("[class*='bg-warning/5']")).toBeNull()
      expect(container.querySelector("[class*='bg-success/5']")).toBeNull()
      cleanup()
    }
  })

  it("passes a verdict-phrased reason straight through to the card", () => {
    // The reason line renders the judgement's text verbatim. Nothing on the
    // client inspects it for verdict phrasing, so the guarantee that it
    // carries none is the claim builder's, server-side. This pins what the
    // CARD controls — headline, tint, reveal — against a reason that states
    // the call outright, and documents that the sentence itself is passed on
    // as written.
    const leaky = claims_first_trace()
    leaky.final_judgement = {
      ...leaky.final_judgement!,
      claim: "Fails Eval: fabricated policy.",
    }
    const { container, getByText } = render_multi_turn([leaky])

    // Everything the card decides for itself stays blind.
    expect(container.textContent).not.toContain("Overall, this conversation")
    expect(container.querySelector("[class*='bg-warning/5']")).toBeNull()
    expect(getByText("Pass").className).toContain("btn-outline")
    // The reason is not filtered. If the server ever emits verdict phrasing,
    // it reaches the reviewer, and this assertion is what will change.
    expect(container.textContent).toContain("Fails Eval: fabricated policy.")
  })

  it("folds the claims behind a collapsed disclosure", async () => {
    const { container, queryByText, getByText, getAllByText } =
      render_multi_turn([claims_first_trace()])

    // Collapsed on arrival: the row is on screen, the claims are not.
    expect(claims_toggle(container).getAttribute("aria-expanded")).toBe("false")
    expect(queryByText("The agent stated a return window as fact.")).toBeNull()
    expect(container.textContent).not.toContain("The main facts the judge used")

    await expand_claims(container)
    expect(claims_toggle(container).getAttribute("aria-expanded")).toBe("true")
    expect(
      getByText(
        "The main facts the judge used to score this conversation. Disagree with any that are wrong.",
      ),
    ).toBeTruthy()
    expect(getByText("The agent stated a return window as fact.")).toBeTruthy()
    expect(getByText("The agent named no policy page.")).toBeTruthy()
    // The description names the only control the cards carry: one flag per
    // claim, and no way to record agreement.
    expect(getAllByText("Disagree")).toHaveLength(2)
    expect(queryByText("Correct")).toBeNull()
  })

  it("finishes a conversation on the overall call, with the claims ungraded", async () => {
    // Sub-claim verdicts were always optional in the gate, which is what makes
    // folding them free: the call alone completes the conversation.
    const traces = [claims_first_trace(), claims_first_trace()]
    traces[1].trace_id = "mt_1"
    const verdicts = build_trace_reviews(traces)
    const { getByText } = render(ClaimEvidenceReview, {
      props: {
        traces,
        verdicts,
        selected_indices: [0, 1],
        judged_noun: "conversation",
        is_multi_turn: true,
      },
    })

    expect((getByText("Next") as HTMLButtonElement).disabled).toBe(true)
    await fireEvent.click(getByText("Fail"))
    expect(verdicts[0].claim_verdicts.every((v) => v.agrees === null)).toBe(
      true,
    )
    expect(is_trace_reviewed(traces[0], verdicts[0])).toBe(true)
    expect((getByText("Next") as HTMLButtonElement).disabled).toBe(false)
  })
})

describe("ClaimEvidenceReview — what a flagged claim records", () => {
  it("carries only the flagged claim into the payload, never an agreement", async () => {
    const traces = [claims_first_trace()]
    const verdicts = build_trace_reviews(traces)
    const { container, getAllByText, getByText } = render(ClaimEvidenceReview, {
      props: {
        traces,
        verdicts,
        selected_indices: [0],
        judged_noun: "conversation",
        is_multi_turn: true,
      },
    })

    await fireEvent.click(getByText("Fail"))
    await expand_claims(container)
    await fireEvent.click(getAllByText("Disagree")[0])
    await fireEvent.input(
      container.querySelectorAll("textarea")[0] as HTMLTextAreaElement,
      { target: { value: "The window is published." } },
    )

    // The flagged claim carries a reason, so the conversation is complete.
    expect(is_trace_reviewed(traces[0], verdicts[0])).toBe(true)

    // Only the flagged claim reaches the record. The one left alone is
    // absent, which the contract reads as no signal — never as agreement.
    const payload = build_claim_review_payload(traces[0], verdicts[0])
    expect(payload.claims).toHaveLength(1)
    expect(payload.claims[0].claim).toBe(
      "The agent stated a return window as fact.",
    )
    expect(payload.claims[0].human_grade).toBe("disagree")
    expect(payload.claims[0].human_feedback).toBe("The window is published.")
    expect(payload.final_judgement.human_grade).toBe("agree")
  })

  it("blocks the conversation until a flagged claim carries a reason", async () => {
    // The one place a claim verdict can still hold up Next: a disagreement
    // without a reason is an incomplete review, flag-only control or not.
    const traces = [claims_first_trace(), claims_first_trace()]
    traces[1].trace_id = "mt_1"
    const verdicts = build_trace_reviews(traces)
    const { container, getAllByText, getByText } = render(ClaimEvidenceReview, {
      props: {
        traces,
        verdicts,
        selected_indices: [0, 1],
        judged_noun: "conversation",
        is_multi_turn: true,
      },
    })

    await fireEvent.click(getByText("Fail"))
    expect((getByText("Next") as HTMLButtonElement).disabled).toBe(false)

    await expand_claims(container)
    await fireEvent.click(getAllByText("Disagree")[0])
    expect((getByText("Next") as HTMLButtonElement).disabled).toBe(true)

    await fireEvent.input(
      container.querySelectorAll("textarea")[0] as HTMLTextAreaElement,
      { target: { value: "The window is published." } },
    )
    expect((getByText("Next") as HTMLButtonElement).disabled).toBe(false)

    // Clearing the flag also clears the reason it demanded, and the
    // conversation is complete again on the overall call alone.
    await fireEvent.click(getAllByText("Disagree")[0])
    expect(verdicts[0].claim_verdicts[0]).toEqual({ agrees: null, why: "" })
    expect((getByText("Next") as HTMLButtonElement).disabled).toBe(false)
  })
})

describe("ClaimEvidenceReview — the claims-first contradiction reveal", () => {
  it("stays away while the reviewer agrees with the call", async () => {
    const traces = [claims_first_trace("fail")]
    const verdicts = build_trace_reviews(traces)
    const { container, getByText } = render(ClaimEvidenceReview, {
      props: {
        traces,
        verdicts,
        selected_indices: [0],
        judged_noun: "conversation",
        is_multi_turn: true,
      },
    })

    await fireEvent.click(getByText("Fail"))
    expect(verdicts[0].final_judgement_verdict.agrees).toBe(true)
    expect(container.textContent).not.toContain("The judge disagrees")
    expect(container.querySelector("textarea")).toBeNull()
    expect(getByText("Fail").className).toContain("btn-error")
  })

  it("appears on a contradiction and does not repeat the reason above it", async () => {
    const traces = [claims_first_trace("fail")]
    const verdicts = build_trace_reviews(traces)
    const { container, getByText, getAllByText } = render(ClaimEvidenceReview, {
      props: {
        traces,
        verdicts,
        selected_indices: [0],
        judged_noun: "conversation",
        is_multi_turn: true,
      },
    })

    await fireEvent.click(getByText("Pass"))
    expect(verdicts[0].final_judgement_verdict.agrees).toBe(false)
    // One line and a full stop: the reason is already on the card, so the
    // reveal has nothing to introduce.
    expect(
      getByText("The judge disagrees. It scored this as a fail."),
    ).toBeTruthy()
    expect(getAllByText("The window was given without a source.")).toHaveLength(
      1,
    )

    // The reason is required while the contradiction stands, and its ask is
    // keyed to the label the reviewer just gave.
    expect(getByText("Teach the Judge")).toBeTruthy()
    const why = container.querySelector("textarea") as HTMLTextAreaElement
    expect(why.placeholder).toBe(
      "Describe why this passes. Detailed explanations will improve the judge.",
    )
    expect(why.className).toContain("textarea-error")
    expect(is_trace_reviewed(traces[0], verdicts[0])).toBe(false)

    await fireEvent.input(why, {
      target: { value: "The window is published." },
    })
    expect(why.className).not.toContain("textarea-error")
    expect(is_trace_reviewed(traces[0], verdicts[0])).toBe(true)

    // Flipping back closes the reveal and drops the reason with it.
    await fireEvent.click(getByText("Fail"))
    expect(container.querySelector("textarea")).toBeNull()
    expect(verdicts[0].final_judgement_verdict.why).toBe("")
  })
})

describe("the single-turn review anatomy, inline", () => {
  it("shows an Input field and an Output section, and no chat", () => {
    const { container, getByText } = render_trace_first([
      short_single_turn_trace(),
    ])

    // Both sections, labelled, in their own tints.
    expect(getByText("Input")).toBeTruthy()
    expect(getByText("Output")).toBeTruthy()
    expect(tinted(section(container, "input"), "bg-base-200")).not.toBeNull()
    expect(tinted(section(container, "output"), "bg-primary/5")).not.toBeNull()
    expect(section(container, "input").textContent).toContain(
      "What's the return window?",
    )
    expect(section(container, "output").textContent).toContain(
      "Our return window is 30 days.",
    )

    // No chat bubbles anywhere: a single exchange is not a conversation.
    expect(chat_bubbles(container)).toHaveLength(0)
    // And the blind label is still the arm's one grading control.
    expect(getByText("Does this example pass?")).toBeTruthy()
  })

  it("never shows the system prompt", () => {
    // The stored trace opens with one; it is task configuration, not something
    // the reviewer grades, and it has no row and no bubble on this surface.
    const { container } = render_trace_first([
      trace_with_placeholder_reasoning(),
    ])
    expect(container.textContent).not.toContain("SYSTEM")
    expect(container.textContent).not.toContain("You are a support agent.")
  })

  it("shows the input once — the sections replace the old chat mount", () => {
    const t = trace_with_placeholder_reasoning()
    const { container } = render_trace_first([t])
    expect(occurrences(container.textContent ?? "", t.raw_input)).toBe(1)
  })

  it("renders prose through the markdown renderer, in both fields", () => {
    const traces = [
      {
        ...short_single_turn_trace(),
        raw_input: "**Which** window applies?",
        raw_output: "The window is **30 days**.",
      },
    ]
    const { container } = render_trace_first(traces)

    for (const name of ["input", "output"] as const) {
      const field = section(container, name)
      expect(field.querySelector("strong")).not.toBeNull()
      expect(field.textContent).not.toContain("**")
    }
  })

  it("renders structured content through the house Output idiom", () => {
    const raw_output = '{"window_days":30,"answer":"30 days"}'
    const traces = [
      {
        ...short_single_turn_trace(),
        raw_input: '{"question":"return window?"}',
        raw_output,
      },
    ]
    const { container } = render_trace_first(traces)

    // Pretty-printed, not the compact source string, and syntax highlighted.
    const output = section(container, "output")
    expect(output.querySelector("pre")?.textContent).toContain(
      '"window_days": 30',
    )
    expect(output.querySelector("pre")?.textContent).not.toContain(raw_output)
    expect(output.querySelector(".hljs-attr")).not.toBeNull()
    expect(section(container, "input").querySelector("pre")).not.toBeNull()
  })
})

describe("the single-turn Output section — rows or a field", () => {
  it("renders a tool loop as rows, with only the FINAL assistant open", () => {
    const { container, getByText } = render_trace_first([tool_loop_trace()])
    const output = section(container, "output")

    // The rows are what the model did AFTER the input: the system prompt and
    // the user turn are not among them.
    expect(linear_role_labels(output)).toEqual([
      "Assistant",
      "Assistant",
      "Tool",
      "Assistant",
    ])
    expect(chat_bubbles(container)).toHaveLength(0)

    // Only the last row starts open — not every assistant, and not the tool.
    expect(expanded_rows(output)).toEqual([false, false, false, true])
    // Open means really rendered: the answer comes through Output's <pre>, not
    // the one-line preview a collapsed row prints.
    expect(rendered_pre_text(output)).toContain("Our return window is 30 days.")
    expect(rendered_pre_text(output)).not.toContain(
      "Let me look up the policy.",
    )
    expect(output.textContent).not.toContain("Tool Result")

    // Still the trace-first review: one blind question, judge off screen.
    expect(getByText("Does this example pass?")).toBeTruthy()
  })

  it("re-opens the right row after Next moves to another trace", async () => {
    // One Trace instance serves every trace the reviewer walks, so the second
    // trace's rows must be re-read. Keeping the first trace's expansion opens
    // a row by its old position — a tool result, on a surface whose whole
    // point is that the final answer costs no click.
    const first = tool_loop_trace({ trace_id: "loop_a" })
    const second: TraceClaims = {
      ...tool_loop_trace({ trace_id: "loop_b" }),
      raw_output: "Exchanges run 14 days.",
      trace: [
        { role: "system", content: "You are a support agent." },
        { role: "user", content: "And the exchange window?" },
        {
          role: "assistant",
          content: null,
          tool_calls: [
            {
              id: "call_2",
              type: "function",
              function: {
                name: "lookup_policy",
                arguments: '{"topic": "exchanges"}',
              },
            },
          ],
        },
        {
          role: "tool",
          content: '{"output": "Exchanges accepted within 14 days."}',
          tool_call_id: "call_2",
        },
        { role: "assistant", content: "Exchanges run 14 days." },
      ] as TraceMessage[],
    }
    const { container, getByText } = render_trace_first([first, second])
    expect(expanded_rows(section(container, "output"))).toEqual([
      false,
      false,
      false,
      true,
    ])

    // Grade the current trace so Next opens, then move on.
    await fireEvent.click(getByText("Fail"))
    await fireEvent.click(getByText("Next"))

    const output = section(container, "output")
    expect(linear_role_labels(output)).toEqual([
      "Assistant",
      "Tool",
      "Assistant",
    ])
    expect(expanded_rows(output)).toEqual([false, false, true])
    expect(rendered_pre_text(output)).toContain("Exchanges run 14 days.")
    expect(rendered_pre_text(output)).not.toContain(
      "Exchanges accepted within 14 days.",
    )
  })

  it("renders a record pair as two plain fields, with no accordion", () => {
    // A stored two-message record, and the echo a traceless run synthesizes:
    // one message after the input, so there is no sequence to order.
    const stored = render_trace_first([
      {
        ...short_single_turn_trace(),
        trace: [
          { role: "user", content: "What's the return window?" },
          { role: "assistant", content: "Our return window is 30 days." },
        ] as TraceMessage[],
      },
    ])
    expect(stored.container.querySelectorAll(".collapse")).toHaveLength(0)
    expect(section(stored.container, "output").textContent).toContain(
      "Our return window is 30 days.",
    )
    cleanup()

    const traceless = render_trace_first([short_single_turn_trace()])
    expect(traceless.container.querySelectorAll(".collapse")).toHaveLength(0)
    expect(section(traceless.container, "output").textContent).toContain(
      "Our return window is 30 days.",
    )
  })

  it("shows raw_output when the answer is a tool call with null content", () => {
    // A function-calling run stores its answer in the call's arguments and
    // leaves content null. Reading the message alone left the section BLANK on
    // a run that answered.
    const raw_output = '{"window_days": 30}'
    const { container } = render_trace_first([
      {
        ...short_single_turn_trace(),
        raw_output,
        trace: [
          { role: "user", content: "What's the return window?" },
          {
            role: "assistant",
            content: null,
            tool_calls: [
              {
                id: "call_1",
                type: "function",
                function: {
                  name: "final_answer",
                  arguments: raw_output,
                },
              },
            ],
          },
        ] as TraceMessage[],
      },
    ])
    expect(section(container, "output").textContent).toContain('"window_days"')
    expect(section(container, "output").textContent).toContain("30")
  })

  it("reports a missing output in the Output slot, keeping the Input", () => {
    // The run recorded no answer anywhere. That is worth saying loudly, but
    // the input it was given is still on the record and still readable — an
    // error covering both sections would hide it for no reason.
    const { container, getByText } = render_trace_first([
      {
        ...short_single_turn_trace(),
        raw_output: "",
        trace: [
          { role: "user", content: "What's the return window?" },
          { role: "assistant", content: null },
        ] as TraceMessage[],
      },
    ])
    expect(section(container, "input").textContent).toContain(
      "What's the return window?",
    )
    const output = section(container, "output")
    expect(output.textContent).toContain("recorded no output")
    expect(output.querySelector("[class*='text-error']")).not.toBeNull()
    // And the grade goes with it: scoping the error to the Output section is
    // what leaves the reviewer something to answer. A run that returned
    // nothing is a gradable result, not a trace they have to skip.
    expect(getByText("Does this example pass?")).toBeTruthy()
  })

  it("shows a lone tool call rather than an empty output", () => {
    // The answer never resolved, but the call the model made is real content
    // and the rows can render it.
    const { container } = render_trace_first([
      {
        ...short_single_turn_trace(),
        raw_output: "",
        trace: [
          { role: "user", content: "What's the return window?" },
          {
            role: "assistant",
            content: null,
            tool_calls: [
              {
                id: "call_1",
                type: "function",
                function: {
                  name: "lookup_policy",
                  arguments: '{"topic": "returns"}',
                },
              },
            ],
          },
        ] as TraceMessage[],
      },
    ])
    const output = section(container, "output")
    expect(output.textContent).not.toContain("recorded no output")
    expect(linear_role_labels(output)).toEqual(["Assistant"])
    expect(output.textContent).toContain("lookup_policy")
  })

  it("keeps the whole-surface error when there is nothing to render", () => {
    // No transcript and no raws: no input either, so the error owns the page.
    const { container, queryByText } = render_trace_first([
      { ...short_single_turn_trace(), raw_input: "", raw_output: "" },
    ])
    expect(container.textContent).toContain("no transcript and no raw input")
    expect(container.querySelector("[data-testid='review-input']")).toBeNull()
    expect(queryByText("Does this example pass?")).toBeNull()
  })

  it("keeps expanded rows through a claims build landing mid-review", async () => {
    // The parent rebuilds its whole trace array whenever a background claims
    // build finishes. That churn must not reach the rows: a reviewer who
    // opened a tool result should not watch it snap shut.
    const traces = [tool_loop_trace({ claims_state: "unbuilt", claims: null })]
    const verdicts = build_trace_reviews(traces)
    const { container, rerender } = render(ClaimEvidenceReview, {
      props: {
        traces,
        verdicts,
        selected_indices: [0],
        judged_noun: "example",
      },
    })
    const output = () => section(container, "output")
    const tool_row = [...output().querySelectorAll(".collapse")].find(
      (block) =>
        block.querySelector(".collapse-title > span")?.textContent?.trim() ===
        "Tool",
    )!
    await fireEvent.click(
      tool_row.querySelector<HTMLInputElement>("input[type=checkbox]")!,
    )
    expect(expanded_rows(output())).toEqual([false, false, true, true])

    // What patch_trace_claims does: a new array, a new object for the patched
    // trace, same trace_id and same stored transcript.
    await rerender({
      traces: traces.map((t) => ({
        ...t,
        claims_state: "built" as const,
        claims: [],
      })),
    })
    expect(expanded_rows(output())).toEqual([false, false, true, true])
    expect(rendered_pre_text(output())).toContain(
      "Returns accepted within 30 days.",
    )
  })
})

// A single-turn trace the LENGTH gate sends claims-first: the output is over
// the cutoff, so the trace lives behind View Full Trace — which is how the
// single-turn path through the modal is reached.
function long_single_turn(base: TraceClaims): TraceClaims {
  return {
    ...base,
    raw_output: `${base.raw_output}\n\n${"padding. ".repeat(CHAR_CUTOFF / 5)}`,
  }
}

function render_single_turn_claims_first(traces: TraceClaims[]) {
  return render(ClaimEvidenceReview, {
    props: {
      traces,
      verdicts: build_trace_reviews(traces),
      selected_indices: [0],
      judged_noun: "example",
      is_multi_turn: false,
    },
  })
}

describe("the trace modal — single-turn", () => {
  it("shows the same two sections the inline surface shows", async () => {
    const traces = [long_single_turn(tool_loop_trace())]
    const { container, getAllByText } = render_single_turn_claims_first(traces)
    await fireEvent.click(getAllByText("View Full Trace")[0])
    const dialog = trace_dialog(container)

    // Input field, output rows, final answer already open — the anatomy, not
    // a chat and not a raw pair of panels.
    expect(section(dialog, "input").textContent).toContain(
      "What's the return window?",
    )
    expect(tinted(section(dialog, "input"), "bg-base-200")).not.toBeNull()
    expect(tinted(section(dialog, "output"), "bg-primary/5")).not.toBeNull()
    expect(linear_role_labels(section(dialog, "output"))).toEqual([
      "Assistant",
      "Assistant",
      "Tool",
      "Assistant",
    ])
    expect(expanded_rows(section(dialog, "output"))).toEqual([
      false,
      false,
      false,
      true,
    ])
    expect(chat_bubbles(dialog)).toHaveLength(0)
    expect(dialog.textContent).not.toContain("You are a support agent.")
    // The input is not repeated as a row inside the output.
    expect(occurrences(dialog.textContent ?? "", traces[0].raw_input)).toBe(1)
  })

  it("marks an input citation inside the Input field", async () => {
    const citation: Citation = {
      marker: 1,
      source: "input",
      from: "return window",
      to: "window?",
    }
    const traces = [long_single_turn(tool_loop_trace({}, [citation]))]
    const { container, getByTitle } = render_single_turn_claims_first(traces)
    await expand_claims(container)
    await fireEvent.click(getByTitle("View in trace"))
    const dialog = trace_dialog(container)
    const mark = dialog.querySelector("mark")

    expect(mark?.textContent).toBe("return window?")
    // In the Input field, not somewhere in the output.
    expect(mark?.closest("[data-testid='review-input']")).not.toBeNull()
  })

  it("marks an output citation inside the row that holds it", async () => {
    // The citation points INTO the rows rather than replacing them: the row
    // holding the cited text opens and the mark goes in where it sits, so the
    // reviewer keeps the tool loop they were reading.
    const citation: Citation = {
      marker: 1,
      source: "output",
      from: "30 days",
      to: "30 days",
    }
    const traces = [long_single_turn(tool_loop_trace({}, [citation]))]
    const { container, getByTitle } = render_single_turn_claims_first(traces)
    await expand_claims(container)
    await fireEvent.click(getByTitle("View in trace"))
    await tick()
    const dialog = trace_dialog(container)
    const mark = dialog.querySelector("mark")

    expect(mark?.textContent).toBe("30 days")
    expect(mark?.closest("[data-testid='review-output']")).not.toBeNull()
    // The rows are still on screen, and the mark is inside one of them.
    expect(
      linear_role_labels(section(dialog, "output")).length,
    ).toBeGreaterThan(0)
    expect(mark?.closest(".collapse-content")).not.toBeNull()
    // The final answer's row, not the tool result that says the same thing.
    const output_rows = [
      ...section(dialog, "output").querySelectorAll(".collapse"),
    ]
    expect(mark?.closest(".collapse")).toBe(output_rows[output_rows.length - 1])
    // The Input field is untouched by an output citation.
    expect(section(dialog, "input").querySelector("mark")).toBeNull()
  })

  it("goes back to the rows once the citation clears", async () => {
    const citation: Citation = {
      marker: 1,
      source: "output",
      from: "30 days",
      to: "30 days",
    }
    const traces = [long_single_turn(tool_loop_trace({}, [citation]))]
    const { container, getByTitle, getAllByText } =
      render_single_turn_claims_first(traces)
    await expand_claims(container)
    await fireEvent.click(getByTitle("View in trace"))
    expect(trace_dialog(container).querySelector("mark")).not.toBeNull()

    // Browsing the same trace: the section is a reader again, not a highlight.
    await fireEvent.click(getAllByText("View Full Trace")[0])
    const dialog = trace_dialog(container)
    expect(dialog.querySelector("mark")).toBeNull()
    expect(
      linear_role_labels(section(dialog, "output")).length,
    ).toBeGreaterThan(0)
  })
})

describe("the trace modal — multi-turn", () => {
  it("shows the conversation alone, with no panels around it", async () => {
    const traces = [echoing_trace()]
    const { container, getAllByText } = render_multi_turn(traces)
    // Two buttons open it (the header and the final-judgement card); either
    // one lands on the same modal.
    await fireEvent.click(getAllByText("View Full Trace")[0])
    const dialog = trace_dialog(container)
    const text = dialog.textContent ?? ""

    expect(dialog.querySelector("[data-testid='chat-msg-user']")).not.toBeNull()
    // No labelled panels, and the opening user message appears once: it IS
    // the input, so a panel above the conversation would print it twice.
    expect(text).not.toContain("Input")
    expect(text).not.toContain("Output")
    expect(occurrences(text, traces[0].raw_input)).toBe(1)
    // The assistant turn renders too (the fixture echoes it as raw_output),
    // so "alone" means without chrome, not without the conversation.
    expect(text).toContain(traces[0].raw_output)
    // The single-turn sections are nowhere near this arm.
    expect(dialog.querySelector("[data-testid='review-input']")).toBeNull()
    // The conversation gets the widest dialog the house chrome offers.
    expect(dialog.querySelector(".modal-box")?.className).toContain("max-w-7xl")
  })

  it("goes back to the plain conversation once the citation clears", async () => {
    const citation: Citation = {
      marker: 1,
      source: "input",
      from: "return window on",
      to: "mattress?",
    }
    const traces = [echoing_trace([citation])]
    const { container, getByTitle, getAllByText } = render_multi_turn(traces)
    await expand_claims(container)
    await fireEvent.click(getByTitle("View in trace"))
    expect(trace_dialog(container).querySelector("mark")).not.toBeNull()

    // Browsing the same trace: the conversation renders unhighlighted.
    await fireEvent.click(getAllByText("View Full Trace")[0])
    const dialog = trace_dialog(container)
    expect(dialog.querySelector("mark")).toBeNull()
    expect(dialog.querySelector("[data-testid='chat-msg-user']")).not.toBeNull()
  })

  it("renders a tool loop as chat, not as the single-turn rows", async () => {
    const { container, getAllByText } = render_multi_turn([tool_loop_trace()])
    await fireEvent.click(getAllByText("View Full Trace")[0])
    const dialog = trace_dialog(container)

    expect(chat_bubbles(dialog).length).toBeGreaterThan(0)
    expect(dialog.querySelector("[data-testid='review-output']")).toBeNull()
  })

  it("keeps both raw panels when the run recorded no trace", async () => {
    const traces = [{ ...echoing_trace(), trace: null }]
    const { container, getAllByText } = render_multi_turn(traces)
    await fireEvent.click(getAllByText("View Full Trace")[0])
    const dialog = trace_dialog(container)
    const text = dialog.textContent ?? ""

    expect(dialog.querySelector("[data-testid='chat-msg-user']")).toBeNull()
    expect(text).toContain("Input")
    expect(text).toContain("Output")
    expect(text).toContain(traces[0].raw_input)
    expect(text).toContain(traces[0].raw_output)
  })

  it("keeps the panels raw, in the tints the shipped modal uses", async () => {
    // The no-conversation fallback is untouched by the single-turn work: its
    // Input panel is neutral base-100 raw text, not the review field's
    // tinted, content-typed rendering. A JSON input reads here as it shipped.
    const raw_input = '{"question": "return window?"}'
    const traces = [{ ...echoing_trace(), raw_input, trace: null }]
    const { container, getAllByText } = render_multi_turn(traces)
    await fireEvent.click(getAllByText("View Full Trace")[0])
    const dialog = trace_dialog(container)

    const panel = [...dialog.querySelectorAll("div")].find((d) =>
      d.className.includes("bg-base-100"),
    )
    expect(panel).not.toBeUndefined()
    expect(panel?.className).toContain("whitespace-pre-wrap")
    // Raw: the compact source string, not Output's pretty-printed panel.
    expect(panel?.textContent?.trim()).toBe(raw_input)
    expect(panel?.querySelector("pre")).toBeNull()
    expect(dialog.querySelector("[data-testid='review-input']")).toBeNull()
  })

  it("marks an input citation on the opening user bubble", async () => {
    const citation: Citation = {
      marker: 1,
      source: "input",
      from: "return window on",
      to: "mattress?",
    }
    const traces = [echoing_trace([citation])]
    const { container, getByTitle } = render_multi_turn(traces)
    await expand_claims(container)
    await fireEvent.click(getByTitle("View in trace"))
    const dialog = trace_dialog(container)
    const mark = dialog.querySelector("mark")

    // The span resolved against raw_input, not raw_output — both texts carry
    // "return window", only the input carries the rest of the anchor. On
    // multi-turn the input IS the conversation's opening message, so the
    // citation lands on that bubble.
    expect(mark?.textContent).toBe("return window on a mattress?")
    expect(mark?.closest("[data-testid='chat-msg-user']")).not.toBeNull()
    expect(dialog.querySelectorAll("mark").length).toBe(1)
  })

  it("marks an output citation on the chat node it came from", async () => {
    const citation: Citation = {
      marker: 1,
      source: "output",
      from: "30 days",
      to: "30 days",
    }
    const traces = [echoing_trace([citation])]
    const { container, getByTitle } = render_multi_turn(traces)
    await expand_claims(container)
    await fireEvent.click(getByTitle("View in trace"))
    const dialog = trace_dialog(container)

    const mark = dialog.querySelector("mark")
    expect(mark?.textContent).toBe("30 days")
    expect(mark?.hasAttribute("data-highlight-target")).toBe(true)
  })
})
