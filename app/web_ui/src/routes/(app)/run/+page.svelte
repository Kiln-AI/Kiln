<script lang="ts">
  import AppPage from "../app_page.svelte"
  import {
    current_task,
    current_project,
    ui_state,
    available_models,
    available_model_details,
    load_available_prompts,
    load_current_task,
  } from "$lib/stores"
  import {
    save_new_task_run_config,
    run_configs_by_task_composite_id,
    get_task_composite_id,
  } from "$lib/stores/run_configs_store"
  import { createKilnError } from "$lib/utils/error_handlers"
  import FormContainer from "$lib/utils/form_container.svelte"
  import PromptTypeSelector from "./prompt_type_selector.svelte"
  import { KilnError } from "$lib/utils/error_handlers"
  import Run from "./run.svelte"
  import { client } from "$lib/api_client"
  import type {
    TaskRun,
    TaskRunConfig,
    RunConfigProperties,
    StructuredOutputMode,
    AvailableModels,
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

  let selected_run_config_id: string | "custom" = "custom"
  let updating_current_run_options = false

  let prompt_method = "simple_prompt_builder"
  let model: string = $ui_state.selected_model
  // These defaults are used by every provider I checked (OpenRouter, Fireworks, Together, etc)
  let temperature: number = 1.0
  let top_p: number = 1.0
  let structured_output_mode: StructuredOutputMode = "default"
  let tools: string[] = []

  $: model_name = model ? model.split("/").slice(1).join("/") : ""
  $: provider = model ? model.split("/")[0] : ""

  let model_dropdown: AvailableModelsDropdown
  let model_dropdown_error_message: string | null = null

  let response: TaskRun | null = null
  $: run_focus = !response

  $: subtitle = $current_task ? "Task: " + $current_task.name : ""
  $: input_schema = $current_task?.input_json_schema
  $: requires_structured_output = !!$current_task?.output_json_schema
  $: requires_tool_support = tools.length > 0

  // Model defaults come from available_models store

  // Update structured_output_mode when model changes
  $: update_structured_output_mode(model_name, provider, $available_models)
  function update_structured_output_mode(
    model_name: string,
    provider: string,
    available_models: AvailableModels[],
  ) {
    if (requires_structured_output) {
      structured_output_mode =
        available_model_details(model_name, provider, available_models)
          ?.structured_output_mode || "default"
    }
  }

  // Check if the Output section headers are visible in the viewport
  // We only care about the top portion being visible (headers + some buffer)
  function is_element_partially_visible(element: HTMLElement): boolean {
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
  function scroll_to_output_if_needed() {
    if (output_section && !is_element_partially_visible(output_section)) {
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
      if (!selected_model || selected_model != model) {
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
            task_id: $current_task?.id || "",
          },
        },
        body: {
          run_config_properties: run_options_as_run_config_properties(),
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
        prompt_method: prompt_method,
      })
      response = data
    } catch (e) {
      error = createKilnError(e)
    } finally {
      submitting = false
      await tick() // ensure {#if !submitting && response} has rendered
      if (response) scroll_to_output_if_needed()
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

  // Handle save run options button clicked from AdvancedRunOptions component
  async function handle_save_run_options() {
    if (!$current_project?.id || !$current_task?.id) {
      return
    }
    try {
      const saved_config = await save_new_task_run_config(
        $current_project.id,
        $current_task.id,
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
            get_task_composite_id(
              $current_project?.id ?? "",
              $current_task?.id ?? "",
            )
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
      error = createKilnError(e)
      // TODO: Show error to user
    }
  }

  $: show_set_as_default_button = (() => {
    if (selected_run_config_id === "custom") {
      return false
    }
    return selected_run_config_id !== $current_task?.default_run_config_id
  })()

  async function handle_set_as_default() {
    if (!$current_project?.id || !$current_task?.id) {
      return
    }
    // Update task default run config
    try {
      await client.PATCH("/api/projects/{project_id}/task/{task_id}", {
        params: {
          path: {
            project_id: $current_project?.id ?? "",
            task_id: $current_task?.id ?? "",
          },
        },
        body: {
          // @ts-expect-error openapi-fetch generates the wrong type for this: Record<string, never>
          default_run_config_id: (selected_run_config as TaskRunConfig).id,
        },
      })
      await load_current_task($current_project)
      await tick()
      if (default_run_config_id) {
        selected_run_config_id = default_run_config_id
      }
    } catch (e) {
      error = createKilnError(e)
      // TODO: Show error to user
    }
  }

  let default_run_config_id: string | null

  // Map selected ID back to TaskRunConfig object
  $: selected_run_config = (() => {
    if (selected_run_config_id === "custom") {
      return "custom"
    }

    // Find the config by ID
    const all_configs =
      $run_configs_by_task_composite_id[
        get_task_composite_id(
          $current_project?.id ?? "",
          $current_task?.id ?? "",
        )
      ] ?? ([] as TaskRunConfig[])
    return (
      all_configs.find((config) => config.id === selected_run_config_id) ??
      "custom"
    )
  })()

  $: $current_task,
    $run_configs_by_task_composite_id,
    update_default_run_config()

  function update_default_run_config() {
    if ($current_task?.default_run_config_id) {
      default_run_config_id = $current_task.default_run_config_id
    } else {
      default_run_config_id = null
    }
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
          {#if $current_project?.id && $current_task?.id}
            <RunOptionsDropdown
              bind:selected_run_config_id
              bind:default_run_config_id
            />
          {/if}
        </div>
        <AvailableModelsDropdown
          bind:model
          bind:requires_structured_output
          bind:requires_tool_support
          bind:error_message={model_dropdown_error_message}
          bind:this={model_dropdown}
        />
        <div>
          <PromptTypeSelector
            bind:prompt_method
            info_description="Choose a prompt. Learn more on the 'Prompts' tab."
            bind:linked_model_selection={model}
          />
        </div>
        {#if $current_project?.id}
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
              project_id={$current_project?.id}
              task_id={$current_task?.id || ""}
              on:saveRunOptions={handle_save_run_options}
              on:setToDefault={handle_set_as_default}
              show_save_button={selected_run_config_id === "custom"}
              {show_set_as_default_button}
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
