// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
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
      field_configs,
      copilot_enabled: true,
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

describe("CreateSpecForm copilot path", () => {
  it("offers the copilot flow and sample selector when copilot is enabled", () => {
    const { queryByTestId, getByText } = render_form()
    expect(getByText("Create with Kiln Pro")).toBeTruthy()
    expect(queryByTestId(SELECTOR_STUB_TESTID)).not.toBeNull()
  })

  it("falls back to manual creation when copilot is unavailable for the task", () => {
    const { queryByTestId, getByText } = render_form({
      copilot_enabled: false,
    })
    expect(getByText("Create Eval")).toBeTruthy()
    expect(queryByTestId(SELECTOR_STUB_TESTID)).toBeNull()
  })
})
