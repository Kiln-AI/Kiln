export interface ToolArgument {
  name: string
  type: string
  description: string | null
  is_required: boolean
}

function is_object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
}

function is_string_array(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string")
}

function schema_types(schema: Record<string, unknown>): string[] {
  if (typeof schema.type === "string") {
    return [schema.type]
  }
  if (is_string_array(schema.type)) {
    return schema.type
  }
  const branches = schema.anyOf ?? schema.oneOf
  if (Array.isArray(branches)) {
    return branches.filter(is_object).flatMap(schema_types)
  }
  return []
}

/**
 * The argument's type, such as "string" or "string | integer". "null" is left
 * out: schemas for optional arguments (Pydantic's `X | None = None`) allow null,
 * and the Optional badge already says the argument can be left out.
 */
function argument_type(schema: Record<string, unknown>): string {
  const types = [...new Set(schema_types(schema))].filter((t) => t !== "null")
  return types.length > 0 ? types.join(" | ") : "Unknown"
}

/** The top-level arguments of a tool's JSON schema, in schema order. */
export function format_tool_arguments(input_schema: unknown): ToolArgument[] {
  if (!is_object(input_schema) || !is_object(input_schema.properties)) {
    return []
  }
  const required = is_string_array(input_schema.required)
    ? input_schema.required
    : []
  const args: ToolArgument[] = []
  for (const [name, schema] of Object.entries(input_schema.properties)) {
    if (!is_object(schema)) {
      continue
    }
    args.push({
      name,
      type: argument_type(schema),
      description:
        typeof schema.description === "string" ? schema.description : null,
      is_required: required.includes(name),
    })
  }
  return args
}
