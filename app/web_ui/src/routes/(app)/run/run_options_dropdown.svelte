<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import type {
    TaskRunConfig,
    PromptResponse,
    ProviderModels,
  } from "$lib/types"
  import {
    model_name,
    model_info,
    provider_name_from_id,
    load_available_prompts,
    current_task_prompts,
    load_model_info,
    current_task,
    current_project,
  } from "$lib/stores"
  import { getRunConfigPromptDisplayName } from "$lib/utils/run_config_formatters"
  import { onMount } from "svelte"
  import {
    load_task_run_configs,
    task_run_configs_by_task_id,
  } from "$lib/stores/run_configs_store"

  export let selected_run_config: TaskRunConfig | "custom" = "custom"

  $: task_id = $current_task?.id ?? ""

  onMount(async () => {
    await load_task_run_configs($current_project?.id ?? "", task_id)
    await load_available_prompts()
    await load_model_info()
    let default_run_config = get_default_run_config()
    if (default_run_config) {
      selected_run_config = default_run_config
    }
  })

  function get_default_run_config(): TaskRunConfig | null {
    if ($current_task?.default_run_config_id) {
      let default_task_run_config = $task_run_configs_by_task_id[task_id]?.find(
        (config) => config.id === $current_task?.default_run_config_id,
      )
      return default_task_run_config ?? null
    }
    return null
  }

  // Build the options for the dropdown
  $: options = build_run_config_options(
    $task_run_configs_by_task_id[task_id] ?? [],
    $current_task_prompts,
    $model_info,
  )

  function build_run_config_options(
    task_run_configs: TaskRunConfig[],
    all_task_prompts: PromptResponse | null,
    model_info: ProviderModels | null,
  ): OptionGroup[] {
    const options: OptionGroup[] = []

    // Add default configuration first if it exists
    let default_run_config = get_default_run_config()
    if (default_run_config) {
      options.push({
        label: "",
        options: [
          {
            value: default_run_config,
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
    if (task_run_configs.length > 0) {
      options.push({
        label: "Saved Configurations",
        options: task_run_configs.map((config) => ({
          value: config,
          label: config.name,
          description:
            config.description ||
            `Model: ${model_name(config.run_config_properties.model_name, model_info)} (${provider_name_from_id(config.run_config_properties.model_provider_name)})
            Prompt: ${getRunConfigPromptDisplayName(config, all_task_prompts)}`,
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
