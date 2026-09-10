import { describe, it, expect } from "vitest"
import {
  parse_reference_data,
  parse_reference_keys,
} from "./reference_data_input"

describe("parse_reference_data", () => {
  it("treats blank input as valid with no data", () => {
    expect(parse_reference_data("")).toEqual({ ok: true, data: null })
    expect(parse_reference_data("   ")).toEqual({ ok: true, data: null })
  })

  it("parses a JSON object", () => {
    expect(parse_reference_data('{"a": 1, "b": "x"}')).toEqual({
      ok: true,
      data: { a: 1, b: "x" },
    })
  })

  it("rejects non-object JSON", () => {
    for (const input of ["null", "[1,2]", '"str"', "42"]) {
      const result = parse_reference_data(input)
      expect(result.ok).toBe(false)
      if (!result.ok) {
        expect(result.error).toContain("must be a JSON object")
      }
    }
  })

  it("rejects invalid JSON", () => {
    const result = parse_reference_data("{not json")
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.error).toContain("valid JSON")
    }
  })
})

describe("parse_reference_keys", () => {
  it("returns top-level keys for a valid object", () => {
    expect(parse_reference_keys('{"a": 1, "b": 2}')).toEqual(["a", "b"])
  })

  it("returns no keys for blank, invalid, or non-object input", () => {
    expect(parse_reference_keys("")).toEqual([])
    expect(parse_reference_keys("[1]")).toEqual([])
    expect(parse_reference_keys("{bad")).toEqual([])
  })
})
