// @vitest-environment jsdom
import { describe, it, expect, afterAll, afterEach, beforeAll } from "vitest"
import { render, fireEvent, cleanup } from "@testing-library/svelte"
import { tick } from "svelte"
import ClaimEvidenceReview from "./claim_evidence_review.svelte"
import {
  build_claim_review_payload,
  build_trace_reviews,
  is_trace_reviewed,
  type Citation,
  type TraceClaims,
} from "./claim_evidence"
import type { TraceMessage } from "$lib/types"

// jsdom does not implement HTMLDialogElement.showModal/close. The trace
// modal's Dialog calls them, so polyfill with no-ops that just track the open
// state.
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

// A short single-turn trace with its claims built — the review renders the
// verdict card and folds the claims under it; the trace itself sits behind
// View Full Trace.
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

// Render the review on its own — the verdict card and the folded claims, with
// the trace still behind its button.
function render_review(
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

// Render the review and open the trace modal, returning the DIALOG as
// `container`. The Input/Output sections render only inside that modal now, so
// every section assertion below reads the surface the reviewer actually opens.
async function render_trace_sections(
  traces: TraceClaims[],
  verdicts = build_trace_reviews(traces),
) {
  const rendered = render(ClaimEvidenceReview, {
    props: {
      traces,
      verdicts,
      selected_indices: traces.map((_, i) => i),
      judged_noun: "example",
    },
  })
  await fireEvent.click(rendered.getAllByText("View Full Trace")[0])
  return { verdicts, ...rendered, container: trace_dialog(rendered.container) }
}

// The span the trace modal highlighted for the citation just clicked — only
// that view renders a <mark>, so its text identifies both which view opened
// and where in the trace it landed.
function cited_text(container: HTMLElement): string | null {
  return container.querySelector("mark")?.textContent ?? null
}

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
    const { container, getByText } = render_review([
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
    const { container, getByText } = render_review([
      {
        ...trace_with_placeholder_reasoning(),
        claims: null,
        final_judgement: null,
        claims_state: "error" as const,
        claims_error: "Copilot request failed.",
      },
    ])

    await fireEvent.click(getByText("Incorrect"))
    expect(container.textContent).toContain(PLACEHOLDER_REASONING)
  })

  it("falls back to judge_reasoning when the final judgement's text is empty", async () => {
    // The judgement still carries citations: they belong to the sentence that
    // was dropped, so they must go with it rather than chip the judge's
    // placeholder with evidence for text nobody is reading.
    const { container, getByText } = render_review([
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
    // The build SUCCEEDED but distilled nothing — a failed build states its
    // verdict instead of asking blind, so it has no reveal to close.
    const { getByText } = render_review([
      {
        ...trace_with_placeholder_reasoning(),
        judge_reasoning: "",
        claims: [],
        final_judgement: null,
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
    const revealed = render_review([trace_with_placeholder_reasoning()])
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

describe("ClaimEvidenceReview — the claims disclosure folds on every move", () => {
  it("re-folds the claims when the reviewer moves to the next example", async () => {
    // The card asks blind. Carrying an expansion forward would answer part of
    // the next example before its question is put.
    const traces = [short_single_turn_trace(), short_single_turn_trace()]
    const { getByText, queryByText } = render_review(traces)

    await fireEvent.click(getByText("Claims"))
    expect(queryByText(/The main facts the judge used/)).toBeTruthy()

    await fireEvent.click(getByText("Pass"))
    await fireEvent.click(getByText("Next"))
    expect(queryByText(/The main facts the judge used/)).toBeNull()
  })

  it("re-folds them walking back too", async () => {
    const traces = [short_single_turn_trace(), short_single_turn_trace()]
    const { getByText, queryByText } = render_review(traces)

    await fireEvent.click(getByText("Pass"))
    await fireEvent.click(getByText("Next"))
    await fireEvent.click(getByText("Claims"))
    expect(queryByText(/The main facts the judge used/)).toBeTruthy()

    await fireEvent.click(getByText("Previous"))
    expect(queryByText(/The main facts the judge used/)).toBeNull()
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

describe("the trace modal — one rendering for both arms", () => {
  it("renders a single-turn trace as a conversation, not as labelled panels", async () => {
    // A single-turn run is a conversation of one turn, so it opens in the same
    // chat view multi-turn does. The Input/Output panels the arm used to get
    // are gone, and with them the second copy of the citation mapping.
    const { container, getAllByText } = render_review([tool_loop_trace()])
    await fireEvent.click(getAllByText("View Full Trace")[0])
    const dialog = trace_dialog(container)

    expect(dialog.querySelector("[data-testid='chat-msg-user']")).not.toBeNull()
    expect(chat_bubbles(dialog).length).toBeGreaterThan(0)
    expect(dialog.querySelector("[data-testid='review-input']")).toBeNull()
    expect(dialog.querySelector("[data-testid='review-output']")).toBeNull()
  })

  it("shows a single-turn tool loop's calls and results as trace nodes", async () => {
    // The reason the shared view is worth adopting: the chat surface renders
    // tool activity as first-class nodes, which the panels never did.
    const { container, getAllByText } = render_review([tool_loop_trace()])
    await fireEvent.click(getAllByText("View Full Trace")[0])
    const dialog = trace_dialog(container)

    // The tool call is a node of its own. Its arguments and result sit behind
    // the node's own disclosure — collapsed until the reviewer opens it, or
    // until a citation targets it — so the assertion is on the node, not on
    // content the surface deliberately holds back.
    expect(
      dialog.querySelector("[data-testid='chat-msg-toolcall']"),
    ).not.toBeNull()
    expect(dialog.textContent ?? "").toContain("Toolcall")
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
