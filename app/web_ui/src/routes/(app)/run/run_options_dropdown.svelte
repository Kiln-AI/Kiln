<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import type { TaskRunConfig } from "$lib/types"
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

  export let selected_run_config: TaskRunConfig | "custom"
  export let default_run_config: TaskRunConfig | null

  $: task_id = $current_task?.id ?? ""

  onMount(async () => {
    await load_task_run_configs($current_project?.id ?? "", task_id)
    await load_available_prompts()
    await load_model_info()
    if (default_run_config) {
      selected_run_config = default_run_config
    }
  })

  // Build the options for the dropdown
  $: options = (() => {
    const options: OptionGroup[] = []

    // Add default configuration first if it exists
    if (default_run_config) {
      options.push({
        label: "",
        options: [
          {
            value: default_run_config,
            label: `Default (${default_run_config.name})`,
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
    const other_task_run_configs = (
      $task_run_configs_by_task_id[task_id] ?? ([] as TaskRunConfig[])
    ).filter((config) => config.id !== default_run_config?.id)
    if (other_task_run_configs.length > 0) {
      options.push({
        label: "Saved Configurations",
        options: other_task_run_configs.map((config) => ({
          value: config,
          label: config.name,
          description:
            config.description ||
            `Model: ${model_name(config.run_config_properties.model_name, $model_info)} (${provider_name_from_id(config.run_config_properties.model_provider_name)})
            Prompt: ${getRunConfigPromptDisplayName(config, $current_task_prompts)}`,
        })),
      })
    }

    return options
  })()
</script>

<FormElement
  label=""
  inputType="fancy_select"
  bind:value={selected_run_config}
  id="run_config"
  bind:fancy_select_options={options}
/>
