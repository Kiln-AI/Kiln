// @vitest-environment jsdom
import { describe, it, expect, vi, beforeAll } from "vitest"
import { render, fireEvent } from "@testing-library/svelte"
import { tick } from "svelte"
import { emitValue, parseValue, JINJA_EXAMPLES } from "./output_value_helpers"

vi.mock("$lib/utils/form_element.svelte", async () => {
  const { default: Stub } = await import(
    "../__tests__/form_element_stub.svelte"
  )
  return { default: Stub }
})

vi.mock("$lib/ui/dialog.svelte", async () => {
  const { default: Stub } = await import("../__tests__/dialog_stub.svelte")
  return { default: Stub }
})

const FormSection = (await import("./form_section.svelte")).default
const OutputValueField = (await import("./output_value_field.svelte")).default

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

describe("FormSection", () => {
  it("renders title text", () => {
    const { getByText } = render(FormSection, {
      props: { title: "Expected Value" },
    })
    expect(getByText("Expected Value")).toBeTruthy()
  })

  it("renders subtitle text when provided", () => {
    const { container, getByText } = render(FormSection, {
      props: {
        title: "Test",
        subtitle: "Choose what value to compare.",
      },
    })
    expect(getByText("Choose what value to compare.")).toBeTruthy()
    const subtitle = container.querySelector(
      '[data-testid="form-section-subtitle"]',
    )
    expect(subtitle).not.toBeNull()
    expect(subtitle?.textContent).toBe("Choose what value to compare.")
  })

  it("does not render subtitle element when not provided", () => {
    const { container } = render(FormSection, {
      props: { title: "Test" },
    })
    const subtitle = container.querySelector(
      '[data-testid="form-section-subtitle"]',
    )
    expect(subtitle).toBeNull()
  })

  it("renders with testid when provided", () => {
    const { getByTestId } = render(FormSection, {
      props: { title: "Test", testid: "my-section" },
    })
    expect(getByTestId("my-section")).toBeTruthy()
  })
})

// --- Pure helper tests ---

describe("emitValue", () => {
  it("Final Message mode emits 'final_message'", () => {
    expect(emitValue({ mode: "final_message", customText: "" })).toBe(
      "final_message",
    )
  })

  it("Entire Trace mode emits 'trace'", () => {
    expect(emitValue({ mode: "trace", customText: "" })).toBe("trace")
  })

  it("Custom mode emits the custom text verbatim (trimmed)", () => {
    expect(
      emitValue({ mode: "custom", customText: "  final_message | upper  " }),
    ).toBe("final_message | upper")
  })

  it("Custom mode with empty text emits null", () => {
    expect(emitValue({ mode: "custom", customText: "" })).toBe(null)
    expect(emitValue({ mode: "custom", customText: "   " })).toBe(null)
  })

  it("Final Message ignores customText", () => {
    expect(emitValue({ mode: "final_message", customText: "something" })).toBe(
      "final_message",
    )
  })

  it("Entire Trace ignores customText", () => {
    expect(emitValue({ mode: "trace", customText: "something" })).toBe("trace")
  })
})

describe("parseValue", () => {
  it("null -> Final Message", () => {
    expect(parseValue(null)).toEqual({ mode: "final_message", customText: "" })
  })

  it("empty string -> Final Message", () => {
    expect(parseValue("")).toEqual({ mode: "final_message", customText: "" })
  })

  it("whitespace -> Final Message", () => {
    expect(parseValue("   ")).toEqual({
      mode: "final_message",
      customText: "",
    })
  })

  it("'final_message' -> Final Message", () => {
    expect(parseValue("final_message")).toEqual({
      mode: "final_message",
      customText: "",
    })
  })

  it("'trace' -> Entire Trace", () => {
    expect(parseValue("trace")).toEqual({ mode: "trace", customText: "" })
  })

  it("anything else -> Custom with text", () => {
    expect(parseValue("final_message.user.status")).toEqual({
      mode: "custom",
      customText: "final_message.user.status",
    })
  })

  it("'(final_message | fromjson).x' -> Custom", () => {
    expect(parseValue("(final_message | fromjson).x")).toEqual({
      mode: "custom",
      customText: "(final_message | fromjson).x",
    })
  })

  it("'trace[-1].content' -> Custom", () => {
    expect(parseValue("trace[-1].content")).toEqual({
      mode: "custom",
      customText: "trace[-1].content",
    })
  })

  it("legacy bare path -> Custom", () => {
    expect(parseValue("user.status")).toEqual({
      mode: "custom",
      customText: "user.status",
    })
  })

  it("unknown prefix -> Custom", () => {
    expect(parseValue("task_input.something")).toEqual({
      mode: "custom",
      customText: "task_input.something",
    })
  })
})

describe("round-trip: parse(emit(state)) === state", () => {
  const cases: Array<{
    label: string
    mode: "final_message" | "trace" | "custom"
    customText: string
  }> = [
    { label: "Final Message", mode: "final_message", customText: "" },
    { label: "Entire Trace", mode: "trace", customText: "" },
    {
      label: "Custom expression",
      mode: "custom",
      customText: "final_message.user.status",
    },
    {
      label: "Custom Jinja pipe",
      mode: "custom",
      customText: "final_message | upper",
    },
    {
      label: "Custom trace index",
      mode: "custom",
      customText: "trace[-1].content",
    },
  ]

  for (const { label, mode, customText } of cases) {
    it(`round-trips: ${label}`, () => {
      const emitted = emitValue({ mode, customText })
      const parsed = parseValue(emitted)
      expect(parsed).toEqual({ mode, customText })
    })
  }
})

describe("JINJA_EXAMPLES", () => {
  it("has exactly 6 examples", () => {
    expect(JINJA_EXAMPLES).toHaveLength(6)
  })

  it("each example has a label and expression", () => {
    for (const example of JINJA_EXAMPLES) {
      expect(example.label).toBeTruthy()
      expect(example.expression).toBeTruthy()
    }
  })

  it("includes the expected canonical labels", () => {
    const labels = JINJA_EXAMPLES.map((e) => e.label)
    expect(labels).toContain("Extract a field from JSON")
    expect(labels).toContain("Truncate a long output")
    expect(labels).toContain("Last message in the trace")
    expect(labels).toContain("Uppercase the output")
    expect(labels).toContain("Count messages in the trace")
    expect(labels).toContain("Tool call name in the trace")
  })
})

// --- Component DOM tests ---

describe("OutputValueField", () => {
  it("renders inside a FormSection with 'Value to Compare' title", () => {
    const { getByTestId, getByText } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    expect(getByTestId("output-value-section")).toBeTruthy()
    expect(getByText("Value to Compare")).toBeTruthy()
  })

  it("renders FormSection subtitle", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    const subtitle = container.querySelector(
      '[data-testid="form-section-subtitle"]',
    )
    expect(subtitle).toBeTruthy()
    expect(subtitle?.textContent).toBe(
      "Choose which part of the model output to evaluate.",
    )
  })

  it("renders a fancy_select dropdown with three options", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    const fancySelect = container.querySelector(
      '[data-testid="fancy-select-test_output_source"]',
    )
    expect(fancySelect).toBeTruthy()
    const options = fancySelect?.querySelectorAll("button[data-testid]")
    expect(options).toHaveLength(3)
  })

  it("renders Final Message option with subtitle", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    const option = container.querySelector(
      '[data-testid="fancy-option-final_message"]',
    )
    expect(option).toBeTruthy()
    expect(option?.textContent).toContain("Final Message")
    expect(option?.textContent).toContain("Entire final message")
  })

  it("renders Entire Trace option with subtitle", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    const option = container.querySelector('[data-testid="fancy-option-trace"]')
    expect(option).toBeTruthy()
    expect(option?.textContent).toContain("Entire Trace")
    expect(option?.textContent).toContain("Entire trace in JSON")
  })

  it("renders Custom (Jinja) option with subtitle", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    const option = container.querySelector(
      '[data-testid="fancy-option-custom"]',
    )
    expect(option).toBeTruthy()
    expect(option?.textContent).toContain("Custom (Jinja)")
    expect(option?.textContent).toContain(
      "Build a custom expression from Jinja syntax.",
    )
  })

  it("hides Jinja Expression input when Final Message is selected", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: "final_message" },
    })
    const jinjaInput = container.querySelector(
      '[data-testid="form-element-test_value_expression"]',
    )
    expect(jinjaInput).toBeNull()
  })

  it("hides Jinja Expression input when Entire Trace is selected", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: "trace" },
    })
    const jinjaInput = container.querySelector(
      '[data-testid="form-element-test_value_expression"]',
    )
    expect(jinjaInput).toBeNull()
  })

  it("shows Jinja Expression input when Custom is selected", () => {
    const { container } = render(OutputValueField, {
      props: {
        id_prefix: "test",
        value: "(final_message | fromjson).user.status",
      },
    })
    const jinjaInput = container.querySelector(
      '[data-testid="form-element-test_value_expression"]',
    )
    expect(jinjaInput).toBeTruthy()
    expect(jinjaInput?.getAttribute("data-label")).toBe("Jinja Expression")
  })

  it("Jinja Expression input has correct subtitle", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: "custom_expr" },
    })
    const jinjaInput = container.querySelector(
      '[data-testid="form-element-test_value_expression"]',
    )
    const desc = jinjaInput?.getAttribute("data-description") || ""
    expect(desc).toContain(
      "Extract parts of the message or trace, using Jinja syntax.",
    )
  })

  it("appends extra_description to Jinja Expression subtitle", () => {
    const { container } = render(OutputValueField, {
      props: {
        id_prefix: "test",
        value: "custom_expr",
        extra_description: "Must be an array.",
      },
    })
    const jinjaInput = container.querySelector(
      '[data-testid="form-element-test_value_expression"]',
    )
    const desc = jinjaInput?.getAttribute("data-description") || ""
    expect(desc).toContain("Jinja syntax.")
    expect(desc).toContain("Must be an array.")
  })

  it("does not append extra text when extra_description is empty", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: "custom_expr" },
    })
    const jinjaInput = container.querySelector(
      '[data-testid="form-element-test_value_expression"]',
    )
    const desc = jinjaInput?.getAttribute("data-description") || ""
    expect(desc).not.toContain("Must be an array.")
  })

  it("Jinja Expression input has correct placeholder", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: "custom_expr" },
    })
    const jinjaInput = container.querySelector(
      '[data-testid="form-element-test_value_expression"]',
    )
    expect(jinjaInput?.getAttribute("data-placeholder")).toBe(
      "(final_message | fromjson).user.status",
    )
  })

  it("shows 'See Examples' inline action when in Custom mode", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: "custom_expr" },
    })
    const jinjaInput = container.querySelector(
      '[data-testid="form-element-test_value_expression"]',
    )
    expect(jinjaInput?.getAttribute("data-inline-action-label")).toBe(
      "See Examples",
    )
  })

  it("uses correct id_prefix for the dropdown", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "exact_match", value: null },
    })
    const formElement = container.querySelector(
      '[data-testid="form-element-exact_match_output_source"]',
    )
    expect(formElement).toBeTruthy()
    expect(formElement?.getAttribute("data-type")).toBe("fancy_select")
  })

  it("hides dropdown label (FormSection provides the header)", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    const formElement = container.querySelector(
      '[data-testid="form-element-test_output_source"]',
    )
    expect(formElement?.getAttribute("data-hide-label")).toBe("true")
  })

  it("loading value='trace' selects Entire Trace mode", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: "trace" },
    })
    const traceOption = container.querySelector(
      '[data-testid="fancy-option-trace"]',
    )
    expect(traceOption?.classList.contains("selected")).toBe(true)
  })

  it("loading value=null selects Final Message mode", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    const fmOption = container.querySelector(
      '[data-testid="fancy-option-final_message"]',
    )
    expect(fmOption?.classList.contains("selected")).toBe(true)
  })

  it("loading a custom value selects Custom mode with field populated", () => {
    const { container } = render(OutputValueField, {
      props: {
        id_prefix: "test",
        value: "(final_message | fromjson).x",
      },
    })
    const customOption = container.querySelector(
      '[data-testid="fancy-option-custom"]',
    )
    expect(customOption?.classList.contains("selected")).toBe(true)
    const jinjaInput = container.querySelector(
      '[data-testid="form-element-test_value_expression"]',
    )
    expect(jinjaInput).toBeTruthy()
  })

  it("selecting Final Message emits 'final_message'", async () => {
    const { container, component } = render(OutputValueField, {
      props: { id_prefix: "test", value: "custom_expr" },
    })
    const fmOption = container.querySelector(
      '[data-testid="fancy-option-final_message"]',
    )
    await fireEvent.click(fmOption!)
    await tick()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).value).toBe("final_message")
  })

  it("selecting Entire Trace emits 'trace'", async () => {
    const { container, component } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    const traceOption = container.querySelector(
      '[data-testid="fancy-option-trace"]',
    )
    await fireEvent.click(traceOption!)
    await tick()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).value).toBe("trace")
  })
})

// --- Examples modal tests ---

describe("Examples modal", () => {
  it("renders a dialog with title 'Jinja Expression Examples'", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: "custom_expr" },
    })
    const dialog = container.querySelector('[data-testid="dialog-stub"]')
    expect(dialog).toBeTruthy()
    expect(dialog?.getAttribute("data-title")).toBe("Jinja Expression Examples")
  })

  it("renders a dialog with subtitle describing final_message and trace", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: "custom_expr" },
    })
    const dialog = container.querySelector('[data-testid="dialog-stub"]')
    expect(dialog?.getAttribute("data-subtitle")).toBe(
      "Examples of extracting data from final_message and trace using Jinja.",
    )
  })

  it("shows all 6 examples in the dialog", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: "custom_expr" },
    })
    const dialog = container.querySelector('[data-testid="dialog-stub"]')
    for (const example of JINJA_EXAMPLES) {
      expect(dialog?.textContent).toContain(example.label)
      expect(dialog?.textContent).toContain(example.expression)
    }
  })

  it("clicking an example populates the field with the expression", async () => {
    const { container, component } = render(OutputValueField, {
      props: { id_prefix: "test", value: "custom_expr" },
    })
    const dialog = container.querySelector('[data-testid="dialog-stub"]')
    const exampleButtons = dialog?.querySelectorAll("button")
    expect(exampleButtons?.length).toBe(6)

    // Click the first example
    await fireEvent.click(exampleButtons![0])
    await tick()

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).value).toBe(JINJA_EXAMPLES[0].expression)
  })

  it("clicking an example from non-custom mode switches to custom", async () => {
    const { container, component } = render(OutputValueField, {
      props: { id_prefix: "test", value: "final_message" },
    })
    const dialog = container.querySelector('[data-testid="dialog-stub"]')
    const exampleButtons = dialog?.querySelectorAll("button")

    // Click the third example (trace[-1].content)
    await fireEvent.click(exampleButtons![2])
    await tick()

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).value).toBe("trace[-1].content")
  })
})
