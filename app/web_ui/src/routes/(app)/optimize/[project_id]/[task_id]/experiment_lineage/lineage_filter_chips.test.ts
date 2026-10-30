// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest"
import { cleanup, fireEvent, render } from "@testing-library/svelte"
import type { FilterKey } from "$lib/utils/lineage/lineage_graph"
import FilterChipsHarness from "./__tests__/filter_chips_harness.svelte"

const COUNTS: Record<FilterKey, number> = {
  prompt: 31,
  tools: 25,
  skills: 12,
  model: 112,
  settings: 41,
  copy: 26,
}

afterEach(cleanup)

function chips(container: HTMLElement): HTMLButtonElement[] {
  return [...container.querySelectorAll<HTMLButtonElement>("[aria-pressed]")]
}

function clear_button(container: HTMLElement): HTMLButtonElement | null {
  return (
    [...container.querySelectorAll("button")].find(
      (button) => button.textContent?.trim() === "Clear",
    ) ?? null
  )
}

describe("LineageFilterChips", () => {
  it("renders six chips with their labels and counts, in order", () => {
    const { container } = render(FilterChipsHarness, {
      props: { counts: COUNTS, active: new Set<FilterKey>() },
    })
    expect(
      chips(container).map((chip) =>
        chip.textContent?.replace(/\s+/g, " ").trim(),
      ),
    ).toEqual([
      "Prompt 31",
      "Tools 25",
      "Skills 12",
      "Model 112",
      "Settings 41",
      "Copy or re-run 26",
    ])
    expect(container.textContent).toContain("Changed from parent")
  })

  it("starts with every chip off and no Clear link", () => {
    const { container } = render(FilterChipsHarness, {
      props: { counts: COUNTS, active: new Set<FilterKey>() },
    })
    for (const chip of chips(container)) {
      expect(chip.getAttribute("aria-pressed")).toBe("false")
      expect(chip.className).toContain("btn-outline")
    }
    expect(clear_button(container)).toBeNull()
  })

  it("toggles a chip and the bound set", async () => {
    const { container, component } = render(FilterChipsHarness, {
      props: { counts: COUNTS, active: new Set<FilterKey>() },
    })
    const tools = chips(container)[1]
    await fireEvent.click(tools)
    expect(tools.getAttribute("aria-pressed")).toBe("true")
    expect(tools.className).toContain("btn-secondary")
    expect([...component.active]).toEqual(["tools"])

    await fireEvent.click(tools)
    expect(tools.getAttribute("aria-pressed")).toBe("false")
    expect([...component.active]).toEqual([])
  })

  it("keeps several chips on at once", async () => {
    const { container, component } = render(FilterChipsHarness, {
      props: { counts: COUNTS, active: new Set<FilterKey>() },
    })
    await fireEvent.click(chips(container)[0])
    await fireEvent.click(chips(container)[5])
    expect([...component.active].sort()).toEqual(["copy", "prompt"])
  })

  it("shows Clear while a chip is on, and Clear turns every chip off", async () => {
    const { container, component } = render(FilterChipsHarness, {
      props: { counts: COUNTS, active: new Set<FilterKey>(["model", "copy"]) },
    })
    const clear = clear_button(container)
    expect(clear).not.toBeNull()
    await fireEvent.click(clear as HTMLButtonElement)
    expect(component.active.size).toBe(0)
    expect(clear_button(container)).toBeNull()
    for (const chip of chips(container)) {
      expect(chip.getAttribute("aria-pressed")).toBe("false")
    }
  })
})
