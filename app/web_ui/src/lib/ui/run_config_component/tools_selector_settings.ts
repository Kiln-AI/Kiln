export interface ToolsSelectorSettings {
  mandatory_tools: string[] | null
  description: string | undefined
  hide_info_description: boolean
  hide_create_kiln_task_tool_button: boolean
  disabled: boolean
  empty_label: string | undefined
  single_select: boolean
}
