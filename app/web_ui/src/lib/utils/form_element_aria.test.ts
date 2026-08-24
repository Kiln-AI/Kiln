// @vitest-environment jsdom
import { describe, it, expect, beforeAll, afterEach } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import Wrapper from "./__tests__/form_element_aria_wrapper.svelte"

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

const ERROR = '"Full Name" is required'

describe("FormElement aria error wiring", () => {
  it("marks the input invalid and points it at the error text", () => {
    const { container } = render(Wrapper, {
      props: { error_message: ERROR },
    })
    const input = container.querySelector("input")
    expect(input?.getAttribute("aria-invalid")).toBe("true")
    expect(input?.getAttribute("aria-describedby")).toBe(
      "aria_test_field-error",
    )

    const described = container.querySelector("#aria_test_field-error")
    expect(described?.textContent?.trim()).toBe(ERROR)
  })

  it("emits no aria attributes when the field is valid", () => {
    const { container } = render(Wrapper, { props: { error_message: null } })
    const input = container.querySelector("input")
    expect(input?.hasAttribute("aria-invalid")).toBe(false)
    expect(input?.hasAttribute("aria-describedby")).toBe(false)
    expect(container.querySelector("#aria_test_field-error")).toBeNull()
  })

  it("keeps the error target out of the visual layout", () => {
    const { container } = render(Wrapper, { props: { error_message: ERROR } })
    expect(
      container.querySelector("#aria_test_field-error")?.className,
    ).toContain("sr-only")
  })

  it("does not change what a sighted user sees in the placeholder", () => {
    const { container } = render(Wrapper, {
      props: { error_message: ERROR, placeholder: "Your name" },
    })
    // Unchanged from before this PR: the error still takes over the placeholder.
    expect(container.querySelector("input")?.placeholder).toBe(ERROR)
  })

  it("does not hand assistive tech the same message twice on a select", () => {
    const { container } = render(Wrapper, {
      props: { inputType: "select", error_message: ERROR },
    })
    // The badge repeats the message visually; it must not also be announced.
    const badge = container.querySelector(".badge-error")
    expect(badge?.textContent?.trim()).toBe(ERROR)
    expect(badge?.getAttribute("aria-hidden")).toBe("true")

    // The exclaim InfoTooltip also holds the text, but its container is
    // display:none until hover, so it is out of the accessibility tree.
    // jsdom has no stylesheet, so exclude it by role rather than by style.
    const exposed = Array.from(container.querySelectorAll("*")).filter(
      (el) =>
        el.children.length === 0 &&
        el.textContent?.trim() === ERROR &&
        !el.closest("[aria-hidden='true']") &&
        !el.closest("[role='tooltip']"),
    )
    expect(exposed).toHaveLength(1)
    expect(exposed[0].id).toBe("aria_test_field-error")
  })

  it("wires a textarea the same way", () => {
    const { container } = render(Wrapper, {
      props: { inputType: "textarea", error_message: ERROR },
    })
    const ta = container.querySelector("textarea")
    expect(ta?.getAttribute("aria-invalid")).toBe("true")
    expect(ta?.getAttribute("aria-describedby")).toBe("aria_test_field-error")
  })

  it("wires a select the same way", () => {
    const { container } = render(Wrapper, {
      props: { inputType: "select", error_message: ERROR },
    })
    const sel = container.querySelector("select")
    expect(sel?.getAttribute("aria-invalid")).toBe("true")
    expect(sel?.getAttribute("aria-describedby")).toBe("aria_test_field-error")
  })
})
