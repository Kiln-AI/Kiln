import type {
  TaskRunConfig,
  PromptResponse,
  ProviderModels,
  ToolSetApiDescription,
} from "$lib/types"
import {
  model_name,
  prompt_name_from_id,
  provider_name_from_id,
} from "$lib/stores"
import {
  get_tools_property_info,
  get_tool_server_name,
} from "$lib/stores/tools_store"
import { prompt_link, tool_link } from "$lib/utils/link_builder"
import type { UiProperty } from "$lib/ui/property_list"
import { formatDate } from "./formatters"

export function getRunConfigDisplayName(
  config: TaskRunConfig,
  model_info: ProviderModels | null,
): string {
  const run_config_type = config.run_config_properties.type
  switch (run_config_type) {
    case "mcp":
      return config.run_config_properties.tool_reference.tool_name ?? "MCP Tool"
    case "kiln_agent":
      return getDetailedModelNameFromParts(
        config.run_config_properties.model_name,
        config.run_config_properties.model_provider_name,
        model_info,
      )
    default: {
      const _exhaustive: never = run_config_type
      throw new Error(`Unknown run config type: ${_exhaustive}`)
    }
  }
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
  const run_config_type = task_run_config.run_config_properties.type
  switch (run_config_type) {
    case "mcp":
      return task_run_config.name || "Unnamed Run Config"
    case "kiln_agent": {
      const prompt_name = prompt_name_from_id(
        task_run_config?.run_config_properties?.prompt_id,
        current_task_prompts,
      )

      if (
        task_run_config.prompt?.generator_id &&
        task_run_config?.run_config_properties?.prompt_id?.startsWith(
          "task_run_config::",
        )
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
    default: {
      const _exhaustive: never = run_config_type
      throw new Error(`Unknown run config type: ${_exhaustive}`)
    }
  }
}

export function getRunConfigPromptInfoText(
  task_run_config: TaskRunConfig,
): string | null {
  const run_config_type = task_run_config.run_config_properties.type
  switch (run_config_type) {
    case "mcp":
      return null
    case "kiln_agent":
      if (
        task_run_config.prompt?.generator_id &&
        task_run_config?.run_config_properties?.prompt_id?.startsWith(
          "task_run_config::",
        )
      ) {
        return (
          'The exact prompt was saved under the name "' +
          task_run_config.prompt?.name +
          '". See the Prompt tab for details.'
        )
      }

      return null
    default: {
      const _exhaustive: never = run_config_type
      throw new Error(`Unknown run config type: ${_exhaustive}`)
    }
  }
}

export function getRunConfigUiProperties(
  project_id: string,
  task_id: string,
  run_config: TaskRunConfig,
  model_info: ProviderModels | null,
  task_prompts: PromptResponse | null,
  available_tools: Record<string, ToolSetApiDescription[]> | null,
): UiProperty[] {
  const run_config_type = run_config.run_config_properties.type
  switch (run_config_type) {
    case "mcp": {
      const tool_id =
        run_config.run_config_properties.tool_reference.tool_id ?? null
      const tool_name =
        run_config.run_config_properties.tool_reference.tool_name ?? "Unknown"
      const tool_server_link = tool_id ? tool_link(project_id, tool_id) : null
      const tool_server_name = available_tools
        ? get_tool_server_name(available_tools, project_id, tool_id)
        : null

      return [
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
          name: "Type",
          value: "MCP Tool (No Agent)",
        },
        {
          name: "MCP Tool",
          value: tool_name,
          link: tool_server_link || undefined,
          tooltip: `This run configuration will invoke the MCP tool "${tool_name}" directly, without any wrapper agent.`,
        },
        ...(tool_server_name
          ? [
              {
                name: "Tool Server",
                value: tool_server_name,
              },
            ]
          : []),
        {
          name: "Tool ID",
          value: tool_id ?? "Unknown",
        },
      ]
    }
    case "kiln_agent": {
      const model_value = model_info
        ? `${model_name(run_config.run_config_properties.model_name, model_info)} (${provider_name_from_id(run_config.run_config_properties.model_provider_name)})`
        : "Loading..."

      const prompt_value = task_prompts
        ? getRunConfigPromptDisplayName(run_config, task_prompts)
        : "Loading..."

      const prompt_id = run_config.run_config_properties.prompt_id
      const prompt_link_value = prompt_id
        ? prompt_link(project_id, task_id, prompt_id)
        : undefined

      const prompt_info_text = getRunConfigPromptInfoText(run_config)

      const tool_ids =
        run_config.run_config_properties.tools_config?.tools || []
      const tools_property_info = available_tools
        ? get_tools_property_info(tool_ids, project_id, available_tools)
        : { value: "Loading...", links: undefined }

      return [
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
        {
          name: "Temperature",
          value: run_config.run_config_properties.temperature.toString(),
        },
        {
          name: "Top P",
          value: run_config.run_config_properties.top_p.toString(),
        },
      ]
    }
    default: {
      const _exhaustive: never = run_config_type
      throw new Error(`Unknown run config type: ${_exhaustive}`)
    }
  }
}
