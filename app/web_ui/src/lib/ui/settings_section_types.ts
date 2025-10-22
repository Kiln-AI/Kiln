// Type definitions for settings section components

export interface SettingsItem {
  type: "settings"
  name: string
  description: string
  button_text: string
  href?: string
  on_click?: () => void
  is_external?: boolean
  badge_text?: string
}

export interface EvalTemplateItem {
  type: "eval_template"
  id: string
  name: string
  description: string
  recommended?: boolean
  highlight_title?: string
  on_select: () => void
}

export type SettingsSectionItem = SettingsItem | EvalTemplateItem
