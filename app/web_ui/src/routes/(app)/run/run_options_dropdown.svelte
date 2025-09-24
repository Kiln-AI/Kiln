<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import type { OptionGroup, Option } from "$lib/ui/fancy_select_types"
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
    run_configs_by_task_composite_id,
    get_task_composite_id,
  } from "$lib/stores/run_configs_store"

  export let selected_run_config_id: string | "custom" | null
  export let default_run_config_id: string | null
  export let label = "Run Configuration"
  export let description = ""
  export let info_description =
    "Select a saved run configuration to quickly apply its settings, or choose None to manually configure run options and save them for future use."
  export let task_id: string | null = null
  export let project_id: string | null = null
  export let show_none_option = false
  export let show_create_new_option = false

  onMount(async () => {
    await load_available_prompts()
    await load_model_info()
  })

  // Use props if provided, otherwise fall back to store values
  $: effective_project_id = project_id ?? $current_project?.id
  $: effective_task_id = task_id ?? $current_task?.id

  $: if (effective_project_id && effective_task_id) {
    load_task_run_configs(effective_project_id, effective_task_id)
  }

  // Get the current run configs for the task
  $: current_run_configs =
    effective_project_id && effective_task_id
      ? $run_configs_by_task_composite_id[
          get_task_composite_id(effective_project_id, effective_task_id)
        ] ?? []
      : []

  // Build the options for the dropdown
  $: options = (() => {
    if (!effective_project_id || !effective_task_id) {
      return []
    }

    const options: OptionGroup[] = []

    // Add options at the top
    const top_options: Option[] = []

    // Add "None" option if requested (for Run page)
    if (show_none_option) {
      top_options.push({
        value: "custom",
        label: "None",
        description: "Run with your current manually selected options.",
      })
    }

    // Add "Create New Run Configuration" option if requested (for Add Kiln Task Tool)
    if (show_create_new_option) {
      top_options.push({
        value: "__create_new_run_config__",
        label: "Create New Run Configuration",
        description: "Create a new run configuration with custom settings.",
        badge: "+",
        badge_color: "primary",
      })
    }

    options.push({
      label: "",
      options: top_options,
    })

    // Add saved configurations if they exist
    let saved_configuration_options: Option[] = []

    // Add default configuration first if it exists
    if (default_run_config_id) {
      const default_config = current_run_configs.find(
        (config) => config.id === default_run_config_id,
      )

      if (default_config) {
        saved_configuration_options.push({
          value: default_run_config_id,
          label: `${default_config.name} (Default)`,
          description: `Model: ${model_name(default_config.run_config_properties.model_name, $model_info)} (${provider_name_from_id(default_config.run_config_properties.model_provider_name)})
            Prompt: ${getRunConfigPromptDisplayName(default_config, $current_task_prompts)}`,
        })
      }
    }

    const other_task_run_configs = current_run_configs.filter(
      (config) => config.id !== default_run_config_id,
    )
    if (other_task_run_configs.length > 0) {
      saved_configuration_options.push(
        ...other_task_run_configs.map((config) => ({
          value: config.id ?? "",
          label: config.name,
          description: `Model: ${model_name(config.run_config_properties.model_name, $model_info)} (${provider_name_from_id(config.run_config_properties.model_provider_name)})
            Prompt: ${getRunConfigPromptDisplayName(config, $current_task_prompts)}`,
        })),
      )
    }

    if (saved_configuration_options.length > 0) {
      options.push({
        label: "Saved Configurations",
        options: saved_configuration_options,
      })
    }

    return options
  })()
</script>

<FormElement
  {label}
  {description}
  {info_description}
  inputType="fancy_select"
  bind:value={selected_run_config_id}
  id="run_config"
  bind:fancy_select_options={options}
/>
