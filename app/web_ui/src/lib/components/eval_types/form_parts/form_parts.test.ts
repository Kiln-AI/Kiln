// @vitest-environment jsdom
import { describe, it, expect, vi, beforeAll } from "vitest"
import { render } from "@testing-library/svelte"

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

describe("OutputValueField", () => {
  it("renders with 'Output Value' label", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "exact_match", value: null },
    })
    const formElement = container.querySelector(
      '[data-testid="form-element-exact_match_value_expression"]',
    )
    expect(formElement).toBeTruthy()
    expect(formElement?.getAttribute("data-label")).toBe("Output Value")
  })

  it("renders Jinja tooltip text", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    const formElement = container.querySelector(
      '[data-testid="form-element-test_value_expression"]',
    )
    expect(formElement?.getAttribute("data-info-description")).toContain(
      "Jinja",
    )
  })

  it("tooltip says 'the model output' (not 'reference data')", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    const formElement = container.querySelector(
      '[data-testid="form-element-test_value_expression"]',
    )
    expect(formElement?.getAttribute("data-info-description")).toContain(
      "the model output",
    )
  })

  it("is a standard FormElement without FormSection wrapper", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    const section = container.querySelector(
      '[data-testid="output-value-section"]',
    )
    expect(section).toBeNull()
    const formElement = container.querySelector(
      '[data-testid="form-element-test_value_expression"]',
    )
    expect(formElement).toBeTruthy()
  })

  it("label is visible (hide_label is false)", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    const formElement = container.querySelector(
      '[data-testid="form-element-test_value_expression"]',
    )
    expect(formElement?.getAttribute("data-hide-label")).toBe("false")
  })

  it("renders description about output field extraction", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    const formElement = container.querySelector(
      '[data-testid="form-element-test_value_expression"]',
    )
    const desc = formElement?.getAttribute("data-description") || ""
    expect(desc).toContain("user.status")
    expect(desc).toContain("Leave blank to compare entire output")
  })

  it("renders placeholder on value expression input", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    const formElement = container.querySelector(
      '[data-testid="form-element-test_value_expression"]',
    )
    expect(formElement?.getAttribute("data-placeholder")).toBe(
      "e.g. result.answer",
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
    const formElement = container.querySelector(
      '[data-testid="form-element-test_value_expression"]',
    )
    const desc = formElement?.getAttribute("data-description") || ""
    expect(desc).toContain("Leave blank to compare entire output")
    expect(desc).toContain("Must be an array.")
  })

  it("does not append extra text when extra_description is empty", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    const formElement = container.querySelector(
      '[data-testid="form-element-test_value_expression"]',
    )
    const desc = formElement?.getAttribute("data-description") || ""
    expect(desc).not.toContain("Must be an array.")
  })
})
