// @vitest-environment jsdom
import { describe, it, expect, afterAll, afterEach, beforeAll } from "vitest"
import { render, fireEvent, cleanup } from "@testing-library/svelte"
import ClaimEvidenceReview from "./claim_evidence_review.svelte"
import {
  build_trace_reviews,
  is_trace_reviewed,
  type TraceClaims,
} from "./claim_evidence"

// jsdom does not implement HTMLDialogElement.showModal/close. The Dialog
// component behind View Claims calls them, so polyfill with no-ops that just
// track the open state.
const original_show_modal = HTMLDialogElement.prototype.showModal
const original_close = HTMLDialogElement.prototype.close
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
})

afterAll(() => {
  HTMLDialogElement.prototype.showModal = original_show_modal
  HTMLDialogElement.prototype.close = original_close
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

// A built trace with an EMPTY claims list — only the final-judgement card
// renders, so grading it (one "Correct" button) reviews the whole trace.
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
    await fireEvent.click(getByText("Correct"))
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

// A short, plain-text single-turn trace: the shape the gate sends
// trace-first. Its claims are built and sit behind View Claims.
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

describe("ClaimEvidenceReview — trace-first arm", () => {
  it("shows the trace and one blind question, with the judge off screen", () => {
    const traces = [short_single_turn_trace()]
    const { container, getByText, queryByText } = render_trace_first(traces)

    // The trace itself, echoed from the raws the run recorded no trace for.
    expect(container.textContent).toContain("What's the return window?")
    expect(container.textContent).toContain("Our return window is 30 days.")
    expect(getByText("Did the agent do the right thing?")).toBeTruthy()

    // Nothing states the judge's call, or the claims that argue it, before
    // the reviewer answers.
    expect(container.textContent).not.toContain("The window was asserted")
    expect(container.textContent).not.toContain("Overall, this example")
    expect(container.textContent).not.toContain("Fails Eval")
    expect(container.textContent).not.toContain("The judge marked")

    // The inverse escape hatch: claims are one click away, the trace is not
    // behind a button any more.
    expect(getByText("View Claims")).toBeTruthy()
    expect(queryByText("View Full Trace")).toBeNull()
  })

  it("a label contradicting the judge reveals it and demands a reason", async () => {
    const traces = [short_single_turn_trace("fail")]
    const { container, getByText, verdicts } = render_trace_first(traces)

    // Judge said fail, reviewer says the agent was right: a mismatch.
    await fireEvent.click(getByText("Correct"))
    expect(verdicts[0].final_judgement_verdict.agrees).toBe(false)
    expect(getByText("The judge marked this FAIL.")).toBeTruthy()
    expect(container.textContent).toContain(
      "The window was asserted with no source.",
    )
    // v1's Teach the Judge block, described by the REVIEWER's label.
    expect(getByText("Teach the Judge")).toBeTruthy()
    expect(container.textContent).toContain("Describe why this result passes.")

    // The reason is required while the mismatch stands.
    const why = container.querySelector("textarea") as HTMLTextAreaElement
    expect(why.className).toContain("textarea-error")
    expect(why.placeholder).toBe("Describe why this passes")
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

    await fireEvent.click(getByText("Incorrect"))
    expect(verdicts[0].final_judgement_verdict.agrees).toBe(true)
    expect(container.textContent).not.toContain("The judge marked")
    expect(container.querySelector("textarea")).toBeNull()
    expect(is_trace_reviewed(traces[0], verdicts[0])).toBe(true)
  })

  it("inverts on a judge-pass trace", async () => {
    const traces = [short_single_turn_trace("pass")]
    const { container, getByText, verdicts } = render_trace_first(traces)

    // Agreeing with a passing judge is the Correct label here.
    await fireEvent.click(getByText("Correct"))
    expect(verdicts[0].final_judgement_verdict.agrees).toBe(true)
    expect(container.textContent).not.toContain("The judge marked")

    await fireEvent.click(getByText("Incorrect"))
    expect(verdicts[0].final_judgement_verdict.agrees).toBe(false)
    expect(getByText("The judge marked this PASS.")).toBeTruthy()
    expect(container.textContent).toContain("Describe why this result fails.")
  })

  it("flipping back to agreement clears the reveal and the reason", async () => {
    const traces = [short_single_turn_trace("fail")]
    const { container, getByText, verdicts } = render_trace_first(traces)

    await fireEvent.click(getByText("Correct"))
    const why = container.querySelector("textarea") as HTMLTextAreaElement
    await fireEvent.input(why, {
      target: { value: "The window is documented." },
    })

    await fireEvent.click(getByText("Incorrect"))
    expect(container.textContent).not.toContain("The judge marked")
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
    await fireEvent.click(getByText("Correct"))
    await fireEvent.click(getByText("View Claims"))
    const dialog = claims_dialog(container)
    expect(dialog.open).toBe(true)
    expect(dialog.textContent).toContain(
      "The agent stated a return window as fact.",
    )
    expect(dialog.textContent).toContain("Overall, this example")

    // The blind row stays the one grading control: the dialog's cards carry
    // no Correct/Incorrect and no reason box of their own.
    expect(getAllByText("Correct")).toHaveLength(1)
    expect(getAllByText("Incorrect")).toHaveLength(1)
    expect(dialog.textContent).not.toContain("Correct")
    expect(dialog.querySelector("textarea")).toBeNull()
    // So no sub-claim grade can appear here and quietly demand a reason the
    // trace-first screen never shows.
    expect(verdicts[0].claim_verdicts.every((v) => v.agrees === null)).toBe(
      true,
    )
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
    await fireEvent.click(getByText("Incorrect"))
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
    await fireEvent.click(getByText("Correct"))
    await fireEvent.input(container.querySelector("textarea")!, {
      target: { value: "The window is documented." },
    })
    await fireEvent.click(getByText("View Claims"))
    expect(claims_dialog(container).textContent).toContain(
      "Overall, this example",
    )

    await fireEvent.click(getByText("Next"))
    // A fresh trace starts unlabelled: no reveal, no reason carried over.
    expect(container.textContent).not.toContain("The judge marked")
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
    expect(getByText("The judge marked this FAIL.")).toBeTruthy()
    expect(
      (container.querySelector("textarea") as HTMLTextAreaElement).value,
    ).toBe("The window is documented.")
    // The grade came back; the claims stay closed until asked for again.
    expect(claims_dialog(container).textContent).not.toContain(
      "Overall, this example",
    )
  })

  it("keeps the claims-first review for multi-turn and for schema'd outputs", () => {
    // Same short trace, both other gate arms: the claim stack, not the
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
    expect(multi.queryByText("Did the agent do the right thing?")).toBeNull()
    expect(multi.queryAllByText("View Full Trace").length).toBeGreaterThan(0)
    expect(multi.queryByText("View Claims")).toBeNull()
    expect(multi.container.textContent).toContain("Overall, this conversation")
    cleanup()

    const schemad = render(ClaimEvidenceReview, {
      props: {
        traces,
        verdicts: build_trace_reviews(traces),
        selected_indices: [0],
        judged_noun: "example",
        has_output_schema: true,
      },
    })
    expect(schemad.queryByText("Did the agent do the right thing?")).toBeNull()
    expect(schemad.queryAllByText("View Full Trace").length).toBeGreaterThan(0)
    expect(schemad.queryByText("View Claims")).toBeNull()
  })

  it("fails loud when a trace has neither a transcript nor raws", () => {
    const traces = [
      { ...short_single_turn_trace(), raw_input: "", raw_output: "" },
    ]
    const { container, queryByText } = render_trace_first(traces)
    expect(container.textContent).toContain("no transcript and no raw input")
    // Nothing to read means nothing to label.
    expect(queryByText("Did the agent do the right thing?")).toBeNull()
  })
})
