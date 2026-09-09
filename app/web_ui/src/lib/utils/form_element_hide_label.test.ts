// @vitest-environment jsdom
import { describe, it, expect, beforeAll, afterEach } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import FormElementHideLabelWrapper from "./__tests__/form_element_hide_label_wrapper.svelte"

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

describe("FormElement hide_label behavior", () => {
  it("hides the label text when hide_label is true", () => {
    const { container } = render(FormElementHideLabelWrapper, {
      props: {
        label: "My Label",
        hide_label: true,
        description: "Some description",
      },
    })
    const labelEl = container.querySelector("label")
    expect(labelEl).toBeTruthy()
    expect(labelEl?.textContent).not.toContain("My Label")
  })

  it("shows the label text when hide_label is false", () => {
    const { container } = render(FormElementHideLabelWrapper, {
      props: {
        label: "My Label",
        hide_label: false,
      },
    })
    const labelEl = container.querySelector("label")
    expect(labelEl?.textContent).toContain("My Label")
  })

  it("renders description when hide_label is true", () => {
    const { container } = render(FormElementHideLabelWrapper, {
      props: {
        label: "My Label",
        hide_label: true,
        description: "Important description text",
      },
    })
    expect(container.textContent).toContain("Important description text")
  })

  it("renders info_description tooltip when hide_label is true", () => {
    const { container } = render(FormElementHideLabelWrapper, {
      props: {
        label: "My Label",
        hide_label: true,
        info_description: "Tooltip content here",
      },
    })
    const labelBlock = container.querySelector("label")
    expect(labelBlock).toBeTruthy()
  })

  it("renders error_message tooltip when hide_label is true", () => {
    const { container } = render(FormElementHideLabelWrapper, {
      props: {
        label: "My Label",
        hide_label: true,
        error_message: "Field has an error",
      },
    })
    const labelBlock = container.querySelector("label")
    expect(labelBlock).toBeTruthy()
  })

  it("does not render label block when hide_label is true and no description/info/error", () => {
    const { container } = render(FormElementHideLabelWrapper, {
      props: {
        label: "",
        hide_label: true,
        description: "",
        info_description: "",
        error_message: null,
      },
    })
    const labelEl = container.querySelector("label")
    expect(labelEl).toBeNull()
  })
})
