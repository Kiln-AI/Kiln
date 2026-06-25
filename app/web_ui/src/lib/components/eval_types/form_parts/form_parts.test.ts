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
  it("renders with 'Output Value to Compare' label", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "exact_match", value: null },
    })
    const formElement = container.querySelector(
      '[data-testid="form-element-exact_match_value_expression"]',
    )
    expect(formElement).toBeTruthy()
    expect(formElement?.getAttribute("data-label")).toBe(
      "Output Value to Compare",
    )
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

  it("renders section title 'Output Extraction'", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    const section = container.querySelector(
      '[data-testid="output-value-section"]',
    )
    expect(section).toBeTruthy()
    const heading = section?.querySelector("h3")
    expect(heading?.textContent).toBe("Output Extraction")
  })

  it("renders description text about Jinja expressions", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    const formElement = container.querySelector(
      '[data-testid="form-element-test_value_expression"]',
    )
    expect(formElement?.getAttribute("data-description")).toContain(
      "Jinja expression",
    )
  })

  it("hides the inner FormElement label (section title is sole heading)", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    const formElement = container.querySelector(
      '[data-testid="form-element-test_value_expression"]',
    )
    expect(formElement?.getAttribute("data-hide-label")).toBe("true")
  })

  it("renders subtitle about extracting fields", () => {
    const { container } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    const subtitle = container.querySelector(
      '[data-testid="form-section-subtitle"]',
    )
    expect(subtitle).toBeTruthy()
    expect(subtitle?.textContent).toContain("extract")
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
})
