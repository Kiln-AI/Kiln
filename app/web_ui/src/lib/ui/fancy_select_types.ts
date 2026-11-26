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

/**
 * An option's description as the menu shows it. Descriptions can come from
 * someone else's docstrings, with blank lines between paragraphs. The menu
 * keeps line breaks but clamps to three lines, so a blank line would use up
 * one of them and could leave the clamp's "…" on an empty line.
 */
export function option_description_for_display(description: string): string {
  return description.replace(/\n[ \t]*(?:\n[ \t]*)+/g, "\n").trim()
}
