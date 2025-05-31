import { KilnError } from "../error_handlers"
import { _ } from "svelte-i18n"
import { get } from "svelte/store"

export type JsonSchema = {
  type: "object"
  properties: Record<string, JsonSchemaProperty>
  required: string[]
}

export type JsonSchemaProperty = {
  title: string
  description: string
  type: "number" | "string" | "integer" | "boolean" | "array" | "object"
  items?: JsonSchemaProperty | JsonSchema
}

// We have our own model type.
// Actual JSON schema is too hard to work with in Svelte. It uses dicts, so order would keep moving around as keys change.
export type SchemaModelProperty = {
  id: string
  title: string
  description: string
  type: "number" | "string" | "integer" | "boolean" | "array" | "object"
  required: boolean
}

export type SchemaModel = {
  properties: SchemaModelProperty[]
}

export function model_from_schema(s: JsonSchema): SchemaModel {
  return {
    properties: Object.entries(s.properties).map(([id, options]) => ({
      id,
      title: options.title || id,
      description: options.description,
      type: options.type,
      required: !!s.required.includes(id),
    })),
  }
}

export function model_from_schema_string(s: string): SchemaModel {
  return model_from_schema(JSON.parse(s))
}

export function string_to_json_key(s: string): string {
  return s
    .trim()
    .toLowerCase()
    .replace(/ /g, "_")
    .replace(/[^a-z0-9_.]/g, "")
}

export function schema_from_model(
  m: SchemaModel,
  creating: boolean,
): JsonSchema {
  const properties: Record<string, JsonSchemaProperty> = {}
  const required: string[] = []
  for (let i = 0; i < m.properties.length; i++) {
    const title = m.properties[i].title
    if (!title) {
      throw new KilnError(get(_)("json_schema.errors.property_empty"), null)
    }
    const safe_name = string_to_json_key(m.properties[i].title)
    if (!safe_name) {
      throw new KilnError(
        get(_)("json_schema.errors.property_special_chars", {
          values: { name: m.properties[i].title },
        }),
        null,
      )
    }
    // When creating a new model, we want to infer the id from the title.
    // When using an existing model, we want to use the id provided, even if title has changed.
    const key = creating ? safe_name : m.properties[i].id || safe_name
    properties[key] = {
      title: m.properties[i].title,
      type: m.properties[i].type,
      description: m.properties[i].description,
    }
    if (m.properties[i].required) {
      required.push(key)
    }
  }
  return {
    type: "object",
    properties: properties,
    required: required,
  }
}

export function empty_schema_model(): SchemaModel {
  return {
    properties: [],
  }
}

export const empty_schema: JsonSchema = schema_from_model(
  empty_schema_model(),
  true,
)

export function example_schema_model(): SchemaModel {
  return {
    properties: [
      // @ts-expect-error we're not using the id, because we want it to be generated from the title
      {
        title: get(_)("json_schema.errors.example_property_title"),
        description: get(_)("json_schema.errors.example_property_description"),
        type: "string",
        required: true,
      },
    ],
  }
}

export function typed_json_from_schema_model(
  m: SchemaModel,
  data: Record<string, string>,
): Record<string, unknown> {
  const parsed_data: Record<string, unknown> = {}
  const errors: string[] = []
  for (const [prop_id, prop_value] of Object.entries(data)) {
    const property = m.properties.find((p) => p.id === prop_id)
    if (!property) {
      throw new KilnError(
        get(_)("json_schema.errors.property_not_allowed", {
          values: { property: prop_id },
        }),
        null,
      )
    }
    if (property.type === "string") {
      parsed_data[prop_id] = prop_value
    } else if (prop_value === "") {
      // JS parsing is too flexible. Empty string is not always an error.
      errors.push(
        get(_)("json_schema.errors.empty_string_non_string", {
          values: { property: prop_id },
        }),
      )
    } else if (property.type === "number") {
      parsed_data[prop_id] = Number(prop_value)
    } else if (property.type === "boolean") {
      if (prop_value !== "true" && prop_value !== "false") {
        errors.push(
          get(_)("json_schema.errors.boolean_invalid", {
            values: { property: prop_id },
          }),
        )
      }
      parsed_data[prop_id] = prop_value === "true"
    } else if (property.type === "integer") {
      const parsedValue = Number(prop_value)
      if (!Number.isInteger(parsedValue)) {
        errors.push(
          get(_)("json_schema.errors.integer_invalid", {
            values: { property: prop_id, value: prop_value },
          }),
        )
      }
      parsed_data[prop_id] = parsedValue
    } else if (property.type === "array") {
      try {
        const parsed_value = JSON.parse(prop_value)
        if (!Array.isArray(parsed_value)) {
          errors.push(
            get(_)("json_schema.errors.array_invalid", {
              values: { property: prop_id, value: prop_value },
            }),
          )
        }
        parsed_data[prop_id] = parsed_value
      } catch (e) {
        errors.push(
          get(_)("json_schema.errors.array_json_invalid", {
            values: { property: prop_id, value: prop_value },
          }),
        )
      }
    } else if (property.type === "object") {
      try {
        const parsed_value = JSON.parse(prop_value)
        // Check if it's an object but not an array, null, or other primitive
        if (
          typeof parsed_value !== "object" ||
          parsed_value === null ||
          Array.isArray(parsed_value)
        ) {
          errors.push(
            get(_)("json_schema.errors.object_invalid", {
              values: { property: prop_id, value: prop_value },
            }),
          )
        }
        parsed_data[prop_id] = parsed_value
      } catch (e) {
        errors.push(
          get(_)("json_schema.errors.object_json_invalid", {
            values: { property: prop_id, value: prop_value },
          }),
        )
      }
    } else {
      errors.push(
        get(_)("json_schema.errors.unsupported_type", {
          values: { type: property.type, property: property.id },
        }),
      )
    }
  }
  for (const model_prop of m.properties) {
    if (
      model_prop.required &&
      (parsed_data[model_prop.id] === undefined ||
        parsed_data[model_prop.id] === "")
    ) {
      errors.push(
        get(_)("json_schema.errors.required_property_missing", {
          values: { property: model_prop.id },
        }),
      )
    }
  }
  if (errors.length > 0) {
    throw new KilnError(
      get(_)("json_schema.errors.schema_validation_failed"),
      errors,
    )
  }
  return parsed_data
}
