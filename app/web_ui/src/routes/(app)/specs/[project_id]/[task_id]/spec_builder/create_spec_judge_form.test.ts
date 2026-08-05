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
  it("seeds the code judge with the score_name_placeholder key, never the quality fallback", () => {
    // The starter code is static by design: the score key note and save-time
    // validation carry the real key, so the code never has to chase the
    // still-being-typed eval name.
    const { container } = render_form("code_eval", "No Hate Regex")

    const editor = container.querySelector(
      '[data-testid="code-editor-textarea"]',
    ) as HTMLTextAreaElement
    expect(editor).not.toBeNull()
    expect(editor.value).toContain('"score_name_placeholder"')
    expect(editor.value).not.toContain('"quality"')
  })

  it("renders name field and judge configuration for non-code judges", () => {
    const { container } = render_form("pattern_match", "My Eval")
    expect(container.textContent).toContain("Eval Name")
    expect(container.textContent).toContain("Judge Configuration")
  })

  it("the score key note tracks the eval name; the code stays static", async () => {
    // Judge-only mode starts with an empty name; the real key comes from
    // whatever the user types. The code is never regenerated — the live note
    // and validation are the contract.
    const { container } = render_form("code_eval", "")
    const editor = container.querySelector(
      '[data-testid="code-editor-textarea"]',
    ) as HTMLTextAreaElement
    const note = container.querySelector(
      '[data-testid="score-key-note"]',
    ) as HTMLElement
    const name_input = container.querySelector(
      'input[aria-label="Eval Name"]',
    ) as HTMLInputElement
    expect(name_input).not.toBeNull()
    expect(note.textContent).toContain("Name your eval above")

    for (const partial of ["N", "No Hate", "No Hate Regex"]) {
      await fireEvent.input(name_input, { target: { value: partial } })
      await tick()
    }
    expect(note.textContent).toContain('"no_hate_regex"')
    expect(editor.value).toContain('"score_name_placeholder"')
    expect(editor.value).not.toContain('"no_hate_regex"')
  })

  it("validation blocks saving until the code returns the real score key", async () => {
    const { container, component } = render_form("code_eval", "")
    const form = component as unknown as {
      validateJudge: () => string | null
    }
    const editor = container.querySelector(
      '[data-testid="code-editor-textarea"]',
    ) as HTMLTextAreaElement
    const name_input = container.querySelector(
      'input[aria-label="Eval Name"]',
    ) as HTMLInputElement

    await fireEvent.input(name_input, { target: { value: "No Hate Regex" } })
    await tick()

    // Untouched starter still carries the placeholder: blocked, with a hint.
    const placeholder_error = form.validateJudge()
    expect(placeholder_error).toContain('"no_hate_regex"')
    expect(placeholder_error).toContain('"score_name_placeholder"')

    // Renaming the key in the code satisfies validation.
    await fireEvent.input(editor, {
      target: {
        value: editor.value.replaceAll(
          "score_name_placeholder",
          "no_hate_regex",
        ),
      },
    })
    await tick()
    expect(form.validateJudge()).toBeNull()

    // Renaming the eval afterwards re-blocks: the code no longer matches.
    await fireEvent.input(name_input, { target: { value: "Renamed" } })
    await tick()
    const renamed_error = form.validateJudge()
    expect(renamed_error).toContain('"renamed"')
    expect(renamed_error).not.toContain("placeholder")
  })
})
