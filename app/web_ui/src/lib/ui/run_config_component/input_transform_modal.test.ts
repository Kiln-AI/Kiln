// @vitest-environment jsdom
import { describe, it, expect, beforeAll } from "vitest"
import { render } from "@testing-library/svelte"
import InputTransformModal from "./input_transform_modal.svelte"
import type { InputTransform } from "$lib/types"

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

const JINJA_TRANSFORM: InputTransform = {
  type: "jinja",
  template: "Hello {{ input }}",
}

describe("InputTransformModal", () => {
  it("renders title and subtitle for jinja transform", () => {
    const { container } = render(InputTransformModal, {
      props: { transform: JINJA_TRANSFORM },
    })

    expect(container.textContent).toContain("Input Transformer")
    expect(container.textContent).toContain("Type: Custom Jinja2 Template")
  })

  it("renders the template body", () => {
    const { container } = render(InputTransformModal, {
      props: { transform: JINJA_TRANSFORM },
    })

    expect(container.textContent).toContain("Hello {{ input }}")
  })

  it("renders with an empty template string", () => {
    const emptyTransform: InputTransform = {
      type: "jinja",
      template: "",
    }
    const { container } = render(InputTransformModal, {
      props: { transform: emptyTransform },
    })

    expect(container.textContent).toContain("Input Transformer")
    expect(container.textContent).toContain("Type: Custom Jinja2 Template")
  })

  it("contains a copy button via Output", () => {
    const { container } = render(InputTransformModal, {
      props: { transform: JINJA_TRANSFORM },
    })

    const copyButton = container.querySelector("button")
    expect(copyButton).not.toBeNull()
  })
})
