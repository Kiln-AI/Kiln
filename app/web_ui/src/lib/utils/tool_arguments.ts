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
      type: typeof schema.type === "string" ? schema.type : "Unknown",
      description:
        typeof schema.description === "string" ? schema.description : null,
      is_required: required.includes(name),
    })
  }
  return args
}
