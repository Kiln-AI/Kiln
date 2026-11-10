import { describe, it, expect } from "vitest"
import { description_layout_class } from "./fancy_select_types"

describe("description_layout_class", () => {
  it("clamps a plain description to three lines", () => {
    expect(
      description_layout_class({ label: "Acme", value: "a", description: "x" }),
    ).toBe("line-clamp-3 whitespace-pre-line")
  })

  it("shows a preformatted description in full, in monospace", () => {
    const layout = description_layout_class({
      label: "Acme",
      value: "a",
      description: "x",
      description_preformatted: true,
    })
    expect(layout).toBe("font-mono whitespace-pre-wrap break-words")
    expect(layout).not.toContain("line-clamp")
  })
})
