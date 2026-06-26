// @vitest-environment jsdom
import { describe, it, expect, beforeAll, afterEach } from "vitest"
import { render, fireEvent, cleanup } from "@testing-library/svelte"
import { tick } from "svelte"
import FormElementRadioWrapper from "./__tests__/form_element_radio_wrapper.svelte"
import FormElementRadioWithContext from "./__tests__/form_element_radio_with_context.svelte"

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

afterEach(cleanup)

const sampleOptions = [
  {
    value: "option_a",
    label: "Option A",
    description: "Description for A",
  },
  {
    value: "option_b",
    label: "Option B",
    description: "Description for B",
  },
  {
    value: "option_c",
    label: "Option C",
  },
]

describe("FormElement radio inputType", () => {
  it("renders all option labels", () => {
    const { getByText } = render(FormElementRadioWrapper, {
      props: {
        radio_options: sampleOptions,
        value: "option_a",
      },
    })
    expect(getByText("Option A")).toBeTruthy()
    expect(getByText("Option B")).toBeTruthy()
    expect(getByText("Option C")).toBeTruthy()
  })

  it("renders option descriptions when provided", () => {
    const { getByText } = render(FormElementRadioWrapper, {
      props: {
        radio_options: sampleOptions,
        value: "option_a",
      },
    })
    expect(getByText("Description for A")).toBeTruthy()
    expect(getByText("Description for B")).toBeTruthy()
  })

  it("omits description element when not provided", () => {
    const { getByText } = render(FormElementRadioWrapper, {
      props: {
        radio_options: sampleOptions,
        value: "option_a",
      },
    })
    const optionCLabel = getByText("Option C")
    const optionCContainer = optionCLabel.closest("span.flex.flex-col")
    expect(optionCContainer).toBeTruthy()
    const children = optionCContainer!.querySelectorAll("span")
    expect(children.length).toBe(1)
  })

  it("renders native radio inputs for each option", () => {
    const { container } = render(FormElementRadioWrapper, {
      props: {
        radio_options: sampleOptions,
        value: "option_a",
      },
    })
    const radios = container.querySelectorAll('input[type="radio"]')
    expect(radios.length).toBe(3)
  })

  it("checks the correct radio for the initial value", () => {
    const { container } = render(FormElementRadioWrapper, {
      props: {
        radio_options: sampleOptions,
        value: "option_b",
      },
    })
    const radios = container.querySelectorAll('input[type="radio"]')
    expect((radios[0] as HTMLInputElement).checked).toBe(false)
    expect((radios[1] as HTMLInputElement).checked).toBe(true)
    expect((radios[2] as HTMLInputElement).checked).toBe(false)
  })

  it("updates value when a different option is selected", async () => {
    const { container } = render(FormElementRadioWrapper, {
      props: {
        radio_options: sampleOptions,
        value: "option_a",
      },
    })
    const radios = container.querySelectorAll('input[type="radio"]')

    await fireEvent.click(radios[2])
    await tick()

    expect((radios[2] as HTMLInputElement).checked).toBe(true)
    expect((radios[0] as HTMLInputElement).checked).toBe(false)
  })

  it("shows primary highlight on the selected row", () => {
    const { container } = render(FormElementRadioWrapper, {
      props: {
        radio_options: sampleOptions,
        value: "option_a",
      },
    })
    const labels = container.querySelectorAll(
      '[data-testid="radio-group-test_radio"] > label',
    )
    expect(labels.length).toBe(3)
    expect(labels[0].className).toContain("border-primary/30")
    expect(labels[0].className).toContain("bg-primary/[0.03]")
    expect(labels[1].className).toContain("border-base-300")
    expect(labels[2].className).toContain("border-base-300")
  })

  it("renders the radiogroup role and aria-label", () => {
    const { container } = render(FormElementRadioWrapper, {
      props: {
        radio_options: sampleOptions,
        value: "option_a",
        label: "My Radio Group",
      },
    })
    const group = container.querySelector('[role="radiogroup"]')
    expect(group).toBeTruthy()
    expect(group!.getAttribute("aria-label")).toBe("My Radio Group")
  })

  it("renders the form label and description", () => {
    const { getByText } = render(FormElementRadioWrapper, {
      props: {
        radio_options: sampleOptions,
        value: "option_a",
        label: "Choose Type",
        description: "Pick one of the available types.",
      },
    })
    expect(getByText("Choose Type")).toBeTruthy()
    expect(getByText("Pick one of the available types.")).toBeTruthy()
  })

  it("applies DaisyUI radio classes to inputs", () => {
    const { container } = render(FormElementRadioWrapper, {
      props: {
        radio_options: sampleOptions,
        value: "option_a",
      },
    })
    const radio = container.querySelector('input[type="radio"]')
    expect(radio).toBeTruthy()
    expect(radio!.classList.contains("radio")).toBe(true)
    expect(radio!.classList.contains("radio-sm")).toBe(true)
    expect(radio!.classList.contains("radio-primary")).toBe(true)
  })

  it("disables all radios when disabled prop is set", () => {
    const { container } = render(FormElementRadioWrapper, {
      props: {
        radio_options: sampleOptions,
        value: "option_a",
        disabled: true,
      },
    })
    const radios = container.querySelectorAll('input[type="radio"]')
    radios.forEach((radio) => {
      expect((radio as HTMLInputElement).disabled).toBe(true)
    })
    const labels = container.querySelectorAll(
      '[data-testid="radio-group-test_radio"] > label',
    )
    labels.forEach((label) => {
      expect(label.className).toContain("opacity-50")
    })
  })

  describe("validation", () => {
    it("run_validator sets error when required radio has no selection", async () => {
      const { component, container } = render(FormElementRadioWithContext, {
        props: {
          radio_options: sampleOptions,
          value: "",
          optional: false,
          label: "Test Radio",
        },
      })

      // No error initially
      expect(container.querySelector("span.text-error")).toBeNull()

      // Call run_validator the same way FormContainer does during validation
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ;(component as any).runValidator()
      await tick()

      // Error tooltip should appear
      const errorSpan = container.querySelector("span.text-error")
      expect(errorSpan).toBeTruthy()
    })

    it("run_validator does not set error when optional radio has no selection", async () => {
      const { component, container } = render(FormElementRadioWithContext, {
        props: {
          radio_options: sampleOptions,
          value: "",
          optional: true,
          label: "Test Radio",
        },
      })

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ;(component as any).runValidator()
      await tick()

      expect(container.querySelector("span.text-error")).toBeNull()
    })

    it("run_validator does not set error when a value is selected", async () => {
      const { component, container } = render(FormElementRadioWithContext, {
        props: {
          radio_options: sampleOptions,
          value: "option_a",
          optional: false,
          label: "Test Radio",
        },
      })

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ;(component as any).runValidator()
      await tick()

      expect(container.querySelector("span.text-error")).toBeNull()
    })

    it("shows error border on radio cards after validation failure", async () => {
      const { component, container } = render(FormElementRadioWithContext, {
        props: {
          radio_options: sampleOptions,
          value: "",
          optional: false,
        },
      })

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ;(component as any).runValidator()
      await tick()

      const labels = container.querySelectorAll(
        '[data-testid="radio-group-test_radio"] > label',
      )
      expect(labels.length).toBe(3)
      labels.forEach((label) => {
        expect(label.className).toContain("border-error/50")
      })
    })

    it("renders input-error on radiogroup for FormContainer detection", async () => {
      const { component, container } = render(FormElementRadioWithContext, {
        props: {
          radio_options: sampleOptions,
          value: "",
          optional: false,
        },
      })

      // Radiogroup exists but no error class initially
      const radioGroup = container.querySelector('[role="radiogroup"]')
      expect(radioGroup).toBeTruthy()
      expect(radioGroup!.classList.contains("input-error")).toBe(false)

      // Trigger validation
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ;(component as any).runValidator()
      await tick()

      // Radiogroup should now have input-error for FormContainer's first_error()
      expect(radioGroup!.classList.contains("input-error")).toBe(true)
    })

    it("clears error after selecting a valid value", async () => {
      const { component, container } = render(FormElementRadioWithContext, {
        props: {
          radio_options: sampleOptions,
          value: "",
          optional: false,
        },
      })

      // Trigger validation error
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ;(component as any).runValidator()
      await tick()
      expect(container.querySelector("span.text-error")).toBeTruthy()

      // Select a value via radio click
      const radios = container.querySelectorAll('input[type="radio"]')
      await fireEvent.click(radios[0])
      await tick()

      // Re-run validator (as FormContainer would on value change)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ;(component as any).runValidator()
      await tick()

      // Error should be cleared
      expect(container.querySelector("span.text-error")).toBeNull()
    })
  })
})
