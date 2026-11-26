import type { SchemaModelProperty } from "$lib/utils/json_schema_editor/json_schema_templates"

/** What a scalar field of the run input form holds for a JSON value. */
export function field_value_from_json(
  property: SchemaModelProperty,
  value: unknown,
): string {
  if (value === undefined || value === null) {
    return ""
  }
  if (property.enum) {
    // FancySelect matches options by the raw enum value, which may not be a string.
    return value as string
  }
  if (property.type === "boolean") {
    return typeof value === "boolean" ? String(value) : ""
  }
  if (property.type === "object") {
    return JSON.stringify(value, null, 2)
  }
  return String(value)
}

/** One key of a JSON object, or undefined when the value isn't an object. */
export function json_property(value: unknown, key: string): unknown {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return undefined
  }
  return (value as Record<string, unknown>)[key]
}
