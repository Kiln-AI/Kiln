<script lang="ts">
  import {
    available_models,
    available_model_details,
    load_available_prompts,
    load_available_models,
  } from "$lib/stores"
  import {
    save_new_task_run_config,
    run_configs_by_task_composite_id,
    get_task_composite_id,
    update_task_default_run_config,
  } from "$lib/stores/run_configs_store"
  import { createKilnError } from "$lib/utils/error_handlers"
  import PromptTypeSelector from "./prompt_type_selector.svelte"
  import { KilnError } from "$lib/utils/error_handlers"
  import type {
    TaskRunConfig,
    RunConfigProperties,
    StructuredOutputMode,
    AvailableModels,
  } from "$lib/types"
  import AvailableModelsDropdown from "./available_models_dropdown.svelte"
  import AdvancedRunOptions from "$lib/ui/advanced_run_options.svelte"
  import Collapse from "$lib/ui/collapse.svelte"
  import { tick, onMount } from "svelte"
  import SavedRunConfigurationsDropdown from "./saved_run_configs_dropdown.svelte"

  // Props
  export let project_id: string
  export let task_id: string
  export let default_run_config_id: string | null = null
  export let model: string = ""
  export let temperature: number = 1.0
  export let top_p: number = 1.0
  export let structured_output_mode: StructuredOutputMode = "default"
  export let tools: string[] = []
  export let prompt_method = "simple_prompt_builder"
  export let requires_structured_output: boolean = false
  export let requires_tool_support: boolean = false

  // Events
  export let onModelChange: (model: string) => void
  export let onTemperatureChange: (temperature: number) => void
  export let onTopPChange: (top_p: number) => void
  export let onStructuredOutputModeChange: (mode: StructuredOutputMode) => void
  export let onToolsChange: (tools: string[]) => void
  export let onPromptMethodChange: (method: string) => void

  onMount(async () => {
    // Wait for page params to load
    await tick()
    // Wait for these to load, as they are needed for better labels. Usually already cached and instant.
    await load_available_models()

    // Load prompts for the specified task
    if (task_id && project_id) {
      await load_available_prompts()
    }
  })

  let save_config_error: KilnError | null = null
  let set_default_error: KilnError | null = null

  let selected_run_config_id: string | null = "custom"
  let updating_current_run_options = false

  $: model_name = model ? model.split("/").slice(1).join("/") : ""
  $: provider = model ? model.split("/")[0] : ""

  // Load prompts when task changes
  $: if (task_id && project_id) {
    load_available_prompts()
  }

  let model_dropdown: AvailableModelsDropdown
  let model_dropdown_error_message: string | null = null

  // Update structured_output_mode when model changes
  $: update_structured_output_mode(model_name, provider, $available_models)
  function update_structured_output_mode(
    model_name: string,
    provider: string,
    available_models: AvailableModels[],
  ) {
    if (requires_structured_output) {
      const new_mode =
        available_model_details(model_name, provider, available_models)
          ?.structured_output_mode || "default"
      if (new_mode !== structured_output_mode) {
        structured_output_mode = new_mode
        onStructuredOutputModeChange(new_mode)
      }
    }
  }

  // RunOptionsDropdown Logic

  // Update form values when selected_run_config changes
  $: if (selected_run_config !== "custom") {
    update_current_run_options()
  }

  async function update_current_run_options() {
    updating_current_run_options = true

    // Populate values from saved configuration
    const config = selected_run_config as TaskRunConfig
    prompt_method = config.run_config_properties.prompt_id
    model =
      config.run_config_properties.model_provider_name +
      "/" +
      config.run_config_properties.model_name
    temperature = config.run_config_properties.temperature
    top_p = config.run_config_properties.top_p
    structured_output_mode = config.run_config_properties.structured_output_mode
    tools = [...(config.run_config_properties.tools_config?.tools ?? [])]

    // Notify parent of changes
    onPromptMethodChange(prompt_method)
    onModelChange(model)
    onTemperatureChange(temperature)
    onTopPChange(top_p)
    onStructuredOutputModeChange(structured_output_mode)
    onToolsChange(tools)

    updating_current_run_options = false
  }

  // Check for manual changes when options change in case user values differ from selected run config to reset to custom options
  $: model,
    prompt_method,
    temperature,
    top_p,
    structured_output_mode,
    tools,
    updating_current_run_options,
    check_for_manual_changes()

  async function check_for_manual_changes() {
    if (updating_current_run_options) {
      return
    }

    // Wait for all reactive statements to complete
    await tick()

    clear_run_options_errors()

    if (selected_run_config !== "custom") {
      const config_properties = (selected_run_config as TaskRunConfig)
        .run_config_properties
      // Check if any values have changed from the saved config properties
      const current_model_name = model
        ? model.split("/").slice(1).join("/")
        : ""
      const current_provider_name = model ? model.split("/")[0] : ""
      if (
        config_properties.model_name !== current_model_name ||
        config_properties.model_provider_name !== current_provider_name ||
        config_properties.prompt_id !== prompt_method ||
        config_properties.temperature !== temperature ||
        config_properties.top_p !== top_p ||
        config_properties.structured_output_mode !== structured_output_mode ||
        !arrays_equal(config_properties.tools_config?.tools ?? [], tools)
      ) {
        selected_run_config_id = "custom"
      }
    }
  }

  // Helper function to compare tools arrays efficiently
  function arrays_equal(a: string[], b: string[]): boolean {
    return a.length === b.length && a.every((val, index) => val === b[index])
  }

  // Helper function to convert run options to server run_config_properties format
  function run_options_as_run_config_properties(): RunConfigProperties {
    return {
      model_name: model_name,
      // @ts-expect-error server will catch if enum is not valid
      model_provider_name: provider,
      prompt_id: prompt_method,
      temperature: temperature,
      top_p: top_p,
      structured_output_mode: structured_output_mode,
      tools_config: {
        tools: tools,
      },
    }
  }

  // Handle save run options button clicked
  async function handle_save_run_options() {
    if (!project_id || !task_id) {
      return
    }
    try {
      save_config_error = null
      const saved_config = await save_new_task_run_config(
        project_id,
        task_id,
        run_options_as_run_config_properties(),
      )
      await load_available_prompts()
      // Wait for all reactive updates to complete (including dropdown options rebuild)
      await tick()
      // Now set the selected config after
      if (saved_config) {
        // Find the matching run config from the loaded options to ensure reference equality
        const loaded_configs =
          $run_configs_by_task_composite_id[
            get_task_composite_id(project_id, task_id)
          ] || []
        const matching_config = loaded_configs.find(
          (config) => config.id === saved_config.id,
        )
        if (matching_config) {
          selected_run_config_id = matching_config.id ?? "custom"
        } else {
          throw new Error("Saved config not found in loaded options")
        }
      }
    } catch (e) {
      save_config_error = createKilnError(e)
    }
  }

  $: show_set_as_default_button = (() => {
    if (selected_run_config_id === "custom") {
      return false
    }
    return selected_run_config_id !== default_run_config_id
  })()

  $: selected_run_config_id, clear_run_options_errors()

  function clear_run_options_errors() {
    if (save_config_error) {
      save_config_error = null
    }
    if (set_default_error) {
      set_default_error = null
    }
  }

  async function handle_set_as_default() {
    if (!project_id || !task_id) {
      return
    }
    // Update task default run config
    try {
      set_default_error = null
      await update_task_default_run_config(
        project_id,
        task_id,
        (selected_run_config as TaskRunConfig).id ?? "",
      )
      // Note: Parent component should handle updating the task's default_run_config_id
      await tick()
      if (default_run_config_id) {
        selected_run_config_id = default_run_config_id
      }
    } catch (e) {
      set_default_error = createKilnError(e)
    }
  }

  let selected_run_config: TaskRunConfig | "custom" = "custom"

  // Map selected ID back to TaskRunConfig object
  $: selected_run_config = (() => {
    if (selected_run_config_id === "custom") {
      return "custom"
    }

    // Find the config by ID
    const all_configs =
      $run_configs_by_task_composite_id[
        get_task_composite_id(project_id, task_id)
      ] ?? []
    return (
      all_configs.find((config) => config.id === selected_run_config_id) ??
      "custom"
    )
  })()

  $: if (default_run_config_id !== undefined) {
    // Initialization of selected_run_config_id
    // Until this runs the dropdown will show "Select an option"
    if (default_run_config_id) {
      if (selected_run_config_id === null) {
        selected_run_config_id = default_run_config_id
      }
    } else {
      if (selected_run_config_id === null) {
        selected_run_config_id = "custom"
      }
    }
  }

  // Expose methods for parent component
  export function get_selected_model() {
    return model_dropdown.get_selected_model()
  }

  export function get_model_dropdown_error_message() {
    return model_dropdown_error_message
  }

  export function clear_model_dropdown_error() {
    model_dropdown_error_message = null
  }

  export function set_model_dropdown_error(message: string) {
    model_dropdown_error_message = message
  }
</script>

<div class="w-72 2xl:w-96 flex-none flex flex-col gap-4">
  <div class="text-xl font-bold">Options</div>
  <SavedRunConfigurationsDropdown
    {project_id}
    {task_id}
    bind:selected_run_config_id
    bind:default_run_config_id
    on:change={clear_run_options_errors}
    show_save_button={selected_run_config_id === "custom"}
    show_set_default_button={show_set_as_default_button}
    on_save={handle_save_run_options}
    on_set_default={handle_set_as_default}
    save_error={save_config_error}
    {set_default_error}
  />
  {#if $available_models.length > 0}
    <AvailableModelsDropdown
      {task_id}
      bind:model
      bind:requires_structured_output
      bind:requires_tool_support
      bind:error_message={model_dropdown_error_message}
      bind:this={model_dropdown}
    />
  {:else}
    <div class="text-sm text-gray-500">Loading models...</div>
  {/if}
  <div>
    <PromptTypeSelector
      bind:prompt_method
      info_description="Choose a prompt. Learn more on the 'Prompts' tab."
      bind:linked_model_selection={model}
    />
  </div>
  <Collapse
    title="Advanced Options"
    badge={tools.length > 0 ? "" + tools.length : null}
  >
    <AdvancedRunOptions
      bind:tools
      bind:temperature
      bind:top_p
      bind:structured_output_mode
      has_structured_output={requires_structured_output}
      {project_id}
      {task_id}
    />
  </Collapse>
</div>
