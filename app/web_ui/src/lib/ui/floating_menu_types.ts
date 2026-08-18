export type FloatingMenuItem = {
  label: string
  // Optional second line, for menus where the label alone isn't enough.
  description?: string
  href?: string
  target?: string
  rel?: string
  onclick?: () => void
  hidden?: boolean
  header?: boolean
}
