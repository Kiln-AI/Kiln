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
    run_configs_by_task_composite_id,
    get_task_composite_id,
  } from "$lib/stores/run_configs_store"

  export let selected_run_config_id: string | "custom"
  export let default_run_config_id: string | null

  onMount(async () => {
    await load_task_run_configs(
      $current_project?.id ?? "",
      $current_task?.id ?? "",
    )
    await load_available_prompts()
    await load_model_info()
    if (default_run_config_id) {
      selected_run_config_id = default_run_config_id
    }
  })

  // Build the options for the dropdown
  $: options = (() => {
    const options: OptionGroup[] = []

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
        options.push({
          label: "",
          options: [
            {
              value: default_run_config_id,
              label: `Default (${default_config.name})`,
              description: "The saved default configuration for this task.",
            },
          ],
        })
      }
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
      $run_configs_by_task_composite_id[
        get_task_composite_id(
          $current_project?.id ?? "",
          $current_task?.id ?? "",
        )
      ] ?? ([] as TaskRunConfig[])
    ).filter((config) => config.id !== default_run_config_id)
    if (other_task_run_configs.length > 0) {
      options.push({
        label: "Saved Configurations",
        options: other_task_run_configs.map((config) => ({
          value: config.id ?? "",
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
  bind:value={selected_run_config_id}
  id="run_config"
  bind:fancy_select_options={options}
/>
