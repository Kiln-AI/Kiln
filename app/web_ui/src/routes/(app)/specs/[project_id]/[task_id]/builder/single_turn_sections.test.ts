// @vitest-environment jsdom
import { describe, it, expect, afterEach, beforeAll, afterAll } from "vitest"
import { render, cleanup, fireEvent } from "@testing-library/svelte"
import { tick } from "svelte"
import SingleTurnSectionsView from "./single_turn_sections.svelte"
import {
  resolve_citation_span,
  single_turn_sections,
  type TraceClaims,
} from "./claim_evidence"
import { CITATION_SEGMENT_ATTR } from "./citation_highlight"
import type { TraceMessage } from "$lib/types"

const original_scroll_into_view = Element.prototype.scrollIntoView
beforeAll(() => {
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = function () {}
  }
})
afterAll(() => {
  Element.prototype.scrollIntoView = original_scroll_into_view
})
afterEach(() => {
  cleanup()
})

// A tool loop: the model says what it is about to do, calls a tool, reads the
// result, then answers. The Output section renders this as rows, and only the
// FINAL answer is open — so a citation into any earlier row has no rendered
// text to mark until that row is opened.
const TOOL_LOOP: TraceMessage[] = [
  { role: "user", content: "Find brand mentions for Acme." },
  {
    role: "assistant",
    content: "I will search the web for Acme mentions first.",
    tool_calls: [
      {
        id: "call_1",
        type: "function",
        function: { name: "web_search", arguments: '{"q":"Acme"}' },
      },
    ],
  },
  { role: "tool", tool_call_id: "call_1", content: '{"results":3}' },
  { role: "assistant", content: "Acme has three mentions this week." },
] as unknown as TraceMessage[]

function trace_claims(): TraceClaims {
  return {
    trace_id: "batch1_case_0",
    leaf_run_id: "run_0",
    raw_input: "Find brand mentions for Acme.",
    raw_output: "Acme has three mentions this week.",
    judge_score: "pass",
    judge_reasoning: "Answered from the tool result.",
    claims: [],
    final_judgement: null,
    claims_state: "built",
    claims_error: null,
    trace: TOOL_LOOP,
  }
}

function cited_props(from: string, to: string) {
  const trace = trace_claims()
  const span = resolve_citation_span(trace.raw_output, { from, to })
  return {
    sections: single_turn_sections(trace),
    cited: {
      source: "output" as const,
      text: trace.raw_output,
      span: span ?? { start: 0, end: trace.raw_output.length },
      anchors: { from, to },
    },
  }
}

function rows(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll(".collapse-content"))
}

function row_boxes(container: HTMLElement): HTMLInputElement[] {
  return Array.from(
    container.querySelectorAll<HTMLInputElement>(
      ".collapse input[type=checkbox]",
    ),
  )
}

// The citation mark is applied on a microtask after each render, and re-opening
// a row costs a further render and microtask, so a settled surface is a few
// turns of both away.
async function settle(): Promise<void> {
  for (let i = 0; i < 5; i++) await tick()
}

function segment_text(el: HTMLElement): string {
  return Array.from(el.querySelectorAll(`[${CITATION_SEGMENT_ATTR}]`))
    .map((m) => m.textContent)
    .join("")
}

describe("single_turn_sections — a citation into the rows", () => {
  it("opens the row that holds it and marks it there", async () => {
    // The cited row is the model's FIRST turn, which the section does not open
    // on its own — the final answer is what opens by default.
    const { container } = render(
      SingleTurnSectionsView,
      cited_props("search the web", "Acme mentions"),
    )
    await tick()

    const row = rows(container)[0]
    const marks = Array.from(row.querySelectorAll(`[${CITATION_SEGMENT_ATTR}]`))
    expect(marks.map((m) => m.textContent).join("")).toBe(
      "search the web for Acme mentions",
    )
    // The rows are still rows: the section did not drop to the raw text.
    expect(rows(container)).toHaveLength(3)
    expect(row.textContent).toContain(
      "I will search the web for Acme mentions first.",
    )
  })

  it("marks inside a row whose content is rendered as JSON", async () => {
    // The tool result renders through the Output idiom like any structured
    // content, so the anchors have to survive pretty-printing here too.
    const { container } = render(
      SingleTurnSectionsView,
      cited_props('{"results":3}', '{"results":3}'),
    )
    await tick()

    const row = rows(container)[1]
    expect(
      row.querySelector(`[${CITATION_SEGMENT_ATTR}]`)?.textContent,
    ).toBeDefined()
    expect(
      Array.from(row.querySelectorAll(`[${CITATION_SEGMENT_ATTR}]`))
        .map((m) => m.textContent)
        .join(""),
    ).toBe('{\n  "results": 3\n}')
  })

  it("leaves the reviewer's own open rows alone when the citation clears", async () => {
    // Opening the cited row costs a remount, and a remount rebuilds every row's
    // expansion from scratch. Clearing a citation must not pay that price: the
    // rows the reviewer opened by hand while reading are theirs to keep, and
    // only the mark goes away.
    const { container, rerender } = render(
      SingleTurnSectionsView,
      cited_props("search the web", "Acme mentions"),
    )
    await tick()
    const boxes = () =>
      Array.from(
        container.querySelectorAll<HTMLInputElement>(
          ".collapse input[type=checkbox]",
        ),
      )
    // The cited row plus the final answer the section opens anyway.
    expect(boxes().filter((b) => b.checked)).toHaveLength(2)

    // The reviewer opens the remaining row themselves.
    const shut = boxes().find((b) => !b.checked)!
    await fireEvent.click(shut)
    expect(boxes().filter((b) => b.checked)).toHaveLength(3)

    await rerender({ cited: null })
    await tick()

    expect(boxes().filter((b) => b.checked)).toHaveLength(3)
    expect(
      container.querySelectorAll(`[${CITATION_SEGMENT_ATTR}]`),
    ).toHaveLength(0)
  })

  it("re-opens the cited row when the reviewer collapsed it and the surface re-fires", async () => {
    // A background claims build reassigns the review's traces, which re-runs
    // the citation resolution. The cited row is collapsed by then and renders
    // no text, so the mark cannot land; the section owes the reviewer the row
    // back, not the raw output.
    const props = cited_props("search the web", "Acme mentions")
    const { container, rerender } = render(SingleTurnSectionsView, props)
    await settle()
    expect(segment_text(rows(container)[0])).toBe(
      "search the web for Acme mentions",
    )

    await fireEvent.click(row_boxes(container)[0])
    expect(row_boxes(container)[0].checked).toBe(false)

    // The same citation arriving again as a new object, which is what the
    // review page hands down when its trace list is rebuilt.
    await rerender({ cited: { ...props.cited } })
    await settle()

    expect(rows(container)).toHaveLength(3)
    expect(row_boxes(container)[0].checked).toBe(true)
    expect(segment_text(rows(container)[0])).toBe(
      "search the web for Acme mentions",
    )

    // Each successful placement re-arms the re-open, so the rescue is not a
    // one-shot: later collapse-then-re-fire rounds get the row back too.
    for (const _round of [2, 3]) {
      await fireEvent.click(row_boxes(container)[0])
      expect(row_boxes(container)[0].checked).toBe(false)
      await rerender({ cited: { ...props.cited } })
      await settle()
      expect(rows(container)).toHaveLength(3)
      expect(row_boxes(container)[0].checked).toBe(true)
      expect(segment_text(rows(container)[0])).toBe(
        "search the web for Acme mentions",
      )
    }
  })

  it("keeps the rows when the reviewer collapses the cited row and nothing re-fires", async () => {
    // Collapsing is the reviewer's own action. It takes the mark off screen
    // with the row, and that is all it does — the section is not rewritten
    // underneath them.
    const { container } = render(
      SingleTurnSectionsView,
      cited_props("search the web", "Acme mentions"),
    )
    await settle()

    await fireEvent.click(row_boxes(container)[0])
    await settle()

    expect(rows(container)).toHaveLength(3)
    expect(row_boxes(container)[0].checked).toBe(false)
  })

  it("leaves rows the reviewer opened by hand alone across a background re-fire", async () => {
    // The re-open is scoped to the CITED row. A re-fire that finds its mark
    // still in place changes nothing, so no remount takes the reviewer's own
    // open rows with it.
    const props = cited_props("search the web", "Acme mentions")
    const { container, rerender } = render(SingleTurnSectionsView, props)
    await settle()

    const shut = row_boxes(container).find((b) => !b.checked)!
    await fireEvent.click(shut)
    expect(row_boxes(container).filter((b) => b.checked)).toHaveLength(3)

    await rerender({ cited: { ...props.cited } })
    await settle()

    expect(row_boxes(container).filter((b) => b.checked)).toHaveLength(3)
    expect(segment_text(rows(container)[0])).toBe(
      "search the web for Acme mentions",
    )
  })

  it("re-opens the cited row once and then takes the fallback, rather than looping", async () => {
    // The re-open is a repair with a budget, not a retry loop. A tool row is
    // matched on its whole stored content but renders only the result's
    // `output` field, so the same row can hold the anchors while the body that
    // comes back has nothing to mark. One re-open is spent on it; the section
    // then settles on the raw output instead of remounting the rows forever.
    const anchors = { from: "search the web", to: "Acme mentions" }
    const cited_text =
      "search the web for Acme mentions\nAcme has three mentions this week."
    const span = resolve_citation_span(cited_text, anchors)
    expect(span).not.toBeNull()
    // The same trace, the same cited row, with the tool result re-serialized
    // between the two renders: the anchors survive in the stored content and
    // not in the `output` field the row shows.
    const sections_holding = (result: string) => {
      const trace = trace_claims()
      trace.raw_output = cited_text
      trace.trace = [
        { role: "user", content: "Find brand mentions for Acme." },
        {
          role: "assistant",
          content: "Looking that up.",
          tool_calls: [
            {
              id: "call_1",
              type: "function",
              function: { name: "web_search", arguments: '{"q":"Acme"}' },
            },
          ],
        },
        { role: "tool", tool_call_id: "call_1", content: result },
        { role: "assistant", content: "Acme has three mentions this week." },
      ] as unknown as TraceMessage[]
      return single_turn_sections(trace)
    }
    const cited = {
      source: "output" as const,
      text: cited_text,
      span: span!,
      anchors,
    }
    const { container, rerender } = render(SingleTurnSectionsView, {
      sections: sections_holding(
        '{"output":"search the web for Acme mentions"}',
      ),
      cited,
    })
    await settle()
    expect(segment_text(rows(container)[1])).toBe(
      "search the web for Acme mentions",
    )

    // The reviewer collapses the cited row, then a background build re-fires
    // the surface — the case the re-open exists for, except that this time the
    // row it opens again cannot hold the mark either.
    await fireEvent.click(row_boxes(container)[1])
    expect(row_boxes(container)[1].checked).toBe(false)

    await rerender({
      sections: sections_holding(
        '{"output":"no matches","query":"search the web for Acme mentions"}',
      ),
      cited: { ...cited },
    })
    await settle()

    // Settled: the rows are gone and the mark is in the raw output. Reaching
    // this at all is the assertion — an unbudgeted re-open would remount the
    // rows on every failed placement and never get here.
    expect(rows(container)).toHaveLength(0)
    expect(
      container.querySelector("[data-citation-mark]")!.textContent,
    ).toContain("search the web")
  })

  it("falls back to the raw output when no row holds the citation", async () => {
    // raw_output is the judge's FLATTENED transcript, and this citation is
    // anchored on its tag chrome — text no message contains, so there is no
    // row to open and nothing in the rows to mark. The reviewer still gets the
    // mark, in the raw output the offsets do index.
    const trace = trace_claims()
    trace.raw_output =
      "assistant:\n<assistant_message>\nAcme has three mentions this week.\n</assistant_message>"
    const anchors = { from: "<assistant_message>", to: "three mentions" }
    const span = resolve_citation_span(trace.raw_output, anchors)
    expect(span).not.toBeNull()
    const { container } = render(SingleTurnSectionsView, {
      sections: single_turn_sections(trace),
      cited: {
        source: "output" as const,
        text: trace.raw_output,
        span: span!,
        anchors,
      },
    })
    await tick()

    expect(rows(container)).toHaveLength(0)
    expect(
      container.querySelector("[data-citation-mark]")!.textContent,
    ).toContain("Acme has three mentions")
  })

  it("falls back when the cited row's rendering does not carry the anchors", async () => {
    // The row holds the anchors in its stored content, but the rows render
    // through the Output idiom and re-serializing JSON drops the trailing zero
    // from 1.50. Opening the row again would not help, so the section takes the
    // raw output rather than leaving the reviewer with no mark.
    const trace = trace_claims()
    const priced = '{"price":1.50}'
    trace.trace = [
      { role: "user", content: "What does it cost?" },
      { role: "assistant", content: "Checking the price." },
      { role: "tool", tool_call_id: "call_1", content: priced },
      { role: "assistant", content: "It costs 1.5 dollars." },
    ] as unknown as TraceMessage[]
    trace.raw_output = `tool: ${priced}\nIt costs 1.5 dollars.`
    const anchors = { from: priced, to: priced }
    const span = resolve_citation_span(trace.raw_output, anchors)
    expect(span).not.toBeNull()
    const { container } = render(SingleTurnSectionsView, {
      sections: single_turn_sections(trace),
      cited: {
        source: "output" as const,
        text: trace.raw_output,
        span: span!,
        anchors,
      },
    })
    await settle()

    expect(rows(container)).toHaveLength(0)
    expect(container.querySelector("[data-citation-mark]")!.textContent).toBe(
      priced,
    )
  })
})
