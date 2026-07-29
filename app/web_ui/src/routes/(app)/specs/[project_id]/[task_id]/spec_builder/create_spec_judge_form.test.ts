// @vitest-environment jsdom
import { describe, it, expect, vi, beforeAll } from "vitest"
import { render } from "@testing-library/svelte"

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
})
