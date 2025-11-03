export type UiProperty = {
  name: string
  value: string | number | string[]
  tooltip?: string
  link?: string // Not supported for value type string[]
  links?: (string | null)[] // Only supported for type string[]
  error?: boolean
  warn_icon?: boolean
  badge?: boolean
  onClick?: () => void // If provided, clicking will call this instead of navigating. Takes precedence over link.
}
