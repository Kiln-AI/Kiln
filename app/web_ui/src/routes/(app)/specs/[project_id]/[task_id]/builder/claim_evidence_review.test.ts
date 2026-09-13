// @vitest-environment jsdom
import {
  describe,
  it,
  expect,
  afterAll,
  afterEach,
  beforeAll,
  vi,
} from "vitest"
import { render, fireEvent, cleanup } from "@testing-library/svelte"
import ClaimEvidenceReview from "./claim_evidence_review.svelte"
import {
  build_claim_review_payload,
  build_trace_reviews,
  is_trace_reviewed,
  user_says_meets_spec,
  type Citation,
  type Claim,
  type JudgeScore,
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

// ── Fixtures ─────────────────────────────────────────────────────────────

const RAW_INPUT = "What is the return window on a mattress?"
const RAW_OUTPUT = "Our return window is 30 days."

function cite(from: string, to = from, source: "input" | "output" = "output") {
  return { marker: 1, source, from, to } satisfies Citation
}

function claim(text: string, overrides: Partial<Claim> = {}): Claim {
  return {
    text,
    citations: [cite("30 days")],
    is_verdict: false,
    ...overrides,
  }
}

const VERDICT_TEXT = "It fails because the window was never verified [1]."

// A built trace: an overview citing the input, one ordinary claim, and a
// second claim that is the verdict unless `verdict: false`.
function built_trace(
  id: string,
  opts: { judge_score?: JudgeScore; verdict?: boolean } = {},
): TraceClaims {
  const verdict = opts.verdict ?? true
  return {
    trace_id: id,
    leaf_run_id: `run_${id}`,
    raw_input: RAW_INPUT,
    raw_output: RAW_OUTPUT,
    judge_score: opts.judge_score ?? "fail",
    judge_reasoning: "The window was asserted with no source.",
    overview: {
      text: "The user asked about a mattress return window [1] and got a number.",
      citations: [cite("return window on", "mattress?", "input")],
    },
    claims: [
      claim("The agent stated a return window as fact [1]."),
      verdict
        ? claim(VERDICT_TEXT, { is_verdict: true })
        : claim("The agent named no policy page.", { citations: [] }),
    ],
    claims_state: "built",
    claims_error: null,
    trace: null,
  }
}

function by_id<T extends HTMLElement>(container: HTMLElement, id: string): T {
  const found = container.querySelector<T>(`#${id}`)
  if (!found) throw new Error(`no element with id ${id}`)
  return found
}

function render_review(
  traces: TraceClaims[],
  extra: Record<string, unknown> = {},
) {
  const verdicts = build_trace_reviews(traces)
  return {
    verdicts,
    ...render(ClaimEvidenceReview, {
      props: {
        traces,
        verdicts,
        selected_indices: traces.map((_, i) => i),
        judged_noun: "conversation",
        ...extra,
      },
    }),
  }
}

// Agree with every claim on the current trace.
async function agree_all(container: HTMLElement, count: number) {
  for (let i = 0; i < count; i++) {
    await fireEvent.click(by_id(container, `claim-agree-${i}`))
  }
}

function next_button(getByText: (t: string) => HTMLElement) {
  return getByText("Next") as HTMLButtonElement
}

// A mounted dialog, picked out by its title. Several are on the page at once,
// so the title is what tells them apart.
function dialog_titled(
  container: HTMLElement,
  title: string,
): HTMLDialogElement {
  const found = [...container.querySelectorAll("dialog")].find(
    (d) => d.querySelector("h3")?.textContent?.trim() === title,
  )
  if (!found) throw new Error(`no dialog titled ${title} rendered`)
  return found
}

function trace_dialog(container: HTMLElement): HTMLDialogElement {
  return dialog_titled(container, "Trace")
}

// The span the trace modal highlighted for the citation just clicked — only
// that view renders a <mark>, so its text identifies where it landed.
function cited_text(container: HTMLElement): string | null {
  return container.querySelector("mark")?.textContent ?? null
}

// ── The review surface ───────────────────────────────────────────────────

describe("ClaimEvidenceReview — overview and claims", () => {
  it("shows the overview with the trace button beside it and every claim open", async () => {
    const { container, getByText } = render_review([built_trace("t0")])

    const overview = by_id(container, "review-overview")
    expect(overview.textContent).toContain(
      "The user asked about a mattress return window",
    )
    expect(overview.querySelector("#view-full-trace")).not.toBeNull()

    // The claims are the review, so they are on screen on arrival, numbered,
    // with no disclosure to open first.
    expect(
      getByText(
        "The decisions the judge made about this conversation. Agree or disagree with each.",
      ),
    ).toBeTruthy()
    expect(by_id(container, "claim-card-0").textContent).toContain("#1")
    expect(by_id(container, "claim-card-1").textContent).toContain(VERDICT_TEXT)
    expect(
      [...container.querySelectorAll("button")].some((b) =>
        /show claims/i.test(b.textContent ?? ""),
      ),
    ).toBe(false)

    await fireEvent.click(by_id(container, "view-full-trace"))
    expect(trace_dialog(container).textContent).toContain(RAW_OUTPUT)
  })

  it("opens the trace at the span an overview chip cites", async () => {
    const { container } = render_review([built_trace("t0")])
    const chip = by_id(container, "review-overview").querySelector(
      "[title='View in trace']",
    ) as HTMLButtonElement
    expect(chip.textContent).toBe("[1]")

    await fireEvent.click(chip)
    // An input citation, so it lands in the Input panel of the raw view.
    expect(cited_text(trace_dialog(container))).toBe(
      "return window on a mattress?",
    )
  })
})

// Two paragraphs and a run of spaces: enough shape that a rendering which
// collapsed whitespace would read differently from the text as written.
const SPEC_TEXT =
  "The agent must not guess at policy details.\n\nIt may state  only the facts it was given."

const SPEC_DIALOG_TITLE = "Eval Description"

function spec_dialog(container: HTMLElement): HTMLDialogElement {
  return dialog_titled(container, SPEC_DIALOG_TITLE)
}

describe("ClaimEvidenceReview — the eval text", () => {
  it("opens the eval's description read-only from the overview header", async () => {
    const { container } = render_review([built_trace("t0")], {
      spec_text: SPEC_TEXT,
    })

    // Beside the trace button, in the overview header, not in the page body.
    const header = by_id(container, "review-overview")
    const button = by_id<HTMLButtonElement>(header, "view-eval")
    expect(button.textContent?.trim()).toBe("Eval Description")
    expect(
      button.compareDocumentPosition(by_id(header, "view-full-trace")) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()

    const dialog = spec_dialog(container)
    expect(dialog.open).toBe(false)

    await fireEvent.click(button)
    expect(dialog.open).toBe(true)
    // The text verbatim, on the house read-only surface. Output prints into a
    // pre, which is what keeps the line breaks and runs of spaces on screen.
    const shown = by_id(dialog, "spec-text")
    expect(shown.textContent?.trim()).toBe(SPEC_TEXT)
    expect(shown.querySelector("pre")?.className).toContain(
      "whitespace-pre-wrap",
    )
    // Read-only: the description is shown, never edited here.
    expect(dialog.querySelector("input, textarea")).toBeNull()
  })

  it("keeps the eval text reachable while the claims are still building", async () => {
    // Every trace starts with no overview and builds lazily. The eval text
    // matters most in that state, where nothing on screen describes the
    // conversation yet.
    const unbuilt: TraceClaims = {
      ...built_trace("t0"),
      overview: null,
      claims: null,
      claims_state: "unbuilt",
    }
    const { container } = render_review([unbuilt], { spec_text: SPEC_TEXT })
    // The Overview section renders in every state, so the escape hatches
    // never lose their header: only the body under it changes.
    expect(container.querySelector("#review-overview")).not.toBeNull()

    const button = by_id<HTMLButtonElement>(container, "view-eval")
    expect(
      button.compareDocumentPosition(by_id(container, "view-full-trace")) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()

    await fireEvent.click(button)
    const dialog = spec_dialog(container)
    expect(dialog.open).toBe(true)
    expect(by_id(dialog, "spec-text").textContent?.trim()).toBe(SPEC_TEXT)
  })

  it("reopens the same dialog after moving to the next conversation", async () => {
    // One eval-level dialog for the whole review: advancing does not tear it
    // down and rebuild it, so the text is one click away on every trace.
    const { container, getByText } = render_review(
      [built_trace("t0"), built_trace("t1")],
      { spec_text: SPEC_TEXT },
    )

    await fireEvent.click(by_id(container, "view-eval"))
    const opened = spec_dialog(container)
    expect(opened.open).toBe(true)
    // jsdom cannot submit the dialog's close form, so close it directly.
    opened.open = false

    await agree_all(container, 2)
    await fireEvent.click(next_button(getByText))
    expect(container.textContent).toContain("2 of 2")

    await fireEvent.click(by_id(container, "view-eval"))
    const reopened = spec_dialog(container)
    // The same node, not a fresh one mounted for this conversation.
    expect(reopened).toBe(opened)
    expect(reopened.open).toBe(true)
    expect(by_id(reopened, "spec-text").textContent?.trim()).toBe(SPEC_TEXT)
  })

  it("leaves the overview header alone when there is no eval text", () => {
    for (const spec_text of [null, "", "   "]) {
      const { container } = render_review([built_trace("t0")], { spec_text })
      const header = by_id(container, "review-overview")

      expect(header.querySelector("#view-eval")).toBeNull()
      expect(header.querySelector("#view-full-trace")).not.toBeNull()
      // Nothing left mounted either: no dialog carrying the eval title.
      expect(
        [...container.querySelectorAll("dialog h3")].some(
          (h) => h.textContent?.trim() === "Eval Description",
        ),
      ).toBe(false)
      cleanup()
    }
  })
})

describe("ClaimEvidenceReview — Next gating", () => {
  it("needs Agree or Disagree on every claim before Next opens", async () => {
    const { container, getByText } = render_review([
      built_trace("t0"),
      built_trace("t1"),
    ])

    expect(next_button(getByText).disabled).toBe(true)
    // Next is the screen's one primary, sized like Previous beside it, and
    // carries no keyboard hint: the shortcut fires Save, never Next.
    expect(next_button(getByText).className).toContain("btn-primary")
    expect(next_button(getByText).className).not.toContain("min-w-64")

    await fireEvent.click(by_id(container, "claim-agree-0"))
    expect(next_button(getByText).disabled).toBe(true)
    await fireEvent.click(by_id(container, "claim-agree-1"))
    expect(next_button(getByText).disabled).toBe(false)
  })

  it("holds Next until a Disagree carries a reason", async () => {
    const { container, getByText, verdicts } = render_review([
      built_trace("t0"),
      built_trace("t1"),
    ])

    await fireEvent.click(by_id(container, "claim-agree-0"))
    await fireEvent.click(by_id(container, "claim-disagree-1"))
    expect(next_button(getByText).disabled).toBe(true)

    await fireEvent.input(by_id(container, "claim-why-1"), {
      target: { value: "The window is published." },
    })
    expect(verdicts[0].claim_verdicts[1]).toEqual({
      agrees: false,
      why: "The window is published.",
    })
    expect(next_button(getByText).disabled).toBe(false)
  })
})

describe("ClaimEvidenceReview — the pass/fail call", () => {
  it("derives the call from the verdict claim's grade, and asks no Pass/Fail row", async () => {
    for (const judge_score of ["fail", "pass"] as const) {
      const traces = [built_trace("t0", { judge_score })]
      const { container, verdicts } = render_review(traces)
      expect(container.querySelector("#review-overall")).toBeNull()

      // Agreeing with the verdict claim keeps the judge's call.
      await agree_all(container, 2)
      expect(is_trace_reviewed(traces[0], verdicts[0])).toBe(true)
      expect(user_says_meets_spec(traces[0], verdicts[0])).toBe(
        judge_score === "pass",
      )

      // Disagreeing with it flips the call the other way.
      await fireEvent.click(by_id(container, "claim-disagree-1"))
      await fireEvent.input(by_id(container, "claim-why-1"), {
        target: { value: "The judge read the transcript wrong." },
      })
      expect(user_says_meets_spec(traces[0], verdicts[0])).toBe(
        judge_score !== "pass",
      )
      expect(build_claim_review_payload(traces[0], verdicts[0])).toMatchObject({
        overview: traces[0].overview?.text,
        human_verdict: judge_score === "pass" ? "fail" : "pass",
        claims: [
          { human_grade: "agree", human_feedback: null },
          {
            text: VERDICT_TEXT,
            human_grade: "disagree",
            human_feedback: "The judge read the transcript wrong.",
          },
        ],
      })
      cleanup()
    }
  })
})

describe("ClaimEvidenceReview — the forward action on the last conversation", () => {
  it("holds the slot disabled until the gate is met, never a dead Next", async () => {
    const traces = [built_trace("only")]

    // Gate not met: the same button holds the slot, simply disabled, the way
    // every other form in the app holds a submit. No Next — there's nothing
    // left to advance to.
    const gated = render_review(traces, { save_disabled: true })
    const blocked = by_id<HTMLButtonElement>(gated.container, "review-continue")
    expect(blocked.disabled).toBe(true)
    expect(gated.queryByText("Next")).toBeNull()
    expect(gated.container.querySelector(".tooltip")).toBeNull()
    cleanup()

    // Gate met on the last conversation: the same slot, now enabled.
    const open = render_review(traces, { save_disabled: false })
    const live = by_id<HTMLButtonElement>(open.container, "review-continue")
    expect(live.disabled).toBe(false)
    expect(open.queryByText("Next")).toBeNull()
    // The slot keeps one size across that flip, so it doesn't resize as the
    // gate completes — and that size is the same button Previous is.
    expect(live.className).toBe(blocked.className)
    expect(live.className).not.toContain("min-w-64")
  })

  it("reads Continue on the last case", () => {
    // The label used to flip between Save and Refine Judge with the grades.
    // It no longer does: what the click leads to is settled in the dialog it
    // opens, so the button carries one word.
    const { container } = render_review([built_trace("only")], {
      save_disabled: false,
    })
    expect(by_id(container, "review-continue").textContent?.trim()).toContain(
      "Continue",
    )
  })

  it("reports the forward action to the parent, which decides what it means", async () => {
    const on_save = vi.fn()
    const { container } = render_review([built_trace("only")], {
      save_disabled: false,
      on_save,
    })
    await fireEvent.click(by_id(container, "review-continue"))
    expect(on_save).toHaveBeenCalledTimes(1)
  })
})

function echoing_trace(citation?: Citation): TraceClaims {
  return {
    ...built_trace("echo_0", { verdict: false }),
    claims: [
      claim(
        citation
          ? "The reply answers the question [1]."
          : "The reply gives 30 days.",
        { citations: citation ? [citation] : [] },
      ),
    ],
    trace: [
      { role: "system", content: "You are a support agent." },
      { role: "user", content: RAW_INPUT },
      { role: "assistant", content: RAW_OUTPUT },
    ],
  }
}

// A run whose stored trace is a tool loop: the model called a tool, read the
// result, then answered.
function tool_loop_trace(): TraceClaims {
  return {
    ...built_trace("tool_0", { verdict: false }),
    trace: [
      { role: "system", content: "You are a support agent." },
      { role: "user", content: RAW_INPUT },
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
      { role: "assistant", content: RAW_OUTPUT },
    ] as TraceMessage[],
  }
}

// The first claim card's citation chip. The fixture's overview carries a chip
// of its own, so a title lookup over the whole page would find two.
function claim_chip(container: HTMLElement): HTMLButtonElement {
  const chip = by_id(
    container,
    "claim-card-0",
  ).querySelector<HTMLButtonElement>("[title='View in trace']")
  if (!chip) throw new Error("no citation chip on the first claim")
  return chip
}

function chat_bubbles(root: ParentNode): Element[] {
  return [...root.querySelectorAll("[data-testid^='chat-msg-']")]
}

function occurrences(haystack: string, needle: string): number {
  return haystack.split(needle).length - 1
}

describe("the trace modal — one rendering for both arms", () => {
  it("renders a single-turn trace as a conversation, not as labelled panels", async () => {
    // A single-turn run is a conversation of one turn, so it opens in the same
    // chat view multi-turn does.
    const { container } = render_review([tool_loop_trace()])
    await fireEvent.click(by_id(container, "view-full-trace"))
    const dialog = trace_dialog(container)

    expect(dialog.querySelector("[data-testid='chat-msg-user']")).not.toBeNull()
    expect(chat_bubbles(dialog).length).toBeGreaterThan(0)
    expect(dialog.querySelector("[data-testid='review-input']")).toBeNull()
    expect(dialog.querySelector("[data-testid='review-output']")).toBeNull()
  })

  it("shows a single-turn tool loop's calls and results as trace nodes", async () => {
    // The reason the shared view is worth adopting: the chat surface renders
    // tool activity as first-class nodes, which the panels never did.
    const { container } = render_review([tool_loop_trace()])
    await fireEvent.click(by_id(container, "view-full-trace"))
    const dialog = trace_dialog(container)

    expect(
      dialog.querySelector("[data-testid='chat-msg-toolcall']"),
    ).not.toBeNull()
    expect(dialog.textContent ?? "").toContain("Toolcall")
  })
})

describe("the trace modal — multi-turn", () => {
  it("shows the conversation alone, with no panels around it", async () => {
    const traces = [echoing_trace()]
    const { container } = render_review(traces)
    await fireEvent.click(by_id(container, "view-full-trace"))
    const dialog = trace_dialog(container)
    const text = dialog.textContent ?? ""

    expect(dialog.querySelector("[data-testid='chat-msg-user']")).not.toBeNull()
    // No labelled panels, and the opening user message appears once: it IS
    // the input, so a panel above the conversation would print it twice.
    expect(text).not.toContain("Input")
    expect(text).not.toContain("Output")
    expect(occurrences(text, traces[0].raw_input)).toBe(1)
    expect(text).toContain(traces[0].raw_output)
    expect(dialog.querySelector("[data-testid='review-input']")).toBeNull()
    // The conversation gets the widest dialog the house chrome offers.
    expect(dialog.querySelector(".modal-box")?.className).toContain("max-w-7xl")
  })

  it("goes back to the plain conversation once the citation clears", async () => {
    const citation = cite("return window on", "mattress?", "input")
    const { container } = render_review([echoing_trace(citation)])
    await fireEvent.click(claim_chip(container))
    expect(trace_dialog(container).querySelector("mark")).not.toBeNull()

    // Browsing the same trace: the conversation renders unhighlighted.
    await fireEvent.click(by_id(container, "view-full-trace"))
    const dialog = trace_dialog(container)
    expect(dialog.querySelector("mark")).toBeNull()
    expect(dialog.querySelector("[data-testid='chat-msg-user']")).not.toBeNull()
  })

  it("keeps both raw panels when the run recorded no trace", async () => {
    const traces = [{ ...echoing_trace(), trace: null }]
    const { container } = render_review(traces)
    await fireEvent.click(by_id(container, "view-full-trace"))
    const dialog = trace_dialog(container)
    const text = dialog.textContent ?? ""

    expect(dialog.querySelector("[data-testid='chat-msg-user']")).toBeNull()
    expect(text).toContain("Input")
    expect(text).toContain("Output")
    expect(text).toContain(traces[0].raw_input)
    expect(text).toContain(traces[0].raw_output)
  })

  it("shows the raw panels on the house read-only surface", async () => {
    // The no-conversation fallback: each panel is an Output, so the trace
    // reads the way every other read-only block in the app does, and a JSON
    // input is printed rather than shown as a typed rendering.
    const raw_input = '{"question": "return window?"}'
    const traces = [{ ...echoing_trace(), raw_input, trace: null }]
    const { container } = render_review(traces)
    await fireEvent.click(by_id(container, "view-full-trace"))
    const dialog = trace_dialog(container)

    const panel = [...dialog.querySelectorAll("div")].find((d) =>
      d.className.includes("bg-base-200"),
    )
    expect(panel).not.toBeUndefined()
    const printed = panel?.querySelector("pre")
    expect(printed?.className).toContain("whitespace-pre-wrap")
    expect(printed?.textContent?.trim()).toBe(
      JSON.stringify(JSON.parse(raw_input), null, 2),
    )
  })

  it("marks an input citation on the opening user bubble", async () => {
    const citation = cite("return window on", "mattress?", "input")
    const { container } = render_review([echoing_trace(citation)])
    await fireEvent.click(claim_chip(container))
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
    const { container } = render_review([echoing_trace(cite("30 days"))])
    await fireEvent.click(claim_chip(container))
    const dialog = trace_dialog(container)

    const mark = dialog.querySelector("mark")
    expect(mark?.textContent).toBe("30 days")
    expect(mark?.hasAttribute("data-highlight-target")).toBe(true)
  })
})

// The step header states the reviewer's position in the graded sequence: it is
// the review's only progress readout, so it must count the subset the reviewer
// actually walks rather than the whole batch.
describe("ClaimEvidenceReview — the case header", () => {
  it("counts the position within the selected subset", async () => {
    const traces = [
      built_trace("t0"),
      built_trace("t1"),
      built_trace("t2"),
      built_trace("t3"),
    ]
    // Two of the four are shown, and they are not the first two.
    const { container, getByText } = render_review(traces, {
      selected_indices: [1, 3],
    })
    const header = () => container.querySelector("h2")!.textContent

    expect(header()).toBe("Case 1 of 2")
    await agree_all(container, 2)
    await fireEvent.click(getByText("Next"))
    expect(header()).toBe("Case 2 of 2")
  })
})
