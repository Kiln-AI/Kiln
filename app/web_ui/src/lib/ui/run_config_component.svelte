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
  } from "$lib/stores/run_configs_store"
  import { createKilnError } from "$lib/utils/error_handlers"
  import PromptTypeSelector from "./prompt_type_selector.svelte"
  import { KilnError } from "$lib/utils/error_handlers"
  import type {
    TaskRunConfig,
    RunConfigProperties,
    StructuredOutputMode,
    AvailableModels,
    Task,
  } from "$lib/types"
  import AvailableModelsDropdown from "./available_models_dropdown.svelte"
  import AdvancedRunOptions from "$lib/ui/advanced_run_options.svelte"
  import Collapse from "$lib/ui/collapse.svelte"
  import { tick, onMount } from "svelte"
  import SavedRunConfigurationsDropdown from "./saved_run_configs_dropdown.svelte"
  import { ui_state } from "$lib/stores"

  // Props
  export let project_id: string
  export let current_task: Task
  export let requires_structured_output: boolean = false

  // Expose reactive values for parent component
  export let model_name: string = ""
  export let provider: string = ""
  export let prompt_method: string = "simple_prompt_builder"

  let selected_run_config_id: string | null = null
  let model: string = $ui_state.selected_model
  let tools: string[] = []

  // These defaults are used by every provider I checked (OpenRouter, Fireworks, Together, etc)
  let temperature: number = 1.0
  let top_p: number = 1.0

  let structured_output_mode: StructuredOutputMode = "default"

  $: model_name = model ? model.split("/").slice(1).join("/") : ""
  $: provider = model ? model.split("/")[0] : ""
  $: requires_tool_support = tools.length > 0

  let save_config_error: KilnError | null = null
  let set_default_error: KilnError | null = null

  let model_dropdown: AvailableModelsDropdown
  let model_dropdown_error_message: string | null = null

  onMount(async () => {
    Promise.all([load_available_models(), load_available_prompts()])
  })

  $: update_structured_output_mode_if_needed(
    model_name,
    provider,
    $available_models,
  )

  // If requires_structured_output, update structured_output_mode when model changes
  function update_structured_output_mode_if_needed(
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
      }
    }
  }

  // Update form values from saved config change if needed
  $: selected_run_config_id, update_current_run_options_if_needed()

  function get_selected_run_config(): TaskRunConfig | "custom" | null {
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

  async function update_current_run_options_if_needed() {
    const selected_run_config = get_selected_run_config()
    if (!selected_run_config || selected_run_config === "custom") {
      return
    }

    model =
      selected_run_config.run_config_properties.model_provider_name +
      "/" +
      selected_run_config.run_config_properties.model_name
    prompt_method = selected_run_config.run_config_properties.prompt_id
    tools = [
      ...(selected_run_config.run_config_properties.tools_config?.tools ?? []),
    ]
    temperature = selected_run_config.run_config_properties.temperature
    top_p = selected_run_config.run_config_properties.top_p
    structured_output_mode =
      selected_run_config.run_config_properties.structured_output_mode
  }

  // Check for manual changes when options change when on a saved config to set back to custom
  $: model,
    prompt_method,
    temperature,
    top_p,
    structured_output_mode,
    tools,
    reset_to_custom_options_if_needed()

  async function reset_to_custom_options_if_needed() {
    const selected_run_config = get_selected_run_config()
    if (!selected_run_config || selected_run_config === "custom") {
      return
    }

    // Wait for all reactive statements to complete
    await tick()

    clear_run_options_errors()

    const config_properties = selected_run_config.run_config_properties

    // Check if any values have changed from the saved config properties
    const current_model_name = model ? model.split("/").slice(1).join("/") : ""
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

  // Helper function to compare tools arrays efficiently
  function arrays_equal(a: string[], b: string[]): boolean {
    return a.length === b.length && a.every((val, index) => val === b[index])
  }

  // Helper function to convert run options to server run_config_properties format
  export function run_options_as_run_config_properties(): RunConfigProperties {
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
  async function save_run_options() {
    if (!project_id || !current_task.id) {
      return
    }
    try {
      save_config_error = null
      const saved_config = await save_new_task_run_config(
        project_id,
        current_task.id,
        run_options_as_run_config_properties(),
      )
      // Reload prompts to update the dropdown with the new static prompt that is made from saving a new run config
      await load_available_prompts()
      if (saved_config.id) {
        selected_run_config_id = saved_config.id
      } else {
        throw new Error("Saved config id not found")
      }
    } catch (e) {
      save_config_error = createKilnError(e)
    }
  }

  // Clear any errors when changing selected_run_config_id
  $: selected_run_config_id, clear_run_options_errors()

  function clear_run_options_errors() {
    if (save_config_error) {
      save_config_error = null
    }
    if (set_default_error) {
      set_default_error = null
    }
  }

  // Expose methods for run parent component
  export function get_selected_model() {
    return model_dropdown.get_selected_model()
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
    {current_task}
    bind:selected_run_config_id
    {set_default_error}
    on:change={clear_run_options_errors}
    on:save_run_options={save_run_options}
  />
  {#if $available_models.length > 0}
    <AvailableModelsDropdown
      task_id={current_task.id ?? ""}
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
      task_id={current_task.id ?? ""}
    />
  </Collapse>
</div>
