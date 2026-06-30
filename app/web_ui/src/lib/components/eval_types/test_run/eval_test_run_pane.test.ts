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

    it("does NOT show Save Without Testing button (D10)", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(EvalTestRunPane as any, {
        props: { available_runs: [], runs_loading: false },
      })
      const saveBtn = container.querySelector(
        '[data-testid="save-without-testing"]',
      )
      expect(saveBtn).toBeNull()
      expect(container.textContent).not.toContain("Save Without Testing")
    })
  })

  describe("State 2: Ready (pick input)", () => {
    it("renders selected run card without quick-picks (D15)", () => {
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
      expect(quickPicks.length).toBe(0)
    })

    it("does NOT show Browse all dataset inputs link (D15)", () => {
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
      expect(browseLink).toBeNull()
    })

    it("shows Run button with btn-primary btn-outline style (D11)", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(EvalTestRunPane as any, {
        props: {
          available_runs: [run1],
          selected_run: run1,
          runs_loading: false,
        },
      })

      const runBtn = container.querySelector(
        '[data-testid="run-test-btn"]',
      ) as HTMLButtonElement
      expect(runBtn).not.toBeNull()
      expect(runBtn?.textContent?.trim()).toContain("Run")
      expect(runBtn?.classList.contains("btn-primary")).toBe(true)
      expect(runBtn?.classList.contains("btn-outline")).toBe(true)
    })

    it("does NOT show results placeholder (D12)", () => {
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
      expect(placeholder).toBeNull()
      expect(container.textContent).not.toContain("Run to see scores")
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

    it("selected card shows Change button that opens browse dialog (D15)", () => {
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
      const changeBtn = selectedCard?.querySelector("button")
      expect(changeBtn).not.toBeNull()
      expect(changeBtn?.textContent?.trim()).toBe("Change")
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

    it("shows Run again button with btn-primary btn-outline style (D11) and no Save button (D10)", () => {
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

      const runAgainBtn = container.querySelector(
        '[data-testid="run-again"]',
      ) as HTMLButtonElement
      expect(runAgainBtn).not.toBeNull()
      expect(runAgainBtn?.classList.contains("btn-primary")).toBe(true)
      expect(runAgainBtn?.classList.contains("btn-outline")).toBe(true)

      const saveBtn = container.querySelector('[data-testid="save-eval"]')
      expect(saveBtn).toBeNull()
    })

    it("shows score-range warning when test_score_range_warning is set", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(EvalTestRunPane as any, {
        props: {
          available_runs: [run1],
          selected_run: run1,
          runs_loading: false,
          test_result: {
            scores: { accuracy: 5.0 },
            skipped_reason: null,
          },
          test_score_range_warning:
            "Score accuracy is a pass_fail rating and must be a float between 0.0 and 1.0 inclusive. Got: 5.0",
          test_has_valid_run: false,
        },
      })

      const rangeWarning = container.querySelector(
        '[data-testid="score-range-warning"]',
      )
      expect(rangeWarning).not.toBeNull()
      expect(rangeWarning?.textContent).toContain("Score Out of Range")
      expect(rangeWarning?.textContent).toContain("pass_fail")
      expect(rangeWarning?.textContent).toContain("5.0")
    })

    it("does not show score-range warning when prop is null", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(EvalTestRunPane as any, {
        props: {
          available_runs: [run1],
          selected_run: run1,
          runs_loading: false,
          test_result: {
            scores: { accuracy: 0.5 },
            skipped_reason: null,
          },
          test_score_range_warning: null,
          test_has_valid_run: true,
        },
      })

      const rangeWarning = container.querySelector(
        '[data-testid="score-range-warning"]',
      )
      expect(rangeWarning).toBeNull()
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

  describe("Test Run heading and subtitle (D13)", () => {
    it("renders Test Run heading", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(EvalTestRunPane as any, {
        props: { available_runs: [], runs_loading: false },
      })

      const heading = container.querySelector(".text-xl.font-bold")
      expect(heading).not.toBeNull()
      expect(heading?.textContent).toContain("Test Judge")
    })

    it("renders updated subtitle text", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(EvalTestRunPane as any, {
        props: { available_runs: [], runs_loading: false },
      })

      const subtitle = container.querySelector(
        '[data-testid="test-run-subtitle"]',
      )
      expect(subtitle).not.toBeNull()
      expect(subtitle?.textContent).toBe(
        "Test your judge on real data before saving.",
      )
    })

    it("subtitle uses standard secondary text style (text-sm text-gray-500)", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(EvalTestRunPane as any, {
        props: { available_runs: [], runs_loading: false },
      })

      const subtitle = container.querySelector(
        '[data-testid="test-run-subtitle"]',
      )
      expect(subtitle).not.toBeNull()
      expect(subtitle?.classList.contains("text-sm")).toBe(true)
      expect(subtitle?.classList.contains("text-gray-500")).toBe(true)
      expect(subtitle?.classList.contains("text-xs")).toBe(false)
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

  it("renders selected variant with 'Selected Test Run' label in non-grey (D14)", () => {
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
    expect(card?.textContent).toContain("Selected Test Run")
    expect(card?.textContent).not.toContain("Selected Run\n")

    const label = card?.querySelector("span.font-medium")
    expect(label).not.toBeNull()
    expect(label?.classList.contains("text-base")).toBe(true)
    expect(label?.classList.contains("text-gray-500")).toBe(false)
  })

  it("renders truncated 2-line input and output", () => {
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

    const dialog = container.querySelector(
      '[data-title="Choose Dataset Sample"]',
    )
    expect(dialog).not.toBeNull()
    expect(dialog?.getAttribute("data-width")).toBe("wide")
  })

  it("renders table with Input, Output, Created columns (no radio column)", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(TestRunBrowseDialog as any, {
      props: {
        available_runs: [run1, run2],
      },
    })

    const table = container.querySelector('[data-testid="browse-table"]')
    expect(table).not.toBeNull()
    const headers = table?.querySelectorAll("th")
    expect(headers?.length).toBe(3)
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

  it("shows 'or add manual example' button with bold styling", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(TestRunBrowseDialog as any, {
      props: {
        available_runs: [run1],
      },
    })

    const addBtn = container.querySelector('[data-testid="add-manual-example"]')
    expect(addBtn).not.toBeNull()
    expect(addBtn?.textContent?.trim()).toContain("or add manual example")
    expect(addBtn?.classList.contains("font-bold")).toBe(true)
  })

  it("shows clickable rows without radio buttons", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(TestRunBrowseDialog as any, {
      props: {
        available_runs: [run1, run2],
      },
    })

    const radios = container.querySelectorAll('input[type="radio"]')
    expect(radios.length).toBe(0)

    const rows = container.querySelectorAll("tbody tr")
    expect(rows.length).toBe(2)
    expect(rows[0].classList.contains("cursor-pointer")).toBe(true)
  })

  it("dispatches select and closes dialog on row click", async () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container, component } = render(TestRunBrowseDialog as any, {
      props: {
        available_runs: [run1, run2],
      },
    })
    const handler = vi.fn()
    component.$on("select", handler)

    const rows = container.querySelectorAll("tbody tr")
    await fireEvent.click(rows[1])
    expect(handler).toHaveBeenCalledTimes(1)
    expect(handler.mock.calls[0][0].detail).toBe(run2)
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

  describe("display value (preview text)", () => {
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

    it("displays 'Invalid: not an object' for non-object JSON values in preview", () => {
      const nonObjects = ['"asdf"', "false", "12", "[1,2]", "null"]
      for (const val of nonObjects) {
        cleanup()
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const { container } = render(ReferenceDataField as any, {
          props: { reference_data: val },
        })
        const field = container.querySelector(
          '[data-testid="reference-data-field"]',
        )
        expect(field?.textContent).toContain("Invalid: not an object")
      }
    })
  })

  describe("dialog structure", () => {
    it("opens a wide dialog with key-value editor on click", () => {
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
      expect(dialog?.getAttribute("data-width")).toBe("wide")
    })

    it("shows key-value editor (not a textarea)", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(ReferenceDataField as any, {
        props: { reference_data: "" },
      })

      const editor = container.querySelector(
        '[data-testid="reference-data-editor"]',
      )
      expect(editor).not.toBeNull()

      const textarea = container.querySelector(
        '[data-testid="reference-data-textarea"]',
      )
      expect(textarea).toBeNull()
    })

    it("shows Add Value button", () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(ReferenceDataField as any, {
        props: { reference_data: "" },
      })

      const addBtn = container.querySelector(
        '[data-testid="reference-data-add"]',
      )
      expect(addBtn).not.toBeNull()
      expect(addBtn?.textContent).toContain("Add Value")
    })
  })

  describe("row management", () => {
    it("starts with one empty row when reference_data is empty", async () => {
      resetActionButtons()
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(ReferenceDataField as any, {
        props: { reference_data: "" },
      })

      const editBtn = container.querySelector(
        '[data-testid="reference-data-edit"]',
      ) as HTMLButtonElement
      await fireEvent.click(editBtn)
      await tick()

      const rows = container.querySelectorAll(
        '[data-testid="reference-data-row"]',
      )
      expect(rows.length).toBe(1)
    })

    it("populates rows from existing JSON data", async () => {
      resetActionButtons()
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(ReferenceDataField as any, {
        props: {
          reference_data: '{"name": "Alice", "age": 30}',
        },
      })

      const editBtn = container.querySelector(
        '[data-testid="reference-data-edit"]',
      ) as HTMLButtonElement
      await fireEvent.click(editBtn)
      await tick()

      const rows = container.querySelectorAll(
        '[data-testid="reference-data-row"]',
      )
      expect(rows.length).toBe(2)

      const keys = container.querySelectorAll(
        '[data-testid="reference-data-key"]',
      ) as NodeListOf<HTMLInputElement>
      const values = container.querySelectorAll(
        '[data-testid="reference-data-value"]',
      ) as NodeListOf<HTMLInputElement>
      expect(keys[0].value).toBe("name")
      expect(values[0].value).toBe('"Alice"')
      expect(keys[1].value).toBe("age")
      expect(values[1].value).toBe("30")
    })

    it("adds a new row when Add Value is clicked", async () => {
      resetActionButtons()
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(ReferenceDataField as any, {
        props: { reference_data: "" },
      })

      const editBtn = container.querySelector(
        '[data-testid="reference-data-edit"]',
      ) as HTMLButtonElement
      await fireEvent.click(editBtn)
      await tick()

      const addBtn = container.querySelector(
        '[data-testid="reference-data-add"]',
      ) as HTMLButtonElement
      await fireEvent.click(addBtn)
      await tick()

      const rows = container.querySelectorAll(
        '[data-testid="reference-data-row"]',
      )
      expect(rows.length).toBe(2)
    })

    it("removes a row when X is clicked", async () => {
      resetActionButtons()
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(ReferenceDataField as any, {
        props: {
          reference_data: '{"a": 1, "b": 2}',
        },
      })

      const editBtn = container.querySelector(
        '[data-testid="reference-data-edit"]',
      ) as HTMLButtonElement
      await fireEvent.click(editBtn)
      await tick()

      let rows = container.querySelectorAll(
        '[data-testid="reference-data-row"]',
      )
      expect(rows.length).toBe(2)

      const removeBtn = container.querySelector(
        '[data-testid="reference-data-remove"]',
      ) as HTMLButtonElement
      await fireEvent.click(removeBtn)
      await tick()

      rows = container.querySelectorAll('[data-testid="reference-data-row"]')
      expect(rows.length).toBe(1)
    })

    it("shows Name and Value column labels on first row only", async () => {
      resetActionButtons()
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = render(ReferenceDataField as any, {
        props: {
          reference_data: '{"a": 1, "b": 2}',
        },
      })

      const editBtn = container.querySelector(
        '[data-testid="reference-data-edit"]',
      ) as HTMLButtonElement
      await fireEvent.click(editBtn)
      await tick()

      const labels = container.querySelectorAll(".label-text")
      const labelTexts = Array.from(labels).map((l) => l.textContent?.trim())
      expect(labelTexts).toContain("Name")
      expect(labelTexts).toContain("Value")
      // Only 2 labels total (Name + Value), not repeated per row
      expect(labels.length).toBe(2)
    })
  })

  describe("save validation", () => {
    async function renderAndGetSaveAction(reference_data = "") {
      resetActionButtons()
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const result = render(ReferenceDataField as any, {
        props: { reference_data },
      })
      const handler = vi.fn()
      result.component.$on("change", handler)

      const editBtn = result.container.querySelector(
        '[data-testid="reference-data-edit"]',
      ) as HTMLButtonElement
      await fireEvent.click(editBtn)
      await tick()

      const buttons = actionButtonsByTitle["Reference Data"]
      const saveBtn = buttons?.find((b) => b.label === "Save") as Record<
        string,
        unknown
      >
      return {
        ...result,
        handler,
        saveAction: saveBtn.action as () => boolean,
      }
    }

    it("saves valid key-value pairs and emits change", async () => {
      const { container, handler, saveAction } = await renderAndGetSaveAction()

      const keys = container.querySelectorAll(
        '[data-testid="reference-data-key"]',
      ) as NodeListOf<HTMLInputElement>
      const values = container.querySelectorAll(
        '[data-testid="reference-data-value"]',
      ) as NodeListOf<HTMLInputElement>

      await fireEvent.input(keys[0], { target: { value: "answer" } })
      await fireEvent.input(values[0], { target: { value: "hello" } })
      await tick()

      const result = saveAction()
      expect(result).toBe(true)
      expect(handler).toHaveBeenCalledTimes(1)
      const emitted = JSON.parse(handler.mock.calls[0][0].detail)
      expect(emitted).toEqual({ answer: "hello" })
    })

    it("emits empty string when all rows are empty", async () => {
      const { handler, saveAction } = await renderAndGetSaveAction()

      const result = saveAction()
      expect(result).toBe(true)
      expect(handler).toHaveBeenCalledTimes(1)
      expect(handler.mock.calls[0][0].detail).toBe("")
    })

    it("rejects rows with value but no name", async () => {
      const { container, handler, saveAction } = await renderAndGetSaveAction()

      const values = container.querySelectorAll(
        '[data-testid="reference-data-value"]',
      ) as NodeListOf<HTMLInputElement>
      await fireEvent.input(values[0], { target: { value: "some value" } })
      await tick()

      const result = saveAction()
      expect(result).toBe(false)
      expect(handler).not.toHaveBeenCalled()
      await tick()
      const error = container.querySelector(
        '[data-testid="reference-data-error"]',
      )
      expect(error?.textContent).toContain("must have a name")
    })

    it("rejects duplicate keys", async () => {
      const { container, handler, saveAction } =
        await renderAndGetSaveAction('{"a": 1}')

      // Add a second row
      const addBtn = container.querySelector(
        '[data-testid="reference-data-add"]',
      ) as HTMLButtonElement
      await fireEvent.click(addBtn)
      await tick()

      const keys = container.querySelectorAll(
        '[data-testid="reference-data-key"]',
      ) as NodeListOf<HTMLInputElement>
      const values = container.querySelectorAll(
        '[data-testid="reference-data-value"]',
      ) as NodeListOf<HTMLInputElement>
      await fireEvent.input(keys[1], { target: { value: "a" } })
      await fireEvent.input(values[1], { target: { value: "2" } })
      await tick()

      const result = saveAction()
      expect(result).toBe(false)
      expect(handler).not.toHaveBeenCalled()
      await tick()
      const error = container.querySelector(
        '[data-testid="reference-data-error"]',
      )
      expect(error?.textContent).toContain("Duplicate")
    })
  })

  describe("value parsing", () => {
    async function renderAndGetSaveAction() {
      resetActionButtons()
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const result = render(ReferenceDataField as any, {
        props: { reference_data: "" },
      })
      const handler = vi.fn()
      result.component.$on("change", handler)

      const editBtn = result.container.querySelector(
        '[data-testid="reference-data-edit"]',
      ) as HTMLButtonElement
      await fireEvent.click(editBtn)
      await tick()

      const buttons = actionButtonsByTitle["Reference Data"]
      const saveBtn = buttons?.find((b) => b.label === "Save") as Record<
        string,
        unknown
      >
      return {
        ...result,
        handler,
        saveAction: saveBtn.action as () => boolean,
      }
    }

    it("parses number values as numbers", async () => {
      const { container, handler, saveAction } = await renderAndGetSaveAction()
      const keys = container.querySelectorAll(
        '[data-testid="reference-data-key"]',
      ) as NodeListOf<HTMLInputElement>
      const values = container.querySelectorAll(
        '[data-testid="reference-data-value"]',
      ) as NodeListOf<HTMLInputElement>

      await fireEvent.input(keys[0], { target: { value: "count" } })
      await fireEvent.input(values[0], { target: { value: "12" } })
      await tick()

      saveAction()
      const emitted = JSON.parse(handler.mock.calls[0][0].detail)
      expect(emitted.count).toBe(12)
      expect(typeof emitted.count).toBe("number")
    })

    it("parses boolean true as boolean", async () => {
      const { container, handler, saveAction } = await renderAndGetSaveAction()
      const keys = container.querySelectorAll(
        '[data-testid="reference-data-key"]',
      ) as NodeListOf<HTMLInputElement>
      const values = container.querySelectorAll(
        '[data-testid="reference-data-value"]',
      ) as NodeListOf<HTMLInputElement>

      await fireEvent.input(keys[0], { target: { value: "flag" } })
      await fireEvent.input(values[0], { target: { value: "true" } })
      await tick()

      saveAction()
      const emitted = JSON.parse(handler.mock.calls[0][0].detail)
      expect(emitted.flag).toBe(true)
      expect(typeof emitted.flag).toBe("boolean")
    })

    it("parses boolean false as boolean", async () => {
      const { container, handler, saveAction } = await renderAndGetSaveAction()
      const keys = container.querySelectorAll(
        '[data-testid="reference-data-key"]',
      ) as NodeListOf<HTMLInputElement>
      const values = container.querySelectorAll(
        '[data-testid="reference-data-value"]',
      ) as NodeListOf<HTMLInputElement>

      await fireEvent.input(keys[0], { target: { value: "disabled" } })
      await fireEvent.input(values[0], { target: { value: "false" } })
      await tick()

      saveAction()
      const emitted = JSON.parse(handler.mock.calls[0][0].detail)
      expect(emitted.disabled).toBe(false)
      expect(typeof emitted.disabled).toBe("boolean")
    })

    it('parses quoted strings as strings (e.g. "12" becomes string "12")', async () => {
      const { container, handler, saveAction } = await renderAndGetSaveAction()
      const keys = container.querySelectorAll(
        '[data-testid="reference-data-key"]',
      ) as NodeListOf<HTMLInputElement>
      const values = container.querySelectorAll(
        '[data-testid="reference-data-value"]',
      ) as NodeListOf<HTMLInputElement>

      await fireEvent.input(keys[0], { target: { value: "code" } })
      await fireEvent.input(values[0], { target: { value: '"12"' } })
      await tick()

      saveAction()
      const emitted = JSON.parse(handler.mock.calls[0][0].detail)
      expect(emitted.code).toBe("12")
      expect(typeof emitted.code).toBe("string")
    })

    it("falls back to string for unparseable JSON values", async () => {
      const { container, handler, saveAction } = await renderAndGetSaveAction()
      const keys = container.querySelectorAll(
        '[data-testid="reference-data-key"]',
      ) as NodeListOf<HTMLInputElement>
      const values = container.querySelectorAll(
        '[data-testid="reference-data-value"]',
      ) as NodeListOf<HTMLInputElement>

      await fireEvent.input(keys[0], { target: { value: "text" } })
      await fireEvent.input(values[0], { target: { value: "hello world" } })
      await tick()

      saveAction()
      const emitted = JSON.parse(handler.mock.calls[0][0].detail)
      expect(emitted.text).toBe("hello world")
      expect(typeof emitted.text).toBe("string")
    })

    it("falls back to string for broken JSON (e.g. unclosed quote)", async () => {
      const { container, handler, saveAction } = await renderAndGetSaveAction()
      const keys = container.querySelectorAll(
        '[data-testid="reference-data-key"]',
      ) as NodeListOf<HTMLInputElement>
      const values = container.querySelectorAll(
        '[data-testid="reference-data-value"]',
      ) as NodeListOf<HTMLInputElement>

      await fireEvent.input(keys[0], { target: { value: "bad" } })
      await fireEvent.input(values[0], { target: { value: '"12' } })
      await tick()

      saveAction()
      const emitted = JSON.parse(handler.mock.calls[0][0].detail)
      expect(emitted.bad).toBe('"12')
      expect(typeof emitted.bad).toBe("string")
    })

    it("parses nested objects as objects", async () => {
      const { container, handler, saveAction } = await renderAndGetSaveAction()
      const keys = container.querySelectorAll(
        '[data-testid="reference-data-key"]',
      ) as NodeListOf<HTMLInputElement>
      const values = container.querySelectorAll(
        '[data-testid="reference-data-value"]',
      ) as NodeListOf<HTMLInputElement>

      await fireEvent.input(keys[0], { target: { value: "nested" } })
      await fireEvent.input(values[0], {
        target: { value: '{"a": 1}' },
      })
      await tick()

      saveAction()
      const emitted = JSON.parse(handler.mock.calls[0][0].detail)
      expect(emitted.nested).toEqual({ a: 1 })
    })

    it("parses null as null", async () => {
      const { container, handler, saveAction } = await renderAndGetSaveAction()
      const keys = container.querySelectorAll(
        '[data-testid="reference-data-key"]',
      ) as NodeListOf<HTMLInputElement>
      const values = container.querySelectorAll(
        '[data-testid="reference-data-value"]',
      ) as NodeListOf<HTMLInputElement>

      await fireEvent.input(keys[0], { target: { value: "empty" } })
      await fireEvent.input(values[0], { target: { value: "null" } })
      await tick()

      saveAction()
      const emitted = JSON.parse(handler.mock.calls[0][0].detail)
      expect(emitted.empty).toBeNull()
    })

    it("saves empty value as empty string when key is present", async () => {
      const { container, handler, saveAction } = await renderAndGetSaveAction()
      const keys = container.querySelectorAll(
        '[data-testid="reference-data-key"]',
      ) as NodeListOf<HTMLInputElement>

      await fireEvent.input(keys[0], { target: { value: "score" } })
      await tick()

      const result = saveAction()
      expect(result).toBe(true)
      expect(handler).toHaveBeenCalledTimes(1)
      const emitted = JSON.parse(handler.mock.calls[0][0].detail)
      expect(emitted.score).toBe("")
      expect(typeof emitted.score).toBe("string")
    })
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

  it("does not show quick-picks when only 1 run (D15)", () => {
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
    expect(browseLink).toBeNull()
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

// ---------------------------------------------------------------------------
// Tests: ReferenceDataField "Missing x" red-state
// ---------------------------------------------------------------------------

describe("ReferenceDataField missing-field red-state", () => {
  afterEach(() => {
    cleanup()
  })

  it("shows 'Missing x' when required field is not in reference data", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(ReferenceDataField as any, {
      props: {
        reference_data: "",
        required_reference_fields: ["expected_answer"],
      },
    })
    const editBtn = container.querySelector(
      '[data-testid="reference-data-edit"]',
    )
    expect(editBtn?.textContent).toContain("Missing expected_answer")
  })

  it("applies text-error class when field is missing", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(ReferenceDataField as any, {
      props: {
        reference_data: "",
        required_reference_fields: ["expected_answer"],
      },
    })
    const editBtn = container.querySelector(
      '[data-testid="reference-data-edit"]',
    )
    expect(editBtn?.classList.contains("text-error")).toBe(true)
    expect(editBtn?.classList.contains("text-gray-500")).toBe(false)
  })

  it("does not show missing state when required field is present", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(ReferenceDataField as any, {
      props: {
        reference_data: '{"expected_answer": "yes"}',
        required_reference_fields: ["expected_answer"],
      },
    })
    const editBtn = container.querySelector(
      '[data-testid="reference-data-edit"]',
    )
    expect(editBtn?.textContent).not.toContain("Missing")
    expect(editBtn?.classList.contains("text-error")).toBe(false)
    expect(editBtn?.classList.contains("text-gray-500")).toBe(true)
  })

  it("shows normal display when no required fields", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(ReferenceDataField as any, {
      props: {
        reference_data: "",
        required_reference_fields: [],
      },
    })
    const editBtn = container.querySelector(
      '[data-testid="reference-data-edit"]',
    )
    expect(editBtn?.textContent).toContain("None")
    expect(editBtn?.classList.contains("text-error")).toBe(false)
  })

  it("shows missing for field with null value in reference data", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(ReferenceDataField as any, {
      props: {
        reference_data: '{"expected_answer": null}',
        required_reference_fields: ["expected_answer"],
      },
    })
    const editBtn = container.querySelector(
      '[data-testid="reference-data-edit"]',
    )
    expect(editBtn?.textContent).toContain("Missing expected_answer")
    expect(editBtn?.classList.contains("text-error")).toBe(true)
  })

  it("shows missing for field with empty string value", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(ReferenceDataField as any, {
      props: {
        reference_data: '{"expected_answer": ""}',
        required_reference_fields: ["expected_answer"],
      },
    })
    const editBtn = container.querySelector(
      '[data-testid="reference-data-edit"]',
    )
    expect(editBtn?.textContent).toContain("Missing expected_answer")
  })

  it("comma-joins multiple missing fields", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(ReferenceDataField as any, {
      props: {
        reference_data: "",
        required_reference_fields: ["field_a", "field_b"],
      },
    })
    const editBtn = container.querySelector(
      '[data-testid="reference-data-edit"]',
    )
    expect(editBtn?.textContent).toContain("Missing field_a, field_b")
  })

  it("shows missing when reference data is invalid JSON", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(ReferenceDataField as any, {
      props: {
        reference_data: "not json",
        required_reference_fields: ["expected_answer"],
      },
    })
    const editBtn = container.querySelector(
      '[data-testid="reference-data-edit"]',
    )
    expect(editBtn?.textContent).toContain("Missing expected_answer")
    expect(editBtn?.classList.contains("text-error")).toBe(true)
  })

  it("shows normal display when field is present with truthy value", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { container } = render(ReferenceDataField as any, {
      props: {
        reference_data: '{"expected_answer": "correct"}',
        required_reference_fields: ["expected_answer"],
      },
    })
    const editBtn = container.querySelector(
      '[data-testid="reference-data-edit"]',
    )
    expect(editBtn?.textContent).toContain("expected_answer")
    expect(editBtn?.textContent).not.toContain("Missing")
    expect(editBtn?.classList.contains("text-gray-500")).toBe(true)
  })
})
