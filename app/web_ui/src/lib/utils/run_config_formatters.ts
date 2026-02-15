import type {
  TaskRunConfig,
  PromptResponse,
  ProviderModels,
  ToolSetApiDescription,
} from "$lib/types"
import { isKilnAgentRunConfig } from "$lib/types"
import {
  model_name,
  prompt_name_from_id,
  provider_name_from_id,
} from "$lib/stores"
import { get_tools_property_info } from "$lib/stores/tools_store"
import { prompt_link } from "$lib/utils/link_builder"
import type { UiProperty } from "$lib/ui/property_list"
import { formatDate } from "./formatters"

export function getDetailedModelName(
  config: TaskRunConfig,
  model_info: ProviderModels | null,
): string {
  if (!isKilnAgentRunConfig(config.run_config_properties)) {
    return "MCP Tool"
  }
  return getDetailedModelNameFromParts(
    config.run_config_properties.model_name,
    config.run_config_properties.model_provider_name,
    model_info,
  )
}

export function getDetailedModelNameFromParts(
  model_name_part: string,
  model_provider_part: string,
  model_info: ProviderModels | null,
): string {
  return `${model_name(model_name_part, model_info)} (${provider_name_from_id(model_provider_part)})`
}

export function getStaticPromptDisplayName(
  prompt_name: string,
  prompt_generator_id: string | null | undefined,
  current_task_prompts: PromptResponse | null,
): string {
  return `${prompt_name} — ${prompt_generator_id ? prompt_name_from_id(prompt_generator_id, current_task_prompts) : "Custom"}`
}

export function getRunConfigPromptDisplayName(
  task_run_config: TaskRunConfig,
  current_task_prompts: PromptResponse | null,
): string {
  const props = task_run_config?.run_config_properties
  if (!isKilnAgentRunConfig(props)) {
    return task_run_config.name || "MCP Run Config"
  }

  const prompt_name = prompt_name_from_id(props.prompt_id, current_task_prompts)

  // Special case: description for prompts frozen to the task run config. The name alone isn't that helpful, so we say where it comes from (eg "Basic (Zero Shot")) -->
  if (
    task_run_config.prompt?.generator_id &&
    props.prompt_id?.startsWith("task_run_config::")
  ) {
    return getStaticPromptDisplayName(
      prompt_name,
      task_run_config.prompt.generator_id,
      current_task_prompts,
    )
  }

  if (prompt_name) {
    return prompt_name
  }

  return task_run_config.name || "Unnamed Run Config"
}

export function getRunConfigPromptInfoText(
  task_run_config: TaskRunConfig,
): string | null {
  const props = task_run_config?.run_config_properties
  if (!isKilnAgentRunConfig(props)) {
    return null
  }
  // Special case: description for prompts frozen to the task run config. The name alone isn't that helpful, so we say where it comes from (eg "Basic (Zero Shot")) -->
  if (
    task_run_config.prompt?.generator_id &&
    props.prompt_id?.startsWith("task_run_config::")
  ) {
    return (
      'The exact prompt was saved under the name "' +
      task_run_config.prompt?.name +
      '". See the Prompt tab for details.'
    )
  }

  return null
}

export function getRunConfigUiProperties(
  project_id: string,
  task_id: string,
  run_config: TaskRunConfig,
  model_info: ProviderModels | null,
  task_prompts: PromptResponse | null,
  available_tools: Record<string, ToolSetApiDescription[]> | null,
): UiProperty[] {
  const props = run_config.run_config_properties
  const isKilnAgent = isKilnAgentRunConfig(props)

  const model_value = isKilnAgent
    ? model_info
      ? `${model_name(props.model_name, model_info)} (${provider_name_from_id(props.model_provider_name)})`
      : "Loading..."
    : "MCP Tool"

  const prompt_value = task_prompts
    ? getRunConfigPromptDisplayName(run_config, task_prompts)
    : "Loading..."

  const prompt_id = isKilnAgent ? props.prompt_id : undefined
  const prompt_link_value = prompt_id
    ? prompt_link(project_id, task_id, prompt_id)
    : undefined

  const prompt_info_text = getRunConfigPromptInfoText(run_config)

  const tool_ids = isKilnAgent ? props.tools_config?.tools || [] : []
  const tools_property_info = available_tools
    ? get_tools_property_info(tool_ids, project_id, available_tools)
    : { value: "Loading...", links: undefined }

  const base_properties: UiProperty[] = [
    {
      name: "ID",
      value: run_config.id || "N/A",
    },
    {
      name: "Name",
      value: run_config.name || "N/A",
    },
    {
      name: "Created At",
      value: formatDate(run_config.created_at),
    },
    {
      name: "Model",
      value: model_value,
    },
    {
      name: "Prompt",
      value: prompt_value,
      link: prompt_link_value,
      tooltip: prompt_info_text || undefined,
    },
    {
      name: "Available Tools",
      value: tools_property_info.value,
      links: tools_property_info.links,
      badge: Array.isArray(tools_property_info.value) ? true : false,
    },
  ]

  // Only add Temperature and Top P for KilnAgent configs
  if (isKilnAgent) {
    base_properties.push(
      {
        name: "Temperature",
        value: props.temperature.toString(),
      },
      {
        name: "Top P",
        value: props.top_p.toString(),
      },
    )
  }

  return base_properties
}
