import type { SandboxCodeContext } from "$lib/stores/tools_store"

export interface ToolsSelectorSettings {
  mandatory_tools: string[] | null
  description: string | undefined
  info_description: string | undefined
  hide_info_description: boolean
  hide_create_kiln_task_tool_button: boolean
  disabled: boolean
  empty_label: string | undefined
  single_select: boolean
  optional: boolean
  // Which sandboxed-code allowlist this picker edits, if any. Governs whether the
  // sandbox-only built-ins (`llm`, `llm_judge`) are offered. "none" by default, so
  // they stay out of every picker that is not editing such an allowlist.
  sandbox_code_context: SandboxCodeContext
}
