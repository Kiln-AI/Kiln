// Type definitions for Kiln section components

import type { EvalTemplateId } from "$lib/types"

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
  id:
    | EvalTemplateId
    | "none"
    | "kiln_requirements_preview"
    | "kiln_issue_preview"
    | "tool_call_preview"
    | "search_tool_reference_answer"
  name: string
  description: string
  recommended?: boolean
  highlight_title?: string
  on_select: () => void
}

export type KilnSectionItem = SettingsItem | EvalTemplateItem
