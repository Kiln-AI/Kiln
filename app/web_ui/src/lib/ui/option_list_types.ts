import type { ComponentType } from "svelte"

export type OptionListTag = {
  label: string
  // "beta" gives the tag a primary (blue) outline, "default" is a plain gray outline.
  tone?: "default" | "beta"
}

export type OptionListItem = {
  id: string
  name: string
  description: string
  // Optional icon component rendered inside the colored square. Should be an
  // SVG that uses `currentColor` so it inherits the icon color.
  icon?: ComponentType
  recommended?: boolean
  tags?: OptionListTag[]
  disabled?: boolean
}
