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
const { showCalls, resetCalls, actionButtonsByTitle } = await import(
  "./__tests__/dialog_stub.svelte"
)
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

  it("renders all eval types as rows in a single list", async () => {
    const { container } = await renderPickerPage()
    const rows = container.querySelectorAll('[data-testid="eval-type-row"]')
    expect(rows.length).toBe(ALL_V2_EVAL_TYPES.length)
  })

  it("does not render an 'All judge types' section heading", async () => {
    const { container } = await renderPickerPage()
    expect(container.textContent).not.toContain("All judge types")
  })

  it("shows page title 'Select a Judge Type'", async () => {
    const { container } = await renderPickerPage()
    const appPage = container.querySelector("[data-testid='app-page-stub']")
    expect(appPage?.getAttribute("data-title")).toBe("Select a Judge Type")
  })

  it("shows updated subtitle copy", async () => {
    const { container } = await renderPickerPage()
    const appPage = container.querySelector("[data-testid='app-page-stub']")
    expect(appPage?.getAttribute("data-subtitle")).toBe(
      "Choose how each output gets scored.",
    )
  })

  it("does not show old subtitle copy", async () => {
    const { container } = await renderPickerPage()
    const appPage = container.querySelector("[data-testid='app-page-stub']")
    expect(appPage?.getAttribute("data-subtitle")).not.toContain(
      "Every type produces the same scores",
    )
  })

  it("recommended item is first and rendered with emphasis", async () => {
    const { container } = await renderPickerPage()
    const rows = container.querySelectorAll('[data-testid="eval-type-row"]')
    const firstRow = rows[0]
    expect(firstRow.textContent).toContain("LLM as Judge")
    expect(firstRow.textContent).toContain("Recommended")
    expect(firstRow.classList.contains("border-2")).toBe(true)
    expect(firstRow.classList.contains("bg-base-200")).toBe(true)
  })

  it("recommended item is a clickable button (no Continue button)", async () => {
    const { container } = await renderPickerPage()
    const rows = container.querySelectorAll('[data-testid="eval-type-row"]')
    const firstRow = rows[0]
    expect(firstRow.tagName).toBe("BUTTON")
    expect(firstRow.textContent).not.toContain("Continue")
  })

  it("every row has a structurally right-aligned chevron (flex-none last child of w-full flex row)", async () => {
    const { container } = await renderPickerPage()
    const rows = container.querySelectorAll('[data-testid="eval-type-row"]')
    expect(rows.length).toBeGreaterThan(0)
    for (const row of rows) {
      const flexRow = row.querySelector(".flex.w-full")
      expect(flexRow).not.toBeNull()

      const children = Array.from(flexRow!.children)
      const lastChild = children[children.length - 1]
      expect(lastChild.tagName).toBe("svg")
      expect(lastChild.classList.contains("flex-none")).toBe(true)

      const contentBlock = flexRow!.querySelector(".flex-1.min-w-0")
      expect(contentBlock).not.toBeNull()
    }
  })

  it("navigates to llm_judge on recommended row click", async () => {
    const { container } = await renderPickerPage()
    const rows = container.querySelectorAll('[data-testid="eval-type-row"]')
    await fireEvent.click(rows[0])
    await tick()

    expect(mockGoto).toHaveBeenCalledWith(
      expect.stringContaining("/create_eval_config/llm_judge"),
    )
  })

  it("navigates to type on list row click", async () => {
    const { container } = await renderPickerPage()
    const rows = container.querySelectorAll('[data-testid="eval-type-row"]')
    expect(rows.length).toBe(ALL_V2_EVAL_TYPES.length)
    await fireEvent.click(rows[1])
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
    const rows = container.querySelectorAll('[data-testid="eval-type-row"]')
    await fireEvent.click(rows[0])
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

      // Wait for task runs to load (auto-selects first run)
      await tick()
      await new Promise((r) => setTimeout(r, 0))
      await tick()

      mockTestV2Eval.mockResolvedValueOnce({
        scores: {},
        skipped_reason: "code_eval_not_trusted",
        skipped_detail: "Code eval is not trusted for this project.",
      })

      const tryBtn = container.querySelector(
        '[data-testid="run-test-btn"]',
      ) as HTMLButtonElement
      expect(tryBtn).not.toBeNull()
      await fireEvent.click(tryBtn)

      await tick()
      await new Promise((r) => setTimeout(r, 0))
      await tick()

      expect(showCalls).toContain("Trust Code and Project?")
    })

    it("shows trust dialog when saving a code_eval without trust", async () => {
      const { container } = await renderBuilder("code_eval")

      mockCheckCodeEvalTrust.mockResolvedValueOnce({ trusted: false })

      const submitBtn = container.querySelector(
        '[data-testid="column-save-button"]',
      ) as HTMLButtonElement
      expect(submitBtn).not.toBeNull()
      await fireEvent.click(submitBtn)

      await tick()
      await new Promise((r) => setTimeout(r, 0))
      await tick()

      expect(showCalls).toContain("Trust Code and Project?")
      expect(mockCreateEvalConfig).not.toHaveBeenCalled()
    })

    it("skips trust check for non-requiresTrust types", async () => {
      const { container } = await renderBuilder("exact_match")

      const submitBtn = container.querySelector(
        '[data-testid="column-save-button"]',
      ) as HTMLButtonElement
      expect(submitBtn).not.toBeNull()
      await fireEvent.click(submitBtn)

      await tick()
      await new Promise((r) => setTimeout(r, 0))
      await tick()

      expect(showCalls).not.toContain("Trust Code and Project?")
      expect(mockCheckCodeEvalTrust).not.toHaveBeenCalled()
      expect(showCalls).toContain("Save Without Testing?")
    })
  })

  describe("save-without-testing confirm modal", () => {
    it("shows confirm dialog when saving V2 eval without running a test", async () => {
      const { container } = await renderBuilder("exact_match")

      const submitBtn = container.querySelector(
        '[data-testid="column-save-button"]',
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

      // Wait for task runs to load (auto-selects first run)
      await tick()
      await new Promise((r) => setTimeout(r, 0))
      await tick()

      mockTestV2Eval.mockResolvedValueOnce({
        scores: { accuracy: 1.0 },
        skipped_reason: null,
        skipped_detail: null,
      })

      const tryBtn = container.querySelector(
        '[data-testid="run-test-btn"]',
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
        '[data-testid="column-save-button"]',
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
        '[data-testid="column-save-button"]',
      ) as HTMLButtonElement
      await fireEvent.click(submitBtn)

      await tick()
      await new Promise((r) => setTimeout(r, 0))
      await tick()

      expect(showCalls).not.toContain("Trust Code and Project?")
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
    const borderedBox = container.querySelector(
      ".rounded-lg.border.bg-base-100",
    )
    expect(borderedBox).toBeNull()
  })

  it("renders Test Run heading with app standard font style", async () => {
    const { container } = await renderBuilder("exact_match")
    const headings = container.querySelectorAll(".text-xl.font-bold")
    const texts = Array.from(headings).map((h) => h.textContent?.trim())
    expect(texts).toContain("Test Judge")
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

  it("B6: explainer is rendered inside a CalloutCard", async () => {
    const { container } = await renderBuilder("exact_match")
    const calloutCard = container.querySelector(
      "[data-testid='eval-type-intro-card']",
    )
    expect(calloutCard).not.toBeNull()
    expect(calloutCard?.classList.contains("card-bordered")).toBe(true)
    const intro = container.querySelector("[data-testid='eval-type-intro']")
    expect(intro).not.toBeNull()
    expect(
      intro?.querySelector("[data-testid='eval-type-intro-card']"),
    ).not.toBeNull()
  })

  it("B7: Save button is at the bottom of column 1 (not spanning both)", async () => {
    const { container } = await renderBuilder("exact_match")
    const saveBtn = container.querySelector(
      "[data-testid='column-save-button']",
    )
    expect(saveBtn).not.toBeNull()
    expect(saveBtn?.textContent?.trim()).toBe("Save")
    expect(saveBtn?.classList.contains("btn-primary")).toBe(true)

    const formContainerSubmit = container.querySelector(
      "[data-testid='form-submit-button']",
    )
    expect(formContainerSubmit).toBeNull()
  })

  it("B7: Save button still gates via handle_submit (trust check for code_eval)", async () => {
    const { container } = await renderBuilder("code_eval")
    mockCheckCodeEvalTrust.mockResolvedValueOnce({ trusted: false })

    const saveBtn = container.querySelector(
      "[data-testid='column-save-button']",
    ) as HTMLButtonElement
    await fireEvent.click(saveBtn)

    await tick()
    await new Promise((r) => setTimeout(r, 0))
    await tick()

    expect(showCalls).toContain("Trust Code and Project?")
    expect(mockCreateEvalConfig).not.toHaveBeenCalled()
  })

  it("B7: Save button still gates via confirm modal when no valid test run", async () => {
    const { container } = await renderBuilder("exact_match")

    const saveBtn = container.querySelector(
      "[data-testid='column-save-button']",
    ) as HTMLButtonElement
    await fireEvent.click(saveBtn)

    await tick()
    await new Promise((r) => setTimeout(r, 0))
    await tick()

    expect(showCalls).toContain("Save Without Testing?")
    expect(mockCreateEvalConfig).not.toHaveBeenCalled()
  })

  it("D10: no Save button in the test run pane", async () => {
    const { container } = await renderBuilder("exact_match")
    const pane = container.querySelector("[data-testid='test-run-pane']")
    expect(pane).not.toBeNull()
    const paneSave = pane?.querySelector("[data-testid='save-eval']")
    expect(paneSave).toBeNull()
    const paneSaveWithout = pane?.querySelector(
      "[data-testid='save-without-testing']",
    )
    expect(paneSaveWithout).toBeNull()
  })

  it("B7: Cmd/Ctrl+Enter triggers gated save (confirm modal when no valid test run)", async () => {
    await renderBuilder("exact_match")

    await fireEvent.keyDown(window, {
      key: "Enter",
      metaKey: true,
    })

    await tick()
    await new Promise((r) => setTimeout(r, 0))
    await tick()

    expect(showCalls).toContain("Save Without Testing?")
    expect(mockCreateEvalConfig).not.toHaveBeenCalled()
  })
})

describe("EvalConfigBuilder — Phase 4: trust modal + bugs", () => {
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

  describe("trust modal redesign", () => {
    it("trust dialog uses new title 'Trust Code and Project?'", async () => {
      const { container } = await renderBuilder("code_eval")

      const dialogs = container.querySelectorAll("[data-testid='dialog-stub']")
      const trustDialog = Array.from(dialogs).find(
        (d) => d.getAttribute("data-title") === "Trust Code and Project?",
      )
      expect(trustDialog).not.toBeNull()
    })

    it("trust dialog body contains new warning copy", async () => {
      const { container } = await renderBuilder("code_eval")

      expect(container.textContent).toContain(
        "This project wants to run Python code on your machine",
      )
      expect(container.textContent).toContain(
        "Never paste code from a stranger or the internet.",
      )
    })

    it("trust dialog has no yellow alert box", async () => {
      const { container } = await renderBuilder("code_eval")

      const dialogs = container.querySelectorAll("[data-testid='dialog-stub']")
      const trustDialog = Array.from(dialogs).find(
        (d) => d.getAttribute("data-title") === "Trust Code and Project?",
      )
      expect(trustDialog).not.toBeNull()
      const alertWarning = trustDialog!.querySelector(".alert-warning")
      expect(alertWarning).toBeNull()
    })

    it("trust dialog has a large warning icon", async () => {
      const { container } = await renderBuilder("code_eval")

      const icon = container.querySelector("[data-testid='trust-warning-icon']")
      expect(icon).not.toBeNull()
      expect(icon!.classList.contains("text-warning")).toBe(true)
      expect(icon!.classList.contains("w-10")).toBe(true)
      expect(icon!.classList.contains("h-10")).toBe(true)
    })

    it("trust dialog action button is labeled 'Run — I Trust This Code'", async () => {
      const { container } = await renderBuilder("code_eval")

      const dialogs = container.querySelectorAll("[data-testid='dialog-stub']")
      const trustDialog = Array.from(dialogs).find(
        (d) => d.getAttribute("data-title") === "Trust Code and Project?",
      )
      expect(trustDialog).not.toBeNull()
      const buttons = JSON.parse(
        trustDialog!.getAttribute("data-action-buttons") || "[]",
      )
      const trustBtn = buttons.find(
        (b: Record<string, unknown>) => b.isWarning === true,
      )
      expect(trustBtn).toBeTruthy()
      expect(trustBtn.label).toContain("I Trust This Code")
    })

    it("C8/C9: trust dialog text is left-aligned with horizontal icon+text layout", async () => {
      const { container } = await renderBuilder("code_eval")

      const dialogs = container.querySelectorAll("[data-testid='dialog-stub']")
      const trustDialog = Array.from(dialogs).find(
        (d) => d.getAttribute("data-title") === "Trust Code and Project?",
      )
      expect(trustDialog).not.toBeNull()

      const layoutDiv = trustDialog!.querySelector(".flex.flex-row.items-start")
      expect(layoutDiv).not.toBeNull()

      const textDiv = layoutDiv!.querySelector(".text-left")
      expect(textDiv).not.toBeNull()

      const centeredText = layoutDiv!.querySelector(".text-center")
      expect(centeredText).toBeNull()

      const columnLayout = trustDialog!.querySelector(
        ".flex.flex-col.items-center.gap-4",
      )
      expect(columnLayout).toBeNull()
    })
  })

  describe("B1: loading state reset on modal defer", () => {
    it("resets create_evaluator_loading when deferring to trust dialog", async () => {
      let trustResolve: (v: unknown) => void
      const trustPromise = new Promise((resolve) => {
        trustResolve = resolve
      })
      mockCheckCodeEvalTrust.mockImplementationOnce(() => trustPromise)

      const { container } = await renderBuilder("code_eval")

      const submitBtn = container.querySelector(
        '[data-testid="column-save-button"]',
      ) as HTMLButtonElement

      await fireEvent.click(submitBtn)
      await tick()

      expect(submitBtn.disabled).toBe(true)

      trustResolve!({ trusted: false })
      await tick()
      await new Promise((r) => setTimeout(r, 0))
      await tick()

      expect(showCalls).toContain("Trust Code and Project?")

      const saveBtn = container.querySelector(
        '[data-testid="column-save-button"]',
      ) as HTMLButtonElement
      expect(saveBtn).not.toBeNull()
      expect(saveBtn.disabled).toBe(false)
    })

    it("resets create_evaluator_loading when deferring to confirm-save dialog", async () => {
      const { container } = await renderBuilder("exact_match")

      const submitBtn = container.querySelector(
        '[data-testid="column-save-button"]',
      ) as HTMLButtonElement

      // For exact_match (no requiresTrust), handle_submit runs synchronously
      // up to the confirm_save_dialog.show() + create_evaluator_loading = false.
      // The stub sets submitting=true on click, but the handler resets it
      // in the same synchronous execution, so we verify the end state.
      await fireEvent.click(submitBtn)
      await tick()
      await new Promise((r) => setTimeout(r, 0))
      await tick()

      expect(showCalls).toContain("Save Without Testing?")

      const saveBtn = container.querySelector(
        '[data-testid="column-save-button"]',
      ) as HTMLButtonElement
      expect(saveBtn).not.toBeNull()
      expect(saveBtn.disabled).toBe(false)
    })

    it("resets loading when checkCodeEvalTrust throws an error", async () => {
      let trustReject: (e: Error) => void
      const trustPromise = new Promise((_resolve, reject) => {
        trustReject = reject
      })
      mockCheckCodeEvalTrust.mockImplementationOnce(() => trustPromise)

      const { container } = await renderBuilder("code_eval")

      const submitBtn = container.querySelector(
        '[data-testid="column-save-button"]',
      ) as HTMLButtonElement

      await fireEvent.click(submitBtn)
      await tick()

      expect(submitBtn.disabled).toBe(true)

      trustReject!(new Error("Network error checking trust"))
      await tick()
      await new Promise((r) => setTimeout(r, 0))
      await tick()

      const saveBtn = container.querySelector(
        '[data-testid="column-save-button"]',
      ) as HTMLButtonElement
      expect(saveBtn).not.toBeNull()
      expect(saveBtn.disabled).toBe(false)
    })
  })

  describe("dismiss-on-trust (fire-and-forget)", () => {
    it("grant_trust fires run_test without awaiting it", async () => {
      const { container } = await renderBuilder("code_eval")

      // Wait for task runs to load (auto-selects first run)
      await tick()
      await new Promise((r) => setTimeout(r, 0))
      await tick()

      mockTestV2Eval.mockResolvedValueOnce({
        scores: {},
        skipped_reason: "code_eval_not_trusted",
        skipped_detail: "Code eval is not trusted for this project.",
      })

      const tryBtn = container.querySelector(
        '[data-testid="run-test-btn"]',
      ) as HTMLButtonElement
      expect(tryBtn).not.toBeNull()
      await fireEvent.click(tryBtn)

      await tick()
      await new Promise((r) => setTimeout(r, 0))
      await tick()

      expect(showCalls).toContain("Trust Code and Project?")

      const buttons = actionButtonsByTitle["Trust Code and Project?"]
      expect(buttons).toBeTruthy()
      const trustAction = buttons.find(
        (b: Record<string, unknown>) => b.isWarning === true,
      )
      expect(trustAction).toBeTruthy()

      let testResolve: (v: unknown) => void
      const testPromise = new Promise((resolve) => {
        testResolve = resolve
      })
      mockGrantCodeEvalTrust.mockResolvedValueOnce({})
      mockTestV2Eval.mockImplementationOnce(() => testPromise)

      const asyncAction = trustAction!.asyncAction as () => Promise<boolean>
      const result = await asyncAction()

      expect(result).toBe(true)
      expect(mockGrantCodeEvalTrust).toHaveBeenCalled()

      testResolve!({
        scores: { accuracy: 1.0 },
        skipped_reason: null,
        skipped_detail: null,
      })
      await tick()
      await new Promise((r) => setTimeout(r, 0))
      await tick()
    })

    it("grant_trust fires do_save without awaiting it", async () => {
      const { container } = await renderBuilder("code_eval")

      mockCheckCodeEvalTrust.mockResolvedValueOnce({ trusted: false })

      const submitBtn = container.querySelector(
        '[data-testid="column-save-button"]',
      ) as HTMLButtonElement
      await fireEvent.click(submitBtn)

      await tick()
      await new Promise((r) => setTimeout(r, 0))
      await tick()

      expect(showCalls).toContain("Trust Code and Project?")

      const buttons = actionButtonsByTitle["Trust Code and Project?"]
      expect(buttons).toBeTruthy()
      const trustAction = buttons.find(
        (b: Record<string, unknown>) => b.isWarning === true,
      )
      expect(trustAction).toBeTruthy()

      let saveResolve: (v: unknown) => void
      const savePromise = new Promise((resolve) => {
        saveResolve = resolve
      })
      mockGrantCodeEvalTrust.mockResolvedValueOnce({})
      mockCreateEvalConfig.mockImplementationOnce(() => savePromise)

      const asyncAction = trustAction!.asyncAction as () => Promise<boolean>
      const result = await asyncAction()

      expect(result).toBe(true)
      expect(mockGrantCodeEvalTrust).toHaveBeenCalled()

      saveResolve!({
        id: "config123",
        type: "v2",
        properties: {},
      })
      await tick()
      await new Promise((r) => setTimeout(r, 0))
      await tick()
    })
  })
})

describe("Explainer placement + Judge Configuration header", () => {
  beforeEach(() => {
    resetCalls()
    mockFetchTaskRuns.mockReset()
    mockFetchTaskRuns.mockResolvedValue([sampleTaskRun])
  })

  afterEach(() => {
    cleanup()
  })

  it("renders eval_type_intro ABOVE the two-column row (sibling, not inside left column)", async () => {
    const { container } = await renderBuilder("exact_match")
    const intro = container.querySelector("[data-testid='eval-type-intro']")
    expect(intro).not.toBeNull()
    const columnsRow = container.querySelector(".xl\\:flex-row")
    expect(columnsRow).not.toBeNull()
    // intro should be a sibling preceding the columns, not a child
    expect(columnsRow!.contains(intro)).toBe(false)
    // intro should come before the columns row in document order
    const comparison = intro!.compareDocumentPosition(columnsRow!)
    expect(comparison & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it("renders 'Judge Configuration' header at the top of the left column", async () => {
    const { container } = await renderBuilder("exact_match")
    const columnsRow = container.querySelector(".xl\\:flex-row")
    expect(columnsRow).not.toBeNull()
    const leftCol = columnsRow!.querySelector(".flex-1.min-w-0")
    expect(leftCol).not.toBeNull()
    const heading = leftCol!.querySelector(".text-xl.font-bold")
    expect(heading).not.toBeNull()
    expect(heading?.textContent).toContain("Judge Configuration")
  })

  it("'Judge Configuration' header matches Test Run header classes (text-xl font-bold)", async () => {
    const { container } = await renderBuilder("exact_match")
    const headings = container.querySelectorAll(".text-xl.font-bold")
    const texts = Array.from(headings).map((h) => h.textContent?.trim())
    expect(texts).toContain("Judge Configuration")
    expect(texts).toContain("Test Judge")
  })
})

describe("Unsaved-changes guard gated on typing", () => {
  beforeEach(() => {
    resetCalls()
    mockFetchTaskRuns.mockReset()
    mockFetchTaskRuns.mockResolvedValue([sampleTaskRun])
  })

  afterEach(() => {
    cleanup()
  })

  it("warn_before_unload is false initially (no guard until user types)", async () => {
    const { container } = await renderBuilder("exact_match")
    const formStub = container.querySelector(
      "[data-testid='form-container-stub']",
    )
    expect(formStub).not.toBeNull()
    expect(formStub!.getAttribute("data-warn-before-unload")).toBe("false")
  })

  it("warn_before_unload becomes true after a form input event", async () => {
    const { container } = await renderBuilder("exact_match")

    // Fire a bubbling input event on the v2 form stub inside the content wrapper.
    // This simulates a real user editing a form field.
    const v2Stub = container.querySelector("[data-testid='v2-form-stub']")
    expect(v2Stub).toBeTruthy()
    await fireEvent.input(v2Stub!)
    await tick()

    const formStub = container.querySelector(
      "[data-testid='form-container-stub']",
    )
    expect(formStub!.getAttribute("data-warn-before-unload")).toBe("true")
  })
})

describe("Breadcrumb — Add Judge", () => {
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

  it("renders an 'Add Judge' breadcrumb on the builder route page", async () => {
    const { container } = await renderBuilderRoutePage("exact_match")
    const appPage = container.querySelector("[data-testid='app-page-stub']")
    expect(appPage).not.toBeNull()
    const breadcrumbs = JSON.parse(
      appPage!.getAttribute("data-breadcrumbs") || "[]",
    )
    const addJudge = breadcrumbs.find(
      (b: { label: string }) => b.label === "Add Judge",
    )
    expect(addJudge).toBeTruthy()
  })

  it("'Add Judge' breadcrumb links to the create_eval_config list page", async () => {
    const { container } = await renderBuilderRoutePage("exact_match")
    const appPage = container.querySelector("[data-testid='app-page-stub']")
    const breadcrumbs = JSON.parse(
      appPage!.getAttribute("data-breadcrumbs") || "[]",
    )
    const addJudge = breadcrumbs.find(
      (b: { label: string }) => b.label === "Add Judge",
    )
    expect(addJudge.href).toContain(
      "/specs/proj1/task1/spec1/eval1/create_eval_config",
    )
    // Should NOT point to the type-specific route
    expect(addJudge.href).not.toContain("/exact_match")
  })
})

describe("Phase 9 — Docs-link audit + theme-aware colors", () => {
  beforeEach(() => {
    resetCalls()
    mockFetchTaskRuns.mockReset()
    mockFetchTaskRuns.mockResolvedValue([sampleTaskRun])
  })

  afterEach(() => {
    cleanup()
  })

  describe("docs-link audit", () => {
    it("select screen does not render Read the Docs or sub_subtitle", async () => {
      const { container } = await renderPickerPage()
      expect(container.textContent).not.toContain("Read the Docs")
      expect(container.textContent).not.toContain("Read the docs")
      expect(container.textContent).not.toContain("All judge types")
    })

    it("builder route does not render Read the Docs or sub_subtitle", async () => {
      const { container } = await renderBuilderRoutePage("exact_match")
      expect(container.textContent).not.toContain("Read the Docs")
      expect(container.textContent).not.toContain("Read the docs")
    })

    it("builder route does not pass sub_subtitle to AppPage", async () => {
      const { container } = await renderBuilderRoutePage("exact_match")
      const appPage = container.querySelector("[data-testid='app-page-stub']")
      expect(appPage).not.toBeNull()
      expect(appPage?.innerHTML).not.toContain("sub_subtitle")
    })
  })

  describe("design-guide color palette in create-flow components", () => {
    it("eval_type_intro uses design-guide secondary text color", async () => {
      const { container } = await renderBuilder("exact_match")
      const intro = container.querySelector("[data-testid='eval-type-intro']")
      expect(intro).not.toBeNull()
      expect(intro?.innerHTML).toContain("text-gray-500")
      expect(intro?.innerHTML).not.toContain("text-base-content")
    })

    it("test run pane uses design-guide palette, not non-standard colors", async () => {
      const { container } = await renderBuilder("exact_match")
      const pane = container.querySelector("[data-testid='test-run-pane']")
      expect(pane).not.toBeNull()
      expect(pane?.innerHTML).not.toContain("text-base-content")
      expect(pane?.innerHTML).not.toContain("text-gray-400")
      expect(pane?.innerHTML).not.toContain("text-gray-600")
      expect(pane?.innerHTML).not.toContain("text-gray-300")
    })

    it("confirm save dialog uses design-guide secondary text color", async () => {
      const { container } = await renderBuilder("exact_match")
      const dialogs = container.querySelectorAll("[data-testid='dialog-stub']")
      const confirmDialog = Array.from(dialogs).find(
        (d) => d.getAttribute("data-title") === "Save Without Testing?",
      )
      expect(confirmDialog).not.toBeNull()
      expect(confirmDialog?.innerHTML).toContain("text-gray-500")
      expect(confirmDialog?.innerHTML).not.toContain("text-base-content")
    })
  })
})
