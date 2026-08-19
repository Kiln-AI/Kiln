import type { Option, OptionGroup } from "$lib/ui/fancy_select_types"
import type {
  ToolApiDescription,
  ToolSetApiDescription,
  ToolSetType,
} from "$lib/types"
import {
  is_tool_selectable_in_context,
  type SandboxCodeContext,
} from "$lib/stores/tools_store"

// The order tool sets are shown in, shared by every picker so the same project's
// tools read the same way wherever they are offered. Skills are excluded: they get
// their own picker (skills_selector.svelte), and a picker that wants them says so
// with its own set_order.
export const AGENT_TOOL_SET_ORDER: ToolSetType[] = [
  "builtin",
  "sandbox_code",
  "code",
  "search",
  "kiln_task",
  "mcp",
  "demo",
]

// What an option's value carries. Pickers that configure which tools something may
// call select the tool itself ("id"). Pickers that match tool calls in a trace
// select the OpenAI-compatible function name the trace records ("function_name"),
// which can differ from the tool's display name in Kiln.
export type ToolOptionValueField = "id" | "function_name"

// An extra affordance on a tool set's group, e.g. "Create New" on Kiln tasks.
export type ToolOptionGroupAction = {
  action_label: string
  action_handler: () => void
  // Label for a placeholder group shown when the project has tools, but none of
  // this set type. Without it the affordance would disappear exactly when it is
  // most useful.
  empty_group_label?: string
}

export type BuildToolOptionGroupsArgs = {
  value_field?: ToolOptionValueField
  // Which sandboxed-code allowlist the picker edits, if any. Governs whether the
  // sandbox-only built-ins are offered. Defaults to "none" — an agent-tool picker.
  sandbox_code_context?: SandboxCodeContext
  set_order?: ToolSetType[]
  // Marks options the caller has locked, e.g. mandatory tools.
  option_disabled?: (
    tool: ToolApiDescription,
    tool_set: ToolSetApiDescription,
  ) => boolean
  group_action?: (
    tool_set_type: ToolSetType,
  ) => ToolOptionGroupAction | undefined
}

// Tool sets holding at least one tool the given context allows, in the order the
// server returned them. This is what "does this project have any tools?" means to a
// picker: judging it on the raw response would never see "no tools" again, because
// the sandbox-only built-ins ship with every project.
export function selectable_tool_sets(
  tool_sets: ToolSetApiDescription[] | undefined,
  sandbox_code_context: SandboxCodeContext = "none",
): ToolSetApiDescription[] {
  return (tool_sets ?? [])
    .map((tool_set) => ({
      ...tool_set,
      tools: tool_set.tools.filter((tool) =>
        is_tool_selectable_in_context(
          tool.id,
          tool_set.type,
          sandbox_code_context,
        ),
      ),
    }))
    .filter((tool_set) => tool_set.tools.length > 0)
}

function tool_option(
  tool: ToolApiDescription,
  tool_set: ToolSetApiDescription,
  value_field: ToolOptionValueField,
  option_disabled: BuildToolOptionGroupsArgs["option_disabled"],
): Option {
  const function_name = tool.function_name ?? tool.name
  const description = tool.description?.trim()
  return {
    value: value_field === "function_name" ? function_name : tool.id,
    label: tool.name,
    description: description ? description : undefined,
    // Only when the selected value isn't already the label: repeating the name as a
    // badge is noise, but a function name that differs from the display name is the
    // value being picked, and has to be visible.
    badge:
      value_field === "function_name" && function_name !== tool.name
        ? function_name
        : undefined,
    disabled: option_disabled ? option_disabled(tool, tool_set) : false,
  }
}

// The canonical dropdown contents for a project's tools: one group per tool set, in
// set order, labelled by tool name and subtitled by the tool's own description.
// Every tool picker builds its options from here so they stay consistent; callers
// layer their own extras (custom values, pseudo-options) on the result.
//
// Returns no groups at all when the project has nothing this context can select,
// which is what a picker's empty state keys on.
export function build_tool_option_groups(
  tool_sets: ToolSetApiDescription[] | undefined,
  {
    value_field = "id",
    sandbox_code_context = "none",
    set_order = AGENT_TOOL_SET_ORDER,
    option_disabled,
    group_action,
  }: BuildToolOptionGroupsArgs = {},
): OptionGroup[] {
  const selectable = selectable_tool_sets(tool_sets, sandbox_code_context)
  if (selectable.length === 0) {
    // Nothing to offer: the caller shows its empty state rather than a lone action.
    return []
  }

  const groups: OptionGroup[] = []
  for (const set_type of set_order) {
    const action = group_action ? group_action(set_type) : undefined
    const sets_of_type = selectable.filter(
      (tool_set) => tool_set.type === set_type,
    )

    if (sets_of_type.length === 0) {
      if (action?.empty_group_label) {
        groups.push({
          label: action.empty_group_label,
          options: [],
          action_label: action.action_label,
          action_handler: action.action_handler,
        })
      }
      continue
    }

    for (const tool_set of sets_of_type) {
      groups.push({
        label: tool_set.set_name,
        options: tool_set.tools.map((tool) =>
          tool_option(tool, tool_set, value_field, option_disabled),
        ),
        action_label: action?.action_label,
        action_handler: action?.action_handler,
      })
    }
  }
  return groups
}
