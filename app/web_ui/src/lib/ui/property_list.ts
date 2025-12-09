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
}
