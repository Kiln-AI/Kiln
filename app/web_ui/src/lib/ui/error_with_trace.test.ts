// @vitest-environment jsdom
import { describe, it, expect, beforeAll } from "vitest"
import { render } from "@testing-library/svelte"
import ErrorWithTrace from "./error_with_trace.svelte"
import type { ErrorWithTrace as ErrorWithTraceType, Trace } from "$lib/types"

// jsdom does not implement ResizeObserver. output.svelte (used via
// ErrorDetailsBlock) constructs one on mount, so we polyfill it with a no-op
// before any component renders.
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

const SAMPLE_TRACE: Trace = [
  { role: "system", content: "You are a helpful assistant." },
  { role: "user", content: "hello" },
]

function makeError(
  overrides: Partial<ErrorWithTraceType> = {},
): ErrorWithTraceType {
  return {
    message: "Something went wrong",
    error_type: "RuntimeError",
    trace: null,
    ...overrides,
  }
}

describe("ErrorWithTrace component", () => {
  it("renders trace and error block when trace is present and non-empty", () => {
    const error = makeError({
      trace: SAMPLE_TRACE as ErrorWithTraceType["trace"],
    })
    const { container } = render(ErrorWithTrace, {
      props: { error },
    })
    // Trace component renders a collapse wrapper per message
    const collapseElements = container.querySelectorAll(".collapse")
    expect(collapseElements.length).toBe(SAMPLE_TRACE.length)
    // Error block is present too
    expect(container.textContent).toContain("Error")
    expect(container.textContent).toContain("Something went wrong")
  })

  it("hides trace section when trace is null", () => {
    const error = makeError({ trace: null })
    const { container } = render(ErrorWithTrace, {
      props: { error },
    })
    expect(container.querySelectorAll(".collapse").length).toBe(0)
    expect(container.textContent).toContain("Something went wrong")
  })

  it("hides trace section when trace is an empty array", () => {
    const error = makeError({ trace: [] })
    const { container } = render(ErrorWithTrace, {
      props: { error },
    })
    expect(container.querySelectorAll(".collapse").length).toBe(0)
    expect(container.textContent).toContain("Something went wrong")
  })

  it("passes troubleshooting_steps through to ErrorDetailsBlock", () => {
    const error = makeError()
    const steps = ["Check your network", "Try again in a minute"]
    const { container } = render(ErrorWithTrace, {
      props: { error, troubleshooting_steps: steps },
    })
    expect(container.textContent).toContain("Troubleshooting Steps")
    for (const step of steps) {
      expect(container.textContent).toContain(step)
    }
    // Each step should be a list item
    const listItems = container.querySelectorAll("ol > li")
    expect(listItems.length).toBe(steps.length)
  })

  it("omits troubleshooting section when no steps are provided", () => {
    const error = makeError()
    const { container } = render(ErrorWithTrace, {
      props: { error },
    })
    expect(container.textContent).not.toContain("Troubleshooting Steps")
  })

  it("uses custom error_title when provided", () => {
    const error = makeError()
    const { container } = render(ErrorWithTrace, {
      props: { error, error_title: "Run Failed" },
    })
    expect(container.textContent).toContain("Run Failed")
  })

  it("defaults error_title to 'Error' when omitted", () => {
    const error = makeError()
    const { container } = render(ErrorWithTrace, {
      props: { error },
    })
    const title = container.querySelector(".text-error")
    expect(title?.textContent?.trim()).toBe("Error")
  })

  it("renders error.message inside the error block", () => {
    const error = makeError({ message: "Rate limit exceeded. Try again." })
    const { container } = render(ErrorWithTrace, {
      props: { error },
    })
    expect(container.textContent).toContain("Error Details")
    expect(container.textContent).toContain("Rate limit exceeded. Try again.")
  })
})
