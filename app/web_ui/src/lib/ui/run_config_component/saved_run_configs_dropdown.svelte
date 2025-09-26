<script lang="ts">
  import FormElement, {
    type InlineAction,
  } from "$lib/utils/form_element.svelte"
  import type { OptionGroup, Option } from "$lib/ui/fancy_select_types"
  import type {
    PromptResponse,
    ProviderModels,
    Task,
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
    getDetailedModelName,
  } from "$lib/utils/run_config_formatters"
  import { onMount } from "svelte"
  import {
    load_task_run_configs,
    run_configs_by_task_composite_id,
    get_task_composite_id,
    update_task_default_run_config,
  } from "$lib/stores/run_configs_store"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import { createEventDispatcher } from "svelte"

  const dispatch = createEventDispatcher<{
    save_run_options: void
  }>()

  export let project_id: string
  export let current_task: Task
  export let selected_run_config_id: string | null = null // This will be null until the default_run_config_id is set
  export let set_default_error: KilnError | null = null

  $: show_save_button = selected_run_config_id === "custom"
  $: show_set_default_button = selected_run_config_id !== default_run_config_id

  onMount(async () => {
    Promise.all([load_available_prompts(), load_model_info()])
  })

  $: default_run_config_id = current_task.default_run_config_id ?? null

  $: if (project_id && current_task.id) {
    load_task_run_configs(project_id, current_task.id)
  }

  // Initialization of selected_run_config_id
  $: if (selected_run_config_id === null) {
    if (default_run_config_id) {
      selected_run_config_id = default_run_config_id
    } else {
      selected_run_config_id = "custom"
    }
  }

  let info_description: string = ""

  let cold_start_info_description =
    "You can save your run configuration including model, prompt, tools and properties. This makes it easy to return to later."
  let saved_configs_info_description =
    "Select a saved run configuration which includes model, prompt, tools and properties. Alternatively choose 'Custom' to manually configure this run."

  $: if (options.length > 0) {
    info_description =
      options.length === 1
        ? cold_start_info_description
        : saved_configs_info_description
  }

  let options: OptionGroup[] = []

  $: options = build_options(
    default_run_config_id,
    $run_configs_by_task_composite_id,
    $model_info,
    $current_task_prompts,
  )

  // Build the options for the dropdown
  function build_options(
    default_run_config_id: string | null | undefined,
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
          get_task_composite_id(project_id, current_task.id ?? "")
        ] ?? []
      ).find((config) => config.id === default_run_config_id)

      if (default_config) {
        saved_configuration_options.push({
          value: default_run_config_id,
          label: `${default_config.name} (Default)`,
          description: `Model: ${getDetailedModelName(default_config, model_info)}
            Prompt: ${getRunConfigPromptDisplayName(default_config, current_task_prompts)}`,
        })
      }
    }

    const other_task_run_configs = (
      run_configs_by_task_composite_id[
        get_task_composite_id(project_id, current_task.id ?? "")
      ] ?? []
    ).filter((config) => config.id !== default_run_config_id)
    if (other_task_run_configs.length > 0) {
      saved_configuration_options.push(
        ...other_task_run_configs.map((config) => ({
          value: config.id ?? "",
          label: config.name,
          description: `Model: ${getDetailedModelName(config, model_info)}
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

  export async function get_selected_run_config(): Promise<
    TaskRunConfig | "custom" | null
  > {
    // Make sure the task run configs are loaded, will be quick if they already are
    await load_task_run_configs(project_id, current_task.id ?? "")

    // Map selected ID back to TaskRunConfig object
    if (!selected_run_config_id) {
      return null
    } else if (selected_run_config_id === "custom") {
      return "custom"
    } else {
      // Find the config by ID
      const all_configs =
        $run_configs_by_task_composite_id[
          get_task_composite_id(project_id, current_task.id ?? "")
        ] ?? []
      let run_config = all_configs.find(
        (config) => config.id === selected_run_config_id,
      )
      return run_config ?? "custom"
    }
  }

  function handle_save() {
    dispatch("save_run_options")
  }

  async function set_run_config_as_default() {
    if (!project_id || !current_task.id || !selected_run_config_id) {
      return
    }
    // Update task default run config
    try {
      set_default_error = null
      await update_task_default_run_config(
        project_id,
        current_task.id,
        selected_run_config_id,
      )
    } catch (e) {
      set_default_error = createKilnError(e)
    }
  }

  let inline_action: InlineAction | null = null

  $: show_save_button, show_set_default_button, update_inline_action()

  function update_inline_action() {
    if (show_save_button) {
      inline_action = {
        handler: handle_save,
        label: "Save current options",
      }
    } else if (show_set_default_button) {
      inline_action = {
        handler: set_run_config_as_default,
        label: "Set as task default",
      }
    } else {
      inline_action = null
    }
  }
</script>

<FormElement
  label="Run Configuration"
  {info_description}
  inputType="fancy_select"
  bind:value={selected_run_config_id}
  id="run_config"
  bind:fancy_select_options={options}
  {inline_action}
/>
