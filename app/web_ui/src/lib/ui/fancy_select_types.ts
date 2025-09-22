export type OptionGroup = {
  label?: string
  options: Option[]
}
export type Option = {
  label: string
  value: unknown
  description?: string
  badge?: string
  // Defaults to ghost if not specified
  badge_color?: "primary"
  disabled?: boolean
}
