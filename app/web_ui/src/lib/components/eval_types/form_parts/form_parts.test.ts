// @vitest-environment jsdom
import { describe, it, expect, vi, beforeAll } from "vitest"
import { render, fireEvent } from "@testing-library/svelte"

vi.mock("$lib/utils/form_element.svelte", async () => {
  const { default: Stub } = await import(
    "../__tests__/form_element_stub.svelte"
  )
  return { default: Stub }
})

const FormSection = (await import("./form_section.svelte")).default
const DisclosureRadioGroup = (await import("./disclosure_radio_group.svelte"))
  .default
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
    const { getByText } = render(FormSection, {
      props: {
        title: "Test",
        subtitle: "Choose what value to compare.",
      },
    })
    expect(getByText("Choose what value to compare.")).toBeTruthy()
  })

  it("does not render subtitle element when not provided", () => {
    const { container } = render(FormSection, {
      props: { title: "Test" },
    })
    const subtitles = container.querySelectorAll(".text-xs.text-gray-500")
    expect(subtitles).toHaveLength(0)
  })

  it("renders with testid when provided", () => {
    const { getByTestId } = render(FormSection, {
      props: { title: "Test", testid: "my-section" },
    })
    expect(getByTestId("my-section")).toBeTruthy()
  })
})

describe("DisclosureRadioGroup", () => {
  const options = [
    {
      value: "fixed",
      label: "Fixed value",
      description: "Specify the value directly.",
    },
    {
      value: "reference",
      label: "Value from reference data",
      description: "Use a key from reference data.",
    },
  ]

  it("renders all option labels", () => {
    const { getByText } = render(DisclosureRadioGroup, {
      props: { name: "test_group", options, selected: "fixed" },
    })
    expect(getByText("Fixed value")).toBeTruthy()
    expect(getByText("Value from reference data")).toBeTruthy()
  })

  it("renders option descriptions", () => {
    const { getAllByText } = render(DisclosureRadioGroup, {
      props: { name: "test_group", options, selected: "fixed" },
    })
    expect(getAllByText("Specify the value directly.").length).toBeGreaterThan(
      0,
    )
    expect(
      getAllByText("Use a key from reference data.").length,
    ).toBeGreaterThan(0)
  })

  it("selects the default option", () => {
    const { container } = render(DisclosureRadioGroup, {
      props: { name: "test_group", options, selected: "fixed" },
    })
    const radios = container.querySelectorAll('input[type="radio"]')
    expect(radios).toHaveLength(2)
    expect((radios[0] as HTMLInputElement).checked).toBe(true)
    expect((radios[1] as HTMLInputElement).checked).toBe(false)
  })

  it("updates selected value on click", async () => {
    const { container } = render(DisclosureRadioGroup, {
      props: { name: "test_group", options, selected: "fixed" },
    })
    const radios = container.querySelectorAll('input[type="radio"]')
    await fireEvent.click(radios[1])
    expect((radios[1] as HTMLInputElement).checked).toBe(true)
  })

  it("renders with correct testid", () => {
    const { container } = render(DisclosureRadioGroup, {
      props: { name: "test_group", options, selected: "fixed" },
    })
    const groups = container.querySelectorAll(
      '[data-testid="disclosure-radio-group-test_group"]',
    )
    expect(groups.length).toBeGreaterThan(0)
  })

  it("renders without descriptions when not provided", () => {
    const simpleOptions = [
      { value: "a", label: "Option A" },
      { value: "b", label: "Option B" },
    ]
    const { getByText } = render(DisclosureRadioGroup, {
      props: { name: "simple", options: simpleOptions, selected: "a" },
    })
    expect(getByText("Option A")).toBeTruthy()
    expect(getByText("Option B")).toBeTruthy()
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

  it("renders section title 'Output Value to Compare'", () => {
    const { getAllByText } = render(OutputValueField, {
      props: { id_prefix: "test", value: null },
    })
    expect(getAllByText("Output Value to Compare").length).toBeGreaterThan(0)
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
})
