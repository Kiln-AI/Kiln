// @vitest-environment jsdom
import { describe, it, expect, vi, beforeAll } from "vitest"
import { render } from "@testing-library/svelte"
import { emitValue, parseValue, joinSelector } from "./output_value_helpers"

vi.mock("$lib/utils/form_element.svelte", async () => {
  const { default: Stub } = await import(
    "../__tests__/form_element_stub.svelte"
  )
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

// ─── Pure helper tests ───────────────────────────────────────────────────

describe("joinSelector", () => {
  it("returns empty for empty/whitespace", () => {
    expect(joinSelector("")).toBe("")
    expect(joinSelector("  ")).toBe("")
  })

  it("prepends dot for normal path", () => {
    expect(joinSelector("user.status")).toBe(".user.status")
  })

  it("does not prepend dot for bracket access", () => {
    expect(joinSelector("[0]")).toBe("[0]")
    expect(joinSelector("[0].content")).toBe("[0].content")
  })

  it("trims whitespace", () => {
    expect(joinSelector("  foo  ")).toBe(".foo")
  })
})

describe("emitValue", () => {
  it("Final Message + empty selector → null", () => {
    expect(emitValue({ source: "final_message", selector: "" })).toBe(null)
  })

  it("Final Message + dot-path selector → final_message.path", () => {
    expect(
      emitValue({ source: "final_message", selector: "user.status" }),
    ).toBe("final_message.user.status")
  })

  it("Final Message + bracket selector → final_message[0]", () => {
    expect(emitValue({ source: "final_message", selector: "[0]" })).toBe(
      "final_message[0]",
    )
  })

  it("Entire Trace + empty selector → 'trace'", () => {
    expect(emitValue({ source: "trace", selector: "" })).toBe("trace")
  })

  it("Entire Trace + dot-path selector → trace.path", () => {
    expect(emitValue({ source: "trace", selector: "messages" })).toBe(
      "trace.messages",
    )
  })

  it("Entire Trace + bracket selector → trace[0].content", () => {
    expect(emitValue({ source: "trace", selector: "[0].content" })).toBe(
      "trace[0].content",
    )
  })

  it("trims whitespace in selector before emitting", () => {
    expect(
      emitValue({ source: "final_message", selector: "  user.status  " }),
    ).toBe("final_message.user.status")
  })
})

describe("parseValue", () => {
  it("null → Final Message, empty selector", () => {
    expect(parseValue(null)).toEqual({
      source: "final_message",
      selector: "",
    })
  })

  it("empty string → Final Message, empty selector", () => {
    expect(parseValue("")).toEqual({
      source: "final_message",
      selector: "",
    })
  })

  it("whitespace → Final Message, empty selector", () => {
    expect(parseValue("   ")).toEqual({
      source: "final_message",
      selector: "",
    })
  })

  it("'final_message' → Final Message, empty selector", () => {
    expect(parseValue("final_message")).toEqual({
      source: "final_message",
      selector: "",
    })
  })

  it("'final_message.user.status' → Final Message, 'user.status'", () => {
    expect(parseValue("final_message.user.status")).toEqual({
      source: "final_message",
      selector: "user.status",
    })
  })

  it("'final_message[0]' → Final Message, '[0]'", () => {
    expect(parseValue("final_message[0]")).toEqual({
      source: "final_message",
      selector: "[0]",
    })
  })

  it("'trace' → Entire Trace, empty selector", () => {
    expect(parseValue("trace")).toEqual({
      source: "trace",
      selector: "",
    })
  })

  it("'trace.messages' → Entire Trace, 'messages'", () => {
    expect(parseValue("trace.messages")).toEqual({
      source: "trace",
      selector: "messages",
    })
  })

  it("'trace[0].content' → Entire Trace, '[0].content'", () => {
    expect(parseValue("trace[0].content")).toEqual({
      source: "trace",
      selector: "[0].content",
    })
  })

  // Legacy/unknown prefixes are intentionally migrated into the
  // "final_message.<path>" form on re-emit. These never worked with the
  // old backend, so the lossy parse→emit is acceptable migration behavior.
  it("legacy bare path → Final Message, whole value as selector", () => {
    expect(parseValue("user.status")).toEqual({
      source: "final_message",
      selector: "user.status",
    })
  })

  it("'task_input.something' → Final Message, whole value as selector", () => {
    expect(parseValue("task_input.something")).toEqual({
      source: "final_message",
      selector: "task_input.something",
    })
  })

  it("'reference_data.key' → Final Message, whole value as selector", () => {
    expect(parseValue("reference_data.key")).toEqual({
      source: "final_message",
      selector: "reference_data.key",
    })
  })
})

describe("round-trip: parse(emit(state)) === state", () => {
  const cases: Array<{
    label: string
    source: "final_message" | "trace"
    selector: string
  }> = [
    { label: "FM blank", source: "final_message", selector: "" },
    { label: "FM dot path", source: "final_message", selector: "user.status" },
    { label: "FM bracket", source: "final_message", selector: "[0]" },
    {
      label: "FM bracket+dot",
      source: "final_message",
      selector: "[0].content",
    },
    { label: "Trace blank", source: "trace", selector: "" },
    { label: "Trace dot path", source: "trace", selector: "messages" },
    { label: "Trace bracket", source: "trace", selector: "[0].content" },
  ]

  for (const { label, source, selector } of cases) {
    it(`round-trips: ${label}`, () => {
      const emitted = emitValue({ source, selector })
      const parsed = parseValue(emitted)
      expect(parsed).toEqual({ source, selector })
    })
  }
})

// ─── Component DOM tests ─────────────────────────────────────────────────

describe("OutputValueField", () => {
  it("renders inside a FormSection with 'Value to Check' title", () => {
    const { getByTestId, getByText } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    expect(getByTestId("output-value-section")).toBeTruthy()
    expect(getByText("Value to Check")).toBeTruthy()
  })

  it("renders radio group with Final Message and Entire Trace options", () => {
    const { getAllByText } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    expect(getAllByText("Final Message").length).toBeGreaterThan(0)
    expect(getAllByText("Entire Trace").length).toBeGreaterThan(0)
  })

  it("renders radio option descriptions", () => {
    const { getAllByText } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    expect(getAllByText("The model's final output.").length).toBeGreaterThan(0)
    expect(
      getAllByText("The full conversation/tool-call trace.").length,
    ).toBeGreaterThan(0)
  })

  it("renders selector input with correct label", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    const selectorInput = container.querySelector(
      '[data-testid="form-element-test_value_expression"]',
    )
    expect(selectorInput).toBeTruthy()
    expect(selectorInput?.getAttribute("data-label")).toBe("Sub-field")
  })

  it("renders Jinja tooltip text on selector", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    const selectorInput = container.querySelector(
      '[data-testid="form-element-test_value_expression"]',
    )
    expect(selectorInput?.getAttribute("data-info-description")).toContain(
      "Jinja",
    )
  })

  it("tooltip mentions 'the model output'", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    const selectorInput = container.querySelector(
      '[data-testid="form-element-test_value_expression"]',
    )
    expect(selectorInput?.getAttribute("data-info-description")).toContain(
      "the model output",
    )
  })

  it("renders description about output field extraction", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    const selectorInput = container.querySelector(
      '[data-testid="form-element-test_value_expression"]',
    )
    const desc = selectorInput?.getAttribute("data-description") || ""
    expect(desc).toContain("user.status")
    expect(desc).toContain("Leave blank to use the entire message")
  })

  it("renders placeholder 'e.g. user.status'", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    const selectorInput = container.querySelector(
      '[data-testid="form-element-test_value_expression"]',
    )
    expect(selectorInput?.getAttribute("data-placeholder")).toBe(
      "e.g. user.status",
    )
  })

  it("appends extra_description when provided", () => {
    const { container } = render(OutputValueField, {
      props: {
        id_prefix: "test",
        value: null,
        extra_description: "Must be an array.",
      },
    })
    const selectorInput = container.querySelector(
      '[data-testid="form-element-test_value_expression"]',
    )
    const desc = selectorInput?.getAttribute("data-description") || ""
    expect(desc).toContain("Leave blank to use the entire message")
    expect(desc).toContain("Must be an array.")
  })

  it("does not append extra text when extra_description is empty", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    const selectorInput = container.querySelector(
      '[data-testid="form-element-test_value_expression"]',
    )
    const desc = selectorInput?.getAttribute("data-description") || ""
    expect(desc).not.toContain("Must be an array.")
  })

  it("uses correct id_prefix for radio group", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "exact_match", value: null },
    })
    const radioGroup = container.querySelector(
      '[data-testid="form-element-exact_match_output_source"]',
    )
    expect(radioGroup).toBeTruthy()
    expect(radioGroup?.getAttribute("data-type")).toBe("radio")
  })

  it("hides radio group label", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    const radioGroup = container.querySelector(
      '[data-testid="form-element-test_output_source"]',
    )
    expect(radioGroup?.getAttribute("data-hide-label")).toBe("true")
  })

  it("parses existing 'trace' value into Entire Trace source", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: "trace" },
    })
    const radioGroup = container.querySelector(
      '[data-testid="radio-group-test_output_source"]',
    )
    const checkedRadio = radioGroup?.querySelector(
      'input[type="radio"]:checked',
    ) as HTMLInputElement | null
    expect(checkedRadio?.value).toBe("trace")
  })

  it("parses existing 'final_message.user.status' into Final Message + selector", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: "final_message.user.status" },
    })
    const radioGroup = container.querySelector(
      '[data-testid="radio-group-test_output_source"]',
    )
    const checkedRadio = radioGroup?.querySelector(
      'input[type="radio"]:checked',
    ) as HTMLInputElement | null
    expect(checkedRadio?.value).toBe("final_message")
  })

  it("parses null value into Final Message source", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    const radioGroup = container.querySelector(
      '[data-testid="radio-group-test_output_source"]',
    )
    const checkedRadio = radioGroup?.querySelector(
      'input[type="radio"]:checked',
    ) as HTMLInputElement | null
    expect(checkedRadio?.value).toBe("final_message")
  })

  // ─── Trace-source copy (examples differ from Final Message) ──────────────

  it("uses 'Sub-field' label when source is trace", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: "trace" },
    })
    const selectorInput = container.querySelector(
      '[data-testid="form-element-test_value_expression"]',
    )
    expect(selectorInput?.getAttribute("data-label")).toBe("Sub-field")
  })

  it("uses index-path placeholder when source is trace", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: "trace" },
    })
    const selectorInput = container.querySelector(
      '[data-testid="form-element-test_value_expression"]',
    )
    expect(selectorInput?.getAttribute("data-placeholder")).toBe(
      "e.g. [-1].content",
    )
  })

  it("description for trace uses an index example, not 'user.status'", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: "trace" },
    })
    const selectorInput = container.querySelector(
      '[data-testid="form-element-test_value_expression"]',
    )
    const desc = selectorInput?.getAttribute("data-description") || ""
    expect(desc).toContain("[-1].content")
    expect(desc).toContain("Leave blank to use the entire trace")
    expect(desc).not.toContain("user.status")
  })

  it("tooltip for trace mentions 'list of messages'", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: "trace" },
    })
    const selectorInput = container.querySelector(
      '[data-testid="form-element-test_value_expression"]',
    )
    const info = selectorInput?.getAttribute("data-info-description") || ""
    expect(info).toContain("list of messages")
    expect(info).toContain("Jinja")
  })
})
