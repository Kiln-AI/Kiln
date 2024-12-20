// A type for a button which can appear on an app page
export type ActionButton = {
  label?: string
  icon?: string
  handler?: () => void
  href?: string
  primary?: boolean
  notice?: boolean
  shortcut?: string
  disabled?: boolean
}
