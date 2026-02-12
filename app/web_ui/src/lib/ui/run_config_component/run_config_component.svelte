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
  // Model-specific suggested run config, such as fine-tuned models. If a model like that is selected, this will be set to the run config ID.
  export let selected_model_specific_run_config_id: string | null = null

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
  // We test each model in our known model list, so a smart default is selected automatically.
  function update_structured_output_mode_if_needed(
    model_name: string,
    provider: string,
    available_models: AvailableModels[],
  ) {
    if (requires_structured_output) {
      const model_details = available_model_details(
        model_name,
        provider,
        available_models,
      )
      const new_mode = model_details?.structured_output_mode || "default"
      if (new_mode !== structured_output_mode) {
        structured_output_mode = new_mode
        return true
      }
    }
  }

  // When a run config is selected, update the current run options to match the selected config
  let prior_selected_run_config_id: string | null = null
  async function update_current_run_options_for_selected_run_config() {
    // Only run once immediately after a run config selection, not every reactive update
    if (prior_selected_run_config_id === selected_run_config_id) {
      return
    }
    prior_selected_run_config_id = selected_run_config_id

    const selected_run_config = await get_selected_run_config()
    if (!selected_run_config || selected_run_config === "custom") {
      // No need to update selected_run_config_id, it's already custom or unset
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

  // Main reactive statement. This class is a bit wild, as many changes are circular.
  // Example: changing the run config will update model, but selecting model will jump back to "custom" run config (or finetune run config).
  // These are legit desired behaviour: respect the user's last selection, and make the rest consistent. But it makes updating the state a bit tricky.
  // Make 1 big reactive statement to update the state. Then we debounce it to avoid excessive updates.
  // Test cases if you edit (including a page reload version of each test):
  // 1. Select a fine-tune model, it's run config should be automatically selected and the RC's values filled
  // 2. Select a legacy fine-tune model (no run config baked in), it's prompt should be selected and RC stays custom
  // 3. Select a saved run config, should set all fields to the saved config's values
  // 4. Change any field after setting a run config, should deselect the run config to "custom"
  $: void (model,
  prompt_method,
  temperature,
  top_p,
  structured_output_mode,
  tools,
  $available_models,
  selected_run_config_id,
  debounce_update_for_state_changes())

  // Since some changes can make many other fields change (eg run config), we debounce the updates to avoid excessive updates.
  // Just mark as dirty, and run again only once, after the update is once.
  // Knowning only 1 is called in parallel also makes it simpler to reason about.
  let running: boolean = false
  let run_again: boolean = false
  async function debounce_update_for_state_changes() {
    if (running) {
      run_again = true
      return
    }
    running = true
    await tick()
    try {
      await update_for_state_changes()
    } finally {
      running = false
      if (run_again) {
        run_again = false
        debounce_update_for_state_changes()
      }
    }
  }

  // Progress step by step, stopping if any step asks to. It could be missing data, and the remaining steps aren't valid.
  async function update_for_state_changes() {
    // All steps need available_models to be loaded. Don't set run_again as it would be tight loop, we're reactive to $available_models.
    if ($available_models.length === 0) {
      return
    }

    // Check if they selected a new model, in which case we want to update the run config to the finetune run config if needed
    process_model_change()

    // Update the structured output mode to match the selected model, if needed
    update_structured_output_mode_if_needed(
      model_name,
      provider,
      $available_models,
    )

    // Update all the run options if they have changed the run config
    await update_current_run_options_for_selected_run_config()

    // deselect the run config if they have changed any run options to not match the selected run config
    await reset_to_custom_options_if_needed()
  }

  let prior_model: string | null = null
  async function process_model_change() {
    // only run once immediately after a model change, not every reactive update
    if (prior_model === model) {
      return
    }
    prior_model = model

    // Special case on model change: if the model says it has a model-specific run config, select that run config.
    // Currently used by fine-tuned models which need to be called like they are trained.
    const model_details = available_model_details(
      model_name,
      provider,
      $available_models,
    )
    if (model_details?.model_specific_run_config) {
      selected_run_config_id = model_details.model_specific_run_config
      selected_model_specific_run_config_id =
        model_details.model_specific_run_config
    } else {
      selected_model_specific_run_config_id = null
    }
  }

  async function reset_to_custom_options_if_needed() {
    const selected_run_config = await get_selected_run_config()
    if (!selected_run_config || selected_run_config === "custom") {
      return
    }

    const config_properties = selected_run_config.run_config_properties

    // Check if any values have changed from the saved config properties
    let model_changed = false
    let provider_changed = false
    let prompt_changed = false
    const current_model_name = model ? model.split("/").slice(1).join("/") : ""
    const current_provider_name = model ? model.split("/")[0] : ""
    model_changed = config_properties.model_name !== current_model_name
    provider_changed =
      config_properties.model_provider_name !== current_provider_name
    prompt_changed = config_properties.prompt_id !== prompt_method

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
      // The user has changed something, so deselect the run config - it no longer matches the selected run config
      selected_run_config_id = "custom"
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
