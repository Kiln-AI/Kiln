<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import type { OptionGroup, Option } from "$lib/ui/fancy_select_types"
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
    run_configs_by_task_composite_id,
    get_task_composite_id,
  } from "$lib/stores/run_configs_store"

  export let selected_run_config_id: string | "custom" | null
  export let default_run_config_id: string | null

  onMount(async () => {
    await load_available_prompts()
    await load_model_info()
  })

  $: if ($current_project?.id && $current_task?.id) {
    load_task_run_configs($current_project.id, $current_task.id)
  }

  // Build the options for the dropdown
  $: options = (() => {
    const options: OptionGroup[] = []

    // Add new custom configuration option
    options.push({
      label: "",
      options: [
        {
          value: "custom",
          label: "Custom",
          description:
            "Manually choose a model, prompt, and tools for this run.",
        },
      ],
    })

    // Add saved configurations if they exist
    let saved_configuration_options: Option[] = []

    // Add default configuration first if it exists
    if (default_run_config_id) {
      const default_config = (
        $run_configs_by_task_composite_id[
          get_task_composite_id(
            $current_project?.id ?? "",
            $current_task?.id ?? "",
          )
        ] ?? ([] as TaskRunConfig[])
      ).find((config) => config.id === default_run_config_id)

      if (default_config) {
        saved_configuration_options.push({
          value: default_run_config_id,
          label: `${default_config.name} (Default)`,
          description: `Model: ${model_name(default_config.run_config_properties.model_name, $model_info)} (${provider_name_from_id(default_config.run_config_properties.model_provider_name)})
            Prompt: ${getRunConfigPromptDisplayName(default_config, $current_task_prompts)}`,
        })
      }
    }

    const other_task_run_configs = (
      $run_configs_by_task_composite_id[
        get_task_composite_id(
          $current_project?.id ?? "",
          $current_task?.id ?? "",
        )
      ] ?? ([] as TaskRunConfig[])
    ).filter((config) => config.id !== default_run_config_id)
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
  label="Run Configuration"
  info_description="Select a saved run configuration to automatically apply its settings, or choose None to manually configure run options and save them for future use."
  inputType="fancy_select"
  bind:value={selected_run_config_id}
  id="run_config"
  bind:fancy_select_options={options}
/>
