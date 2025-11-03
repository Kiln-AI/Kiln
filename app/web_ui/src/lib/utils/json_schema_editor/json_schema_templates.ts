import { KilnError } from "../error_handlers"

// Definition of a JSON schema: https://json-schema.org/
// Only supporting "object" type at top level for now
export type JsonSchema = {
  type: "object"
  properties: Record<string, JsonSchemaProperty>
  required: string[]
  additionalProperties?: boolean
}

// Definition of a JSON schema: https://json-schema.org/
export type JsonSchemaProperty = {
  title: string
  description: string
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
  description: string
  type: "number" | "string" | "integer" | "boolean" | "array" | "object"
  required: boolean
  items?: SchemaModelProperty // only set for arrays
  properties?: Array<SchemaModelProperty> // only set for objects
  additionalProperties?: boolean // only set for objects
}

export type SchemaModel = {
  properties: SchemaModelProperty[]
  additionalProperties?: boolean
}

export function model_from_schema(s: JsonSchema): SchemaModel {
  return {
    properties: Object.entries(s.properties).map(([id, options]) =>
      build_schema_model_property(id, options, s.required),
    ),
    additionalProperties: s.additionalProperties ?? true, // json schema spec defaults to true if not specified
  }
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
    const prop = m.properties[i]
    const key = validate_and_get_key(prop.title, prop.id, creating)
    properties[key] = build_json_schema_property(prop, creating)
    if (prop.required) {
      required.push(key)
    }
  }
  return {
    type: "object",
    properties: properties,
    required: required,
    additionalProperties: m.additionalProperties,
  }
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
        title: "Example Property",
        description: "Replace this with your own property",
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
        "Property not allowed in JSON schema: " + prop_id,
        null,
      )
    }
    if (property.type === "string") {
      parsed_data[prop_id] = prop_value
    } else if (prop_value === "") {
      // JS parsing is too flexible. Empty string is not always an error.
      errors.push("Empty string provided for non-string property: " + prop_id)
    } else if (property.type === "number") {
      parsed_data[prop_id] = Number(prop_value)
    } else if (property.type === "boolean") {
      if (prop_value !== "true" && prop_value !== "false") {
        errors.push("Boolean property must be 'true' or 'false': " + prop_id)
      }
      parsed_data[prop_id] = prop_value === "true"
    } else if (property.type === "integer") {
      const parsedValue = Number(prop_value)
      if (!Number.isInteger(parsedValue)) {
        errors.push(
          `Property ${prop_id} must be an integer, got: ${prop_value}`,
        )
      }
      parsed_data[prop_id] = parsedValue
    } else if (property.type === "array") {
      try {
        const parsed_value = JSON.parse(prop_value)
        if (!Array.isArray(parsed_value)) {
          errors.push(
            `Property ${prop_id} must be an array, got: ${prop_value}`,
          )
        }
        parsed_data[prop_id] = parsed_value
      } catch (e) {
        errors.push(
          `Property ${prop_id} must be a valid JSON array, got: ${prop_value}`,
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
            `Property ${prop_id} must be a valid JSON object, got: ${prop_value}`,
          )
        }
        parsed_data[prop_id] = parsed_value
      } catch (e) {
        errors.push(
          `Property ${prop_id} must be a valid JSON object, got: ${prop_value}`,
        )
      }
    } else {
      errors.push(
        "Unsupported property type: " +
          property.type +
          "for property " +
          property.id +
          ". This may be supported by the python framework, but is not yet supported in the UI.",
      )
    }
  }
  for (const model_prop of m.properties) {
    if (
      model_prop.required &&
      (parsed_data[model_prop.id] === undefined ||
        parsed_data[model_prop.id] === "")
    ) {
      errors.push("Required property not provided: " + model_prop.id)
    }
  }
  if (errors.length > 0) {
    throw new KilnError(
      "The data did not match the required JSON schema.",
      errors,
    )
  }
  return parsed_data
}
