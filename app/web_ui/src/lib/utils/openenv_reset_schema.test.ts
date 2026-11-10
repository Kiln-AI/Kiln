import { describe, it, expect } from "vitest"
import {
  form_value_to_kwargs,
  kwargs_fit_form,
  reset_schema_to_form_schema,
} from "./openenv_reset_schema"
import type { JsonSchemaProperty } from "$lib/utils/json_schema_editor/json_schema_templates"

// The shape Seahaven serves at /seahaven/schemas, trimmed to one of each construct.
const SEAHAVEN_RESET_SCHEMA = {
  $defs: {
    Startup: {
      additionalProperties: false,
      properties: {
        acting_user: {
          anyOf: [{ type: "string" }, { type: "null" }],
          default: null,
          title: "Acting User",
        },
      },
      title: "Startup",
      type: "object",
    },
    ClockMode: { enum: ["fixed", "tick"], title: "ClockMode", type: "string" },
  },
  additionalProperties: false,
  properties: {
    fixture: {
      anyOf: [{ enum: ["acme", "beta"], type: "string" }, { type: "null" }],
      default: null,
      description: "The fixture to start from, by id.",
      title: "Fixture",
    },
    startup: {
      anyOf: [{ $ref: "#/$defs/Startup" }, { type: "null" }],
      default: null,
      description: "The world's own startup keywords.",
    },
    seed: {
      anyOf: [{ minimum: 0, type: "integer" }, { type: "null" }],
      default: null,
      title: "Seed",
    },
    clock_mode: { $ref: "#/$defs/ClockMode" },
    company: { type: "string", title: "Company" },
    episode_id: {
      anyOf: [{ maxLength: 255, type: "string" }, { type: "null" }],
      default: null,
      title: "Episode Id",
    },
  },
  required: ["company", "seed"],
  title: "SeahavenResetRequest",
  type: "object",
}

function object_schema(properties: Record<string, unknown>): unknown {
  return { type: "object", properties }
}

describe("reset_schema_to_form_schema", () => {
  it("converts the Seahaven reset schema shape", () => {
    expect(reset_schema_to_form_schema(SEAHAVEN_RESET_SCHEMA)).toEqual({
      type: "object",
      title: "SeahavenResetRequest",
      properties: {
        fixture: {
          type: "string",
          title: "Fixture",
          description: "The fixture to start from, by id.",
          enum: ["acme", "beta"],
        },
        startup: {
          type: "object",
          title: "Startup",
          description: "The world's own startup keywords.",
          properties: {
            acting_user: { type: "string", title: "Acting User" },
          },
          required: [],
        },
        seed: { type: "integer", title: "Seed" },
        clock_mode: {
          type: "string",
          title: "Clock Mode",
          enum: ["fixed", "tick"],
        },
        company: { type: "string", title: "Company" },
      },
      required: ["company"],
    })
  })

  it.each([
    [
      "another anyOf",
      object_schema({
        a: { anyOf: [{ type: "string" }, { type: "integer" }] },
      }),
    ],
    [
      "an anyOf of three",
      object_schema({
        a: {
          anyOf: [{ type: "string" }, { type: "integer" }, { type: "null" }],
        },
      }),
    ],
    ["oneOf", object_schema({ a: { oneOf: [{ type: "string" }] } })],
    ["allOf", object_schema({ a: { allOf: [{ type: "string" }] } })],
    ["const", object_schema({ a: { type: "string", const: "x" } })],
    ["a type list", object_schema({ a: { type: ["string", "null"] } })],
    ["no type", object_schema({ a: { title: "A" } })],
    ["an array", object_schema({ a: { type: "array", items: {} } })],
    ["a free-form object", object_schema({ a: { type: "object" } })],
    [
      "additional properties",
      object_schema({
        a: {
          type: "object",
          properties: { b: { type: "string" } },
          additionalProperties: true,
        },
      }),
    ],
    [
      "a null enum value",
      object_schema({ a: { type: "string", enum: [null] } }),
    ],
    ["a missing ref", object_schema({ a: { $ref: "#/$defs/Missing" } })],
    ["a remote ref", object_schema({ a: { $ref: "other.json#/x" } })],
    [
      "a cyclic ref",
      {
        $defs: {
          Node: {
            type: "object",
            properties: { child: { $ref: "#/$defs/Node" } },
          },
        },
        ...(object_schema({ root: { $ref: "#/$defs/Node" } }) as object),
      },
    ],
    ["a non-object root", { type: "string" }],
    ["a root with no properties", { type: "object" }],
    ["not an object", "schema"],
    ["null", null],
    [
      "a schema whose only field Kiln sets",
      object_schema({ episode_id: { type: "string" } }),
    ],
  ])("returns null for %s", (_, schema) => {
    expect(reset_schema_to_form_schema(schema)).toBeNull()
  })
})

const FORM_SCHEMA = reset_schema_to_form_schema(
  SEAHAVEN_RESET_SCHEMA,
) as JsonSchemaProperty

describe("kwargs_fit_form", () => {
  it.each([
    ["empty", {}],
    ["a string and an enum", { company: "acme", fixture: "beta" }],
    ["an integer", { seed: 3 }],
    ["a nested object", { startup: { acting_user: "sam" } }],
  ])("fits %s", (_, kwargs) => {
    expect(kwargs_fit_form(kwargs, FORM_SCHEMA)).toEqual({ fits: true })
  })

  it.each([
    ["an unknown key", { foo: 1 }, "unknown field 'foo'"],
    [
      "an unknown nested key",
      { startup: { foo: 1 } },
      "unknown field 'startup.foo'",
    ],
    ["a wrong type", { company: 3 }, "'company' isn't a string"],
    ["a non-integer", { seed: 1.5 }, "'seed' isn't an integer"],
    [
      "an enum miss",
      { fixture: "other" },
      "'fixture' isn't one of the options",
    ],
    ["null", { fixture: null }, "'fixture' is null"],
    ["an empty string", { company: "" }, "'company' is empty"],
    ["an empty object", { startup: {} }, "'startup' is empty"],
    ["an array for an object", { startup: [] }, "'startup' isn't an object"],
    ["a non-object", [1], "they aren't a JSON object"],
    [
      "an episode_id, which Kiln sets",
      { company: "acme", episode_id: "ep_1" },
      "'episode_id' is set by Kiln on every reset",
    ],
  ])("doesn't fit %s", (_, kwargs, reason) => {
    expect(kwargs_fit_form(kwargs, FORM_SCHEMA)).toEqual({
      fits: false,
      reason,
    })
  })
})

describe("form_value_to_kwargs", () => {
  it("leaves out empty values and objects left empty", () => {
    expect(
      form_value_to_kwargs({
        company: "acme",
        fixture: "",
        seed: 0,
        flag: false,
        missing: undefined,
        gone: null,
        startup: { acting_user: "" },
        nested: { keep: { me: 1 }, drop: { x: "" } },
      }),
    ).toEqual({
      company: "acme",
      seed: 0,
      flag: false,
      nested: { keep: { me: 1 } },
    })
  })

  it("is an empty object for an empty form", () => {
    expect(form_value_to_kwargs({ company: "" })).toEqual({})
    expect(form_value_to_kwargs(undefined)).toEqual({})
  })
})
