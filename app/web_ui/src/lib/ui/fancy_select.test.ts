// @vitest-environment jsdom
import { describe, it, expect, vi, beforeAll } from "vitest"
import { render } from "@testing-library/svelte"
import type { OptionGroup } from "./fancy_select_types"

vi.mock("$app/navigation", () => ({ goto: vi.fn() }))

const FancySelect = (await import("./fancy_select.svelte")).default

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

const options: OptionGroup[] = [
  {
    options: [
      { label: "Search", value: "search" },
      { label: "Fetch", value: "fetch" },
    ],
  },
]

function label_for(
  props: { selected: unknown } & Record<string, unknown>,
): string {
  const { container } = render(FancySelect, {
    props: { options, empty_label: "None", ...props },
  })
  return container.querySelector("span.truncate")?.textContent?.trim() ?? ""
}

const name_unlisted = (value: unknown) =>
  value === "unlisted_tool" ? "Unlisted Tool" : null

describe("FancySelect selected label", () => {
  it("shows empty_label for an unlisted value by default", () => {
    expect(
      label_for({ multi_select: true, selected: ["search", "unlisted_tool"] }),
    ).toBe("2 Selected: Search, None")
  })

  it("names unlisted values with unlisted_value_label in a multi select", () => {
    expect(
      label_for({
        multi_select: true,
        selected: ["search", "unlisted_tool", "other"],
        unlisted_value_label: name_unlisted,
      }),
    ).toBe("3 Selected: Search, Unlisted Tool, None")
  })

  it("names a lone unlisted value", () => {
    expect(
      label_for({
        multi_select: true,
        selected: ["unlisted_tool"],
        unlisted_value_label: name_unlisted,
      }),
    ).toBe("Unlisted Tool")
    expect(
      label_for({
        selected: "unlisted_tool",
        unlisted_value_label: name_unlisted,
      }),
    ).toBe("Unlisted Tool")
  })

  it("still shows empty_label when nothing is selected", () => {
    expect(
      label_for({
        multi_select: true,
        selected: [],
        unlisted_value_label: name_unlisted,
      }),
    ).toBe("None")
  })
})
