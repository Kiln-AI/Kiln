import type { TaskRunConfig, PromptResponse } from "$lib/types"
import { prompt_name_from_id } from "$lib/stores"

export function getRunConfigPromptDisplayName(
  task_run_config: TaskRunConfig,
  current_task_prompts: PromptResponse | null,
): string {
  // Special case: description for prompts frozen to the task run config. The name alone isn't that helpful, so we say where it comes from (eg "Basic (Zero Shot")) -->
  if (
    task_run_config.prompt?.generator_id &&
    task_run_config?.run_config_properties?.prompt_id?.startsWith(
      "task_run_config::",
    )
  ) {
    return prompt_name_from_id(
      task_run_config?.prompt?.generator_id,
      current_task_prompts,
    )
  }

  return task_run_config.name || "Unnamed Run Method"
}

export function getRunConfigPromptInfoText(
  task_run_config: TaskRunConfig,
): string | null {
  // Special case: description for prompts frozen to the task run config. The name alone isn't that helpful, so we say where it comes from (eg "Basic (Zero Shot")) -->
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
}
