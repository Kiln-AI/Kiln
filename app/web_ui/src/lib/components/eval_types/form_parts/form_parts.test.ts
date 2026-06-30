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

const OutputValueField = (await import("./output_value_field.svelte")).default
const ReferenceFieldSelect = (await import("./reference_field_select.svelte"))
  .default
const ReferenceFieldHarness = (
  await import("../__tests__/reference_field_harness.svelte")
).default

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
  it("renders 'Output to Check' label on the dropdown FormElement", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    const formElement = container.querySelector(
      '[data-testid="form-element-test_output_source"]',
    )
    expect(formElement).toBeTruthy()
    expect(formElement?.getAttribute("data-label")).toBe("Output to Check")
  })

  it("renders description on the dropdown FormElement", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    const formElement = container.querySelector(
      '[data-testid="form-element-test_output_source"]',
    )
    expect(formElement).toBeTruthy()
    expect(formElement?.getAttribute("data-description")).toBe(
      "Which part of the model's output to compare against the expected value.",
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
      "Select part of the output or trace using Jinja syntax.",
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

  it("shows dropdown label (label is visible on the FormElement)", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    const formElement = container.querySelector(
      '[data-testid="form-element-test_output_source"]',
    )
    expect(formElement?.getAttribute("data-hide-label")).toBe("false")
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

  it("switching from Final Message to Custom emits null (empty customText shows placeholder)", async () => {
    const { container, component } = render(OutputValueField, {
      props: { id_prefix: "test", value: "final_message" },
    })
    const customOption = container.querySelector(
      '[data-testid="fancy-option-custom"]',
    )
    await fireEvent.click(customOption!)
    await tick()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).value).toBeNull()
  })

  it("switching from Entire Trace to Custom emits null (empty customText shows placeholder)", async () => {
    const { container, component } = render(OutputValueField, {
      props: { id_prefix: "test", value: "trace" },
    })
    const customOption = container.querySelector(
      '[data-testid="fancy-option-custom"]',
    )
    await fireEvent.click(customOption!)
    await tick()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).value).toBeNull()
  })

  it("switching to Custom preserves previously entered custom text", async () => {
    const { container, component } = render(OutputValueField, {
      props: {
        id_prefix: "test",
        value: "final_message | upper",
      },
    })
    // Start in custom mode with text. Switch to final_message, then back to custom.
    const fmOption = container.querySelector(
      '[data-testid="fancy-option-final_message"]',
    )
    await fireEvent.click(fmOption!)
    await tick()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).value).toBe("final_message")

    const customOption = container.querySelector(
      '[data-testid="fancy-option-custom"]',
    )
    await fireEvent.click(customOption!)
    await tick()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).value).toBe("final_message | upper")
  })

  it("external value change on edit re-parses into correct state", async () => {
    const { container, component } = render(OutputValueField, {
      props: { id_prefix: "test", value: "final_message" },
    })
    // Verify initial state
    const fmOption = container.querySelector(
      '[data-testid="fancy-option-final_message"]',
    )
    expect(fmOption?.classList.contains("selected")).toBe(true)

    // Externally set to a custom expression (simulates edit/load)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(component as any).$set({ value: "trace[-1].content" })
    await tick()

    const customOption = container.querySelector(
      '[data-testid="fancy-option-custom"]',
    )
    expect(customOption?.classList.contains("selected")).toBe(true)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).value).toBe("trace[-1].content")
  })

  it("external value change to preset correctly sets dropdown", async () => {
    const { container, component } = render(OutputValueField, {
      props: { id_prefix: "test", value: "custom_expr" },
    })
    // Start in custom mode
    const customOption = container.querySelector(
      '[data-testid="fancy-option-custom"]',
    )
    expect(customOption?.classList.contains("selected")).toBe(true)

    // Externally set to 'trace'
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(component as any).$set({ value: "trace" })
    await tick()

    const traceOption = container.querySelector(
      '[data-testid="fancy-option-trace"]',
    )
    expect(traceOption?.classList.contains("selected")).toBe(true)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).value).toBe("trace")
  })

  it("custom text input is empty after switching from trace to custom", async () => {
    const { container, component } = render(OutputValueField, {
      props: { id_prefix: "test", value: "trace" },
    })
    // Switch from Entire Trace to Custom
    const customOption = container.querySelector(
      '[data-testid="fancy-option-custom"]',
    )
    await fireEvent.click(customOption!)
    await tick()

    // The Jinja input should be visible (mode is custom)
    const jinjaInput = container.querySelector(
      '[data-testid="form-element-test_value_expression"]',
    )
    expect(jinjaInput).toBeTruthy()
    // Value must be null, meaning custom text is empty — placeholder shows
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).value).toBeNull()
  })

  it("round-trip: custom -> preset -> custom preserves custom text independently", async () => {
    const { container, component } = render(OutputValueField, {
      props: { id_prefix: "test", value: "my.custom.expr" },
    })

    // Switch to trace
    const traceOption = container.querySelector(
      '[data-testid="fancy-option-trace"]',
    )
    await fireEvent.click(traceOption!)
    await tick()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).value).toBe("trace")

    // Switch back to custom — custom text is preserved
    const customOption = container.querySelector(
      '[data-testid="fancy-option-custom"]',
    )
    await fireEvent.click(customOption!)
    await tick()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).value).toBe("my.custom.expr")

    // Switch to final_message
    const fmOption = container.querySelector(
      '[data-testid="fancy-option-final_message"]',
    )
    await fireEvent.click(fmOption!)
    await tick()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).value).toBe("final_message")

    // Switch back to custom — still preserved
    await fireEvent.click(customOption!)
    await tick()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((component as any).value).toBe("my.custom.expr")
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

// --- ReferenceFieldSelect tests ---

describe("ReferenceFieldSelect", () => {
  describe("no candidates (plain text fallback)", () => {
    it("renders a plain text input when candidate_keys is empty", () => {
      const { container } = render(ReferenceFieldSelect, {
        props: { id_prefix: "test", value: null, candidate_keys: [] },
      })
      const field = container.querySelector(
        '[data-testid="form-element-test_reference_key"]',
      )
      expect(field).toBeTruthy()
      expect(field?.getAttribute("data-type")).toBe("input")
    })

    it("plain text input has correct label and description", () => {
      const { container } = render(ReferenceFieldSelect, {
        props: { id_prefix: "test", value: null, candidate_keys: [] },
      })
      const field = container.querySelector(
        '[data-testid="form-element-test_reference_key"]',
      )
      expect(field?.getAttribute("data-label")).toBe("Reference Data Field")
      expect(field?.getAttribute("data-description")).toContain(
        "reference data",
      )
    })

    it("plain text input has tooltip", () => {
      const { container } = render(ReferenceFieldSelect, {
        props: { id_prefix: "test", value: null, candidate_keys: [] },
      })
      const field = container.querySelector(
        '[data-testid="form-element-test_reference_key"]',
      )
      const tooltip = field?.getAttribute("data-info-description") || ""
      expect(tooltip).toContain("top-level field")
      expect(tooltip).toContain("expected_answer")
    })

    it("binds value in plain text mode", () => {
      const { component } = render(ReferenceFieldSelect, {
        props: {
          id_prefix: "test",
          value: "my_field",
          candidate_keys: [],
        },
      })
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      expect((component as any).value).toBe("my_field")
    })
  })

  describe("with candidates (dropdown mode)", () => {
    const keys = ["expected_answer", "expected_status"]

    it("renders a fancy_select when candidates are present", () => {
      const { container } = render(ReferenceFieldSelect, {
        props: { id_prefix: "test", value: null, candidate_keys: keys },
      })
      const field = container.querySelector(
        '[data-testid="form-element-test_reference_key"]',
      )
      expect(field).toBeTruthy()
      expect(field?.getAttribute("data-type")).toBe("fancy_select")
    })

    it("renders candidate keys as dropdown options plus Custom", () => {
      const { container } = render(ReferenceFieldSelect, {
        props: { id_prefix: "test", value: null, candidate_keys: keys },
      })
      const fancySelect = container.querySelector(
        '[data-testid="fancy-select-test_reference_key"]',
      )
      const options = fancySelect?.querySelectorAll("button[data-testid]")
      expect(options?.length).toBe(3)
      expect(
        fancySelect?.querySelector(
          '[data-testid="fancy-option-expected_answer"]',
        ),
      ).toBeTruthy()
      expect(
        fancySelect?.querySelector(
          '[data-testid="fancy-option-expected_status"]',
        ),
      ).toBeTruthy()
      expect(
        fancySelect?.querySelector('[data-testid="fancy-option-__custom__"]'),
      ).toBeTruthy()
    })

    it("selecting a key emits that key as value", async () => {
      const { container, component } = render(ReferenceFieldSelect, {
        props: { id_prefix: "test", value: null, candidate_keys: keys },
      })
      const option = container.querySelector(
        '[data-testid="fancy-option-expected_answer"]',
      )
      await fireEvent.click(option!)
      await tick()
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      expect((component as any).value).toBe("expected_answer")
    })

    it("selecting Custom opens the modal dialog", async () => {
      const { container } = render(ReferenceFieldSelect, {
        props: {
          id_prefix: "test",
          value: "expected_answer",
          candidate_keys: keys,
        },
      })
      const customOption = container.querySelector(
        '[data-testid="fancy-option-__custom__"]',
      )
      await fireEvent.click(customOption!)
      await tick()
      const dialog = container.querySelector('[data-title="Custom Field Name"]')
      expect(dialog).toBeTruthy()
    })

    it("custom field name input exists inside the modal dialog (not inline)", () => {
      const { container } = render(ReferenceFieldSelect, {
        props: {
          id_prefix: "test",
          value: "expected_answer",
          candidate_keys: keys,
        },
      })
      const customInput = container.querySelector(
        '[data-testid="custom-field-name-input"]',
      )
      expect(customInput).toBeTruthy()
    })

    it("adds non-candidate value to option list and selects it", () => {
      const { container, component } = render(ReferenceFieldSelect, {
        props: {
          id_prefix: "test",
          value: "unknown_field",
          candidate_keys: keys,
        },
      })
      const unknownOption = container.querySelector(
        '[data-testid="fancy-option-unknown_field"]',
      )
      expect(unknownOption).toBeTruthy()
      expect(unknownOption?.classList.contains("selected")).toBe(true)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      expect((component as any).value).toBe("unknown_field")
    })

    it("selects matching key when value matches a candidate", () => {
      const { container } = render(ReferenceFieldSelect, {
        props: {
          id_prefix: "test",
          value: "expected_status",
          candidate_keys: keys,
        },
      })
      const option = container.querySelector(
        '[data-testid="fancy-option-expected_status"]',
      )
      expect(option?.classList.contains("selected")).toBe(true)
    })

    it("null value shows placeholder (no option selected), not Custom sentinel", () => {
      const { container, component } = render(ReferenceFieldSelect, {
        props: { id_prefix: "test", value: null, candidate_keys: keys },
      })
      // Custom sentinel must NOT be selected — it is only a momentary
      // modal trigger, never a persisted selection.
      const customOption = container.querySelector(
        '[data-testid="fancy-option-__custom__"]',
      )
      expect(customOption?.classList.contains("selected")).toBe(false)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      expect((component as any).value).toBeNull()
    })
  })

  describe("no-candidates → has-candidates transition preserves typed value", () => {
    it("DOM typing: value typed via real input is preserved when candidates appear", async () => {
      // Render via harness that does bind:value like the real form does.
      const { container, component } = render(ReferenceFieldHarness, {
        props: { value: null, candidate_keys: [] },
      })

      // Confirm text input mode
      const formEl = container.querySelector(
        '[data-testid="form-element-t_reference_key"]',
      )
      expect(formEl?.getAttribute("data-type")).toBe("input")

      // Type "asdf" into the real <input> rendered by the stub.
      // This goes through the actual DOM → bind:value chain:
      //   stub <input> → FormElement.value → bind → custom_raw_reference_value
      const input = container.querySelector(
        '[data-testid="input-t_reference_key"]',
      ) as HTMLInputElement
      expect(input).toBeTruthy()

      await fireEvent.input(input, { target: { value: "asdf" } })
      await tick()

      // Confirm value propagated up through the harness bind
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      expect((component as any).value).toBe("asdf")

      // candidate_keys becomes non-empty (user entered reference data)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ;(component as any).$set({ candidate_keys: ["foo"] })
      await tick()
      await tick()

      // Control must now be a dropdown
      const dropdown = container.querySelector(
        '[data-testid="form-element-t_reference_key"]',
      )
      expect(dropdown?.getAttribute("data-type")).toBe("fancy_select")

      // "asdf" must be preserved as the value — on both the component and harness
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      expect((component as any).value).toBe("asdf")

      // "asdf" must appear as a selected option in the dropdown
      const asdfOption = container.querySelector(
        '[data-testid="fancy-option-asdf"]',
      )
      expect(asdfOption).toBeTruthy()
      expect(asdfOption?.classList.contains("selected")).toBe(true)

      // The sentinel must NOT be selected
      const customOption = container.querySelector(
        '[data-testid="fancy-option-__custom__"]',
      )
      expect(customOption?.classList.contains("selected")).toBe(false)
    })

    it("typed value in plain text mode is preserved when candidates appear", async () => {
      const { container, component } = render(ReferenceFieldHarness, {
        props: { value: "my_field", candidate_keys: [] },
      })
      const field = container.querySelector(
        '[data-testid="form-element-t_reference_key"]',
      )
      expect(field?.getAttribute("data-type")).toBe("input")
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      expect((component as any).value).toBe("my_field")

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ;(component as any).$set({
        candidate_keys: ["expected_answer", "expected_status"],
      })
      await tick()
      await tick()

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      expect((component as any).value).toBe("my_field")

      // Must appear as a selected dropdown option
      const option = container.querySelector(
        '[data-testid="fancy-option-my_field"]',
      )
      expect(option).toBeTruthy()
      expect(option?.classList.contains("selected")).toBe(true)
    })

    it("null value stays null when candidates appear", async () => {
      const { component } = render(ReferenceFieldHarness, {
        props: { value: null, candidate_keys: [] },
      })
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      expect((component as any).value).toBeNull()

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ;(component as any).$set({ candidate_keys: ["expected_answer"] })
      await tick()

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      expect((component as any).value).toBeNull()
    })

    it("typed value matching a candidate selects the candidate option", async () => {
      const { container, component } = render(ReferenceFieldHarness, {
        props: { value: null, candidate_keys: [] },
      })

      // Type a value that will match a future candidate
      const input = container.querySelector(
        '[data-testid="input-t_reference_key"]',
      ) as HTMLInputElement
      await fireEvent.input(input, { target: { value: "expected_answer" } })
      await tick()

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      expect((component as any).value).toBe("expected_answer")

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ;(component as any).$set({
        candidate_keys: ["expected_answer", "expected_status"],
      })
      await tick()

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      expect((component as any).value).toBe("expected_answer")
      const option = container.querySelector(
        '[data-testid="fancy-option-expected_answer"]',
      )
      expect(option?.classList.contains("selected")).toBe(true)
    })
  })
})
