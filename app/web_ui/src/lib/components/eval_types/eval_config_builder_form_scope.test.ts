// @vitest-environment jsdom
/**
 * Structural guard: the <form> rendered by FormContainer must NOT contain the
 * test-run pane. If it does, FormElement validators inside the test pane (or
 * any future inputs there) will block Save with spurious validation errors.
 *
 * This test uses the REAL FormContainer (no stub) so the <form> element exists
 * in the DOM. Sub-components that need network or complex setup are stubbed.
 */
import { describe, it, expect, vi, afterEach } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import { tick } from "svelte"
import * as svelteMod from "svelte"

// ---------------------------------------------------------------------------
// Mocks — stub network/stores/navigation, but keep FormContainer REAL
// ---------------------------------------------------------------------------

const { mockPage, mockClientGET, mockLoadTask, mockLoadModels, onMountCbs } =
  vi.hoisted(() => {
    type PageValue = { params: Record<string, string>; url: URL }
    let pageValue: PageValue = {
      params: {
        project_id: "p1",
        task_id: "t1",
        eval_id: "e1",
        spec_id: "s1",
      },
      url: new URL("http://localhost/specs/p1/t1/s1/e1/create_eval_config"),
    }
    type Sub = (v: PageValue) => void
    const subs = new Set<Sub>()
    const mockPage = {
      subscribe(fn: Sub) {
        subs.add(fn)
        fn(pageValue)
        return () => subs.delete(fn)
      },
    }
    return {
      mockPage,
      mockClientGET: vi.fn().mockResolvedValue({ data: null, error: null }),
      mockLoadTask: vi.fn().mockResolvedValue({
        id: "t1",
        name: "T",
        input_json_schema: "{}",
        output_json_schema: "{}",
      }),
      mockLoadModels: vi.fn().mockResolvedValue([]),
      onMountCbs: [] as Array<() => unknown>,
    }
  })

vi.mock("$app/stores", () => ({ page: mockPage }))
vi.mock("$app/navigation", () => ({
  goto: vi.fn(),
  beforeNavigate: vi.fn(),
}))
vi.mock("$lib/api_client", () => ({ client: { GET: mockClientGET } }))
vi.mock("$lib/stores", () => ({
  load_task: mockLoadTask,
  load_available_models: mockLoadModels,
}))
vi.mock("posthog-js", () => ({ default: { capture: vi.fn() } }))
vi.mock("$lib/stores/evals_store", () => ({
  set_current_eval_config: vi.fn(),
}))
vi.mock("$lib/agent", () => ({ agentInfo: { set: vi.fn() } }))

// Stub the heavy form sub-components but NOT FormContainer
vi.mock("$lib/components/eval_types/llm_judge_form.svelte", async () => {
  const S = await import(
    "../../../routes/(app)/specs/[project_id]/[task_id]/[spec_id]/[eval_id]/create_eval_config/__tests__/llm_judge_form_stub.svelte"
  )
  return { default: S.default }
})

// Use the v2 form stub via the registry mock
const V2Stub = await import(
  "../../../routes/(app)/specs/[project_id]/[task_id]/[spec_id]/[eval_id]/create_eval_config/__tests__/v2_form_stub.svelte"
)
vi.mock("$lib/utils/eval_types/registry", async (importOriginal) => {
  const orig = (await importOriginal()) as Record<string, unknown>
  return {
    ...orig,
    getV2EvalTypeMetadata: (type: string) => {
      const meta = (
        orig.getV2EvalTypeMetadata as (t: string) => Record<string, unknown>
      )(type)
      return { ...meta, createFormComponent: V2Stub.default }
    },
  }
})

// Stub eval API calls (network)
vi.mock("$lib/api/v2_eval_api", async (importOriginal) => {
  const orig = (await importOriginal()) as Record<string, unknown>
  return {
    ...orig,
    testV2Eval: vi.fn(),
    testV2EvalLlmJudge: vi.fn(),
    createEvalConfig: vi.fn(),
    createLlmJudgeConfig: vi.fn(),
    checkCodeEvalTrust: vi.fn(),
    grantCodeEvalTrust: vi.fn(),
    fetchTaskRuns: vi.fn().mockResolvedValue([]),
  }
})

vi.mock("$lib/utils/json_schema_editor/json_schema_templates", () => ({
  string_to_json_key: (s: string) =>
    s
      .trim()
      .toLowerCase()
      .replace(/ /g, "_")
      .replace(/[^a-z0-9_.]/g, ""),
}))

vi.mock("$lib/utils/format_expanded_content", () => ({
  formatExpandedContent: (text: string) => ({ isJson: false, value: text }),
}))

// Dynamic import AFTER mocks
const EvalConfigBuilder = (
  await import("$lib/components/eval_types/eval_config_builder.svelte")
).default

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

async function renderBuilder(evalType: string = "contains") {
  onMountCbs.length = 0
  const spy = vi
    .spyOn(svelteMod, "onMount")
    .mockImplementation((fn: () => unknown) => {
      onMountCbs.push(fn)
    })

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const result = render(EvalConfigBuilder as any, {
    props: {
      eval_config_type: evalType,
      evaluator: { id: "e1", name: "E", output_scores: [] },
      task: {
        id: "t1",
        name: "T",
        instruction: "i",
        input_json_schema: "{}",
        output_json_schema: "{}",
      },
      spec: { id: "s1", name: "S" },
      project_id: "p1",
      task_id: "t1",
      eval_id: "e1",
      spec_id: "s1",
    },
  })

  spy.mockRestore()
  for (const cb of onMountCbs) await cb()
  await tick()
  return result
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("Form-scope guard: test-run pane outside <form>", () => {
  afterEach(() => cleanup())

  it("the <form> element does NOT contain the test-run pane", async () => {
    const { container } = await renderBuilder("contains")

    const form = container.querySelector("form")
    expect(form).not.toBeNull()

    const testRunPane = container.querySelector("[data-testid='test-run-pane']")
    expect(testRunPane).not.toBeNull()

    // The critical invariant: the test-run pane must be OUTSIDE the <form>.
    expect(form!.contains(testRunPane)).toBe(false)
  })

  it("guard holds for code_eval type as well", async () => {
    const { container } = await renderBuilder("code_eval")

    const form = container.querySelector("form")
    expect(form).not.toBeNull()

    const testRunPane = container.querySelector("[data-testid='test-run-pane']")
    expect(testRunPane).not.toBeNull()

    expect(form!.contains(testRunPane)).toBe(false)
  })

  it("guard holds for llm_judge type as well", async () => {
    const { container } = await renderBuilder("llm_judge")

    const form = container.querySelector("form")
    expect(form).not.toBeNull()

    const testRunPane = container.querySelector("[data-testid='test-run-pane']")
    expect(testRunPane).not.toBeNull()

    expect(form!.contains(testRunPane)).toBe(false)
  })

  it("the save button IS inside the <form>", async () => {
    const { container } = await renderBuilder("contains")

    const form = container.querySelector("form")
    const saveBtn = container.querySelector(
      "[data-testid='column-save-button']",
    )
    expect(form).not.toBeNull()
    expect(saveBtn).not.toBeNull()
    expect(form!.contains(saveBtn)).toBe(true)
  })
})
