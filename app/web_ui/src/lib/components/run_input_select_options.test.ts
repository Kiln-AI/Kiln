import { describe, it, expect } from "vitest"
import { NOT_SET_LABEL, enum_select_options } from "./run_input_select_options"

describe("enum_select_options", () => {
  it("leads an optional enum with Not Set", () => {
    const [group] = enum_select_options(["acme", "beta"], true)
    expect(group.options.map((o) => o.label)).toEqual([
      NOT_SET_LABEL,
      "acme",
      "beta",
    ])
    expect(group.options[0].value).toBeUndefined()
  })

  it("lists Not Set last for a required enum", () => {
    const [group] = enum_select_options(["acme", "beta"], false)
    expect(group.options.map((o) => o.label)).toEqual([
      "acme",
      "beta",
      NOT_SET_LABEL,
    ])
  })

  it("keeps raw enum values and labels null", () => {
    const [group] = enum_select_options([1, null], false)
    expect(group.options.slice(0, 2)).toEqual([
      { label: "1", value: 1 },
      { label: "null", value: null },
    ])
  })
})
