// @vitest-environment jsdom
import { describe, it, expect, vi, beforeAll } from "vitest"
import { render, fireEvent } from "@testing-library/svelte"
import { tick } from "svelte"

vi.mock("$lib/components/code_editor.svelte", async () => {
  const StubModule = await import(
    "$lib/components/eval_types/__tests__/code_editor_stub.svelte"
  )
  return { default: StubModule.default }
})

vi.mock("$lib/ui/dialog.svelte", async () => {
  const StubModule = await import(
    "$lib/components/eval_types/__tests__/dialog_stub.svelte"
  )
  return { default: StubModule.default }
})

const CreateSpecJudgeForm = (await import("./create_spec_judge_form.svelte"))
  .default

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

function render_form(judge_type: "code_eval" | "pattern_match", name: string) {
  return render(CreateSpecJudgeForm, {
    props: {
      name,
      judge_type,
      project_id: "proj1",
      task_id: "task1",
      priority: 1 as const,
      evaluate_full_trace: false,
      full_trace_disabled: false,
      error: null,
      submitting: false,
      warn_before_unload: false,
    },
  })
}

describe("CreateSpecJudgeForm", () => {
  it("seeds the code judge's starter code with the eval's score key", () => {
    // The eval is created with one pass/fail score named after the eval, so
    // the generated code must return that key -- the "quality" fallback would
    // fail score validation on every run.
    const { container } = render_form("code_eval", "No Hate Regex")

    const editor = container.querySelector(
      '[data-testid="code-editor-textarea"]',
    ) as HTMLTextAreaElement
    expect(editor).not.toBeNull()
    expect(editor.value).toContain('"no_hate_regex"')
    expect(editor.value).not.toContain('"quality"')
  })

  it("renders name field and judge configuration for non-code judges", () => {
    const { container } = render_form("pattern_match", "My Eval")
    expect(container.textContent).toContain("Eval Name")
    expect(container.textContent).toContain("Judge Configuration")
  })

  it("regenerates starter code as the eval name is typed", async () => {
    // Judge-only mode starts with an empty name; the score key comes from
    // whatever the user types. The editor's own programmatic setValue fires a
    // change event, which must NOT count as a user edit — otherwise the first
    // keystroke freezes regeneration and the saved code returns a score key
    // that can never match the eval.
    const { container } = render_form("code_eval", "")
    const editor = container.querySelector(
      '[data-testid="code-editor-textarea"]',
    ) as HTMLTextAreaElement
    const name_input = container.querySelector(
      'input[aria-label="Eval Name"]',
    ) as HTMLInputElement
    expect(name_input).not.toBeNull()

    // Simulate typing keystroke by keystroke: each triggers a regeneration.
    for (const partial of ["N", "No Hate", "No Hate Regex"]) {
      await fireEvent.input(name_input, { target: { value: partial } })
      await tick()
    }
    expect(editor.value).toContain('"no_hate_regex"')

    // A real user edit freezes regeneration from then on.
    await fireEvent.input(editor, {
      target: { value: 'return {"custom": 1.0}' },
    })
    await tick()
    await fireEvent.input(name_input, { target: { value: "Renamed" } })
    await tick()
    expect(editor.value).toContain('"custom"')
    expect(editor.value).not.toContain('"renamed"')
  })
})
