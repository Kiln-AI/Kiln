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
  // When true, tools that are only meaningful inside a code judge (e.g. the
  // llm_judge built-in) are offered in the picker. Off by default so those
  // tools are hidden everywhere except the code-eval allowlist context.
  code_eval_context: boolean
}
