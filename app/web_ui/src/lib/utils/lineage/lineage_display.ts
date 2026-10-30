import type {
  KilnAgentRunConfigProperties,
  PromptResponse,
  ProviderModels,
  TaskRunConfig,
  ToolSetApiDescription,
} from "$lib/types"
import { assertNever } from "$lib/utils/exhaustive"
import { structuredOutputModeToString } from "$lib/utils/formatters"
import {
  getInputTransformDisplay,
  getRunConfigModelDisplayName,
  getRunConfigPromptDisplayName,
  getThinkingLevelDisplayName,
} from "$lib/utils/run_config_formatters"
import {
  get_tool_names_from_ids,
  split_tool_and_skill_ids,
} from "$lib/stores/tools_store"
import { changed_setting_fields, type SettingField } from "./lineage_changes"
import type { ChangeKind, LineageNode, LineageStatus } from "./lineage_graph"
import { CHANGE_KIND_LABELS } from "./lineage_glyph"

export interface DisplayContext {
  model_info: ProviderModels | null
  task_prompts: PromptResponse | null
  project_tools: ToolSetApiDescription[] | null // available_tools[project_id] ?? null
}

/** One "Changed from Parent" row: the child's value and the parent's. */
export interface ChangeRow {
  kind: ChangeKind
  value: string
  previous: string
  provider_id: string | null // the child's model provider, for its logo
}

const NOT_APPLICABLE = "—"

export function node_title(node: LineageNode): string {
  return node.config ? node.config.name : "Deleted run config"
}

export function status_text(status: LineageStatus): string {
  switch (status.type) {
    case "starting_point":
      return "Starting point"
    case "changed":
      return status.kinds.map((kind) => CHANGE_KIND_LABELS[kind]).join(", ")
    case "copy":
      return "Copy or re-run, no changes"
    case "parent_deleted":
      return "Parent deleted"
    case "no_parent":
      return "No recorded parent"
    case "deleted":
      return "This run config was deleted"
    default:
      return assertNever(status)
  }
}

/** The model with its provider, the MCP tool, or "" for a placeholder. */
export function node_model_text(
  node: LineageNode,
  model_info: ProviderModels | null,
): string {
  return node.config ? config_model_text(node.config, model_info) : ""
}

export function children_text(count: number): string {
  if (count === 0) {
    return "No children"
  }
  return count === 1 ? "1 child" : `${count} children`
}

export function change_rows(
  parent: TaskRunConfig,
  child: TaskRunConfig,
  kinds: ChangeKind[],
  ctx: DisplayContext,
): ChangeRow[] {
  const child_properties = child.run_config_properties
  const provider_id =
    child_properties.type === "kiln_agent"
      ? child_properties.model_provider_name
      : null
  return kinds.map((kind) => {
    if (kind === "settings") {
      const [value, previous] = settings_texts(parent, child)
      return { kind, value, previous, provider_id: null }
    }
    return {
      kind,
      value: kind_value(kind, child, ctx),
      previous: kind_value(kind, parent, ctx),
      provider_id: kind === "model" ? provider_id : null,
    }
  })
}

function config_model_text(
  config: TaskRunConfig,
  model_info: ProviderModels | null,
): string {
  const properties = config.run_config_properties
  if (properties.type === "mcp") {
    return `MCP: ${properties.tool_reference.tool_name ?? "Unknown"}`
  }
  return getRunConfigModelDisplayName(config, model_info) ?? ""
}

function kind_value(
  kind: Exclude<ChangeKind, "settings">,
  config: TaskRunConfig,
  ctx: DisplayContext,
): string {
  const properties = config.run_config_properties
  if (kind === "model") {
    return config_model_text(config, ctx.model_info)
  }
  if (properties.type !== "kiln_agent") {
    return NOT_APPLICABLE
  }
  switch (kind) {
    case "prompt":
      return (
        getRunConfigPromptDisplayName(config, ctx.task_prompts) ??
        properties.prompt_id
      )
    case "tools":
    case "skills": {
      const split = split_tool_and_skill_ids(
        properties.tools_config?.tools ?? [],
      )
      const ids = kind === "tools" ? split.tool_ids : split.skill_ids
      return tool_list_text(ids, ctx.project_tools)
    }
    default:
      return assertNever(kind)
  }
}

function tool_list_text(
  ids: string[],
  project_tools: ToolSetApiDescription[] | null,
): string {
  if (ids.length === 0) {
    return "None"
  }
  const names = project_tools
    ? get_tool_names_from_ids(ids, project_tools)
    : ids
  return names.join(", ")
}

// Shows only the fields that differ, so both sides list the same settings.
function settings_texts(
  parent: TaskRunConfig,
  child: TaskRunConfig,
): [value: string, previous: string] {
  const a = parent.run_config_properties
  const b = child.run_config_properties
  if (a.type !== "kiln_agent" || b.type !== "kiln_agent") {
    return [NOT_APPLICABLE, NOT_APPLICABLE]
  }
  const fields = changed_setting_fields(a, b)
  return [settings_text(b, fields), settings_text(a, fields)]
}

const SETTING_LABELS: Record<SettingField, string> = {
  temperature: "Temperature",
  top_p: "Top P",
  thinking_level: "Thinking",
  structured_output_mode: "Output",
  input_transform: "Input transform",
}

function settings_text(
  properties: KilnAgentRunConfigProperties,
  fields: SettingField[],
): string {
  return fields
    .map(
      (field) => `${SETTING_LABELS[field]} ${setting_value(properties, field)}`,
    )
    .join(" · ")
}

function setting_value(
  properties: KilnAgentRunConfigProperties,
  field: SettingField,
): string {
  switch (field) {
    case "temperature":
      return String(properties.temperature)
    case "top_p":
      return String(properties.top_p)
    case "thinking_level":
      return properties.thinking_level
        ? getThinkingLevelDisplayName(properties.thinking_level)
        : "Default"
    case "structured_output_mode":
      return (
        structuredOutputModeToString(properties.structured_output_mode) ??
        properties.structured_output_mode
      )
    case "input_transform":
      return properties.input_transform
        ? getInputTransformDisplay(properties.input_transform).valueLabel
        : "None"
    default:
      return assertNever(field)
  }
}
