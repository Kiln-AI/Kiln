import type {
  KilnAgentRunConfigProperties,
  PromptResponse,
  ProviderModels,
  TaskRunConfig,
  ToolSetApiDescription,
} from "$lib/types"
import { assertNever } from "$lib/utils/exhaustive"
import { structuredOutputModeToString } from "$lib/utils/formatters"
import { prompt_link, tool_link } from "$lib/utils/link_builder"
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
import type {
  ChangeKind,
  LineageGraph,
  LineageNode,
  LineageStatus,
} from "./lineage_graph"
import { CHANGE_KIND_LABELS } from "./lineage_glyph"

export interface DisplayContext {
  project_id: string
  task_id: string
  model_info: ProviderModels | null
  task_prompts: PromptResponse | null
  project_tools: ToolSetApiDescription[] | null // available_tools[project_id] ?? null
}

/** A display string, with the page it links to when one exists. */
export interface LinkedValue {
  text: string
  link: string | null
}

type ListKind = Extract<ChangeKind, "tools" | "skills">

/**
 * One "Changed from Parent" row. A single value shows the child's value over
 * the parent's; a list shows what the child added and removed.
 */
export type ChangeRow =
  | {
      type: "value"
      kind: Exclude<ChangeKind, ListKind>
      value: LinkedValue
      previous: LinkedValue
    }
  | {
      type: "list"
      kind: ListKind
      added: LinkedValue[]
      removed: LinkedValue[]
    }

/** A parent or child in the lineage dialog. */
export interface Relative {
  id: string
  text: string
  deleted: boolean // the placeholder for a missing parent; it can't be selected
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
  return count === 1 ? "1 child" : `${count} children`
}

/**
 * The panel's lineage line, for example "Derived from 2 parents · 3 children".
 * The children part is left off when there are none.
 */
export function lineage_summary_text(node: LineageNode): string {
  const lead = lineage_lead_text(node)
  const children = node.child_ids.length
  return children === 0 ? lead : `${lead} · ${children_text(children)}`
}

function lineage_lead_text(node: LineageNode): string {
  switch (node.status.type) {
    case "starting_point":
      return "Starting point"
    case "no_parent":
      return "No recorded parent"
    case "deleted":
      return "This run config was deleted"
    case "changed":
    case "copy":
    case "parent_deleted": {
      const count = node.parent_ids.length
      return `Derived from ${count} ${count === 1 ? "parent" : "parents"}`
    }
    default:
      return assertNever(node.status)
  }
}

/** A node's parents (primary first) and children (oldest first). */
export function lineage_relatives(
  node: LineageNode,
  graph: LineageGraph,
): { parents: Relative[]; children: Relative[] } {
  const relative = (id: string): Relative => {
    const other = graph.nodes.get(id)
    return {
      id,
      text: other ? node_title(other) : id,
      deleted: other?.status.type === "deleted",
    }
  }
  return {
    parents: node.parent_ids.map(relative),
    children: node.child_ids.map(relative),
  }
}

/** The creator badge's label, from the provenance origin; null when unknown. */
export function origin_text(origin: string | null | undefined): string | null {
  switch (origin) {
    case "agent":
      return "Agent Created"
    case "human":
      return "Human Created"
    default:
      return null
  }
}

/** For example "2 added, 1 removed", leaving off a part that is zero. */
export function added_removed_text(added: number, removed: number): string {
  const parts = [
    ...(added > 0 ? [`${added} added`] : []),
    ...(removed > 0 ? [`${removed} removed`] : []),
  ]
  return parts.join(", ")
}

export function change_rows(
  parent: TaskRunConfig,
  child: TaskRunConfig,
  kinds: ChangeKind[],
  ctx: DisplayContext,
): ChangeRow[] {
  return kinds.map((kind): ChangeRow => {
    switch (kind) {
      case "tools":
      case "skills": {
        const before = new Set(tool_ids_of(kind, parent))
        const after = tool_ids_of(kind, child)
        const after_set = new Set(after)
        return {
          type: "list",
          kind,
          added: linked_tools(
            after.filter((id) => !before.has(id)),
            ctx,
          ),
          removed: linked_tools(
            [...before].filter((id) => !after_set.has(id)),
            ctx,
          ),
        }
      }
      case "settings": {
        const [value, previous] = settings_texts(parent, child)
        return {
          type: "value",
          kind,
          value: { text: value, link: null },
          previous: { text: previous, link: null },
        }
      }
      case "prompt":
      case "model":
        return {
          type: "value",
          kind,
          value: kind_value(kind, child, ctx),
          previous: kind_value(kind, parent, ctx),
        }
      default:
        return assertNever(kind)
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
  kind: "prompt" | "model",
  config: TaskRunConfig,
  ctx: DisplayContext,
): LinkedValue {
  if (kind === "model") {
    return { text: config_model_text(config, ctx.model_info), link: null }
  }
  const properties = config.run_config_properties
  if (properties.type !== "kiln_agent") {
    return { text: NOT_APPLICABLE, link: null }
  }
  return {
    text:
      getRunConfigPromptDisplayName(config, ctx.task_prompts) ??
      properties.prompt_id,
    link: prompt_page_link(properties.prompt_id, ctx),
  }
}

// Generator prompts, such as "Basic (Zero Shot)", have no page of their own.
function prompt_page_link(
  prompt_id: string,
  ctx: DisplayContext,
): string | null {
  const is_generator =
    ctx.task_prompts?.generators.some(
      (generator) => generator.id === prompt_id,
    ) ?? false
  return is_generator
    ? null
    : prompt_link(ctx.project_id, ctx.task_id, prompt_id) ?? null
}

function tool_ids_of(kind: ListKind, config: TaskRunConfig): string[] {
  const properties = config.run_config_properties
  if (properties.type !== "kiln_agent") {
    return []
  }
  const split = split_tool_and_skill_ids(properties.tools_config?.tools ?? [])
  return kind === "tools" ? split.tool_ids : split.skill_ids
}

function linked_tools(ids: string[], ctx: DisplayContext): LinkedValue[] {
  const names = ctx.project_tools
    ? get_tool_names_from_ids(ids, ctx.project_tools)
    : ids
  return ids.map((id, index) => ({
    text: names[index],
    link: tool_link(ctx.project_id, id),
  }))
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
