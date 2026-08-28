// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest"
import { render, cleanup, fireEvent } from "@testing-library/svelte"
import KilnProPromptsTable from "./kiln_pro_prompts_table.svelte"

// The strings this component shipped with, before items_label and
// expanded_description existed. The defaults must still produce them exactly:
// /generate renders this component with no overrides.
const SHIPPED_HEADER = "All Dataset Items (2)"
const SHIPPED_SHOW_LABEL = "Show dataset items"
const SHIPPED_HIDE_LABEL = "Hide dataset items"
const SHIPPED_DESCRIPTION =
  "Each prompt below will be used to guide one dataset sample."

afterEach(cleanup)

function setup(props: Record<string, unknown> = {}) {
  const utils = render(KilnProPromptsTable, {
    props: { prompts: ["first prompt", "second prompt"], ...props },
  })
  const toggle = utils.container.querySelector("button") as HTMLButtonElement
  return { ...utils, toggle }
}

function header_text(container: HTMLElement): string {
  return (
    container.querySelector("span.text-sm.font-medium")?.textContent?.trim() ??
    ""
  )
}

// The sentence lives in the header's own text column, alongside the title —
// scoped so the chevron's wrapper (same text classes) can't be mistaken for it.
function description_text(container: HTMLElement): string | null {
  const node = container.querySelector(
    "div.flex.flex-col.gap-2 > div.text-sm.text-gray-500",
  )
  return node ? node.textContent?.trim() ?? "" : null
}

describe("KilnProPromptsTable defaults", () => {
  it("renders the shipped header and toggle label", () => {
    const { container, toggle } = setup()
    expect(header_text(container)).toBe(SHIPPED_HEADER)
    expect(toggle.getAttribute("aria-label")).toBe(SHIPPED_SHOW_LABEL)
    expect(toggle.getAttribute("aria-expanded")).toBe("false")
  })

  it("renders the shipped description once expanded", async () => {
    const { container, toggle } = setup()
    expect(description_text(container)).toBeNull()
    await fireEvent.click(toggle)
    expect(description_text(container)).toBe(SHIPPED_DESCRIPTION)
    expect(toggle.getAttribute("aria-label")).toBe(SHIPPED_HIDE_LABEL)
    expect(toggle.getAttribute("aria-expanded")).toBe("true")
  })
})

describe("items_label", () => {
  it("drives the header and the aria-label from the one noun", async () => {
    // The point of a single prop: a screen reader can never announce a
    // different noun than the one on screen.
    const { container, toggle } = setup({ items_label: "Items" })
    expect(header_text(container)).toBe("All Items (2)")
    expect(toggle.getAttribute("aria-label")).toBe("Show items")
    await fireEvent.click(toggle)
    expect(toggle.getAttribute("aria-label")).toBe("Hide items")
  })

  it("lowercases a multi-word noun for the aria-label only", () => {
    const { container, toggle } = setup({ items_label: "Test Inputs" })
    expect(header_text(container)).toBe("All Test Inputs (2)")
    expect(toggle.getAttribute("aria-label")).toBe("Show test inputs")
  })
})

describe("expanded_description", () => {
  it("renders a caller's sentence in place of the default", async () => {
    const { container, toggle } = setup({
      expanded_description: "One line per test conversation.",
    })
    await fireEvent.click(toggle)
    expect(description_text(container)).toBe("One line per test conversation.")
  })

  it("renders no description at all when false", async () => {
    const { container, toggle } = setup({ expanded_description: false })
    await fireEvent.click(toggle)
    expect(description_text(container)).toBeNull()
    // The rows still expand — false suppresses the sentence, not the table.
    expect(container.textContent).toContain("first prompt")
  })
})
