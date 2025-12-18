export type UiProperty = {
  name: string
  value: string | number | string[]
  tooltip?: string
  link?: string // Not supported for value type string[]
  links?: (string | null)[] // Only supported for type string[]
  error?: boolean
  warn_icon?: boolean
  badge?: boolean
  value_with_link?: {
    prefix: string
    link_text: string
    link: string
  }

  // If true, the PropertyList component must have a "custom_value" slot defined.
  // Falls back to displaying the value if the slot is not provided.
  use_custom_slot?: boolean
}
