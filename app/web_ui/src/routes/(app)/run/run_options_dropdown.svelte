<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import type {
    TaskRunConfig,
    PromptResponse,
    ProviderModels,
  } from "$lib/types"
  import {
    current_task,
    current_task_prompts,
    prompt_name_from_id,
    model_name,
    model_info,
  } from "$lib/stores"
  import { task_run_configs_by_task_id } from "$lib/stores/run_configs_store"

  export let selected_run_config: string | null = "default"

  // Build the options for the dropdown
  $: options = build_run_config_options(
    $task_run_configs_by_task_id[$current_task?.id ?? ""],
    $current_task_prompts,
    $model_info,
  )

  function build_run_config_options(
    task_run_configs: TaskRunConfig[] | null,
    prompts: PromptResponse | null,
    model_info: ProviderModels | null,
  ): OptionGroup[] {
    const options: OptionGroup[] = []

    // Add default configuration if it exists
    if ($current_task?.default_run_config_id) {
      options.push({
        label: "",
        options: [
          {
            value: $current_task?.default_run_config_id || "",
            label: "Default",
            description: "The saved default configuration for this task.",
          },
        ],
      })
    }

    // Add custom configuration option
    options.push({
      label: "",
      options: [
        {
          value: "custom",
          label: "Custom",
          description: "Choose your own model, prompt, and more.",
        },
      ],
    })

    // Add saved configurations if they exist
    if (task_run_configs && task_run_configs.length > 0) {
      options.push({
        label: "Saved Configurations",
        options: task_run_configs.map((config) => ({
          value: config.id || "",
          label: config.name,
          description:
            config.description ||
            `Model: ${model_name(config.run_config_properties.model_name, model_info)}
            Prompt: ${prompt_name_from_id(config.run_config_properties.prompt_id || "", prompts)}`,
        })),
      })
    }

    return options
  }
</script>

<FormElement
  label=""
  inputType="fancy_select"
  bind:value={selected_run_config}
  id="run_config"
  bind:fancy_select_options={options}
/>
