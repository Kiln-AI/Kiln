import type { KilnAgentRunConfigProperties, TaskRunConfig } from "$lib/types"
import { sets_equal } from "$lib/utils/collections"
import { inputTransformsEqual } from "$lib/utils/run_config_formatters"
import { split_tool_and_skill_ids } from "$lib/stores/tools_store"

export type ChangeKind = "prompt" | "tools" | "skills" | "model" | "settings"
export const CHANGE_KINDS: readonly ChangeKind[] = [
  "prompt",
  "tools",
  "skills",
  "model",
  "settings",
]

export type SettingField =
  | "temperature"
  | "top_p"
  | "thinking_level"
  | "structured_output_mode"
  | "input_transform"

export const SETTING_FIELDS: readonly SettingField[] = [
  "temperature",
  "top_p",
  "thinking_level",
  "structured_output_mode",
  "input_transform",
]

/**
 * The kinds of change from `parent` to `child`, in CHANGE_KINDS order. An MCP
 * run config has only its tool to compare, so any difference involving one
 * counts as a model change.
 */
export function detect_changes(
  parent: TaskRunConfig,
  child: TaskRunConfig,
): ChangeKind[] {
  const a = parent.run_config_properties
  const b = child.run_config_properties
  if (a.type === "kiln_agent" && b.type === "kiln_agent") {
    return agent_changes(a, b)
  }
  if (a.type === "mcp" && b.type === "mcp") {
    return a.tool_reference.tool_id === b.tool_reference.tool_id
      ? []
      : ["model"]
  }
  return ["model"]
}

export function changed_setting_fields(
  parent: KilnAgentRunConfigProperties,
  child: KilnAgentRunConfigProperties,
): SettingField[] {
  const changed: Record<SettingField, boolean> = {
    temperature: parent.temperature !== child.temperature,
    top_p: parent.top_p !== child.top_p,
    thinking_level:
      (parent.thinking_level ?? null) !== (child.thinking_level ?? null),
    structured_output_mode:
      parent.structured_output_mode !== child.structured_output_mode,
    input_transform: !inputTransformsEqual(
      parent.input_transform,
      child.input_transform,
    ),
  }
  return SETTING_FIELDS.filter((field) => changed[field])
}

function agent_changes(
  a: KilnAgentRunConfigProperties,
  b: KilnAgentRunConfigProperties,
): ChangeKind[] {
  const tools_a = split_tool_and_skill_ids(a.tools_config?.tools ?? [])
  const tools_b = split_tool_and_skill_ids(b.tools_config?.tools ?? [])
  const changed: Record<ChangeKind, boolean> = {
    prompt: a.prompt_id !== b.prompt_id,
    tools: !sets_equal(new Set(tools_a.tool_ids), new Set(tools_b.tool_ids)),
    skills: !sets_equal(new Set(tools_a.skill_ids), new Set(tools_b.skill_ids)),
    model:
      a.model_name !== b.model_name ||
      a.model_provider_name !== b.model_provider_name,
    settings: changed_setting_fields(a, b).length > 0,
  }
  return CHANGE_KINDS.filter((kind) => changed[kind])
}
