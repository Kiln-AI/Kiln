// @vitest-environment jsdom
import { describe, it, expect, beforeAll, afterAll, afterEach } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import { tick } from "svelte"
import ClaimTraceModal from "./claim_trace_modal.svelte"
import type { TraceClaims } from "./claim_evidence"

// jsdom does not implement HTMLDialogElement.showModal/close.
const originalShowModal = HTMLDialogElement.prototype.showModal
const originalClose = HTMLDialogElement.prototype.close

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
  // jsdom also lacks scrollIntoView, which open_citation uses on the mark.
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = function () {}
  }
})

afterAll(() => {
  HTMLDialogElement.prototype.showModal = originalShowModal
  HTMLDialogElement.prototype.close = originalClose
})

afterEach(() => cleanup())

describe("ClaimTraceModal", () => {
  it("open_trace renders input and output from a plain transcript object", async () => {
    // The reuse contract: non-builder surfaces (eval run results) pass just
    // {raw_input, raw_output} — no claims machinery required.
    const { container, component } = render(ClaimTraceModal)
    component.open_trace({
      raw_input: "opening user message",
      raw_output: "assistant:\n<assistant_message>\nfinal reply",
    })
    await tick()
    expect(container.textContent).toContain("opening user message")
    expect(container.textContent).toContain("final reply")
  })

  it("open_citation still highlights the cited span of a full TraceClaims", async () => {
    const trace: TraceClaims = {
      trace_id: "t1",
      leaf_run_id: null,
      raw_input: "the input text",
      raw_output: "before target words after",
      judge_score: "pass",
      judge_reasoning: "reasoning",
      claims: [],
      final_judgement: {
        claim: "c",
        expected_result: "pass",
        evidence: "e",
        citations: [],
      },
    }
    const { container, component } = render(ClaimTraceModal)
    await component.open_citation(trace, {
      marker: 1,
      source: "output",
      from: "target",
      to: "words",
    })
    await tick()
    const mark = container.querySelector("mark")
    expect(mark?.textContent).toContain("target")
  })
})
