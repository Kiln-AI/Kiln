export type OptionGroup = {
  label?: string
  options: Option[]
  action_label?: string
  action_handler?: () => void
}
export type Option = {
  label: string
  value: unknown
  description?: string
  badge?: string
  // Defaults to ghost if not specified
  badge_color?: "primary"
  // "below" renders the badge on its own row under the label instead of beside
  // it — for long badges (e.g. function names) that would cramp the label.
  // Defaults to inline.
  badge_placement?: "below"
  disabled?: boolean
  hide_check?: boolean
}
