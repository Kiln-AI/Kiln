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
  // Shows the description in full, in a monospace font with its line breaks
  // and indentation kept, e.g. formatted JSON. Defaults to a clamped
  // three-line description.
  description_preformatted?: boolean
  disabled?: boolean
  hide_check?: boolean
}

export function description_layout_class(option: Option): string {
  return option.description_preformatted
    ? "font-mono whitespace-pre-wrap break-words"
    : "line-clamp-3 whitespace-pre-line"
}
