function is_empty(value: unknown): boolean {
  console.log("is_empty value", value)
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
  console.log("value", value)
  if (!optional && is_empty(value)) {
    return '"' + label + '" is required'
  } else if (optional && is_empty(value)) {
    console.log("optional and empty")
    return null
  }

  let numValue: number

  if (typeof value === "string") {
    numValue = parseFloat(value)
    if (isNaN(numValue)) {
      console.log("is not a number")
      return "Please enter a valid number"
    }
    if (integer && !Number.isInteger(numValue)) {
      return `${label} must be an integer`
    }
  } else if (typeof value === "number") {
    numValue = value
  } else {
    console.log("is not a number")
    return "Please enter a valid number"
  }

  if (min !== undefined && numValue < min) {
    console.log("is less than min")
    return `${label} must be greater than ${min}`
  }
  if (max !== undefined && numValue > max) {
    console.log("is greater than max")
    return `${label} must be less than ${max}`
  }

  console.log("is valid")
  return null
}

export function number_validator({
  min,
  max,
  integer,
  label,
  optional,
}: NumberValidatorOptions): (value: unknown) => string | null {
  return (value: unknown) => {
    const result = validate_number(value, {
      min,
      max,
      integer,
      label,
      optional,
    })
    console.log("result", result)
    return result
  }
}
