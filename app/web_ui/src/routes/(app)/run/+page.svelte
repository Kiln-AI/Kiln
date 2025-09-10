<script lang="ts">
  import AppPage from "../app_page.svelte"
  import {
    current_task,
    current_project,
    ui_state,
    available_models,
    available_model_details,
  } from "$lib/stores"
  import {
    load_task_run_configs,
    run_config_from_id,
  } from "$lib/stores/run_configs_store"
  import { createKilnError } from "$lib/utils/error_handlers"
  import FormContainer from "$lib/utils/form_container.svelte"
  import PromptTypeSelector from "./prompt_type_selector.svelte"
  import { KilnError } from "$lib/utils/error_handlers"
  import Run from "./run.svelte"
  import { client } from "$lib/api_client"
  import type {
    TaskRun,
    StructuredOutputMode,
    AvailableModels,
    TaskRunConfig,
  } from "$lib/types"
  import AvailableModelsDropdown from "./available_models_dropdown.svelte"
  import RunInputForm from "./run_input_form.svelte"
  import AdvancedRunOptions from "./advanced_run_options.svelte"
  import Collapse from "$lib/ui/collapse.svelte"
  import posthog from "posthog-js"
  import { tick } from "svelte"
  import RunOptionsDropdown from "./run_options_dropdown.svelte"

  let error: KilnError | null = null
  let submitting = false
  let run_complete = false

  let input_form: RunInputForm
  let output_section: HTMLElement | null = null

  let selected_run_config: string = "custom"
  // Options object to encapsulate all run configuration values
  let options = createDefaultCustomOptions()

  $: model_name = options.model
    ? options.model.split("/").slice(1).join("/")
    : ""
  $: provider = options.model ? options.model.split("/")[0] : ""

  // Update form values when selected_run_config changes
  $: if (selected_run_config) {
    if (selected_run_config === "custom") {
      // Reset to default values
      options = createDefaultCustomOptions()
    } else {
      // Populate values from saved configuration
      const task_run_config = run_config_from_id(selected_run_config, task_id)
      if (task_run_config) {
        options = createOptionsFromConfig(task_run_config)
      }
    }
  }

  // Helper function to create default custom options
  function createDefaultCustomOptions() {
    return {
      prompt_method: "simple_prompt_builder",
      model: $ui_state.selected_model,
      // These defaults are used by every provider I checked (OpenRouter, Fireworks, Together, etc)
      temperature: 1.0,
      top_p: 1.0,
      structured_output_mode: "default" as StructuredOutputMode,
      tools: [] as string[],
    }
  }

  // Helper function to create options from a task run config
  function createOptionsFromConfig(task_run_config: TaskRunConfig) {
    return {
      model: `${task_run_config.run_config_properties.model_provider_name}/${task_run_config.run_config_properties.model_name}`,
      prompt_method: task_run_config.run_config_properties.prompt_id,
      temperature: task_run_config.run_config_properties.temperature,
      top_p: task_run_config.run_config_properties.top_p,
      structured_output_mode:
        task_run_config.run_config_properties.structured_output_mode,
      tools: task_run_config.run_config_properties.tools_config?.tools || [],
    }
  }

  // Function to check if current values differ from selected run config
  function checkForManualChanges() {
    if (selected_run_config !== "custom") {
      const task_run_config = run_config_from_id(selected_run_config, task_id)
      if (task_run_config) {
        const config_options = createOptionsFromConfig(task_run_config)

        // Check if any values have changed from the saved config
        if (
          options.model !== config_options.model ||
          options.prompt_method !== config_options.prompt_method ||
          options.temperature !== config_options.temperature ||
          options.top_p !== config_options.top_p ||
          options.structured_output_mode !==
            config_options.structured_output_mode ||
          JSON.stringify(options.tools) !== JSON.stringify(config_options.tools)
        ) {
          selected_run_config = "custom"
        }
      }
    }
  }

  // Check for manual changes when form values change
  $: options, checkForManualChanges()

  let model_dropdown: AvailableModelsDropdown
  let model_dropdown_error_message: string | null = null

  let response: TaskRun | null = null
  $: run_focus = !response

  $: subtitle = $current_task ? "Task: " + $current_task.name : ""
  $: input_schema = $current_task?.input_json_schema
  $: requires_structured_output = !!$current_task?.output_json_schema
  $: requires_tool_support = options.tools.length > 0
  $: task_id = $current_task?.id || ""

  // Load run configs when both project and task are available
  $: if ($current_project?.id && $current_task?.id) {
    load_task_run_configs($current_project.id, $current_task.id)
  }

  // Model defaults come from available_models store

  // Update structured_output_mode when model changes
  $: update_structured_output_mode(model_name, provider, $available_models)
  function update_structured_output_mode(
    model_name: string,
    provider: string,
    available_models: AvailableModels[],
  ) {
    options.structured_output_mode =
      available_model_details(model_name, provider, available_models)
        ?.structured_output_mode || "default"
  }

  // Check if the Output section headers are visible in the viewport
  // We only care about the top portion being visible (headers + some buffer)
  function isElementPartiallyVisible(element: HTMLElement): boolean {
    const rect = element.getBoundingClientRect()
    const viewportHeight =
      window.innerHeight || document.documentElement.clientHeight

    // Check if the top of the element is visible and there's enough buffer
    // We want to see the headers (roughly 100px from top) plus some buffer
    // If the element is smaller than 100px, just check if it's fully visible
    const bufferSize = Math.min(100, rect.height)
    return rect.top >= 0 && rect.top <= viewportHeight - bufferSize
  }

  // Smooth scroll to output section if it's not visible
  function scrollToOutputIfNeeded() {
    if (output_section && !isElementPartiallyVisible(output_section)) {
      // Calculate the target scroll position to show just the headers + buffer
      const rect = output_section.getBoundingClientRect()
      const currentScrollTop =
        window.pageYOffset || document.documentElement.scrollTop
      const viewportHeight =
        window.innerHeight || document.documentElement.clientHeight

      // Position the Output section so that 200px of it is visible from the top
      // This shows the headers and some buffer, but not the entire section
      // If the element is smaller than 200px, show the entire element
      const visibleHeight = Math.min(200, rect.height)
      const targetScrollTop =
        currentScrollTop + rect.top - (viewportHeight - visibleHeight)

      window.scrollTo({
        top: targetScrollTop,
        behavior: "smooth",
      })
    }
  }

  async function run_task() {
    try {
      submitting = true
      error = null
      response = null
      run_complete = false
      model_dropdown_error_message = null
      let selected_model = model_dropdown.get_selected_model()
      if (!selected_model || selected_model != options.model) {
        model_dropdown_error_message = "Required"
        throw new Error("You must select a model before running")
      }
      const {
        data, // only present if 2XX response
        error: fetch_error, // only present if 4XX or 5XX response
      } = await client.POST("/api/projects/{project_id}/tasks/{task_id}/run", {
        params: {
          path: {
            project_id: $current_project?.id || "",
            task_id: task_id,
          },
        },
        body: {
          run_config_properties: {
            model_name: model_name,
            model_provider_name: provider,
            prompt_id: options.prompt_method,
            temperature: options.temperature,
            top_p: options.top_p,
            structured_output_mode: options.structured_output_mode,
            tools_config: {
              tools: options.tools,
            },
          },
          plaintext_input: input_form.get_plaintext_input_data(),
          // @ts-expect-error openapi-fetch generates the wrong type for this: Record<string, never>
          structured_input: input_form.get_structured_input_data(),
          tags: ["manual_run"],
        },
      })
      if (fetch_error) {
        throw fetch_error
      }
      posthog.capture("run_task", {
        model_name: model_name,
        provider: provider,
        prompt_method: options.prompt_method,
      })
      response = data
    } catch (e) {
      error = createKilnError(e)
    } finally {
      submitting = false
      await tick() // ensure {#if !submitting && response} has rendered
      if (response) scrollToOutputIfNeeded()
    }
  }

  function clear_all() {
    input_form.clear_input()
    response = null
    run_complete = false
  }

  function next_task_run() {
    // Keep the input, but clear the response
    response = null
    run_complete = false
    clear_all()
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Run"
    bind:subtitle
    action_buttons={[{ label: "Clear All", handler: clear_all }]}
  >
    <div class="flex flex-col xl:flex-row gap-8 xl:gap-16">
      <div class="grow">
        <div class="text-xl font-bold mb-4">Input</div>
        <FormContainer
          submit_label="Run"
          on:submit={run_task}
          bind:error
          bind:submitting
          bind:primary={run_focus}
          bind:keyboard_submit={run_focus}
        >
          <RunInputForm bind:input_schema bind:this={input_form} />
        </FormContainer>
      </div>
      <div class="w-72 2xl:w-96 flex-none flex flex-col gap-4">
        <div class="text-xl font-bold">Options</div>
        <div>
          <RunOptionsDropdown bind:selected_run_config />
        </div>
        <AvailableModelsDropdown
          bind:model={options.model}
          bind:requires_structured_output
          bind:requires_tool_support
          bind:error_message={model_dropdown_error_message}
          bind:this={model_dropdown}
        />
        <div>
          <PromptTypeSelector
            bind:prompt_method={options.prompt_method}
            info_description="Choose a prompt. Learn more on the 'Prompts' tab."
            bind:linked_model_selection={options.model}
          />
        </div>
        {#if $current_project?.id}
          <Collapse
            title="Advanced Options"
            badge={options.tools.length > 0 ? "" + options.tools.length : null}
          >
            <AdvancedRunOptions
              bind:tools={options.tools}
              bind:temperature={options.temperature}
              bind:top_p={options.top_p}
              bind:structured_output_mode={options.structured_output_mode}
              has_structured_output={requires_structured_output}
              project_id={$current_project?.id}
              {task_id}
            />
          </Collapse>
        {/if}
      </div>
    </div>
    {#if $current_task && !submitting && response != null && $current_project?.id}
      <div class="mt-8 xl:mt-12" bind:this={output_section} id="output-section">
        <Run
          initial_run={response}
          task={$current_task}
          project_id={$current_project.id}
          bind:model_name
          bind:provider
          bind:run_complete
          focus_repair_on_appear={true}
        />
      </div>
    {/if}
    {#if run_complete}
      <div class="flex flex-col md:flex-row gap-6 place-content-center mt-10">
        <button
          class="btn btn-primary mt-2 min-w-48"
          on:click={() => next_task_run()}
        >
          Next Run
        </button>
      </div>
    {/if}
  </AppPage>
</div>
