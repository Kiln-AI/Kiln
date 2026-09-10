import type { Option, OptionGroup } from "$lib/ui/fancy_select_types"
import type {
  ToolApiDescription,
  ToolSetApiDescription,
  ToolSetType,
} from "$lib/types"
import {
  duplicate_tool_names,
  is_tool_selectable_in_context,
  tool_display_name,
  type SandboxCodeContext,
} from "$lib/stores/tools_store"

// Where each tool set type sits in a picker, lowest first, with null for a type no
// agent picker offers by default: skills get their own picker
// (skills_selector.svelte), and a picker that wants them says so with its own
// set_order.
//
// Exhaustive on purpose. Anything a picker does not order is dropped silently, so a
// ToolSetType added server-side has to be a type error here rather than a tool set
// that quietly stops appearing anywhere in the app.
const AGENT_TOOL_SET_RANK: Record<ToolSetType, number | null> = {
  builtin: 0,
  sandbox_code: 1,
  code: 2,
  search: 3,
  kiln_task: 4,
  mcp: 5,
  demo: 6,
  skill: null,
}

// The order tool sets are shown in, shared by every picker so the same project's
// tools read the same way wherever they are offered.
export const AGENT_TOOL_SET_ORDER: ToolSetType[] = (
  Object.entries(AGENT_TOOL_SET_RANK) as [ToolSetType, number | null][]
)
  .filter((entry): entry is [ToolSetType, number] => entry[1] !== null)
  .sort(([, a], [, b]) => a - b)
  .map(([set_type]) => set_type)

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
  duplicate_names: Set<string>,
  option_disabled: BuildToolOptionGroupsArgs["option_disabled"],
): Option {
  const function_name = tool.function_name ?? tool.name
  const description = tool.description?.trim()
  return {
    value: value_field === "function_name" ? function_name : tool.id,
    label: tool_display_name(tool, duplicate_names),
    description: description ? description : undefined,
    // Only when it differs from the label: repeating the name as a badge is noise,
    // but a function name that differs from the display name is what the model
    // actually calls, and has to be visible. Function names are long, so the
    // badge goes under the label rather than cramping it.
    badge: function_name !== tool.name ? function_name : undefined,
    badge_placement: "below",
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

  // Counted over the sets this picker actually renders -- context-filtered and in
  // its set order -- because a collision the user cannot see is not one worth
  // qualifying. Only for an id-valued picker: a "function_name" picker selects the
  // name a trace records, and colliding tools genuinely share that one value, so
  // telling those options apart would promise a choice that does not exist.
  const rendered = selectable.filter((tool_set) =>
    set_order.includes(tool_set.type),
  )
  const duplicate_names =
    value_field === "id" ? duplicate_tool_names(rendered) : new Set<string>()

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
          tool_option(
            tool,
            tool_set,
            value_field,
            duplicate_names,
            option_disabled,
          ),
        ),
        action_label: action?.action_label,
        action_handler: action?.action_handler,
      })
    }
  }

  // Colliding tools share one function name, so a "function_name" picker would
  // otherwise offer several rows carrying the same value: FancySelect check-marks
  // every option matching the selection and labels the closed picker from the
  // first match, making the extra rows unselectable duplicates. One row per value
  // is the honest offer.
  return value_field === "function_name"
    ? dedupe_options_by_value(groups)
    : groups
}

// Keeps the first option carrying each value, and drops a group left with nothing
// to show rather than rendering a bare header.
function dedupe_options_by_value(groups: OptionGroup[]): OptionGroup[] {
  const seen = new Set<unknown>()
  return groups
    .map((group) => ({
      ...group,
      options: group.options.filter((option) => {
        if (seen.has(option.value)) {
          return false
        }
        seen.add(option.value)
        return true
      }),
    }))
    .filter((group) => group.options.length > 0 || Boolean(group.action_label))
}
