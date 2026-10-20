// @vitest-environment jsdom
import { describe, it, expect, beforeAll, afterAll, afterEach } from "vitest"
import { render, fireEvent, cleanup } from "@testing-library/svelte"
import { tick } from "svelte"
import JudgeTraceDialog from "./judge_trace_dialog.svelte"
import type { Trace } from "$lib/types"

// jsdom does not implement HTMLDialogElement.showModal, which Dialog.show() calls.
let original_show_modal: HTMLDialogElement["showModal"]
beforeAll(() => {
  original_show_modal = HTMLDialogElement.prototype.showModal
  HTMLDialogElement.prototype.showModal = function () {
    this.open = true
  }
})
afterAll(() => {
  HTMLDialogElement.prototype.showModal = original_show_modal
})
afterEach(() => cleanup())

const judge_trace: Trace = [
  { role: "system", content: "You are an evaluator." },
  { role: "user", content: "Rendered judge prompt" },
  { role: "assistant", content: '{"accuracy": 1.0}' },
]

function renderDialog() {
  return render(JudgeTraceDialog, { props: { judge_trace } })
}

function expandedRowCount(container: HTMLElement): number {
  return [
    ...container.querySelectorAll<HTMLInputElement>(
      ".collapse input[type=checkbox]",
    ),
  ].filter((checkbox) => checkbox.checked).length
}

// The browser fires `close` on the <dialog> however the user closes it: the X,
// Escape or the backdrop.
async function closeDialog(container: HTMLElement) {
  await fireEvent(container.querySelector("dialog")!, new Event("close"))
}

describe("JudgeTraceDialog", () => {
  it("builds no trace while the dialog is closed", () => {
    const { container } = renderDialog()

    expect(container.querySelector("h3")?.textContent?.trim()).toBe(
      "Judge Trace",
    )
    expect(container.querySelector(".collapse")).toBeNull()
    expect(container.textContent).not.toContain("Rendered judge prompt")
  })

  it("shows every message expanded once the dialog opens", async () => {
    const { container, component } = renderDialog()

    component.show()
    await tick()

    expect(container.querySelectorAll(".collapse")).toHaveLength(3)
    expect(expandedRowCount(container)).toBe(3)
    expect(container.textContent).toContain("You are an evaluator.")
    expect(container.textContent).toContain("Rendered judge prompt")
    expect(container.textContent).toContain('{"accuracy": 1.0}')
  })

  it("removes the trace when the dialog closes and builds it again on reopen", async () => {
    const { container, component } = renderDialog()
    component.show()
    await tick()

    await closeDialog(container)

    expect(container.querySelector(".collapse")).toBeNull()
    expect(container.textContent).not.toContain("Rendered judge prompt")

    component.show()
    await tick()

    expect(expandedRowCount(container)).toBe(3)
    expect(container.textContent).toContain("Rendered judge prompt")
  })
})
