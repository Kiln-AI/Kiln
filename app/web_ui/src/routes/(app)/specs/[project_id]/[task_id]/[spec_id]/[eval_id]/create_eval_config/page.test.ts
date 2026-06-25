// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, fireEvent, cleanup } from "@testing-library/svelte"
import { tick } from "svelte"
import * as svelteMod from "svelte"

// ---------------------------------------------------------------------------
// Module-level mocks -- must come before the dynamic page import
// ---------------------------------------------------------------------------

const {
  mockPage,
  mockGoto,
  mockClientGET,
  mockLoadTask,
  mockLoadModels,
  onMountCallbacks,
} = vi.hoisted(() => {
  type PageValue = {
    params: Record<string, string>
    url: URL
  }
  let pageValue: PageValue = {
    params: {
      project_id: "proj1",
      task_id: "task1",
      eval_id: "eval1",
      spec_id: "spec1",
    },
    url: new URL(
      "http://localhost/specs/proj1/task1/spec1/eval1/create_eval_config",
    ),
  }
  type Subscriber = (value: PageValue) => void
  const subscribers = new Set<Subscriber>()
  const mockPage = {
    subscribe(fn: Subscriber) {
      subscribers.add(fn)
      fn(pageValue)
      return () => subscribers.delete(fn)
    },
    set(v: PageValue) {
      pageValue = v
      subscribers.forEach((fn) => fn(v))
    },
  }

  const mockGoto = vi.fn()

  const mockClientGET = vi.fn().mockImplementation((path: string) => {
    if (path.includes("/evals/")) {
      return Promise.resolve({
        data: {
          id: "eval1",
          name: "Test Eval",
          eval_set_filter_id: null,
          eval_configs: [],
          eval_config_type: "v2",
          output_scores: [],
        },
        error: null,
      })
    }
    if (path.includes("/specs/")) {
      return Promise.resolve({
        data: { id: "spec1", name: "Test Spec" },
        error: null,
      })
    }
    return Promise.resolve({ data: null, error: null })
  })

  const mockLoadTask = vi.fn().mockResolvedValue({
    id: "task1",
    name: "Test Task",
    description: "desc",
    input_json_schema: "{}",
    output_json_schema: "{}",
  })

  const mockLoadModels = vi.fn().mockResolvedValue([])

  const onMountCallbacks: Array<() => unknown> = []

  return {
    mockPage,
    mockGoto,
    mockClientGET,
    mockLoadTask,
    mockLoadModels,
    onMountCallbacks,
  }
})

vi.mock("$app/stores", () => ({
  page: mockPage,
}))

vi.mock("$app/navigation", () => ({
  goto: mockGoto,
  beforeNavigate: vi.fn(),
}))

vi.mock("$lib/api_client", () => ({
  client: {
    GET: mockClientGET,
  },
}))

vi.mock("$lib/stores", () => ({
  load_task: mockLoadTask,
  load_available_models: mockLoadModels,
}))

vi.mock("posthog-js", () => ({
  default: { capture: vi.fn() },
}))

vi.mock("$lib/stores/evals_store", () => ({
  set_current_eval_config: vi.fn().mockResolvedValue({}),
}))

vi.mock("$lib/agent", () => ({
  agentInfo: { set: vi.fn() },
}))

// Stub heavy Svelte components
vi.mock("../../../../../../app_page.svelte", async () => {
  const Stub = await import("./__tests__/app_page_stub.svelte")
  return { default: Stub.default }
})

vi.mock("../../../../../../../app_page.svelte", async () => {
  const Stub = await import("./__tests__/app_page_stub.svelte")
  return { default: Stub.default }
})

vi.mock("$lib/utils/form_container.svelte", async () => {
  const Stub = await import("./__tests__/form_container_stub.svelte")
  return { default: Stub.default }
})

vi.mock("$lib/ui/collapse.svelte", async () => {
  const Stub = await import("./__tests__/collapse_stub.svelte")
  return { default: Stub.default }
})

vi.mock("$lib/ui/dialog.svelte", async () => {
  const Stub = await import("./__tests__/dialog_stub.svelte")
  return { default: Stub.default }
})

vi.mock("$lib/components/eval_types/llm_judge_form.svelte", async () => {
  const Stub = await import("./__tests__/llm_judge_form_stub.svelte")
  return { default: Stub.default }
})

// Stub TaskRunPicker
vi.mock("$lib/utils/task_run_picker.svelte", async () => {
  const Stub = await import("./__tests__/task_run_picker_stub.svelte")
  return { default: Stub.default }
})

// Mock the registry so that svelte:component uses our lightweight V2 form stub
const V2FormStubModule = await import("./__tests__/v2_form_stub.svelte")
vi.mock("$lib/utils/eval_types/registry", async (importOriginal) => {
  const original = (await importOriginal()) as Record<string, unknown>
  return {
    ...original,
    getV2EvalTypeMetadata: (type: string) => {
      const meta = (
        original.getV2EvalTypeMetadata as (t: string) => Record<string, unknown>
      )(type)
      return {
        ...meta,
        createFormComponent: V2FormStubModule.default,
      }
    },
  }
})

// Mock the v2_eval_api functions
const mockTestV2Eval = vi.fn()
const mockCreateEvalConfig = vi.fn()
const mockCreateLlmJudgeConfig = vi.fn()
const mockCheckCodeEvalTrust = vi.fn()
const mockGrantCodeEvalTrust = vi.fn()
const mockFetchTaskRuns = vi.fn()
const mockTestV2EvalLlmJudge = vi.fn()

const sampleTaskRun = {
  v: 1,
  id: "run1",
  input: "test input",
  output: { output: "test output", source: { type: "human" as const } },
  tags: [],
  created_at: new Date().toISOString(),
}

vi.mock("$lib/api/v2_eval_api", async (importOriginal) => {
  const original = (await importOriginal()) as Record<string, unknown>
  return {
    ...original,
    testV2Eval: (...args: unknown[]) => mockTestV2Eval(...args),
    testV2EvalLlmJudge: (...args: unknown[]) => mockTestV2EvalLlmJudge(...args),
    createEvalConfig: (...args: unknown[]) => mockCreateEvalConfig(...args),
    createLlmJudgeConfig: (...args: unknown[]) =>
      mockCreateLlmJudgeConfig(...args),
    checkCodeEvalTrust: (...args: unknown[]) => mockCheckCodeEvalTrust(...args),
    grantCodeEvalTrust: (...args: unknown[]) => mockGrantCodeEvalTrust(...args),
    fetchTaskRuns: (...args: unknown[]) => mockFetchTaskRuns(...args),
  }
})

// Mock string_to_json_key
vi.mock("$lib/utils/json_schema_editor/json_schema_templates", () => ({
  string_to_json_key: (s: string) =>
    s
      .trim()
      .toLowerCase()
      .replace(/ /g, "_")
      .replace(/[^a-z0-9_.]/g, ""),
}))

// Mock format_expanded_content
vi.mock("$lib/utils/format_expanded_content", () => ({
  formatExpandedContent: (text: string) => ({ isJson: false, value: text }),
}))

// Dynamic imports after all mocks
const PickerPage = (await import("./+page.svelte")).default
const BuilderRoutePage = (await import("./[eval_config_type]/+page.svelte"))
  .default
const EvalConfigBuilder = (
  await import("$lib/components/eval_types/eval_config_builder.svelte")
).default
const { showCalls, resetCalls } = await import("./__tests__/dialog_stub.svelte")
const { ALL_V2_EVAL_TYPES, getV2EvalTypeMetadata } = await import(
  "$lib/utils/eval_types/registry"
)
const { CREATE_EVAL_LAYOUT_KEY } = await import("./context")

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Render the picker page with context provided.
 */
async function renderPickerPage() {
  onMountCallbacks.length = 0

  // The picker page uses getContext("create_eval_layout"). We need to
  // set it up before rendering. Use Svelte's component-level context
  // via the `context` option of @testing-library/svelte.
  const { writable } = await import("svelte/store")

  const ctx = new Map()
  ctx.set(CREATE_EVAL_LAYOUT_KEY, {
    evaluator: writable({
      id: "eval1",
      name: "Test Eval",
      output_scores: [],
    }),
    task: writable({
      id: "task1",
      name: "Test Task",
      instruction: "test instruction",
    }),
    spec: writable({ id: "spec1", name: "Test Spec" }),
    project_id: writable("proj1"),
    task_id: writable("task1"),
    eval_id: writable("eval1"),
    spec_id: writable("spec1"),
  })

  const result = render(PickerPage, { context: ctx })
  await tick()
  return result
}

/**
 * Render the EvalConfigBuilder component directly.
 */
async function renderBuilder(evalType: string = "code_eval") {
  onMountCallbacks.length = 0

  const spy = vi
    .spyOn(svelteMod, "onMount")
    .mockImplementation((fn: () => unknown) => {
      onMountCallbacks.push(fn)
    })

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const result = render(EvalConfigBuilder as any, {
    props: {
      eval_config_type: evalType,
      evaluator: {
        id: "eval1",
        name: "Test Eval",
        output_scores: [],
      },
      task: {
        id: "task1",
        name: "Test Task",
        instruction: "test instruction",
        input_json_schema: "{}",
        output_json_schema: "{}",
      },
      spec: { id: "spec1", name: "Test Spec" },
      project_id: "proj1",
      task_id: "task1",
      eval_id: "eval1",
      spec_id: "spec1",
    },
  })

  spy.mockRestore()

  for (const cb of onMountCallbacks) {
    await cb()
  }
  await tick()

  return result
}

/**
 * Render the builder route page ([eval_config_type]/+page.svelte) with context.
 */
async function renderBuilderRoutePage(evalConfigType: string) {
  onMountCallbacks.length = 0

  mockPage.set({
    params: {
      project_id: "proj1",
      task_id: "task1",
      eval_id: "eval1",
      spec_id: "spec1",
      eval_config_type: evalConfigType,
    },
    url: new URL(
      `http://localhost/specs/proj1/task1/spec1/eval1/create_eval_config/${evalConfigType}`,
    ),
  })

  const { writable } = await import("svelte/store")

  const ctx = new Map()
  ctx.set(CREATE_EVAL_LAYOUT_KEY, {
    evaluator: writable({
      id: "eval1",
      name: "Test Eval",
      output_scores: [],
    }),
    task: writable({
      id: "task1",
      name: "Test Task",
      instruction: "test instruction",
      input_json_schema: "{}",
      output_json_schema: "{}",
    }),
    spec: writable({ id: "spec1", name: "Test Spec" }),
    project_id: writable("proj1"),
    task_id: writable("task1"),
    eval_id: writable("eval1"),
    spec_id: writable("spec1"),
  })

  const result = render(BuilderRoutePage, { context: ctx })
  await tick()
  return result
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("create_eval_config picker page", () => {
  afterEach(() => {
    cleanup()
  })

  it("renders hero card and all remaining type rows", async () => {
    const { container } = await renderPickerPage()
    const cards = container.querySelectorAll(".card")
    expect(cards.length).toBe(ALL_V2_EVAL_TYPES.length)
  })

  it("shows LLM as Judge in the hero card", async () => {
    const { container } = await renderPickerPage()
    const cards = container.querySelectorAll(".card")
    expect(cards[0].textContent).toContain("LLM as Judge")
    expect(cards[0].textContent).toContain("Recommended")
  })

  it("navigates to llm_judge on hero Continue click", async () => {
    const { container } = await renderPickerPage()
    const continueBtn = container.querySelector(
      ".btn-primary",
    ) as HTMLButtonElement
    expect(continueBtn).not.toBeNull()
    expect(continueBtn.textContent).toContain("Continue")
    await fireEvent.click(continueBtn)
    await tick()

    expect(mockGoto).toHaveBeenCalledWith(
      expect.stringContaining("/create_eval_config/llm_judge"),
    )
  })

  it("navigates to type on list row click", async () => {
    const { container } = await renderPickerPage()
    const rows = container.querySelectorAll('[data-testid="eval-type-row"]')
    expect(rows.length).toBe(ALL_V2_EVAL_TYPES.length - 1)
    await fireEvent.click(rows[0])
    await tick()

    expect(mockGoto).toHaveBeenCalledWith(
      expect.stringContaining("/create_eval_config/code_eval"),
    )
  })

  it("preserves query params when navigating", async () => {
    mockPage.set({
      params: {
        project_id: "proj1",
        task_id: "task1",
        eval_id: "eval1",
        spec_id: "spec1",
      },
      url: new URL(
        "http://localhost/specs/proj1/task1/spec1/eval1/create_eval_config?next_page=eval_configs&save_as_default=true",
      ),
    })

    const { container } = await renderPickerPage()
    const continueBtn = container.querySelector(
      ".btn-primary",
    ) as HTMLButtonElement
    await fireEvent.click(continueBtn)
    await tick()

    expect(mockGoto).toHaveBeenCalledWith(
      expect.stringContaining("next_page=eval_configs"),
    )
    expect(mockGoto).toHaveBeenCalledWith(
      expect.stringContaining("save_as_default=true"),
    )

    // Reset page for other tests
    mockPage.set({
      params: {
        project_id: "proj1",
        task_id: "task1",
        eval_id: "eval1",
        spec_id: "spec1",
      },
      url: new URL(
        "http://localhost/specs/proj1/task1/spec1/eval1/create_eval_config",
      ),
    })
  })
})

describe("EvalConfigBuilder", () => {
  beforeEach(() => {
    resetCalls()
    mockTestV2Eval.mockReset()
    mockTestV2EvalLlmJudge.mockReset()
    mockCreateEvalConfig.mockReset()
    mockCreateLlmJudgeConfig.mockReset()
    mockCheckCodeEvalTrust.mockReset()
    mockGrantCodeEvalTrust.mockReset()
    mockFetchTaskRuns.mockReset()
    mockFetchTaskRuns.mockResolvedValue([sampleTaskRun])
  })

  afterEach(() => {
    cleanup()
  })

  describe("trust modal for code_eval", () => {
    it("shows trust dialog when test returns code_eval_not_trusted", async () => {
      const { container } = await renderBuilder("code_eval")

      // Wait for task runs to load
      await tick()
      await new Promise((r) => setTimeout(r, 0))
      await tick()

      // Select a run from the picker
      const selectBtn = container.querySelector(
        '[data-testid="select-run-0"]',
      ) as HTMLButtonElement
      expect(selectBtn).not.toBeNull()
      await fireEvent.click(selectBtn)
      await tick()

      mockTestV2Eval.mockResolvedValueOnce({
        scores: {},
        skipped_reason: "code_eval_not_trusted",
        skipped_detail: "Code eval is not trusted for this project.",
      })

      const tryBtn = container.querySelector(
        "button.btn-primary.btn-sm",
      ) as HTMLButtonElement
      expect(tryBtn).not.toBeNull()
      await fireEvent.click(tryBtn)

      await tick()
      await new Promise((r) => setTimeout(r, 0))
      await tick()

      expect(showCalls).toContain("Allow Code Execution")
    })

    it("shows trust dialog when saving a code_eval without trust", async () => {
      const { container } = await renderBuilder("code_eval")

      mockCheckCodeEvalTrust.mockResolvedValueOnce({ trusted: false })

      const submitBtn = container.querySelector(
        '[data-testid="form-submit-button"]',
      ) as HTMLButtonElement
      expect(submitBtn).not.toBeNull()
      await fireEvent.click(submitBtn)

      await tick()
      await new Promise((r) => setTimeout(r, 0))
      await tick()

      expect(showCalls).toContain("Allow Code Execution")
      expect(mockCreateEvalConfig).not.toHaveBeenCalled()
    })

    it("skips trust check for non-requiresTrust types", async () => {
      const { container } = await renderBuilder("exact_match")

      const submitBtn = container.querySelector(
        '[data-testid="form-submit-button"]',
      ) as HTMLButtonElement
      expect(submitBtn).not.toBeNull()
      await fireEvent.click(submitBtn)

      await tick()
      await new Promise((r) => setTimeout(r, 0))
      await tick()

      expect(showCalls).not.toContain("Allow Code Execution")
      expect(mockCheckCodeEvalTrust).not.toHaveBeenCalled()
      expect(showCalls).toContain("Save Without Testing?")
    })
  })

  describe("save-without-testing confirm modal", () => {
    it("shows confirm dialog when saving V2 eval without running a test", async () => {
      const { container } = await renderBuilder("exact_match")

      const submitBtn = container.querySelector(
        '[data-testid="form-submit-button"]',
      ) as HTMLButtonElement
      await fireEvent.click(submitBtn)

      await tick()
      await new Promise((r) => setTimeout(r, 0))
      await tick()

      expect(showCalls).toContain("Save Without Testing?")
      expect(mockCreateEvalConfig).not.toHaveBeenCalled()
    })

    it("does not show confirm dialog after a successful test run", async () => {
      const { container } = await renderBuilder("exact_match")

      // Wait for task runs to load
      await tick()
      await new Promise((r) => setTimeout(r, 0))
      await tick()

      // Select a run from the picker
      const selectBtn = container.querySelector(
        '[data-testid="select-run-0"]',
      ) as HTMLButtonElement
      expect(selectBtn).not.toBeNull()
      await fireEvent.click(selectBtn)
      await tick()

      mockTestV2Eval.mockResolvedValueOnce({
        scores: { accuracy: 1.0 },
        skipped_reason: null,
        skipped_detail: null,
      })

      const tryBtn = container.querySelector(
        "button.btn-primary.btn-sm",
      ) as HTMLButtonElement
      expect(tryBtn).not.toBeNull()
      await fireEvent.click(tryBtn)

      await tick()
      await new Promise((r) => setTimeout(r, 0))
      await tick()

      resetCalls()
      mockCreateEvalConfig.mockResolvedValueOnce({
        id: "config123",
        type: "v2",
        properties: {},
      })

      const submitBtn = container.querySelector(
        '[data-testid="form-submit-button"]',
      ) as HTMLButtonElement
      await fireEvent.click(submitBtn)

      await tick()
      await new Promise((r) => setTimeout(r, 0))
      await tick()

      expect(showCalls).not.toContain("Save Without Testing?")
      expect(mockCreateEvalConfig).toHaveBeenCalledTimes(1)
    })

    it("shows confirm dialog for code_eval after trust is already granted", async () => {
      const { container } = await renderBuilder("code_eval")

      mockCheckCodeEvalTrust.mockResolvedValueOnce({ trusted: true })

      const submitBtn = container.querySelector(
        '[data-testid="form-submit-button"]',
      ) as HTMLButtonElement
      await fireEvent.click(submitBtn)

      await tick()
      await new Promise((r) => setTimeout(r, 0))
      await tick()

      expect(showCalls).not.toContain("Allow Code Execution")
      expect(showCalls).toContain("Save Without Testing?")
    })
  })
})

describe("builder route page ([eval_config_type])", () => {
  afterEach(() => {
    cleanup()
    mockPage.set({
      params: {
        project_id: "proj1",
        task_id: "task1",
        eval_id: "eval1",
        spec_id: "spec1",
      },
      url: new URL(
        "http://localhost/specs/proj1/task1/spec1/eval1/create_eval_config",
      ),
    })
  })

  it("shows error for unknown eval type", async () => {
    const { container } = await renderBuilderRoutePage("bogus_type")
    expect(container.textContent).toContain("Unknown Eval Type")
    expect(container.textContent).toContain('"bogus_type" is not a recognized')
  })

  it("renders builder for valid eval type", async () => {
    const { container } = await renderBuilderRoutePage("exact_match")
    expect(container.textContent).not.toContain("Unknown Eval Type")
  })

  it("sets per-type pageTitle on AppPage for each eval type", async () => {
    for (const evalType of ALL_V2_EVAL_TYPES) {
      const meta = getV2EvalTypeMetadata(evalType)
      const { container } = await renderBuilderRoutePage(evalType)
      const appPage = container.querySelector("[data-testid='app-page-stub']")
      expect(appPage?.getAttribute("data-title")).toBe(meta.pageTitle)
      cleanup()
    }
  })

  it("sets per-type pageSubtitle on AppPage", async () => {
    const meta = getV2EvalTypeMetadata("exact_match")
    const { container } = await renderBuilderRoutePage("exact_match")
    const appPage = container.querySelector("[data-testid='app-page-stub']")
    expect(appPage?.getAttribute("data-subtitle")).toBe(meta.pageSubtitle)
  })

  it("does not render sub_subtitle (Read the Docs link removed)", async () => {
    const { container } = await renderBuilderRoutePage("exact_match")
    expect(container.textContent).not.toContain("Read the Docs")
  })
})

describe("EvalConfigBuilder — Phase 3: container shell + intro", () => {
  beforeEach(() => {
    resetCalls()
    mockFetchTaskRuns.mockReset()
    mockFetchTaskRuns.mockResolvedValue([sampleTaskRun])
  })

  afterEach(() => {
    cleanup()
  })

  it("uses xl breakpoint two-column layout (not lg)", async () => {
    const { container } = await renderBuilder("exact_match")
    const flexRow = container.querySelector(".xl\\:flex-row")
    expect(flexRow).not.toBeNull()
    const lgFlexRow = container.querySelector(
      ".lg\\:flex-row:not(.xl\\:flex-row)",
    )
    expect(lgFlexRow).toBeNull()
  })

  it("does not render secondary-title block (icon + label heading)", async () => {
    const { container } = await renderBuilder("exact_match")
    const secondaryTitle = container.querySelector(
      ".flex.items-center.gap-2.pt-4.mb-2",
    )
    expect(secondaryTitle).toBeNull()
  })

  it("right column has no bordered box wrapper", async () => {
    const { container } = await renderBuilder("exact_match")
    const borderedBox = container.querySelector(".rounded-lg.border.bg-base-100")
    expect(borderedBox).toBeNull()
  })

  it("renders Test Run heading with app standard font style", async () => {
    const { container } = await renderBuilder("exact_match")
    const heading = container.querySelector(".text-xl.font-bold")
    expect(heading).not.toBeNull()
    expect(heading?.textContent).toContain("Test Run")
  })

  it("renders eval_type_intro with explainer text", async () => {
    const { container } = await renderBuilder("exact_match")
    const intro = container.querySelector("[data-testid='eval-type-intro']")
    expect(intro).not.toBeNull()
    const meta = getV2EvalTypeMetadata("exact_match")
    expect(intro?.textContent).toContain(meta.explainer!)
  })

  it("renders eval_type_intro with type label", async () => {
    const { container } = await renderBuilder("exact_match")
    const intro = container.querySelector("[data-testid='eval-type-intro']")
    expect(intro?.textContent).toContain("Exact Match")
  })

  it("renders eval_type_intro with example when available", async () => {
    const { container } = await renderBuilder("exact_match")
    const intro = container.querySelector("[data-testid='eval-type-intro']")
    const meta = getV2EvalTypeMetadata("exact_match")
    expect(meta.example).toBeTruthy()
    expect(intro?.textContent).toContain(meta.example!)
  })

  it("renders eval_type_intro without example when not available", async () => {
    const { container } = await renderBuilder("contains")
    const intro = container.querySelector("[data-testid='eval-type-intro']")
    expect(intro).not.toBeNull()
    const meta = getV2EvalTypeMetadata("contains")
    expect(meta.example).toBeFalsy()
    expect(intro?.textContent).toContain(meta.explainer!)
  })
})
