// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import { tick } from "svelte"

// ---------------------------------------------------------------------------
// Module-level mocks — must come before the dynamic page import
// ---------------------------------------------------------------------------

const { mockPage, mockClientGET, setEval, setEvalConfigs, setScoreSummary } =
  vi.hoisted(() => {
    const pageValue = {
      params: {
        project_id: "proj1",
        task_id: "task1",
        spec_id: "legacy",
        eval_id: "eval1",
      },
      url: new URL("http://localhost/specs/proj1/task1/legacy/eval1"),
    }
    const mockPage = {
      subscribe(fn: (value: typeof pageValue) => void) {
        fn(pageValue)
        return () => {}
      },
    }

    let eval_response: Record<string, unknown> = {}
    let eval_configs_response: Record<string, unknown>[] = []
    let score_summary_response: Record<string, unknown> = {}
    const setEval = (v: Record<string, unknown>) => {
      eval_response = v
    }
    const setEvalConfigs = (v: Record<string, unknown>[]) => {
      eval_configs_response = v
    }
    const setScoreSummary = (v: Record<string, unknown>) => {
      score_summary_response = v
    }

    const mockClientGET = vi.fn().mockImplementation((path: string) => {
      if (path.endsWith("/eval_configs_score_summary")) {
        return Promise.resolve({ data: score_summary_response, error: null })
      }
      if (path.endsWith("/eval_configs")) {
        return Promise.resolve({ data: eval_configs_response, error: null })
      }
      if (path.endsWith("/evals/{eval_id}")) {
        return Promise.resolve({ data: eval_response, error: null })
      }
      return Promise.resolve({ data: null, error: null })
    })

    return { mockPage, mockClientGET, setEval, setEvalConfigs, setScoreSummary }
  })

vi.mock("$app/stores", () => ({ page: mockPage }))

vi.mock("$lib/api_client", () => ({
  client: { GET: mockClientGET },
  base_url: "http://localhost:8757",
}))

vi.mock("$lib/stores", () => ({
  load_model_info: vi.fn(),
  load_available_models: vi.fn(),
  model_info: {
    subscribe: (fn: (v: null) => void) => {
      fn(null)
      return () => {}
    },
  },
  model_name: (name: string | null) => name ?? "",
  provider_name_from_id: (id: string) => id,
}))

vi.mock("$lib/stores/prompts_store", () => ({
  load_task_prompts: vi.fn(),
  prompts: {
    subscribe: (fn: (v: null) => void) => {
      fn(null)
      return () => {}
    },
  },
}))

vi.mock("$lib/stores/evals_store", () => ({
  set_current_eval_config: vi.fn(),
}))

vi.mock("$lib/agent", () => ({ agentInfo: { set: vi.fn() } }))

vi.mock("../../../../../../app_page.svelte", async () => {
  const Stub = await import("../__tests__/app_page_stub.svelte")
  return { default: Stub.default }
})

vi.mock("$lib/ui/info_tooltip.svelte", async () => {
  const Stub = await import("../__tests__/info_tooltip_stub.svelte")
  return { default: Stub.default }
})

vi.mock("$lib/components/run_eval.svelte", async () => {
  const Stub = await import("./__tests__/run_eval_stub.svelte")
  return { default: Stub.default }
})

const EvalConfigsPage = (await import("./+page.svelte")).default

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const RUN_ALL_TOOLTIP =
  "No scores were found for this judge. Click 'Run All Evals' to generate scores"
const REFERENCE_DATA_WARNING =
  "This judge requires reference data, which is not populated. It can't be run or compared here."
const SELECT_A_WINNER = "Click 'Set as Default' below to select a winner."
const INCOMPLETE_WARNING = "You evals are incomplete."

function evaluator(overrides: Record<string, unknown> = {}) {
  return {
    v: 1,
    id: "eval1",
    name: "Test Eval",
    output_scores: [
      { name: "score1", instruction: "desc1", type: "five_star" },
    ],
    eval_set_filter_id: "tag::eval_set",
    eval_configs_filter_id: "tag::golden",
    evaluation_data_type: "final_answer",
    current_config_id: null,
    model_type: "eval",
    ...overrides,
  }
}

function llm_judge_config(
  id: string,
  name: string,
  reference_keys: string[],
): Record<string, unknown> {
  return {
    v: 1,
    id,
    name,
    config_type: "v2",
    properties: {
      type: "llm_judge",
      model_name: "gpt-4",
      model_provider: "openai",
      prompt_template: "Grade {{ final_message }}",
      reference_keys,
      g_eval: false,
    },
    model_type: "v2",
  }
}

function v1_config(id: string, name: string): Record<string, unknown> {
  return {
    v: 1,
    id,
    name,
    config_type: "g_eval",
    properties: { eval_steps: ["step1"] },
    model_name: "gpt-4",
    model_provider: "openai",
    model_type: "legacy",
  }
}

function score_summary(
  percent_complete: Record<string, number>,
  overrides: Record<string, unknown> = {},
) {
  return {
    results: {},
    eval_config_percent_complete: percent_complete,
    dataset_size: 30,
    fully_rated_count: 30,
    partially_rated_count: 0,
    not_rated_count: 0,
    ...overrides,
  }
}

async function render_page(): Promise<HTMLElement> {
  const { container } = render(EvalConfigsPage)
  await tick()
  await new Promise((r) => setTimeout(r, 0))
  await tick()
  return container
}

/** The table row whose Judge cell names this judge. */
function row_for(container: HTMLElement, judge_name: string): HTMLElement {
  const row = Array.from(container.querySelectorAll("tbody tr")).find((tr) =>
    tr.textContent?.includes(judge_name),
  )
  if (!row) {
    throw new Error(`No row found for judge '${judge_name}'`)
  }
  return row as HTMLElement
}

/** The row's "Set as Default" button, whose styling carries the winner nudge. */
function set_as_default_button(
  container: HTMLElement,
  judge_name: string,
): HTMLButtonElement {
  const button = Array.from(
    row_for(container, judge_name).querySelectorAll("button"),
  ).find((b) => b.textContent?.includes("Set as Default"))
  if (!button) {
    throw new Error(`No 'Set as Default' button in the row for '${judge_name}'`)
  }
  return button
}

beforeEach(() => {
  setEval(evaluator())
  setEvalConfigs([])
  setScoreSummary(score_summary({}))
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("judges that need reference data", () => {
  it("warns on the V2 judge that declares a reference key, and only that one", async () => {
    setEvalConfigs([
      llm_judge_config("ordinary", "Ordinary Judge", []),
      llm_judge_config("reference", "Reference Judge", ["reference_answer"]),
    ])
    setScoreSummary(score_summary({ ordinary: 1.0, reference: 0.0 }))

    const container = await render_page()

    expect(row_for(container, "Reference Judge").textContent).toContain(
      REFERENCE_DATA_WARNING,
    )
    expect(row_for(container, "Ordinary Judge").textContent).not.toContain(
      REFERENCE_DATA_WARNING,
    )
  })

  it("warns on a V1 judge when the eval grades against a reference answer", async () => {
    setEval(evaluator({ evaluation_data_type: "reference_answer" }))
    setEvalConfigs([v1_config("legacy", "Legacy Judge")])
    setScoreSummary(score_summary({ legacy: 0.0 }))

    const container = await render_page()

    expect(row_for(container, "Legacy Judge").textContent).toContain(
      REFERENCE_DATA_WARNING,
    )
  })

  it("leaves a V1 judge alone on an eval that grades the output on its own", async () => {
    setEvalConfigs([v1_config("legacy", "Legacy Judge")])
    setScoreSummary(score_summary({ legacy: 1.0 }))

    const container = await render_page()

    expect(row_for(container, "Legacy Judge").textContent).not.toContain(
      REFERENCE_DATA_WARNING,
    )
  })

  it("stops telling the user to click 'Run All Evals' from an unscoreable row", async () => {
    setEvalConfigs([
      llm_judge_config("ordinary", "Ordinary Judge", []),
      llm_judge_config("reference", "Reference Judge", ["reference_answer"]),
    ])
    setScoreSummary(score_summary({ ordinary: 1.0, reference: 0.0 }))

    const container = await render_page()

    expect(row_for(container, "Reference Judge").textContent).not.toContain(
      RUN_ALL_TOOLTIP,
    )
    // The ordinary judge has no scores either, and for it the advice still applies.
    expect(row_for(container, "Ordinary Judge").textContent).toContain(
      RUN_ALL_TOOLTIP,
    )
  })

  it("does not report the evals as incomplete because of a judge it will skip", async () => {
    setEvalConfigs([
      llm_judge_config("ordinary", "Ordinary Judge", []),
      llm_judge_config("reference", "Reference Judge", ["reference_answer"]),
    ])
    setScoreSummary(score_summary({ ordinary: 1.0, reference: 0.0 }))

    const container = await render_page()

    expect(container.textContent).not.toContain(INCOMPLETE_WARNING)
  })

  it("still reports the evals as incomplete when a comparable judge is behind", async () => {
    setEvalConfigs([
      llm_judge_config("ordinary", "Ordinary Judge", []),
      llm_judge_config("reference", "Reference Judge", ["reference_answer"]),
    ])
    setScoreSummary(score_summary({ ordinary: 0.5, reference: 0.0 }))

    const container = await render_page()

    expect(container.textContent).toContain(INCOMPLETE_WARNING)
  })

  it("reports the row as not comparable rather than as behind", async () => {
    setEvalConfigs([
      llm_judge_config("reference", "Reference Judge", ["reference_answer"]),
      llm_judge_config("ordinary", "Ordinary Judge", []),
    ])
    setScoreSummary(score_summary({ reference: 0.0, ordinary: 0.5 }))

    const container = await render_page()

    const blocked_row = row_for(container, "Reference Judge")
    expect(blocked_row.textContent).toContain("Not comparable")
    expect(blocked_row.textContent).not.toContain("0% Complete")
    expect(blocked_row.querySelector(".text-error")).toBeNull()
    // The judge that really is behind still says so, in error red.
    const behind_row = row_for(container, "Ordinary Judge")
    expect(behind_row.textContent).toContain("50% Complete")
    expect(behind_row.querySelector(".text-error")).not.toBeNull()
  })

  it("does not stack 'evals are incomplete' on top of an empty golden dataset", async () => {
    // The server sends no per-config completion at all for an empty golden set, so a
    // missing entry must not be read as 0%.
    setEvalConfigs([llm_judge_config("ordinary", "Ordinary Judge", [])])
    setScoreSummary(
      score_summary({}, { dataset_size: 0, fully_rated_count: 0 }),
    )

    const container = await render_page()

    expect(container.textContent).toContain("zero items in your golden dataset")
    expect(container.textContent).not.toContain(INCOMPLETE_WARNING)
  })

  it("does not nudge the user to pick a winner when no judge can be compared", async () => {
    setEvalConfigs([
      llm_judge_config("reference", "Reference Judge", ["reference_answer"]),
    ])
    setScoreSummary(score_summary({ reference: 0.0 }))

    const container = await render_page()

    expect(container.textContent).not.toContain(SELECT_A_WINNER)
  })

  it("still nudges the user to pick a winner among the judges it did compare", async () => {
    setEvalConfigs([
      llm_judge_config("ordinary", "Ordinary Judge", []),
      llm_judge_config("reference", "Reference Judge", ["reference_answer"]),
    ])
    setScoreSummary(score_summary({ ordinary: 1.0, reference: 0.0 }))

    const container = await render_page()

    expect(container.textContent).toContain(SELECT_A_WINNER)
    // Every comparable judge is complete, so the nudge is the primary call to action
    // and "Run All Evals" steps down — an unscoreable judge must not hold that back.
    const run_button = container.querySelector("[data-testid='run-eval-stub']")
    expect(run_button?.getAttribute("data-btn-primary")).toBe("false")

    // ...but the nudge points at the judge that has scores, not the one that can't.
    expect(
      set_as_default_button(container, "Ordinary Judge").className,
    ).toContain("btn-primary")
    expect(
      set_as_default_button(container, "Reference Judge").className,
    ).not.toContain("btn-primary")
  })

  it("keeps 'Run All Evals' as the call to action while a comparable judge is unscored", async () => {
    setEvalConfigs([
      llm_judge_config("ordinary", "Ordinary Judge", []),
      llm_judge_config("reference", "Reference Judge", ["reference_answer"]),
    ])
    setScoreSummary(score_summary({ ordinary: 0.0, reference: 0.0 }))

    const container = await render_page()

    const run_button = container.querySelector("[data-testid='run-eval-stub']")
    expect(run_button?.getAttribute("data-btn-primary")).toBe("true")
  })
})
