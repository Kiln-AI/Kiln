// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import { tick } from "svelte"

// ---------------------------------------------------------------------------
// Module-level mocks — must come before the dynamic page import
// ---------------------------------------------------------------------------

const { mockPage, mockClientGET, setResultsResponse } = vi.hoisted(() => {
  const pageValue = {
    params: {
      project_id: "proj1",
      task_id: "task1",
      spec_id: "spec1",
      eval_id: "eval1",
      eval_config_id: "ec1",
      run_config_id: "rc1",
    },
    url: new URL("http://localhost/specs/proj1/task1/spec1/eval1/ec1/rc1"),
  }
  const mockPage = {
    subscribe(fn: (value: typeof pageValue) => void) {
      fn(pageValue)
      return () => {}
    },
  }

  let results_response: Record<string, unknown> = {}
  const setResultsResponse = (v: Record<string, unknown>) => {
    results_response = v
  }
  const mockClientGET = vi.fn().mockImplementation(() => {
    return Promise.resolve({ data: results_response, error: null })
  })

  return { mockPage, mockClientGET, setResultsResponse }
})

vi.mock("$app/stores", () => ({
  page: mockPage,
}))

vi.mock("$lib/api_client", () => ({
  client: {
    GET: mockClientGET,
  },
}))

vi.mock("$lib/stores", () => ({
  model_info: {
    subscribe: (fn: (v: null) => void) => {
      fn(null)
      return () => {}
    },
  },
  load_model_info: vi.fn(),
  model_name: () => "Model",
  provider_name_from_id: () => "Provider",
  prompt_name_from_id: () => "Prompt",
  load_available_models: vi.fn(),
  get_task_composite_id: (project_id: string, task_id: string) =>
    `${project_id}:${task_id}`,
}))

vi.mock("$lib/stores/prompts_store", () => ({
  prompts_by_task_composite_id: {
    subscribe: (fn: (v: Record<string, unknown>) => void) => {
      fn({})
      return () => {}
    },
  },
  load_task_prompts: vi.fn(),
}))

vi.mock("$lib/agent", () => ({
  agentInfo: { set: vi.fn() },
}))

// Stub heavy UI components with real .svelte stubs
vi.mock("../../../../../../../../app_page.svelte", async () => {
  const Stub = await import("../../../__tests__/app_page_stub.svelte")
  return { default: Stub.default }
})

// jsdom does not implement <dialog>.showModal(), which the real Dialog calls on mount.
vi.mock("$lib/ui/dialog.svelte", async () => {
  const Stub = await import("./__tests__/dialog_stub.svelte")
  return { default: Stub.default }
})

// Dynamic import after all mocks
const RunResultPage = (await import("./+page.svelte")).default

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const base_response = {
  eval: {
    id: "eval1",
    name: "Test Eval",
    eval_set_filter_id: "tag::eval_set",
    eval_configs_filter_id: "tag::golden",
    output_scores: [{ name: "accuracy", type: "five_star" }],
  },
  eval_config: {
    id: "ec1",
    name: "Judge",
    config_type: "g_eval",
    model_name: "gpt-4",
    model_provider: "openai",
    properties: {},
  },
  run_config: {
    id: "rc1",
    name: "Run Config",
    run_config_properties: {
      type: "kiln_agent",
      model_name: "gpt-4",
      model_provider_name: "openai",
      prompt_id: "simple_prompt_builder",
    },
  },
}

async function render_page(
  results: Array<Record<string, unknown>>,
): Promise<HTMLElement> {
  setResultsResponse({ ...base_response, results })
  const { container } = render(RunResultPage)
  await tick()
  await new Promise((r) => setTimeout(r, 0))
  await tick()
  return container
}

// The placeholder copy is wrapped across source lines, so compare on collapsed
// whitespace.
function visible_text(container: HTMLElement): string {
  return (container.textContent ?? "").replace(/\s+/g, " ").trim()
}

const PLACEHOLDER =
  "Trace unavailable. It may have been deleted or not included in an import."

function result_row(overrides: Record<string, unknown>) {
  return {
    input: null,
    output: null,
    task_run_trace: null,
    task_run_usage: null,
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("run result page — missing trace placeholder", () => {
  afterEach(() => {
    cleanup()
  })

  it("renders the placeholder in the output cell for a dangling scored_run_id", async () => {
    const container = await render_page([
      result_row({
        eval_run: {
          id: "er1",
          scored_run_id: "gone_run",
          scores: {},
          intermediate_outputs: null,
        },
      }),
    ])

    const text = visible_text(container)
    expect(text).toContain(PLACEHOLDER)
  })

  it("renders the placeholder beside a filled input when only the trace is gone", async () => {
    // The server fills input from the dataset item when the trace can't supply it,
    // so a dangling pointer usually arrives with input set and output null. The
    // placeholder must still appear where the output would have been.
    const container = await render_page([
      result_row({
        eval_run: {
          id: "er4",
          scored_run_id: "gone_run",
          scores: {},
          intermediate_outputs: null,
        },
        input: "the question from the dataset item",
      }),
    ])

    const text = visible_text(container)
    expect(text).toContain(PLACEHOLDER)
    expect(text).toContain("the question from the dataset item")
  })

  it("renders input and output, not the placeholder, when the trace resolved", async () => {
    const container = await render_page([
      result_row({
        eval_run: {
          id: "er2",
          scored_run_id: "tr2",
          scores: {},
          intermediate_outputs: null,
        },
        input: "the input",
        output: "the output",
      }),
    ])

    const text = visible_text(container)
    expect(text).not.toContain(PLACEHOLDER)
    expect(text).toContain("the input")
    expect(text).toContain("the output")
  })

  it("does not use the placeholder for records that never pointed at a trace", async () => {
    // A run skipped before generation has no scored_run_id; nothing was deleted, so
    // "trace unavailable" would be the wrong statement.
    const container = await render_page([
      result_row({
        eval_run: {
          id: "er3",
          scores: {},
          intermediate_outputs: null,
          skipped_reason: "missing_reference_key",
        },
      }),
    ])

    expect(visible_text(container)).not.toContain(PLACEHOLDER)
  })
})
