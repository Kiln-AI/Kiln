// @vitest-environment jsdom
import {
  describe,
  it,
  expect,
  afterEach,
  beforeAll,
  afterAll,
  vi,
} from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import { tick } from "svelte"
import ClaimTraceModal from "./claim_trace_modal.svelte"
import type { Citation, TraceClaims } from "./claim_evidence"
import type { TraceMessage } from "$lib/types"

// The happy path — an input citation landing on the opening user bubble of a
// conversation shown on its own — is pinned end-to-end through the review
// component (claim_evidence_review.test.ts); this file covers the modal's
// fallback and observability behavior.

const original_scroll_into_view = Element.prototype.scrollIntoView
let original_show_modal: unknown
let original_close: unknown
beforeAll(() => {
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = function () {}
  }
  // jsdom's <dialog> doesn't reliably implement showModal()/close(); minimal
  // stubs keep the `open` flag in sync so the dialog's content renders.
  const proto = HTMLDialogElement.prototype as unknown as Record<
    string,
    unknown
  >
  original_show_modal = proto.showModal
  original_close = proto.close
  proto.showModal = function () {
    ;(this as unknown as { open: boolean }).open = true
  }
  proto.close = function () {
    ;(this as unknown as { open: boolean }).open = false
  }
})
afterAll(() => {
  Element.prototype.scrollIntoView = original_scroll_into_view
  const proto = HTMLDialogElement.prototype as unknown as Record<
    string,
    unknown
  >
  proto.showModal = original_show_modal
  proto.close = original_close
})
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

const RAW_INPUT = "I want to return my order from last week."

// A multi-turn conversation whose opening user message IS raw_input (the
// server derives raw_input from it verbatim) plus the flattener's rendering
// of the whole conversation as raw_output.
const CONVERSATION: TraceMessage[] = [
  { role: "user", content: RAW_INPUT },
  { role: "assistant", content: "Happy to help with the return." },
] as unknown as TraceMessage[]

const RAW_OUTPUT = [
  `user:\n<user_message>\n${RAW_INPUT}\n</user_message>`,
  "assistant:\n<assistant_message>\nHappy to help with the return.\n</assistant_message>",
].join("\n\n")

function multi_turn_trace(overrides: Partial<TraceClaims> = {}): TraceClaims {
  return {
    trace_id: "batch1_case_0",
    leaf_run_id: "run_0",
    raw_input: RAW_INPUT,
    raw_output: RAW_OUTPUT,
    judge_score: "pass",
    judge_reasoning: "Helped with the return.",
    claims: [],
    final_judgement: null,
    claims_state: "built",
    claims_error: null,
    trace: CONVERSATION,
    ...overrides,
  }
}

function input_citation(): Citation {
  return {
    marker: 1,
    source: "input",
    from: "return my order",
    to: "return my order",
  }
}

describe("claim_trace_modal — citation mapping fallbacks", () => {
  it("shows an unmappable input citation without a highlight", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    // An opening message that differs from raw_input: the chat mapping
    // refuses. The conversation is the whole modal on this arm, so there is
    // no second copy of the input to mark instead.
    const diverged = multi_turn_trace({
      trace: [
        { role: "user", content: "A different opening entirely." },
        { role: "assistant", content: "Happy to help with the return." },
      ] as unknown as TraceMessage[],
    })
    const { container, component } = render(ClaimTraceModal, {
      props: { single_turn: false },
    })
    component.open_citation(diverged, input_citation())
    await tick()

    expect(
      container.querySelector("[data-testid='chat-msg-user']"),
    ).not.toBeNull()
    expect(container.querySelector("mark")).toBeNull()
    // The silent miss is observable.
    expect(warn).toHaveBeenCalled()
  })

  it("logs a span that resolves but maps onto no single chat node", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    const { container, component } = render(ClaimTraceModal, {
      props: { single_turn: false },
    })
    // Both anchors exist in raw_output but in different blocks (user turn →
    // assistant turn), so the span straddles the flattener's tag chrome and
    // map_output_span_to_trace refuses.
    component.open_citation(multi_turn_trace(), {
      marker: 1,
      source: "output",
      from: "return my order",
      to: "Happy to help",
    })
    await tick()

    expect(container.querySelector("mark")).toBeNull()
    expect(warn).toHaveBeenCalled()
  })

  it("rejects a highlight onto a row the chat never draws", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    // The flattener emits a block for the system prompt but ChatTrace drops
    // system rows — passing the highlight through would target nothing,
    // silently. It must be treated as a miss instead.
    const system_text = "You must never invent policy."
    const trace_with_system = [
      { role: "system", content: system_text },
      ...CONVERSATION,
    ] as unknown as TraceMessage[]
    const raw_output = [
      `system:\n<system_message>\n${system_text}\n</system_message>`,
      RAW_OUTPUT,
    ].join("\n\n")
    const { container, component } = render(ClaimTraceModal, {
      props: { single_turn: false },
    })
    component.open_citation(
      multi_turn_trace({ trace: trace_with_system, raw_output }),
      {
        marker: 1,
        source: "output",
        from: "never invent policy",
        to: "never invent policy",
      },
    )
    await tick()

    expect(container.querySelector("mark")).toBeNull()
    expect(warn).toHaveBeenCalled()
  })

  it("does not warn on an empty trace — the raw panels carry the mark", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    const { container, component } = render(ClaimTraceModal, {
      props: { single_turn: false },
    })
    component.open_citation(multi_turn_trace({ trace: [] }), input_citation())
    await tick()

    // No chat renders; the Input panel marks the citation as it always has.
    const panel_mark = container.querySelector("[data-citation-mark]")
    expect(panel_mark?.textContent).toBe("return my order")
    expect(warn).not.toHaveBeenCalled()
  })
})
