import { describe, it, expect } from "vitest"
import {
  form_value_to_kwargs,
  kwargs_fit_form,
  reset_schema_to_form_schema,
} from "./openenv_reset_schema"
import type { JsonSchemaProperty } from "$lib/utils/json_schema_editor/json_schema_templates"

// The shape of the `reset` key Seahaven serves at /schema, trimmed to one of each construct.
const SEAHAVEN_RESET_SCHEMA = {
  $defs: {
    Startup: {
      additionalProperties: true,
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
      required: ["seed", "company"],
    })
  })

  it("keeps a required object whose fields are all optional", () => {
    const schema = {
      $defs: {
        Config: object_schema({ level: { type: "integer" } }),
      },
      ...(object_schema({ cfg: { $ref: "#/$defs/Config" } }) as object),
      required: ["cfg"],
    }
    expect(reset_schema_to_form_schema(schema)).toEqual({
      type: "object",
      properties: {
        cfg: {
          type: "object",
          title: "Cfg",
          properties: { level: { type: "integer", title: "Level" } },
          required: [],
        },
      },
      required: ["cfg"],
    })
  })

  it("leaves out an optional object with no fields", () => {
    // Seahaven's `startup` for a world with no startup keywords.
    const schema = {
      $defs: {
        SeahavenStartup: {
          additionalProperties: false,
          properties: {},
          title: "SeahavenStartup",
          type: "object",
        },
      },
      ...(object_schema({
        fixture: {
          anyOf: [
            { enum: ["empty", "small"], type: "string" },
            { type: "null" },
          ],
          title: "Fixture",
        },
        startup: {
          anyOf: [{ $ref: "#/$defs/SeahavenStartup" }, { type: "null" }],
          default: null,
        },
        nested: object_schema({ empty: object_schema({}) }),
      }) as object),
    }
    expect(reset_schema_to_form_schema(schema)).toEqual({
      type: "object",
      properties: {
        fixture: { type: "string", title: "Fixture", enum: ["empty", "small"] },
      },
      required: [],
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
      "a free-form object that allows extra keys",
      object_schema({ a: { type: "object", additionalProperties: true } }),
    ],
    [
      "additional properties with a schema",
      object_schema({
        a: {
          type: "object",
          properties: { b: { type: "string" } },
          additionalProperties: { type: "string" },
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
    [
      "a free-form object with no declared fields",
      object_schema({
        a: { type: "object", properties: {}, additionalProperties: true },
      }),
    ],
    [
      "a required object with no fields",
      {
        ...(object_schema({ a: object_schema({}) }) as object),
        required: ["a"],
      },
    ],
    ["a root with no properties", { type: "object" }],
    ["a root with empty properties", object_schema({})],
    [
      "a root whose only field has no fields",
      object_schema({ a: object_schema({}) }),
    ],
    ["a field that isn't a schema", object_schema({ a: true })],
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

describe("reset_schema_to_form_schema errors", () => {
  it("throws an error that isn't about the schema's shape", () => {
    const schema = {
      type: "object",
      get properties(): unknown {
        throw new Error("read failed")
      },
    }
    expect(() => reset_schema_to_form_schema(schema)).toThrow("read failed")
  })
})

const FORM_SCHEMA = reset_schema_to_form_schema(
  SEAHAVEN_RESET_SCHEMA,
) as JsonSchemaProperty

// A required object whose fields are all optional, inside an optional object.
const REQUIRED_OBJECT_FORM_SCHEMA: JsonSchemaProperty = {
  type: "object",
  properties: {
    cfg: {
      type: "object",
      properties: { level: { type: "integer" } },
      required: [],
    },
    extra: {
      type: "object",
      properties: {
        name: { type: "string" },
        inner: {
          type: "object",
          properties: { flag: { type: "boolean" } },
          required: [],
        },
      },
      required: ["inner"],
    },
  },
  required: ["cfg"],
}

describe("kwargs_fit_form", () => {
  it.each([
    ["empty", {}],
    ["a string and an enum", { company: "acme", fixture: "beta" }],
    ["an integer", { seed: 3 }],
    ["a nested object", { startup: { acting_user: "sam" } }],
  ])("fits %s", (_, kwargs) => {
    expect(kwargs_fit_form(kwargs, FORM_SCHEMA)).toEqual({ fits: true })
  })

  const NUMBER_AND_FLAG_SCHEMA: JsonSchemaProperty = {
    type: "object",
    properties: { ratio: { type: "number" }, flag: { type: "boolean" } },
    required: [],
  }

  it("fits a number and a boolean", () => {
    expect(
      kwargs_fit_form({ ratio: 0.5, flag: false }, NUMBER_AND_FLAG_SCHEMA),
    ).toEqual({ fits: true })
  })

  it.each([
    ["a string for a number", { ratio: "0.5" }, "'ratio' isn't a number"],
    ["infinity for a number", { ratio: Infinity }, "'ratio' isn't a number"],
    ["a string for a boolean", { flag: "true" }, "'flag' isn't true or false"],
  ])("doesn't fit %s", (_, kwargs, reason) => {
    expect(kwargs_fit_form(kwargs, NUMBER_AND_FLAG_SCHEMA)).toEqual({
      fits: false,
      reason,
    })
  })

  it("doesn't fit a field whose type the form has no control for", () => {
    const schema = {
      type: "object",
      properties: { tags: { type: "array" } },
      required: [],
    } as unknown as JsonSchemaProperty
    expect(kwargs_fit_form({ tags: ["a"] }, schema)).toEqual({
      fits: false,
      reason: "'tags' is an unsupported type",
    })
  })

  it("fits an empty required object", () => {
    expect(
      kwargs_fit_form(
        { cfg: {}, extra: { name: "x", inner: {} } },
        REQUIRED_OBJECT_FORM_SCHEMA,
      ),
    ).toEqual({ fits: true })
  })

  it.each([
    ["an unknown key", { foo: 1 }, "unknown field 'foo'"],
    [
      "an extra key in an object that allows extra keys",
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
      form_value_to_kwargs(
        {
          company: "acme",
          fixture: "",
          seed: 0,
          flag: false,
          missing: undefined,
          gone: null,
          startup: { acting_user: "" },
          nested: { keep: { me: 1 }, drop: { x: "" } },
        },
        FORM_SCHEMA,
      ),
    ).toEqual({
      company: "acme",
      seed: 0,
      flag: false,
      nested: { keep: { me: 1 } },
    })
  })

  it("is an empty object for an empty form", () => {
    expect(form_value_to_kwargs({ company: "" }, FORM_SCHEMA)).toEqual({})
    expect(form_value_to_kwargs(undefined, FORM_SCHEMA)).toEqual({})
  })

  it("sends a required object left empty as {}", () => {
    expect(
      form_value_to_kwargs(
        { cfg: { level: undefined }, extra: { name: "", inner: {} } },
        REQUIRED_OBJECT_FORM_SCHEMA,
      ),
    ).toEqual({ cfg: {} })
  })

  it("adds a required object inside an optional object that's kept", () => {
    expect(
      form_value_to_kwargs(
        { cfg: { level: 2 }, extra: { name: "x", inner: { flag: undefined } } },
        REQUIRED_OBJECT_FORM_SCHEMA,
      ),
    ).toEqual({ cfg: { level: 2 }, extra: { name: "x", inner: {} } })
  })
})
