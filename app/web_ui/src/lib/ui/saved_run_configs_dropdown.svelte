<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import type { OptionGroup, Option } from "$lib/ui/fancy_select_types"
  import type {
    PromptResponse,
    ProviderModels,
    TaskRunConfig,
  } from "$lib/types"
  import {
    model_info,
    load_available_prompts,
    current_task_prompts,
    load_model_info,
  } from "$lib/stores"
  import {
    getRunConfigPromptDisplayName,
    getDetailedModelMame,
  } from "$lib/utils/run_config_formatters"
  import { onMount } from "svelte"
  import {
    load_task_run_configs,
    run_configs_by_task_composite_id,
    get_task_composite_id,
  } from "$lib/stores/run_configs_store"

  export let project_id: string
  export let task_id: string
  export let selected_run_config_id: string | null
  export let default_run_config_id: string | null

  // Button props for inline actions
  export let show_save_button: boolean = false
  export let show_set_default_button: boolean = false
  export let on_save: (() => void) | null = null
  export let on_set_default: (() => void) | null = null
  export let save_error: { getErrorMessages(): string[] } | null = null
  export let set_default_error: { getErrorMessages(): string[] } | null = null

  onMount(async () => {
    Promise.all([load_available_prompts(), load_model_info()])
  })

  $: if (project_id && task_id) {
    load_task_run_configs(project_id, task_id)
  }

  $: info_description =
    options.length === 1
      ? "You can save your run configuration including model, prompt, tools and properties. This makes it easy to return to later."
      : "Select a saved run configuration which includes model, prompt, tools and properties. Alternatively choose 'Custom' to manually configure this run."

  $: options = build_options(
    default_run_config_id,
    $run_configs_by_task_composite_id,
    $model_info,
    $current_task_prompts,
  )

  // Build the options for the dropdown
  function build_options(
    default_run_config_id: string | null,
    run_configs_by_task_composite_id: Record<string, TaskRunConfig[]>,
    model_info: ProviderModels | null,
    current_task_prompts: PromptResponse | null,
  ): OptionGroup[] {
    const options: OptionGroup[] = []

    // Add new custom configuration option
    options.push({
      label: "",
      options: [
        {
          value: "custom",
          label: "Custom",
          description: "Run with the options specified below.",
        },
      ],
    })

    // Add saved configurations if they exist
    let saved_configuration_options: Option[] = []

    // Add default configuration first if it exists
    if (default_run_config_id) {
      const default_config = (
        run_configs_by_task_composite_id[
          get_task_composite_id(project_id, task_id)
        ] ?? []
      ).find((config) => config.id === default_run_config_id)

      if (default_config) {
        saved_configuration_options.push({
          value: default_run_config_id,
          label: `${default_config.name} (Default)`,
          description: `Model: ${getDetailedModelMame(default_config, model_info)}
            Prompt: ${getRunConfigPromptDisplayName(default_config, current_task_prompts)}`,
        })
      }
    }

    const other_task_run_configs = (
      run_configs_by_task_composite_id[
        get_task_composite_id(project_id, task_id)
      ] ?? []
    ).filter((config) => config.id !== default_run_config_id)
    if (other_task_run_configs.length > 0) {
      saved_configuration_options.push(
        ...other_task_run_configs.map((config) => ({
          value: config.id ?? "",
          label: config.name,
          description: `Model: ${getDetailedModelMame(config, model_info)}
            Prompt: ${getRunConfigPromptDisplayName(config, current_task_prompts)}`,
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
  }
</script>

<FormElement
  label="Run Configuration"
  {info_description}
  inputType="fancy_select"
  bind:value={selected_run_config_id}
  id="run_config"
  bind:fancy_select_options={options}
>
  <svelte:fragment slot="inline-actions">
    {#if show_save_button}
      <button
        type="button"
        class="link text-gray-500 text-sm font-normal"
        on:click={on_save}
      >
        Save current options
      </button>
    {:else if show_set_default_button}
      <button
        type="button"
        class="link text-gray-500 text-sm font-normal"
        on:click={on_set_default}
      >
        Set as task default
      </button>
    {:else}
      <button
        type="button"
        class="link text-gray-500 text-sm invisible font-normal"
        on:click={on_set_default}
      >
        Placeholder
      </button>
    {/if}
  </svelte:fragment>
</FormElement>

<!-- Error messages -->
{#if save_error}
  <div class="text-sm text-error text-right -mt-3">
    {#each save_error.getErrorMessages() as error_line}
      <div>{error_line}</div>
    {/each}
  </div>
{/if}
{#if set_default_error}
  <div class="text-sm text-error text-right -mt-3">
    {#each set_default_error.getErrorMessages() as error_line}
      <div>{error_line}</div>
    {/each}
  </div>
{/if}
