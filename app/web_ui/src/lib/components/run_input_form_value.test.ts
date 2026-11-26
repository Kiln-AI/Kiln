import { describe, it, expect } from "vitest"
import { field_value_from_json, json_property } from "./run_input_form_value"
import type { SchemaModelProperty } from "$lib/utils/json_schema_editor/json_schema_templates"

function field(
  type: SchemaModelProperty["type"],
  extra: Partial<SchemaModelProperty> = {},
): SchemaModelProperty {
  return { id: "f", title: "F", type, required: false, ...extra }
}

describe("field_value_from_json", () => {
  it.each([
    ["no value", field("string"), undefined, ""],
    ["null", field("string"), null, ""],
    ["a string", field("string"), "acme", "acme"],
    ["a number", field("number"), 1.5, "1.5"],
    ["an integer", field("integer"), 0, "0"],
    ["true", field("boolean"), true, "true"],
    ["false", field("boolean"), false, "false"],
    ["a non-boolean for a boolean", field("boolean"), "yes", ""],
    ["a JSON object", field("object"), { a: 1 }, '{\n  "a": 1\n}'],
  ])("gives %s", (_, property, value, expected) => {
    expect(field_value_from_json(property, value)).toBe(expected)
  })

  it("keeps an enum value as it is, so the dropdown matches it", () => {
    expect(field_value_from_json(field("integer", { enum: [1, 2] }), 2)).toBe(2)
  })
})

describe("json_property", () => {
  it("reads a key of an object", () => {
    expect(json_property({ a: { b: 1 } }, "a")).toEqual({ b: 1 })
  })

  it.each([undefined, null, [1], "text"])("is undefined for %s", (value) => {
    expect(json_property(value, "a")).toBeUndefined()
  })
})
