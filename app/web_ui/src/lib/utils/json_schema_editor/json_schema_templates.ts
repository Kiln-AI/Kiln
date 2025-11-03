import { KilnError } from "../error_handlers"

// Definition of a JSON schema: https://json-schema.org/
// Only supporting "object" type at top level for now
// TODO: why have this? root is just another property
export type JsonSchema = {
  type: "object"
  properties: Record<string, JsonSchemaProperty>
  required: string[]
  additionalProperties?: boolean
}

// Definition of a JSON schema: https://json-schema.org/
export type JsonSchemaProperty = {
  title?: string
  description?: string
  type: "number" | "string" | "integer" | "boolean" | "array" | "object"
  items?: JsonSchemaProperty // Format for elements of an array, only set for arrays
  properties?: Record<string, JsonSchemaProperty> // only set for objects
  required?: string[] // only set for objects
  additionalProperties?: boolean // only set for objects
}

// We have our own model type for using in Svelte.
// Actual JSON schema is too hard to work with in Svelte. It uses dicts, so order would keep moving around as keys change.
export type SchemaModelProperty = {
  id: string
  title: string
  description?: string
  type: "number" | "string" | "integer" | "boolean" | "array" | "object"
  required: boolean
  items?: SchemaModelProperty // only set for arrays
  properties?: Array<SchemaModelProperty> // only set for objects
  additionalProperties?: boolean // only set for objects
}

/*export type SchemaModel = {
  properties: SchemaModelProperty[]
  additionalProperties?: boolean
}*/

export function model_from_schema(s: JsonSchemaProperty): SchemaModelProperty {
  let schema = build_schema_model_property("root", s, s.required ?? [])
  // Root is always required even though spec doesn't say so
  schema.required = true
  return schema
}

function build_schema_model_property(
  id: string,
  options: JsonSchemaProperty,
  required: string[],
): SchemaModelProperty {
  const result: SchemaModelProperty = {
    id,
    title: options.title || id,
    description: options.description,
    type: options.type,
    required: !!required.includes(id),
  }

  if (options.type === "array" && options.items) {
    // TODO why empty array
    result.items = build_schema_model_property("items", options.items, [])
  }

  if (options.type === "object" && options.properties) {
    const nestedRequired = options.required ?? []
    result.properties = Object.entries(options.properties).map(
      ([nestedId, nestedOptions]) =>
        build_schema_model_property(nestedId, nestedOptions, nestedRequired),
    )
  }
  if (options.type === "object") {
    // json schema spec defaults to true if not specified
    result.additionalProperties = options.additionalProperties ?? true
  }
  return result
}

export function model_from_schema_string(s: string): SchemaModelProperty {
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
  m: SchemaModelProperty,
  creating: boolean,
): JsonSchemaProperty {
  let result: JsonSchemaProperty = {
    type: m.type,
  }

  if (m.type === "object" && m.properties) {
    const properties: Record<string, JsonSchemaProperty> = {}
    const required: string[] = []
    for (let i = 0; i < m.properties.length; i++) {
      const prop = m.properties[i]
      const key = validate_and_get_key(prop.title, prop.id, creating)
      properties[key] = build_json_schema_property(prop, creating)
      if (prop.required) {
        required.push(key)
      }
    }
    result.properties = properties
    result.required = required
    result.additionalProperties = m.additionalProperties
  }
  if (m.type === "array" && m.items) {
    result.items = build_json_schema_property(m.items, creating)
  }

  return result
}

function validate_and_get_key(
  title: string,
  id: string,
  creating: boolean,
): string {
  if (!title) {
    throw new KilnError("Property is empty. Please provide a name.", null)
  }
  const safe_name = string_to_json_key(title)
  if (!safe_name) {
    throw new KilnError(
      "Property name only contains special characters. Must be alphanumeric. Provided name with issues: " +
        title,
      null,
    )
  }
  // When creating a new model, we want to infer the id from the title.
  // When using an existing model, we want to use the id provided, even if title has changed.
  return creating ? safe_name : id || safe_name
}

function build_json_schema_property(
  prop: SchemaModelProperty,
  creating: boolean,
): JsonSchemaProperty {
  const result: JsonSchemaProperty = {
    title: prop.title,
    type: prop.type,
    description: prop.description,
  }

  if (prop.type === "array" && prop.items) {
    result.items = build_json_schema_property(prop.items, creating)
  }

  if (prop.type === "object" && prop.properties) {
    result.properties = {}
    result.required = []
    for (const nestedProp of prop.properties) {
      const key = validate_and_get_key(
        nestedProp.title,
        nestedProp.id,
        creating,
      )
      result.properties[key] = build_json_schema_property(nestedProp, creating)
      if (nestedProp.required) {
        result.required.push(key)
      }
    }
  }

  if (prop.type === "object") {
    result.additionalProperties = prop.additionalProperties
  }

  return result
}

export function empty_schema_model(): SchemaModelProperty {
  return {
    type: "object",
    id: "root",
    title: "root",
    required: true,
    properties: [],
    additionalProperties: true,
  }
}

export const empty_schema: JsonSchemaProperty = schema_from_model(
  empty_schema_model(),
  true,
)

export function example_schema_model(): SchemaModelProperty {
  return {
    properties: [
      // @ts-expect-error we're not using the id, because we want it to be generated from the title
      {
        title: "Example Property",
        description: "Replace this with your own property",
        type: "string",
        required: true,
      },
    ],
  }
}
