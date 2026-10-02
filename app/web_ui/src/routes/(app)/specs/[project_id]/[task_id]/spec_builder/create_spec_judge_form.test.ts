// @vitest-environment jsdom
import {
  describe,
  it,
  expect,
  vi,
  beforeAll,
  beforeEach,
  afterEach,
} from "vitest"
import { render, fireEvent, cleanup } from "@testing-library/svelte"
import { tick } from "svelte"
import * as svelteMod from "svelte"

const mockFetchTaskRuns = vi.fn()

vi.mock("$lib/api/v2_eval_api", async (importOriginal) => {
  const original = (await importOriginal()) as Record<string, unknown>
  return {
    ...original,
    fetchTaskRuns: (...args: unknown[]) => mockFetchTaskRuns(...args),
  }
})

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
      error: null,
      submitting: false,
      warn_before_unload: false,
    },
  })
}

/**
 * Render the form and run the onMount callbacks, which load the task runs the
 * Test Judge pane selects from. onMount doesn't fire on its own under vitest,
 * so collect the callbacks and invoke them by hand.
 */
async function render_form_with_runs(runs: unknown[]) {
  mockFetchTaskRuns.mockResolvedValue(runs)

  const on_mount_callbacks: Array<() => unknown> = []
  const spy = vi
    .spyOn(svelteMod, "onMount")
    .mockImplementation((fn: () => unknown) => {
      on_mount_callbacks.push(fn)
    })
  const result = render_form("pattern_match", "My Eval")
  spy.mockRestore()

  for (const callback of on_mount_callbacks) {
    await callback()
  }
  await tick()
  return result
}

function task_run(id: string, trace: unknown[] | null) {
  return {
    v: 1,
    id,
    input: `input ${id}`,
    output: { output: `output ${id}`, source: { type: "human" as const } },
    tags: [],
    created_at: new Date().toISOString(),
    trace,
  }
}

describe("CreateSpecJudgeForm", () => {
  beforeEach(() => {
    mockFetchTaskRuns.mockReset()
    mockFetchTaskRuns.mockResolvedValue([])
  })

  afterEach(() => {
    cleanup()
  })

  it("seeds the code judge with the real score key, never the quality fallback", () => {
    // With a valid name the starter regenerates with the real key; the
    // placeholder only appears while the name is empty or invalid. Neither
    // state may fall back to the generic "quality" key.
    const { container } = render_form("code_eval", "No Hate Regex")

    const editor = container.querySelector(
      '[data-testid="code-editor-textarea"]',
    ) as HTMLTextAreaElement
    expect(editor).not.toBeNull()
    expect(editor.value).toContain('"no_hate_regex"')
    expect(editor.value).not.toContain('"quality"')
    expect(editor.value).not.toContain('"score_name_placeholder"')
  })

  it("renders name field and judge configuration for non-code judges", () => {
    const { container } = render_form("pattern_match", "My Eval")
    expect(container.textContent).toContain("Eval Name")
    expect(container.textContent).toContain("Judge Configuration")
  })

  it("the score key note and starter code track the eval name until edited", async () => {
    // Judge-only mode starts with an empty name; the real key comes from
    // whatever the user types. Until the code is manually edited, the starter
    // regenerates live with the real key.
    const { container } = render_form("code_eval", "")
    const editor = container.querySelector(
      '[data-testid="code-editor-textarea"]',
    ) as HTMLTextAreaElement
    const name_input = container.querySelector(
      'input[aria-label="Eval Name"]',
    ) as HTMLInputElement
    expect(name_input).not.toBeNull()
    // No note while the name is empty: there's no key to show yet.
    expect(container.querySelector('[data-testid="score-key-note"]')).toBeNull()
    expect(editor.value).toContain('"score_name_placeholder"')

    for (const partial of ["N", "No Hate", "No Hate Regex"]) {
      await fireEvent.input(name_input, { target: { value: partial } })
      await tick()
    }
    const note = container.querySelector(
      '[data-testid="score-key-note"]',
    ) as HTMLElement
    expect(note).not.toBeNull()
    expect(note.textContent).toContain("must return the score key")
    expect(note.textContent).toContain('"no_hate_regex"')
    expect(editor.value).toContain('"no_hate_regex"')
    expect(editor.value).not.toContain('"score_name_placeholder"')

    // A manual edit freezes the code: renaming no longer regenerates it.
    await fireEvent.input(editor, {
      target: { value: editor.value + "\n# tweak" },
    })
    await fireEvent.input(name_input, { target: { value: "Renamed Eval" } })
    await tick()
    expect(editor.value).toContain('"no_hate_regex"')
    expect(editor.value).toContain("# tweak")
    expect(editor.value).not.toContain('"renamed_eval"')
  })

  it("renders the Test Judge pane beside the form", () => {
    const { container } = render_form("pattern_match", "My Eval")
    const pane = container.querySelector('[data-testid="test-run-pane"]')
    expect(pane).not.toBeNull()
    expect(pane?.textContent).toContain("Test Judge")
    expect(pane?.textContent).toContain(
      "Test your judge on real data before saving.",
    )
  })

  describe("default test run selection", () => {
    async function selected_run_text(runs: unknown[]) {
      const { container } = await render_form_with_runs(runs)
      const card = container.querySelector(
        '[data-testid="selected-run-card"]',
      ) as HTMLElement
      expect(card).not.toBeNull()
      return card.textContent ?? ""
    }

    it("auto-selects the newest run that has a trace", async () => {
      const text = await selected_run_text([
        task_run("no_trace", null),
        task_run("traced", [{ role: "user", content: "hi" }]),
      ])
      expect(text).toContain("input traced")
      expect(text).not.toContain("input no_trace")
    })

    it("treats an empty trace as no trace", async () => {
      const text = await selected_run_text([
        task_run("empty_trace", []),
        task_run("traced", [{ role: "user", content: "hi" }]),
      ])
      expect(text).toContain("input traced")
    })

    it("falls back to the newest run when none have a trace", async () => {
      const text = await selected_run_text([
        task_run("newest", null),
        task_run("older", null),
      ])
      expect(text).toContain("input newest")
    })
  })

  // Note: hiding the score-key note while the name field has a validation
  // error (name_error -> no output_scores) isn't testable here — FormElement
  // only starts validating after onMount, which plain render_form doesn't
  // drive (see render_form_with_runs for the manual onMount path).
  // The render-side behavior (no scores -> no note) is covered in
  // code_eval_form.test.ts.
})
