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
