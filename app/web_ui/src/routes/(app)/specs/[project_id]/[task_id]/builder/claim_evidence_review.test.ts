// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest"
import { render, fireEvent, cleanup } from "@testing-library/svelte"
import ClaimEvidenceReview from "./claim_evidence_review.svelte"
import {
  build_trace_reviews,
  is_trace_reviewed,
  type TraceClaims,
} from "./claim_evidence"

afterEach(() => {
  cleanup()
})

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
