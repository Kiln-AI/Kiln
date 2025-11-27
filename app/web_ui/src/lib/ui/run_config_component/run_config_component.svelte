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
  import { arrays_equal } from "$lib/utils/collections"
  import type { ToolsSelectorSettings } from "./tools_selector_settings"

  // Props
  export let project_id: string
  export let current_task: Task | null = null // When task is null, certain functionality is disabled such as saving a new run config
  export let model_name: string = ""
  export let provider: string = ""
  export let model_dropdown_settings: Partial<ModelDropdownSettings> = {}
  export let tools_selector_settings: Partial<ToolsSelectorSettings> = {}
  export let selected_run_config_id: string | null = null
  export let save_config_error: KilnError | null = null
  export let set_default_error: KilnError | null = null
  export let hide_prompt_selector: boolean = false
  export let hide_tools_selector: boolean = false
  export let show_tools_selector_in_advanced: boolean = false
  export let requires_structured_output: boolean = false
  export let hide_model_selector: boolean = false

  export let model: string = $ui_state.selected_model
  let prompt_method: string = "simple_prompt_builder"
  export let tools: string[] = []
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

  let is_updating_from_saved_config: boolean = false
  let prior_selected_run_config_id: string | null = null
  async function update_current_run_options_if_needed() {
    console.log(
      "update_current_run_options_if_needed",
      prior_selected_run_config_id,
      selected_run_config_id,
    )
    // Only run if the selected run config id has changed
    if (prior_selected_run_config_id === selected_run_config_id) {
      //return
    }
    prior_selected_run_config_id = selected_run_config_id
    is_updating_from_saved_config = true

    const selected_run_config = await get_selected_run_config()
    if (!selected_run_config || selected_run_config === "custom") {
      return
    }

    //is_updating_from_saved_config = true

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

    is_updating_from_saved_config = false
  }

  // Main reactive statement
  $: void (model,
  prompt_method,
  temperature,
  top_p,
  structured_output_mode,
  tools,
  $available_models,
  selected_run_config_id,
  debounce_update_for_state_changes())

  let running: boolean = false
  let run_again: boolean = false
  async function debounce_update_for_state_changes() {
    if (running) {
      run_again = true
      return
    }
    await tick()
    try {
      running = true
      await update_for_state_changes()
    } finally {
      running = false
      if (run_again) {
        run_again = false
        debounce_update_for_state_changes()
      }
    }
  }

  async function update_for_state_changes() {
    await process_model_change()
    await update_structured_output_mode_if_needed(
      model_name,
      provider,
      $available_models,
    )
    await update_current_run_options_if_needed()
    await reset_to_custom_options_if_needed()
  }

  let prior_model: string | null = null
  async function process_model_change() {
    //
    if (prior_model === model) {
      return
    }
    prior_model = model

    console.log("process_model_change", prior_model, model)

    // Special case on model change
    // if only the model changed and it changed to a finetune, select that run config
    const FINETUNE_MODEL_PREFIX = "kiln_fine_tune/"
    const is_finetune_model = model.startsWith(FINETUNE_MODEL_PREFIX)
    console.log("is_finetune_model", is_finetune_model, model)
    // Special case:
    if (is_finetune_model) {
      const finetune_id = model.substring(FINETUNE_MODEL_PREFIX.length)
      // TODO P0 handle legacy case
      const finetune_run_config_id = `finetune_run_config::${finetune_id}`
      selected_run_config_id = finetune_run_config_id
      console.log(
        "selected_run_config_id set to finetune run config in RunConfigComponent",
        selected_run_config_id,
        finetune_id,
        finetune_run_config_id,
      )
    }
  }

  async function reset_to_custom_options_if_needed() {
    if (is_updating_from_saved_config) {
      return
    }
    console.log("reset_to_custom_options_if_needed", model)
    // If we are updating from a saved config don't reset back to custom
    /*if (is_updating_from_saved_config) {
      return
    }*/

    const selected_run_config = await get_selected_run_config()
    if (!selected_run_config || selected_run_config === "custom") {
      return
    }
    // Wait for all reactive statements to complete
    await tick()

    const config_properties = selected_run_config.run_config_properties

    const is_finetune_run_config = selected_run_config.id?.startsWith(
      "finetune_run_config::",
    )

    // Check if any values have changed from the saved config properties
    let model_changed = false
    let provider_changed = false
    let prompt_changed = false

    if (is_finetune_run_config) {
      // TODO P0 deelte special case
      const finetune_id = selected_run_config.id?.split("::").pop()
      const expected_model = `kiln_fine_tune/${project_id}::${current_task?.id}::${finetune_id}`
      const expected_prompt = `fine_tune_prompt::${project_id}::${current_task?.id}::${finetune_id}`
      model_changed = model !== expected_model
      prompt_changed = prompt_method !== expected_prompt
      provider_changed = provider !== "kiln_fine_tune"
      // TODO P0
      provider_changed = false
    } else {
      const current_model_name = model
        ? model.split("/").slice(1).join("/")
        : ""
      const current_provider_name = model ? model.split("/")[0] : ""
      model_changed = config_properties.model_name !== current_model_name
      provider_changed =
        config_properties.model_provider_name !== current_provider_name
      prompt_changed = config_properties.prompt_id !== prompt_method
    }

    console.log("model_changed", model_changed)
    console.log("provider_changed", provider_changed)
    console.log("prompt_changed", prompt_changed)
    console.log("temperature", temperature)
    console.log("top_p", top_p)
    console.log("structured_output_mode", structured_output_mode)
    console.log("tools", tools)
    console.log("config_properties.temperature", config_properties.temperature)
    console.log("config_properties.top_p", config_properties.top_p)
    console.log(
      "config_properties.structured_output_mode",
      config_properties.structured_output_mode,
    )
    console.log(
      "config_properties.tools_config?.tools",
      config_properties.tools_config?.tools,
    )
    console.log(
      "arrays_equal(config_properties.tools_config?.tools ?? [], tools)",
      arrays_equal(config_properties.tools_config?.tools ?? [], tools),
    )
    // Legacy models can be "unknown". Don't consider those as mismatches.
    const output_mode_mismatch =
      config_properties.structured_output_mode !== "unknown" &&
      config_properties.structured_output_mode !== structured_output_mode
    if (
      model_changed ||
      provider_changed ||
      prompt_changed ||
      config_properties.temperature !== temperature ||
      config_properties.top_p !== top_p ||
      output_mode_mismatch ||
      !arrays_equal(config_properties.tools_config?.tools ?? [], tools)
    ) {
      selected_run_config_id = "custom"
      console.log(
        "selected_run_config_id set to custom in RunConfigComponent",
        selected_run_config_id,
      )
    }
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
        ]
      // TODO P0 - is this change correct?
      if (!all_configs) {
        return null
      }
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
    return [...tools]
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
        settings={tools_selector_settings}
      />
    {/if}
    <Collapse title="Advanced Options">
      <slot name="advanced" />
      <AdvancedRunOptions
        bind:temperature
        bind:top_p
        bind:structured_output_mode
        has_structured_output={requires_structured_output}
      />
    </Collapse>
  {:else}
    <Collapse title="Advanced Options">
      <slot name="advanced" />
      {#if !hide_tools_selector}
        <ToolsSelector
          bind:tools
          {project_id}
          task_id={current_task?.id ?? null}
          settings={tools_selector_settings}
        />
      {/if}
      <AdvancedRunOptions
        bind:temperature
        bind:top_p
        bind:structured_output_mode
        has_structured_output={requires_structured_output}
      />
    </Collapse>
  {/if}
</div>
