export function is_empty(value: unknown): boolean {
  if (value === null || value === undefined) {
    return true
  }
  if (typeof value === "string") {
    return value.trim() === ""
  }
  return false
}

export interface NumberValidatorOptions {
  min?: number
  max?: number
  integer?: boolean
  label: string
  optional?: boolean
}

export function validate_number(
  value: unknown,
  { min, max, integer, label, optional }: NumberValidatorOptions,
): string | null {
  if (!optional && is_empty(value)) {
    return '"' + label + '" is required'
  } else if (optional && is_empty(value)) {
    return null
  }

  let numValue: number

  if (typeof value === "string") {
    numValue = parseFloat(value)
    if (isNaN(numValue)) {
      return "Please enter a valid number"
    }
    if (integer && !Number.isInteger(numValue)) {
      return `${label} must be an integer`
    }
  } else if (typeof value === "number") {
    numValue = value
  } else {
    return "Please enter a valid number"
  }

  if (min !== undefined && numValue < min) {
    return `${label} must be greater than ${min}`
  }
  if (max !== undefined && numValue > max) {
    return `${label} must be less than ${max}`
  }

  return null
}

export function number_validator({
  min,
  max,
  integer,
  label,
  optional,
}: NumberValidatorOptions): (value: unknown) => string | null {
  return (value: unknown) =>
    validate_number(value, {
      min,
      max,
      integer,
      label,
      optional,
    })
}

// Important: if updating this, also update the corresponding validator in the backend datamodel/basemodel.py
// This mirrors the name_validator and string_to_valid_name functions
export function filename_string_validator(
  value: unknown,
  min_length: number = 1,
  max_length: number = 120,
): string | null {
  if (is_empty(value)) {
    return "Cannot be empty"
  }

  if (typeof value !== "string") {
    return "Must be a string"
  }

  const name = value

  // Check length
  if (name.length < min_length) {
    return `Must be at least ${min_length} character${min_length > 1 ? "s" : ""} long`
  }

  if (name.length > max_length) {
    return `Must be at most ${max_length} characters long`
  }

  // Check for forbidden characters: / \ ? % * : | " < > . , ; = newline
  // ref: https://en.wikipedia.org/wiki/Filename#Problematic_characters
  const forbidden_chars_regex = /[/\\?%*:|"<>.,;=\n]/
  if (forbidden_chars_regex.test(name)) {
    return 'Cannot contain any of these characters: / \\ ? % * : | " < > . , ; = or newlines'
  }

  // Check for leading/trailing whitespace or underscores
  if (name !== name.trim()) {
    return "Cannot have leading or trailing whitespace"
  }
  if (name.startsWith("_") || name.endsWith("_")) {
    return "Cannot start or end with an underscore"
  }

  // Check for consecutive whitespace
  if (/\s\s+/.test(name)) {
    return "Cannot contain consecutive whitespace"
  }

  // Check for consecutive underscores
  if (name.includes("__")) {
    return "Cannot contain consecutive underscores"
  }

  return null
}

// FilenameStringShort validator (max 32 characters) - used for eval score names, task requirement names
export const filename_string_short_validator: (
  value: unknown,
) => string | null = (value: unknown) => {
  return filename_string_validator(value, 1, 32)
}

// FilenameString validator (max 120 characters) - used for task names, eval names, etc
export const filename_string_validator_default: (
  value: unknown,
) => string | null = (value: unknown) => {
  return filename_string_validator(value, 1, 120)
}

// Important: if updating this, also update the corresponding validator in the backend utils/validation.py
export const tool_name_validator: (value: unknown) => string | null = (
  value: unknown,
) => {
  if (is_empty(value)) {
    return "Cannot be empty"
  }

  if (typeof value !== "string") {
    return "Must be a string"
  }

  const name = value

  // Check if name contains only lowercase letters, numbers, and underscores
  const snake_case_regex = /^[a-z0-9_]+$/
  if (!snake_case_regex.test(name)) {
    return "Must be in snake_case: containing only lowercase letters (a-z), numbers (0-9), and underscores"
  }

  // Check that it doesn't start or end with underscore
  if (name.startsWith("_") || name.endsWith("_")) {
    return "Cannot start or end with an underscore"
  }

  // Check that it doesn't have consecutive underscores
  if (name.includes("__")) {
    return "Cannot contain consecutive underscores"
  }

  // Check that it starts with a letter (good snake_case practice)
  if (!/^[a-z]/.test(name)) {
    return "Must start with a lowercase letter"
  }

  // Check length
  if (name.length > 64) {
    return "Must be less than 65 characters long"
  }

  return null
}
