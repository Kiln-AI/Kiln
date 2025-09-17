function is_empty(value: unknown): boolean {
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

  return null
}
