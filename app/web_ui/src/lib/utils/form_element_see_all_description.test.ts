// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, cleanup, fireEvent, waitFor } from "@testing-library/svelte"

// ClampedText measures its text from onMount.
vi.mock("svelte", async (importOriginal) =>
  (await import("$lib/test_support/browser_svelte")).browser_svelte(
    importOriginal,
  ),
)

const FormElement = (await import("./form_element.svelte")).default

const LONG = "A description the schema's author wrote at length. ".repeat(20)

// jsdom has no layout, so every element measures 0 tall. ClampedText shows See
// all only when its text is taller than its box, so the tests that need it
// stub the two heights it compares.
function stub_overflow(overflowing: boolean) {
  vi.spyOn(Element.prototype, "scrollHeight", "get").mockReturnValue(
    overflowing ? 200 : 40,
  )
  vi.spyOn(Element.prototype, "clientHeight", "get").mockReturnValue(40)
}

function see_all(container: HTMLElement) {
  return Array.from(container.querySelectorAll("button")).find(
    (b) => b.textContent?.trim() === "See all",
  )
}

// jsdom has no ResizeObserver. This one measures once, when observing
// starts, which is all ClampedText needs to decide on See all.
class MeasureOnceResizeObserver {
  constructor(private callback: () => void) {}
  observe() {
    this.callback()
  }
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", MeasureOnceResizeObserver)
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe("FormElement on_see_all_description", () => {
  it("shows the whole description, with no See all, when it isn't set", () => {
    stub_overflow(true)
    const { container } = render(FormElement, {
      props: { id: "field", label: "Seed", value: "", description: LONG },
    })
    expect(container.querySelector("label")?.textContent).toContain(LONG.trim())
    expect(container.querySelector("pre")).toBeNull()
    expect(see_all(container)).toBeUndefined()
  })

  it("cuts a long description to three lines, and See all passes it on in full", async () => {
    stub_overflow(true)
    const on_see_all_description = vi.fn()
    const { container } = render(FormElement, {
      props: {
        id: "field",
        label: "Seed",
        value: "",
        description: LONG,
        on_see_all_description,
      },
    })
    const text = container.querySelector("pre")
    expect(text?.getAttribute("style")).toContain("-webkit-line-clamp: 3")

    await waitFor(() => expect(see_all(container)).toBeDefined())
    await fireEvent.click(see_all(container)!)
    expect(on_see_all_description).toHaveBeenCalledWith("Seed", LONG)
  })

  it("has no See all when the description fits", () => {
    stub_overflow(false)
    const { container } = render(FormElement, {
      props: {
        id: "field",
        label: "Seed",
        value: "",
        description: "Random seed.",
        on_see_all_description: vi.fn(),
      },
    })
    expect(container.querySelector("pre")?.textContent).toBe("Random seed.")
    expect(see_all(container)).toBeUndefined()
  })
})
