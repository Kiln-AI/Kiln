import { describe, it, expect } from "vitest"
import { format_tool_arguments } from "./tool_arguments"

describe("format_tool_arguments", () => {
  it("lists each argument with its type, description and whether it's required", () => {
    expect(
      format_tool_arguments({
        type: "object",
        properties: {
          item_id: { type: "string", description: "The item to update." },
          limit: { type: "integer" },
        },
        required: ["item_id"],
      }),
    ).toEqual([
      {
        name: "item_id",
        type: "string",
        description: "The item to update.",
        is_required: true,
      },
      { name: "limit", type: "integer", description: null, is_required: false },
    ])
  })

  it("marks an argument with no string type as Unknown", () => {
    expect(
      format_tool_arguments({ properties: { value: { type: ["string"] } } }),
    ).toEqual([
      { name: "value", type: "Unknown", description: null, is_required: false },
    ])
  })

  it("skips properties whose schema isn't an object", () => {
    expect(
      format_tool_arguments({
        properties: { bad: true, ok: { type: "string" } },
      }),
    ).toEqual([
      { name: "ok", type: "string", description: null, is_required: false },
    ])
  })

  it.each([undefined, null, {}, { properties: [] }, "schema"])(
    "returns no arguments for a schema without properties: %s",
    (schema) => {
      expect(format_tool_arguments(schema)).toEqual([])
    },
  )
})
