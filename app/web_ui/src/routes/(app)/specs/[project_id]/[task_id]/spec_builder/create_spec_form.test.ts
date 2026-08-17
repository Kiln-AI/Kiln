// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from "vitest"
import { render, fireEvent, cleanup } from "@testing-library/svelte"
import type { FieldConfig } from "../select_template/spec_templates"

vi.mock("$app/navigation", () => ({
  goto: vi.fn(),
  beforeNavigate: vi.fn(),
}))

// TaskSampleSelector fetches candidate runs from the API on mount. Stub it so
// these tests only exercise create_spec_form's own conditional rendering.
vi.mock("$lib/utils/task_sample_selector.svelte", async () => {
  const StubModule = await import(
    "./__tests__/task_sample_selector_stub.svelte"
  )
  return { default: StubModule.default }
})

// Import the component under test after the mocks are registered.
const CreateSpecForm = (await import("./create_spec_form.svelte")).default

const NOTICE_TESTID = "copilot-full-trace-notice"
const SELECTOR_STUB_TESTID = "task-sample-selector-stub"

const field_configs: FieldConfig[] = [
  {
    key: "behaviour",
    label: "Behaviour",
    description: "The behaviour to enforce.",
    required: true,
  },
]

function render_form(overrides: Record<string, unknown> = {}) {
  return render(CreateSpecForm, {
    props: {
      name: "My Eval",
      property_values: { behaviour: "Be concise" },
      initial_property_values: { behaviour: "Be concise" },
      evaluate_full_trace: false,
      field_configs,
      copilot_enabled: true,
      hide_full_trace_option: false,
      full_trace_disabled: false,
      error: null,
      submitting: false,
      warn_before_unload: false,
      project_id: "p1",
      task_id: "t1",
      ...overrides,
    },
  })
}

afterEach(() => {
  cleanup()
})

describe("CreateSpecForm copilot full-trace notice", () => {
  it("shows the notice and switches to manual creation when full trace is on", () => {
    const { queryByTestId, getByText } = render_form({
      evaluate_full_trace: true,
    })
    const notice = queryByTestId(NOTICE_TESTID)
    expect(notice).not.toBeNull()
    expect(notice?.textContent).toContain(
      "does not support evaluating complete agent history",
    )
    // The consequence the notice describes: manual submit, no sample selector.
    expect(getByText("Create Eval")).toBeTruthy()
    expect(queryByTestId(SELECTOR_STUB_TESTID)).toBeNull()
  })

  it("hides the notice while the form is still on the copilot path", () => {
    const { queryByTestId, getByText } = render_form()
    expect(queryByTestId(NOTICE_TESTID)).toBeNull()
    expect(getByText("Create with Kiln Pro")).toBeTruthy()
    expect(queryByTestId(SELECTOR_STUB_TESTID)).not.toBeNull()
  })

  it("hides the notice when copilot is unavailable for the task", () => {
    const { queryByTestId } = render_form({
      copilot_enabled: false,
      evaluate_full_trace: true,
    })
    expect(queryByTestId(NOTICE_TESTID)).toBeNull()
  })

  it("toggles the notice as the user turns full trace on and off", async () => {
    const { queryByTestId, container } = render_form()
    expect(queryByTestId(NOTICE_TESTID)).toBeNull()

    const checkbox = container.querySelector(
      "#evaluate_full_trace",
    ) as HTMLInputElement
    expect(checkbox).not.toBeNull()
    await fireEvent.click(checkbox)
    expect(queryByTestId(NOTICE_TESTID)).not.toBeNull()

    await fireEvent.click(checkbox)
    expect(queryByTestId(NOTICE_TESTID)).toBeNull()
  })
})
