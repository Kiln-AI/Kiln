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
})
