import { describe, it, expect } from "vitest"
import {
  RESET_ARGUMENTS_INVALID_JSON,
  RESET_ARGUMENTS_NOT_OBJECT,
  format_reset_arguments,
  parse_reset_arguments,
} from "./openenv"

describe("format_reset_arguments", () => {
  it("formats over several lines with a 2-space indent", () => {
    expect(format_reset_arguments({ fixture: "acme", user: { id: 7 } })).toBe(
      '{\n  "fixture": "acme",\n  "user": {\n    "id": 7\n  }\n}',
    )
  })

  it("shows missing arguments as an empty object", () => {
    expect(format_reset_arguments(undefined)).toBe("{}")
    expect(format_reset_arguments(null)).toBe("{}")
    expect(format_reset_arguments({})).toBe("{}")
  })
})

describe("parse_reset_arguments", () => {
  it("parses a JSON object", () => {
    expect(parse_reset_arguments('{"fixture": "acme", "seed": 3}')).toEqual({
      reset_kwargs: { fixture: "acme", seed: 3 },
      error: null,
    })
  })

  it("treats an empty object and blank text as no arguments", () => {
    expect(parse_reset_arguments("{}")).toEqual({
      reset_kwargs: {},
      error: null,
    })
    expect(parse_reset_arguments("  \n ")).toEqual({
      reset_kwargs: {},
      error: null,
    })
  })

  it("rejects invalid JSON", () => {
    expect(parse_reset_arguments('{"fixture": ')).toEqual({
      reset_kwargs: null,
      error: RESET_ARGUMENTS_INVALID_JSON,
    })
  })

  it.each(['["acme", "tech"]', '"acme"', "3", "null", "true"])(
    "rejects JSON that isn't an object: %s",
    (text) => {
      expect(parse_reset_arguments(text)).toEqual({
        reset_kwargs: null,
        error: RESET_ARGUMENTS_NOT_OBJECT,
      })
    },
  )

  it("round-trips formatted arguments", () => {
    const kwargs = { fixture: "beta", role: "tech", flags: [1, 2] }
    expect(parse_reset_arguments(format_reset_arguments(kwargs))).toEqual({
      reset_kwargs: kwargs,
      error: null,
    })
  })
})
