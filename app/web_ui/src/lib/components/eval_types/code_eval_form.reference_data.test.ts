// @vitest-environment jsdom
import { describe, it, expect, vi, beforeAll } from "vitest"
// Pins the behavior restored by flipping SHOW_REFERENCE_DATA_UI back on, so the
// gated code paths don't rot while reference data is hidden from the UI.
vi.mock("$lib/utils/eval_types/reference_data_ui", () => ({
  SHOW_REFERENCE_DATA_UI: true,
}))

import { render } from "@testing-library/svelte"

vi.mock("$lib/components/code_editor.svelte", async () => {
  const StubModule = await import("./__tests__/code_editor_stub.svelte")
  return { default: StubModule.default }
})

vi.mock("$lib/ui/dialog.svelte", async () => {
  const StubModule = await import("./__tests__/dialog_stub.svelte")
  return { default: StubModule.default }
})

vi.mock("$lib/utils/form_element.svelte", async () => {
  const StubModule = await import("./__tests__/form_element_stub.svelte")
  return { default: StubModule.default }
})

const CodeEvalForm = (await import("./code_eval_form.svelte")).default

beforeAll(() => {
  if (typeof globalThis.ResizeObserver === "undefined") {
    // eslint-disable-next-line @typescript-eslint/no-extraneous-class
    class ResizeObserverStub {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    ;(
      globalThis as unknown as { ResizeObserver: typeof ResizeObserverStub }
    ).ResizeObserver = ResizeObserverStub
  }
})

describe("CodeEvalForm (reference data shown)", () => {
  it("default code contains the expected function signature", () => {
    const { component } = render(CodeEvalForm)
    const props = component.getProperties()
    expect(props.code).toContain(
      "def score(output, trace, reference_data, task_input)",
    )
  })

  it("Score Function info_description mentions reference data", () => {
    const { container } = render(CodeEvalForm)
    const el = container.querySelector(
      '[data-testid="form-element-code_eval_score_function"]',
    )
    expect(el?.getAttribute("data-info-description")).toBe(
      "The Python function can use the model's output, trace, and eval's reference data to drive pragmatic scoring. Faster and cheaper than LLM as a judge.",
    )
  })
})
