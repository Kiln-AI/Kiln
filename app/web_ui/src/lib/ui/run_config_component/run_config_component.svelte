<script lang="ts">
  import {
    available_models,
    available_model_details,
    load_available_models,
    get_task_composite_id,
  } from "$lib/stores"
  import {
    load_task_run_configs,
    run_configs_by_task_composite_id,
    save_new_task_run_config,
  } from "$lib/stores/run_configs_store"
  import { createKilnError } from "$lib/utils/error_handlers"
  import { KilnError } from "$lib/utils/error_handlers"
  import type {
    RunConfigProperties,
    StructuredOutputMode,
    AvailableModels,
    Task,
    TaskRunConfig,
  } from "$lib/types"
  import AvailableModelsDropdown from "./available_models_dropdown.svelte"
  import PromptTypeSelector from "./prompt_type_selector.svelte"
  import ToolsSelector from "./tools_selector.svelte"
  import AdvancedRunOptions from "./advanced_run_options.svelte"
  import Collapse from "$lib/ui/collapse.svelte"
  import { tick, onMount } from "svelte"
  import { ui_state } from "$lib/stores"
  import { load_task_prompts } from "$lib/stores/prompts_store"
  import type { ModelDropdownSettings } from "./model_dropdown_settings"

  // Props
  export let project_id: string
  export let current_task: Task | null = null // When task is null, certain functionality is disabled such as saving a new run config
  export let model_name: string = ""
  export let provider: string = ""
  export let model_dropdown_settings: Partial<ModelDropdownSettings> = {}
  export let selected_run_config_id: string | null = null
  export let save_config_error: KilnError | null = null
  export let set_default_error: KilnError | null = null
  export let hide_create_kiln_task_tool_button: boolean = false
  export let hide_prompt_selector: boolean = false
  export let hide_tools_selector: boolean = false
  export let show_tools_selector_in_advanced: boolean = false
  export let requires_structured_output: boolean = false
  export let hide_model_selector: boolean = false

  let model: string = $ui_state.selected_model
  let prompt_method: string = "simple_prompt_builder"
  let tools: string[] = []
  let requires_tool_support: boolean = false

  // These defaults are used by every provider I checked (OpenRouter, Fireworks, Together, etc)
  let temperature: number = 1.0
  let top_p: number = 1.0

  let structured_output_mode: StructuredOutputMode = "default"

  $: model_name = model ? model.split("/").slice(1).join("/") : ""
  $: provider = model ? model.split("/")[0] : ""
  $: requires_tool_support = tools.length > 0

  $: updated_model_dropdown_settings = {
    ...model_dropdown_settings,
    requires_tool_support: requires_tool_support,
    requires_structured_output: requires_structured_output,
  }

  let model_dropdown: AvailableModelsDropdown
  let model_dropdown_error_message: string | null = null

  onMount(async () => {
    await load_available_models()
  })

  $: if (project_id && current_task?.id) {
    load_task_prompts(project_id, current_task.id)
  }

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
  $: if (selected_run_config_id !== null) {
    update_current_run_options_if_needed()
  }

  async function update_current_run_options_if_needed() {
    const selected_run_config = await get_selected_run_config()
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
  $: void (model,
  prompt_method,
  temperature,
  top_p,
  structured_output_mode,
  tools,
  reset_to_custom_options_if_needed())

  async function reset_to_custom_options_if_needed() {
    const selected_run_config = await get_selected_run_config()
    if (!selected_run_config || selected_run_config === "custom") {
      return
    }
    // Wait for all reactive statements to complete
    await tick()

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

  export async function save_new_run_config(): Promise<TaskRunConfig | null> {
    if (!current_task?.id) {
      return null
    }
    try {
      save_config_error = null
      const saved_config = await save_new_task_run_config(
        project_id,
        current_task.id,
        run_options_as_run_config_properties(),
      )
      // Reload prompts to update the dropdown with the new static prompt that is made from saving a new run config
      await load_task_prompts(project_id, current_task.id)
      if (!saved_config || !saved_config.id) {
        throw new Error("Saved config id not found")
      }
      return saved_config
    } catch (e) {
      save_config_error = createKilnError(e)
    }
    return null
  }

  async function get_selected_run_config(): Promise<
    TaskRunConfig | "custom" | null
  > {
    if (!current_task?.id) {
      return null
    }
    // Make sure the task run configs are loaded, will be quick if they already are
    await load_task_run_configs(project_id, current_task.id)

    // Map selected ID back to TaskRunConfig object
    if (!selected_run_config_id) {
      return null
    } else if (selected_run_config_id === "custom") {
      return "custom"
    } else {
      // Find the config by ID
      const all_configs =
        $run_configs_by_task_composite_id[
          get_task_composite_id(project_id, current_task.id)
        ] ?? []
      let run_config = all_configs.find(
        (config) => config.id === selected_run_config_id,
      )
      return run_config ?? "custom"
    }
  }

  // Expose methods for run parent component
  export function get_selected_model(): string | null {
    return model_dropdown ? model_dropdown.get_selected_model() : null
  }

  export function clear_run_options_errors() {
    save_config_error = null
    set_default_error = null
  }

  export function clear_model_dropdown_error() {
    model_dropdown_error_message = null
  }

  export function set_model_dropdown_error(message: string) {
    model_dropdown_error_message = message
  }

  export function get_prompt_method(): string {
    return prompt_method
  }

  export function get_tools(): string[] {
    return tools
  }

  export function clear_tools() {
    tools = []
  }
</script>

<div class="w-full flex flex-col gap-4">
  {#if !hide_model_selector}
    <AvailableModelsDropdown
      task_id={current_task?.id ?? null}
      bind:model
      settings={updated_model_dropdown_settings}
      bind:error_message={model_dropdown_error_message}
      bind:this={model_dropdown}
    />
  {/if}
  {#if !hide_prompt_selector}
    <PromptTypeSelector
      bind:prompt_method
      info_description="Choose a prompt. Learn more on the 'Prompts' tab."
      bind:linked_model_selection={model}
    />
  {/if}
  {#if !show_tools_selector_in_advanced}
    {#if !hide_tools_selector}
      <ToolsSelector
        bind:tools
        {project_id}
        task_id={current_task?.id ?? null}
        {hide_create_kiln_task_tool_button}
      />
    {/if}
    <Collapse title="Advanced Options">
      <AdvancedRunOptions
        bind:temperature
        bind:top_p
        bind:structured_output_mode
        has_structured_output={requires_structured_output}
      />
    </Collapse>
  {:else}
    <Collapse title="Advanced Options">
      <div class="flex flex-col gap-0">
        {#if !hide_tools_selector}
          <ToolsSelector
            bind:tools
            {project_id}
            task_id={current_task?.id ?? null}
            {hide_create_kiln_task_tool_button}
          />
        {/if}
        <AdvancedRunOptions
          bind:temperature
          bind:top_p
          bind:structured_output_mode
          has_structured_output={requires_structured_output}
        />
      </div>
    </Collapse>
  {/if}
</div>
