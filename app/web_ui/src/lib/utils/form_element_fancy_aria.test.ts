// @vitest-environment jsdom
import { describe, it, expect, beforeAll, afterEach } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import Wrapper from "./__tests__/form_element_fancy_wrapper.svelte"

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

describe("FancySelect aria error wiring", () => {
  it("reaches the listbox trigger through FormElement", () => {
    const { container } = render(Wrapper, {
      props: { error_message: '"Dataset Filter Tag" is required' },
    })
    const trigger = container.querySelector('[role="listbox"]')
    expect(trigger?.getAttribute("aria-invalid")).toBe("true")
    expect(trigger?.getAttribute("aria-describedby")).toBe(
      "fancy_test_field-error",
    )
    expect(
      container.querySelector("#fancy_test_field-error")?.textContent?.trim(),
    ).toBe('"Dataset Filter Tag" is required')
  })

  it("emits nothing when valid", () => {
    const { container } = render(Wrapper, { props: { error_message: null } })
    const trigger = container.querySelector('[role="listbox"]')
    expect(trigger?.hasAttribute("aria-invalid")).toBe(false)
    expect(trigger?.hasAttribute("aria-describedby")).toBe(false)
  })
})
