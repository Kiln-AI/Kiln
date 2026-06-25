// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest"
import { render, fireEvent, cleanup } from "@testing-library/svelte"
import { tick } from "svelte"

// ---------------------------------------------------------------------------
// Module-level mocks
// ---------------------------------------------------------------------------

vi.mock("$lib/ui/dialog.svelte", async () => {
  const Stub = await import("../__tests__/dialog_stub.svelte")
  return { default: Stub.default }
})

vi.mock("$lib/utils/format_expanded_content", () => ({
  formatExpandedContent: (text: string) => ({ isJson: false, value: text }),
}))

vi.mock("$app/navigation", () => ({
  goto: vi.fn(),
}))

// Dynamic imports after mocks
const EvalTestRunPane = (await import("./eval_test_run_pane.svelte")).default
const TestRunInputCard = (await import("./test_run_input_card.svelte")).default
const TestRunBrowseDialog = (await import("./test_run_browse_dialog.svelte"))
  .default
const ManualExampleDialog = (await import("./manual_example_dialog.svelte"))
  .default
const ReferenceDataField = (await import("./reference_data_field.svelte"))
  .default
const { actionButtonsByTitle, resetActionButtons } = await import(
  "../__tests__/dialog_stub.svelte"
)

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeRun(
  id: string,
  input: string,
  output: string,
  created_at?: string,
) {
  return {
    v: 1,
    id,
    input,
    output: { output, source: { type: "human" as const } },
    tags: [],
    created_at: created_at || new Date().toISOString(),
  }
}

function makeKilnError(msg: string) {
  return { getMessage: () => msg }
}

const run1 = makeRun("r1", "input one", "output one")
const run2 = makeRun("r2", "input two", "output two")
const run3 = makeRun("r3", "input three", "output three")
const run4 = makeRun("r4", "input four", "output four")

// ---------------------------------------------------------------------------
// Tests: EvalTestRunPane
// ---------------------------------------------------------------------------

describe("EvalTestRunPane", () => {
  afterEach(() => {
    cleanup()
  })

  describe("State 1: Empty dataset", () => {
    it("renders empty state when no runs available", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(EvalTestRunPane as any, {
        props: { available_runs: [], runs_loading: false },
      })
      const emptyState = container.querySelector('[data-testid="empty-state"]')
      expect(emptyState).not.toBeNull()
      expect(container.textContent).toContain("No sample inputs yet")
      expect(container.textContent).toContain(
        "Run your task to generate inputs",
      )
    })

    it("shows Go to Run link", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(EvalTestRunPane as any, {
        props: { available_runs: [], runs_loading: false },
      })
      const goToRunLink = container.querySelector("a.btn")
      expect(goToRunLink).not.toBeNull()
      expect(goToRunLink?.textContent?.trim()).toContain("Go to Run")
    })

    it("shows Save Without Testing button", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(EvalTestRunPane as any, {
        props: { available_runs: [], runs_loading: false },
      })
      const saveBtn = container.querySelector(
        '[data-testid="save-without-testing"]',
      )
      expect(saveBtn).not.toBeNull()
      expect(saveBtn?.textContent?.trim()).toContain("Save Without Testing")
    })

    it("dispatches saveWithoutTesting event on button click", async () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container, component } = render(EvalTestRunPane as any, {
        props: { available_runs: [], runs_loading: false },
      })
      const handler = vi.fn()
      component.$on("saveWithoutTesting", handler)

      const saveBtn = container.querySelector(
        '[data-testid="save-without-testing"]',
      ) as HTMLButtonElement
      await fireEvent.click(saveBtn)
      expect(handler).toHaveBeenCalled()
    })
  })

  describe("State 2: Ready (pick input)", () => {
    it("renders selected run card and quick-picks", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(EvalTestRunPane as any, {
        props: {
          available_runs: [run1, run2, run3, run4],
          selected_run: run1,
          runs_loading: false,
        },
      })

      const selectedCard = container.querySelector(
        '[data-testid="selected-run-card"]',
      )
      expect(selectedCard).not.toBeNull()
      expect(selectedCard?.textContent).toContain("input one")

      const quickPicks = container.querySelectorAll(
        '[data-testid="quick-pick-card"]',
      )
      expect(quickPicks.length).toBe(2)
    })

    it("shows max 2 quick-picks excluding selected", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(EvalTestRunPane as any, {
        props: {
          available_runs: [run1, run2, run3, run4],
          selected_run: run1,
          runs_loading: false,
        },
      })

      const quickPicks = container.querySelectorAll(
        '[data-testid="quick-pick-card"]',
      )
      expect(quickPicks.length).toBe(2)
      expect(quickPicks[0].textContent).toContain("input two")
      expect(quickPicks[1].textContent).toContain("input three")
    })

    it("always shows Browse all dataset inputs link", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(EvalTestRunPane as any, {
        props: {
          available_runs: [run1],
          selected_run: run1,
          runs_loading: false,
        },
      })

      const browseLink = container.querySelector(
        '[data-testid="browse-all-link"]',
      )
      expect(browseLink).not.toBeNull()
      expect(browseLink?.textContent?.trim()).toBe("Browse all dataset inputs")
    })

    it("shows Run button", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(EvalTestRunPane as any, {
        props: {
          available_runs: [run1],
          selected_run: run1,
          runs_loading: false,
        },
      })

      const runBtn = container.querySelector('[data-testid="run-test-btn"]')
      expect(runBtn).not.toBeNull()
      expect(runBtn?.textContent?.trim()).toContain("Run")
    })

    it("shows results placeholder", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(EvalTestRunPane as any, {
        props: {
          available_runs: [run1],
          selected_run: run1,
          runs_loading: false,
        },
      })

      const placeholder = container.querySelector(
        '[data-testid="results-placeholder"]',
      )
      expect(placeholder).not.toBeNull()
      expect(placeholder?.textContent).toContain("Run to see scores")
    })

    it("dispatches run event on Run button click", async () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container, component } = render(EvalTestRunPane as any, {
        props: {
          available_runs: [run1],
          selected_run: run1,
          runs_loading: false,
        },
      })
      const handler = vi.fn()
      component.$on("run", handler)

      const runBtn = container.querySelector(
        '[data-testid="run-test-btn"]',
      ) as HTMLButtonElement
      await fireEvent.click(runBtn)
      expect(handler).toHaveBeenCalled()
    })

    it("dispatches select event when clicking a quick-pick", async () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container, component } = render(EvalTestRunPane as any, {
        props: {
          available_runs: [run1, run2, run3],
          selected_run: run1,
          runs_loading: false,
        },
      })
      const handler = vi.fn()
      component.$on("select", handler)

      const quickPicks = container.querySelectorAll(
        '[data-testid="quick-pick-card"]',
      )
      await fireEvent.click(quickPicks[0])
      expect(handler).toHaveBeenCalled()
    })

    it("shows reference data field", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(EvalTestRunPane as any, {
        props: {
          available_runs: [run1],
          selected_run: run1,
          runs_loading: false,
        },
      })

      const refField = container.querySelector(
        '[data-testid="reference-data-field"]',
      )
      expect(refField).not.toBeNull()
    })
  })

  describe("State 3: Running", () => {
    it("renders running state with spinner", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(EvalTestRunPane as any, {
        props: {
          available_runs: [run1],
          selected_run: run1,
          test_loading: true,
          runs_loading: false,
        },
      })

      const runningState = container.querySelector(
        '[data-testid="running-state"]',
      )
      expect(runningState).not.toBeNull()
      expect(container.textContent).toContain("Running...")
      expect(container.textContent).toContain("Executing the scorer")
    })

    it("shows Cancel button", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(EvalTestRunPane as any, {
        props: {
          available_runs: [run1],
          selected_run: run1,
          test_loading: true,
          runs_loading: false,
        },
      })

      const cancelBtn = container.querySelector('[data-testid="cancel-run"]')
      expect(cancelBtn).not.toBeNull()
    })

    it("dispatches cancel event on Cancel click", async () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container, component } = render(EvalTestRunPane as any, {
        props: {
          available_runs: [run1],
          selected_run: run1,
          test_loading: true,
          runs_loading: false,
        },
      })
      const handler = vi.fn()
      component.$on("cancel", handler)

      const cancelBtn = container.querySelector(
        '[data-testid="cancel-run"]',
      ) as HTMLButtonElement
      await fireEvent.click(cancelBtn)
      expect(handler).toHaveBeenCalled()
    })

    it("shows selected run with Change disabled", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(EvalTestRunPane as any, {
        props: {
          available_runs: [run1],
          selected_run: run1,
          test_loading: true,
          runs_loading: false,
        },
      })

      const selectedCard = container.querySelector(
        '[data-testid="selected-run-card"]',
      )
      expect(selectedCard).not.toBeNull()

      const changeBtn = selectedCard?.querySelector(
        "button",
      ) as HTMLButtonElement
      expect(changeBtn?.disabled).toBe(true)
    })
  })

  describe("State 4: Results", () => {
    it("renders scores when test result has scores", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(EvalTestRunPane as any, {
        props: {
          available_runs: [run1],
          selected_run: run1,
          runs_loading: false,
          test_result: {
            scores: { accuracy: 0.95, helpfulness: 4.0 },
            skipped_reason: null,
            skipped_detail: null,
          },
          test_has_valid_run: true,
        },
      })

      const scoresSection = container.querySelector(
        '[data-testid="scores-section"]',
      )
      expect(scoresSection).not.toBeNull()
      expect(container.textContent).toContain("accuracy")
      expect(container.textContent).toContain("0.95")
      expect(container.textContent).toContain("helpfulness")
      expect(container.textContent).toContain("4")
      expect(container.textContent).toContain("preview")
      expect(container.textContent).toContain("not saved")
    })

    it("shows skipped result with reason", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(EvalTestRunPane as any, {
        props: {
          available_runs: [run1],
          selected_run: run1,
          runs_loading: false,
          test_result: {
            scores: null,
            skipped_reason: "no_reference_data",
            skipped_detail: "No reference data available",
          },
        },
      })

      const skippedResult = container.querySelector(
        '[data-testid="skipped-result"]',
      )
      expect(skippedResult).not.toBeNull()
      expect(container.textContent).toContain("Skipped")
      expect(container.textContent).toContain("No reference data available")
    })

    it("shows shape warning when present", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(EvalTestRunPane as any, {
        props: {
          available_runs: [run1],
          selected_run: run1,
          runs_loading: false,
          test_result: {
            scores: { wrong_key: 1.0 },
            skipped_reason: null,
          },
          test_shape_warning: "Missing expected scores: accuracy",
        },
      })

      const shapeWarning = container.querySelector(
        '[data-testid="shape-warning"]',
      )
      expect(shapeWarning).not.toBeNull()
      expect(container.textContent).toContain("Score Shape Mismatch")
      expect(container.textContent).toContain("Missing expected scores")
    })

    it("shows Run again and Save buttons", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(EvalTestRunPane as any, {
        props: {
          available_runs: [run1],
          selected_run: run1,
          runs_loading: false,
          test_result: {
            scores: { accuracy: 1.0 },
            skipped_reason: null,
          },
          test_has_valid_run: true,
        },
      })

      const runAgainBtn = container.querySelector('[data-testid="run-again"]')
      expect(runAgainBtn).not.toBeNull()

      const saveBtn = container.querySelector('[data-testid="save-eval"]')
      expect(saveBtn).not.toBeNull()
    })

    it("Save is disabled when test_has_valid_run is false", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(EvalTestRunPane as any, {
        props: {
          available_runs: [run1],
          selected_run: run1,
          runs_loading: false,
          test_result: {
            scores: { wrong: 1.0 },
            skipped_reason: null,
          },
          test_has_valid_run: false,
        },
      })

      const saveBtn = container.querySelector(
        '[data-testid="save-eval"]',
      ) as HTMLButtonElement
      expect(saveBtn?.disabled).toBe(true)
    })

    it("Save is enabled when test_has_valid_run is true", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(EvalTestRunPane as any, {
        props: {
          available_runs: [run1],
          selected_run: run1,
          runs_loading: false,
          test_result: {
            scores: { accuracy: 1.0 },
            skipped_reason: null,
          },
          test_has_valid_run: true,
        },
      })

      const saveBtn = container.querySelector(
        '[data-testid="save-eval"]',
      ) as HTMLButtonElement
      expect(saveBtn?.disabled).toBe(false)
    })

    it("dispatches save event on Save click", async () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container, component } = render(EvalTestRunPane as any, {
        props: {
          available_runs: [run1],
          selected_run: run1,
          runs_loading: false,
          test_result: {
            scores: { accuracy: 1.0 },
            skipped_reason: null,
          },
          test_has_valid_run: true,
        },
      })
      const handler = vi.fn()
      component.$on("save", handler)

      const saveBtn = container.querySelector(
        '[data-testid="save-eval"]',
      ) as HTMLButtonElement
      await fireEvent.click(saveBtn)
      expect(handler).toHaveBeenCalled()
    })

    it("dispatches runAgain event on Run again click", async () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container, component } = render(EvalTestRunPane as any, {
        props: {
          available_runs: [run1],
          selected_run: run1,
          runs_loading: false,
          test_result: {
            scores: { accuracy: 1.0 },
            skipped_reason: null,
          },
          test_has_valid_run: true,
        },
      })
      const handler = vi.fn()
      component.$on("runAgain", handler)

      const runAgainBtn = container.querySelector(
        '[data-testid="run-again"]',
      ) as HTMLButtonElement
      await fireEvent.click(runAgainBtn)
      expect(handler).toHaveBeenCalled()
    })
  })

  describe("Loading and error states", () => {
    it("renders loading spinner when runs_loading", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(EvalTestRunPane as any, {
        props: { runs_loading: true },
      })

      const loading = container.querySelector('[data-testid="runs-loading"]')
      expect(loading).not.toBeNull()
      expect(container.textContent).toContain("Loading task runs")
    })

    it("renders error when runs_error set", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(EvalTestRunPane as any, {
        props: {
          runs_loading: false,
          runs_error: makeKilnError("Failed to load"),
        },
      })

      const error = container.querySelector('[data-testid="runs-error"]')
      expect(error).not.toBeNull()
      expect(container.textContent).toContain("Failed to load")
    })
  })

  describe("Test Run heading and subtitle", () => {
    it("renders Test Run heading", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(EvalTestRunPane as any, {
        props: { available_runs: [], runs_loading: false },
      })

      const heading = container.querySelector(".text-xl.font-bold")
      expect(heading).not.toBeNull()
      expect(heading?.textContent).toContain("Test Run")
    })

    it("renders orienting subtitle", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(EvalTestRunPane as any, {
        props: { available_runs: [], runs_loading: false },
      })

      expect(container.textContent).toContain(
        "Pick a recent task output to test your evaluator before saving",
      )
    })
  })
})

// ---------------------------------------------------------------------------
// Tests: TestRunInputCard
// ---------------------------------------------------------------------------

describe("TestRunInputCard", () => {
  afterEach(() => {
    cleanup()
  })

  it("renders selected variant with truncated 2-line input and output", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(TestRunInputCard as any, {
      props: {
        run: run1,
        variant: "selected",
        disabled: false,
      },
    })

    const card = container.querySelector('[data-testid="selected-run-card"]')
    expect(card).not.toBeNull()
    expect(card?.textContent).toContain("Selected Run")
    expect(card?.textContent).toContain("input one")
    expect(card?.textContent).toContain("output one")

    const lineClampedElements = card?.querySelectorAll(".line-clamp-2")
    expect(lineClampedElements?.length).toBeGreaterThanOrEqual(2)
  })

  it("renders pick variant as clickable", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(TestRunInputCard as any, {
      props: {
        run: run2,
        variant: "pick",
      },
    })

    const card = container.querySelector('[data-testid="quick-pick-card"]')
    expect(card).not.toBeNull()
    expect(card?.textContent).toContain("input two")
    expect(card?.textContent).toContain("output two")
  })

  it("dispatches select event when clicking pick card", async () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container, component } = render(TestRunInputCard as any, {
      props: {
        run: run2,
        variant: "pick",
      },
    })
    const handler = vi.fn()
    component.$on("select", handler)

    const card = container.querySelector(
      '[data-testid="quick-pick-card"]',
    ) as HTMLButtonElement
    await fireEvent.click(card)
    expect(handler).toHaveBeenCalled()
  })

  it("Change button is disabled when disabled prop is true", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(TestRunInputCard as any, {
      props: {
        run: run1,
        variant: "selected",
        disabled: true,
      },
    })

    const changeBtn = container.querySelector("button") as HTMLButtonElement
    expect(changeBtn?.disabled).toBe(true)
  })

  it("Change button is enabled when disabled prop is false", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(TestRunInputCard as any, {
      props: {
        run: run1,
        variant: "selected",
        disabled: false,
      },
    })

    const changeBtn = container.querySelector("button") as HTMLButtonElement
    expect(changeBtn?.disabled).toBe(false)
  })

  it("shows full input and output as title attributes (tooltip)", () => {
    const longInput = "a".repeat(200)
    const longOutput = "b".repeat(200)
    const longRun = makeRun("long", longInput, longOutput)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(TestRunInputCard as any, {
      props: {
        run: longRun,
        variant: "selected",
        disabled: false,
      },
    })

    const paragraphs = container.querySelectorAll("p[title]")
    const titles = Array.from(paragraphs).map((p) => p.getAttribute("title"))
    expect(titles).toContain(longInput)
    expect(titles).toContain(longOutput)
  })

  it("dispatches change event when Change clicked in selected variant", async () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container, component } = render(TestRunInputCard as any, {
      props: {
        run: run1,
        variant: "selected",
        disabled: false,
      },
    })
    const handler = vi.fn()
    component.$on("change", handler)

    const changeBtn = container.querySelector("button") as HTMLButtonElement
    await fireEvent.click(changeBtn)
    expect(handler).toHaveBeenCalledTimes(1)
  })

  it("pick variant passes run in select event detail", async () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container, component } = render(TestRunInputCard as any, {
      props: {
        run: run3,
        variant: "pick",
      },
    })
    const handler = vi.fn()
    component.$on("select", handler)

    const card = container.querySelector(
      '[data-testid="quick-pick-card"]',
    ) as HTMLButtonElement
    await fireEvent.click(card)
    expect(handler.mock.calls[0][0].detail).toBe(run3)
  })

  it("pick variant renders as button element", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(TestRunInputCard as any, {
      props: {
        run: run2,
        variant: "pick",
      },
    })

    const card = container.querySelector('[data-testid="quick-pick-card"]')
    expect(card?.tagName).toBe("BUTTON")
  })
})

// ---------------------------------------------------------------------------
// Tests: TestRunBrowseDialog
// ---------------------------------------------------------------------------

describe("TestRunBrowseDialog", () => {
  afterEach(() => {
    cleanup()
  })

  it("renders wide dialog with correct title", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(TestRunBrowseDialog as any, {
      props: {
        available_runs: [run1, run2],
      },
    })

    const dialog = container.querySelector('[data-title="Choose an input"]')
    expect(dialog).not.toBeNull()
    expect(dialog?.getAttribute("data-width")).toBe("wide")
  })

  it("renders table with Input, Output, Created columns", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(TestRunBrowseDialog as any, {
      props: {
        available_runs: [run1, run2],
      },
    })

    const table = container.querySelector('[data-testid="browse-table"]')
    expect(table).not.toBeNull()
    const headers = table?.querySelectorAll("th")
    const headerTexts = Array.from(headers || []).map((h) =>
      h.textContent?.trim(),
    )
    expect(headerTexts).toContain("Input preview")
    expect(headerTexts).toContain("Output preview")
    expect(headerTexts).toContain("Created")
  })

  it("does not render a search field", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(TestRunBrowseDialog as any, {
      props: {
        available_runs: [run1],
      },
    })

    const searchInput = container.querySelector('input[type="search"]')
    expect(searchInput).toBeNull()
    const searchPlaceholder = container.querySelector(
      'input[placeholder*="Search"]',
    )
    expect(searchPlaceholder).toBeNull()
  })

  it("shows Add manual example button", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(TestRunBrowseDialog as any, {
      props: {
        available_runs: [run1],
      },
    })

    const addBtn = container.querySelector('[data-testid="add-manual-example"]')
    expect(addBtn).not.toBeNull()
    expect(addBtn?.textContent?.trim()).toContain("Add manual example")
  })

  it("shows input count", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(TestRunBrowseDialog as any, {
      props: {
        available_runs: [run1, run2, run3],
      },
    })

    expect(container.textContent).toContain("3")
    expect(container.textContent).toContain("inputs")
  })

  it("uses singular 'input' for single item", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(TestRunBrowseDialog as any, {
      props: {
        available_runs: [run1],
      },
    })

    expect(container.textContent).toContain("1")
    expect(container.textContent).toMatch(/\b1\s+input\b/)
  })

  it("shows rows with radio buttons, first preselected", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(TestRunBrowseDialog as any, {
      props: {
        available_runs: [run1, run2],
      },
    })

    const radios = container.querySelectorAll('input[type="radio"]')
    expect(radios.length).toBe(2)
    expect((radios[0] as HTMLInputElement).checked).toBe(true)
    expect((radios[1] as HTMLInputElement).checked).toBe(false)
  })

  it("paginates with PAGE_SIZE of 5", () => {
    const manyRuns = Array.from({ length: 8 }, (_, i) =>
      makeRun(`r${i}`, `input ${i}`, `output ${i}`),
    )
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(TestRunBrowseDialog as any, {
      props: {
        available_runs: manyRuns,
      },
    })

    const rows = container.querySelectorAll("tbody tr")
    expect(rows.length).toBe(5)

    const nextBtn = Array.from(container.querySelectorAll("button")).find(
      (b) => b.textContent?.trim() === "Next",
    )
    expect(nextBtn).not.toBeNull()
  })

  it("truncates long text in table cells", () => {
    const longRun = makeRun("long", "x".repeat(200), "y".repeat(200))
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(TestRunBrowseDialog as any, {
      props: {
        available_runs: [longRun],
      },
    })

    const cells = container.querySelectorAll("td span.font-mono")
    const inputCell = cells[0]?.textContent || ""
    expect(inputCell.length).toBeLessThan(200)
    expect(inputCell.endsWith("...")).toBe(true)
  })

  it("shows subtitle text", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(TestRunBrowseDialog as any, {
      props: {
        available_runs: [run1],
      },
    })

    const dialogStub = container.querySelector('[data-testid="dialog-stub"]')
    expect(dialogStub).not.toBeNull()
  })

  it("handle_manual_confirm dispatches ephemeral run via select event", async () => {
    resetActionButtons()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container, component } = render(ManualExampleDialog as any)
    const handler = vi.fn()
    component.$on("confirm", handler)

    const inputTextarea = container.querySelector(
      '[data-testid="manual-input"]',
    ) as HTMLTextAreaElement
    const outputTextarea = container.querySelector(
      '[data-testid="manual-output"]',
    ) as HTMLTextAreaElement
    await fireEvent.input(inputTextarea, {
      target: { value: "manual input" },
    })
    await fireEvent.input(outputTextarea, {
      target: { value: "manual output" },
    })
    await tick()

    const buttons = actionButtonsByTitle["Add Manual Example"]
    expect(buttons).toBeDefined()
    const useExampleBtn = buttons?.find(
      (b) => b.label === "Use Example",
    ) as Record<string, unknown>
    expect(useExampleBtn).toBeDefined()
    expect(typeof useExampleBtn.action).toBe("function")
    ;(useExampleBtn.action as () => boolean)()

    expect(handler).toHaveBeenCalledTimes(1)
    const detail = handler.mock.calls[0][0].detail
    expect(detail.v).toBe(1)
    expect(detail.input).toBe("manual input")
    expect(detail.output.output).toBe("manual output")
    expect(detail.output.source.type).toBe("human")
    expect(detail.output.source.properties).toEqual({})
    expect(detail.tags).toEqual([])
    expect(detail.model_type).toBe("manual")
    expect(detail.id).toBeUndefined()
    expect(detail.path).toBeUndefined()
  })
})

// ---------------------------------------------------------------------------
// Tests: ManualExampleDialog — ephemeral flow
// ---------------------------------------------------------------------------

describe("ManualExampleDialog ephemeral flow", () => {
  afterEach(() => {
    cleanup()
  })

  it("ephemeral run constructed by ManualExampleDialog has no id or path", async () => {
    resetActionButtons()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container, component } = render(ManualExampleDialog as any)
    const handler = vi.fn()
    component.$on("confirm", handler)

    const inputTextarea = container.querySelector(
      '[data-testid="manual-input"]',
    ) as HTMLTextAreaElement
    const outputTextarea = container.querySelector(
      '[data-testid="manual-output"]',
    ) as HTMLTextAreaElement
    await fireEvent.input(inputTextarea, {
      target: { value: "ephemeral input" },
    })
    await fireEvent.input(outputTextarea, {
      target: { value: "ephemeral output" },
    })
    await tick()

    const buttons = actionButtonsByTitle["Add Manual Example"]
    const useExampleBtn = buttons?.find(
      (b) => b.label === "Use Example",
    ) as Record<string, unknown>
    ;(useExampleBtn.action as () => boolean)()

    expect(handler).toHaveBeenCalledTimes(1)
    const detail = handler.mock.calls[0][0].detail
    expect(detail.id).toBeUndefined()
    expect(detail.path).toBeUndefined()
    expect(detail.v).toBe(1)
    expect(detail.tags).toEqual([])
  })

  it("renders dialog and ephemeral note without API calls", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(ManualExampleDialog as any)

    const dialog = container.querySelector('[data-title="Add Manual Example"]')
    expect(dialog).not.toBeNull()
    expect(container.textContent).toContain("won't be saved")

    const inputTextarea = container.querySelector(
      '[data-testid="manual-input"]',
    ) as HTMLTextAreaElement
    const outputTextarea = container.querySelector(
      '[data-testid="manual-output"]',
    ) as HTMLTextAreaElement
    expect(inputTextarea).not.toBeNull()
    expect(outputTextarea).not.toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Tests: ManualExampleDialog
// ---------------------------------------------------------------------------

describe("ManualExampleDialog", () => {
  afterEach(() => {
    cleanup()
  })

  it("renders input and output textareas", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(ManualExampleDialog as any)

    const inputTextarea = container.querySelector(
      '[data-testid="manual-input"]',
    )
    const outputTextarea = container.querySelector(
      '[data-testid="manual-output"]',
    )
    expect(inputTextarea).not.toBeNull()
    expect(outputTextarea).not.toBeNull()
  })

  it("renders both textareas empty by default", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(ManualExampleDialog as any)

    const inputTextarea = container.querySelector(
      '[data-testid="manual-input"]',
    ) as HTMLTextAreaElement
    const outputTextarea = container.querySelector(
      '[data-testid="manual-output"]',
    ) as HTMLTextAreaElement
    expect(inputTextarea?.value).toBe("")
    expect(outputTextarea?.value).toBe("")
  })

  it("dialog title says Add Manual Example", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(ManualExampleDialog as any)

    const dialog = container.querySelector('[data-title="Add Manual Example"]')
    expect(dialog).not.toBeNull()
  })

  it("includes note about temporary/ephemeral nature", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(ManualExampleDialog as any)

    expect(container.textContent).toContain("won't be saved")
  })

  it("textareas are editable", async () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(ManualExampleDialog as any)

    const inputTextarea = container.querySelector(
      '[data-testid="manual-input"]',
    ) as HTMLTextAreaElement
    const outputTextarea = container.querySelector(
      '[data-testid="manual-output"]',
    ) as HTMLTextAreaElement

    await fireEvent.input(inputTextarea, { target: { value: "test input" } })
    await fireEvent.input(outputTextarea, { target: { value: "test output" } })
    await tick()

    expect(inputTextarea.value).toBe("test input")
    expect(outputTextarea.value).toBe("test output")
  })

  it("has labels for Input and Output", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(ManualExampleDialog as any)

    const labels = container.querySelectorAll(".label-text")
    const labelTexts = Array.from(labels).map((l) => l.textContent?.trim())
    expect(labelTexts).toContain("Input")
    expect(labelTexts).toContain("Output")
  })
})

// ---------------------------------------------------------------------------
// Tests: ReferenceDataField
// ---------------------------------------------------------------------------

describe("ReferenceDataField", () => {
  afterEach(() => {
    cleanup()
  })

  it("displays 'None' when reference_data is empty", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(ReferenceDataField as any, {
      props: { reference_data: "" },
    })

    const field = container.querySelector(
      '[data-testid="reference-data-field"]',
    )
    expect(field?.textContent).toContain("None")
    expect(field?.textContent).toContain("Reference Data")
  })

  it("displays key summary when valid JSON is provided", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(ReferenceDataField as any, {
      props: { reference_data: '{"expected": "hello", "key2": "world"}' },
    })

    const field = container.querySelector(
      '[data-testid="reference-data-field"]',
    )
    expect(field?.textContent).toContain("expected")
    expect(field?.textContent).toContain("key2")
  })

  it("opens a dialog for JSON editing on click", async () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(ReferenceDataField as any, {
      props: { reference_data: "" },
    })

    const editBtn = container.querySelector(
      '[data-testid="reference-data-edit"]',
    ) as HTMLButtonElement
    expect(editBtn).not.toBeNull()

    const dialog = container.querySelector('[data-title="Reference Data"]')
    expect(dialog).not.toBeNull()
  })

  it("shows textarea in the JSON modal", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(ReferenceDataField as any, {
      props: { reference_data: "" },
    })

    const textarea = container.querySelector(
      '[data-testid="reference-data-textarea"]',
    )
    expect(textarea).not.toBeNull()
  })

  it("displays 'Invalid JSON' for malformed reference_data", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(ReferenceDataField as any, {
      props: { reference_data: "not json" },
    })

    const field = container.querySelector(
      '[data-testid="reference-data-field"]',
    )
    expect(field?.textContent).toContain("Invalid JSON")
  })

  it("displays keys with '+N more' for many keys", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(ReferenceDataField as any, {
      props: {
        reference_data: '{"a": 1, "b": 2, "c": 3, "d": 4, "e": 5}',
      },
    })

    const field = container.querySelector(
      '[data-testid="reference-data-field"]',
    )
    expect(field?.textContent).toContain("+2 more")
  })

  it("displays 'Empty object' for empty JSON object", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(ReferenceDataField as any, {
      props: { reference_data: "{}" },
    })

    const field = container.querySelector(
      '[data-testid="reference-data-field"]',
    )
    expect(field?.textContent).toContain("Empty object")
  })
})

// ---------------------------------------------------------------------------
// Tests: Auto-select first run
// ---------------------------------------------------------------------------

describe("Auto-select integration", () => {
  afterEach(() => {
    cleanup()
  })

  it("pane renders ready state when selected_run is provided", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(EvalTestRunPane as any, {
      props: {
        available_runs: [run1, run2],
        selected_run: run1,
        runs_loading: false,
      },
    })

    const selectedCard = container.querySelector(
      '[data-testid="selected-run-card"]',
    )
    expect(selectedCard).not.toBeNull()
    expect(selectedCard?.textContent).toContain("input one")
  })

  it("shows fallback when has runs but no selected_run", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(EvalTestRunPane as any, {
      props: {
        available_runs: [run1],
        selected_run: null,
        runs_loading: false,
      },
    })

    expect(container.textContent).toContain("Select a run to get started")
  })

  it("does not show quick-picks when only 1 run, but shows browse link", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(EvalTestRunPane as any, {
      props: {
        available_runs: [run1],
        selected_run: run1,
        runs_loading: false,
      },
    })

    const quickPicks = container.querySelectorAll(
      '[data-testid="quick-pick-card"]',
    )
    expect(quickPicks.length).toBe(0)

    const browseLink = container.querySelector(
      '[data-testid="browse-all-link"]',
    )
    expect(browseLink).not.toBeNull()
  })

  it("Go to Run link uses flat /run route", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(EvalTestRunPane as any, {
      props: {
        available_runs: [],
        runs_loading: false,
      },
    })

    const link = container.querySelector("a.btn") as HTMLAnchorElement
    expect(link?.getAttribute("href")).toBe("/run")
  })
})
