// Turns an OpenEnv server's reset schema (Pydantic's `model_json_schema()`)
// into the subset of JSON schema Kiln's run input form reads, and checks
// saved reset arguments against it.
import type { JsonSchemaProperty } from "$lib/utils/json_schema_editor/json_schema_templates"

type JsonRecord = Record<string, unknown>

const FORM_TYPES = ["string", "number", "integer", "boolean", "object"] as const
type FormType = (typeof FORM_TYPES)[number]

// Constructs the form has no control for. Anything not listed here and not
// read below (defaults, examples, min/max, lengths, patterns) is dropped: the
// server still checks those when a run resets it.
const UNSUPPORTED_KEYS = [
  "oneOf",
  "allOf",
  "not",
  "const",
  "items",
  "prefixItems",
  "patternProperties",
  "if",
] as const

const LOCAL_REF_PREFIX = "#/$defs/"

class UnsupportedSchema extends Error {}

/**
 * An object that declares no fields and allows no others, such as Seahaven's
 * `startup` for a world with no startup keywords. Its parent leaves it out
 * when it's optional, since there's nothing in it to fill in.
 */
class NoFields extends UnsupportedSchema {}

function is_record(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function is_form_type(value: unknown): value is FormType {
  return FORM_TYPES.includes(value as FormType)
}

/** Pydantic's own field title: `clock_mode` becomes "Clock Mode". */
function title_from_key(key: string): string {
  return key
    .split("_")
    .filter((word) => word.length > 0)
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(" ")
}

function with_outer_text(
  converted: JsonSchemaProperty,
  outer: JsonRecord,
  keep_inner_title: boolean,
): JsonSchemaProperty {
  const property = { ...converted }
  if (!keep_inner_title) {
    delete property.title
  }
  if (typeof outer.title === "string") {
    property.title = outer.title
  }
  if (typeof outer.description === "string") {
    property.description = outer.description
  }
  return property
}

function is_null_schema(node: unknown): boolean {
  return (
    is_record(node) && node.type === "null" && Object.keys(node).length === 1
  )
}

/**
 * The form property for a schema node. A nullable node (`anyOf [X, null]`) becomes
 * X: the form can't send null, so it leaves an empty field out instead, and a
 * required field stays required.
 */
function convert(
  node: unknown,
  defs: JsonRecord,
  refs: string[],
): JsonSchemaProperty {
  if (!is_record(node)) {
    throw new UnsupportedSchema()
  }
  if (UNSUPPORTED_KEYS.some((key) => key in node)) {
    throw new UnsupportedSchema()
  }

  if (typeof node.$ref === "string") {
    const ref = node.$ref
    if (!ref.startsWith(LOCAL_REF_PREFIX) || refs.includes(ref)) {
      throw new UnsupportedSchema()
    }
    const name = ref.slice(LOCAL_REF_PREFIX.length)
    if (!(name in defs)) {
      throw new UnsupportedSchema()
    }
    // A definition's title is its class name, which isn't a field label.
    return with_outer_text(
      convert(defs[name], defs, [...refs, ref]),
      node,
      false,
    )
  }

  if (node.anyOf !== undefined) {
    const variants = node.anyOf
    if (!Array.isArray(variants) || variants.length !== 2) {
      throw new UnsupportedSchema()
    }
    const non_null = variants.filter((variant) => !is_null_schema(variant))
    if (non_null.length !== 1) {
      throw new UnsupportedSchema()
    }
    return with_outer_text(convert(non_null[0], defs, refs), node, true)
  }

  if (!is_form_type(node.type)) {
    throw new UnsupportedSchema()
  }
  const property: JsonSchemaProperty = { type: node.type }
  if (typeof node.title === "string") {
    property.title = node.title
  }
  if (typeof node.description === "string") {
    property.description = node.description
  }
  if (node.enum !== undefined) {
    if (!Array.isArray(node.enum) || node.enum.includes(null)) {
      throw new UnsupportedSchema()
    }
    property.enum = node.enum
  }
  if (node.type === "object") {
    Object.assign(property, convert_object(node, defs, refs))
  }
  return property
}

function convert_object(
  node: JsonRecord,
  defs: JsonRecord,
  refs: string[],
): Pick<JsonSchemaProperty, "properties" | "required"> {
  // The form shows only the declared fields of an object that allows extra
  // keys. Extra keys are entered in Raw JSON, and `kwargs_fit_form` keeps
  // arguments that have them out of the form.
  if (
    node.additionalProperties !== undefined &&
    typeof node.additionalProperties !== "boolean"
  ) {
    throw new UnsupportedSchema()
  }
  if (!is_record(node.properties)) {
    throw new UnsupportedSchema()
  }
  const declared_required = Array.isArray(node.required) ? node.required : []
  const properties: Record<string, JsonSchemaProperty> = {}
  const required: string[] = []
  for (const [key, child] of Object.entries(node.properties)) {
    let converted: JsonSchemaProperty
    try {
      converted = convert(child, defs, refs)
    } catch (e) {
      if (e instanceof NoFields && !declared_required.includes(key)) {
        continue
      }
      throw e
    }
    properties[key] = {
      ...converted,
      title: converted.title ?? title_from_key(key),
    }
    if (declared_required.includes(key)) {
      required.push(key)
    }
  }
  if (Object.keys(properties).length === 0) {
    // An object that allows extra keys is free-form JSON, which the form
    // can't show, rather than one with nothing to fill in.
    throw node.additionalProperties === true
      ? new UnsupportedSchema()
      : new NoFields()
  }
  return { properties, required }
}

// OpenEnv's base reset request declares `episode_id`, but Kiln sets it on every
// reset, so a value saved for it would be ignored.
const KILN_SET_RESET_KEYS = ["episode_id"]

function without_kiln_set_properties(
  root: JsonSchemaProperty,
): JsonSchemaProperty | null {
  const properties = Object.fromEntries(
    Object.entries(root.properties ?? {}).filter(
      ([key]) => !KILN_SET_RESET_KEYS.includes(key),
    ),
  )
  if (Object.keys(properties).length === 0) {
    return null
  }
  return {
    ...root,
    properties,
    required: (root.required ?? []).filter(
      (key) => !KILN_SET_RESET_KEYS.includes(key),
    ),
  }
}

/**
 * The run input form's schema for a reset schema, or null when the reset
 * schema uses anything the form can't show. Then the dialog keeps the JSON
 * editor.
 */
export function reset_schema_to_form_schema(
  schema: unknown,
): JsonSchemaProperty | null {
  if (!is_record(schema)) {
    return null
  }
  const defs = is_record(schema.$defs) ? schema.$defs : {}
  try {
    const property = convert(schema, defs, [])
    if (property.type !== "object") {
      return null
    }
    return without_kiln_set_properties(property)
  } catch (e) {
    if (e instanceof UnsupportedSchema) {
      return null
    }
    throw e
  }
}

export type FormFit = { fits: true } | { fits: false; reason: string }

const TYPE_NAMES: Record<FormType, string> = {
  string: "a string",
  number: "a number",
  integer: "an integer",
  boolean: "true or false",
  object: "an object",
}

function matches_type(value: unknown, type: FormType): boolean {
  switch (type) {
    case "string":
      return typeof value === "string"
    case "number":
      return typeof value === "number" && Number.isFinite(value)
    case "integer":
      return Number.isInteger(value)
    case "boolean":
      return typeof value === "boolean"
    case "object":
      return is_record(value)
  }
}

function value_misfit(
  value: unknown,
  property: JsonSchemaProperty,
  path: string,
  required: boolean,
): string | null {
  // The form can't produce null or an empty value: it leaves those fields out.
  if (value === null) {
    return `'${path}' is null`
  }
  if (!is_form_type(property.type)) {
    return `'${path}' is an unsupported type`
  }
  if (!matches_type(value, property.type)) {
    return `'${path}' isn't ${TYPE_NAMES[property.type]}`
  }
  if (value === "") {
    return `'${path}' is empty`
  }
  if (property.enum && !property.enum.includes(value as never)) {
    return `'${path}' isn't one of the options`
  }
  if (property.type === "object") {
    const misfit = object_misfit(value as JsonRecord, property, `${path}.`)
    if (misfit) {
      return misfit
    }
    // The form sends `{}` for a required object left empty, and leaves out an
    // optional one that holds nothing it would send.
    if (!required && cleaned(value, property) === undefined) {
      return `'${path}' is empty`
    }
  }
  return null
}

function object_misfit(
  value: JsonRecord,
  schema: JsonSchemaProperty,
  prefix: string,
): string | null {
  const properties = schema.properties ?? {}
  for (const [key, child] of Object.entries(value)) {
    const path = prefix + key
    const property = properties[key]
    if (!property) {
      return `unknown field '${path}'`
    }
    const misfit = value_misfit(
      child,
      property,
      path,
      schema.required?.includes(key) ?? false,
    )
    if (misfit) {
      return misfit
    }
  }
  return null
}

/**
 * Whether the form can show these reset arguments without losing any: every
 * key is a known field and every value is one the field can hold.
 */
export function kwargs_fit_form(
  kwargs: unknown,
  form_schema: JsonSchemaProperty,
): FormFit {
  if (!is_record(kwargs)) {
    return { fits: false, reason: "they aren't a JSON object" }
  }
  const kiln_set_key = KILN_SET_RESET_KEYS.find((key) => key in kwargs)
  if (kiln_set_key) {
    return {
      fits: false,
      reason: `'${kiln_set_key}' is set by Kiln on every reset`,
    }
  }
  const misfit = object_misfit(kwargs, form_schema, "")
  return misfit ? { fits: false, reason: misfit } : { fits: true }
}

/**
 * `value` with `{}` added for each required object field it leaves out. The
 * server needs the key even when all of the object's own fields are optional.
 */
function with_required_objects(
  value: JsonRecord,
  schema: JsonSchemaProperty | undefined,
): JsonRecord {
  const result = { ...value }
  for (const key of schema?.required ?? []) {
    const child = schema?.properties?.[key]
    if (child?.type === "object" && !(key in result)) {
      result[key] = with_required_objects({}, child)
    }
  }
  return result
}

function cleaned(
  value: unknown,
  schema: JsonSchemaProperty | undefined,
): unknown {
  if (value === "" || value === null || value === undefined) {
    return undefined
  }
  if (is_record(value)) {
    const entries = Object.entries(value)
      .map(
        ([key, child]) =>
          [key, cleaned(child, schema?.properties?.[key])] as const,
      )
      .filter(([, child]) => child !== undefined)
    return entries.length > 0
      ? with_required_objects(Object.fromEntries(entries), schema)
      : undefined
  }
  return value
}

/**
 * The reset arguments for a form value: empty fields are left out so the
 * server uses its defaults, and so are optional objects left with no fields.
 * A required object left with no fields is sent as `{}`.
 */
export function form_value_to_kwargs(
  value: unknown,
  form_schema: JsonSchemaProperty,
): Record<string, unknown> {
  const result = cleaned(value, form_schema)
  return with_required_objects(is_record(result) ? result : {}, form_schema)
}
