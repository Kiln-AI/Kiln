<script lang="ts">
  import AppPage from "../app_page.svelte"
  import {
    current_task,
    current_project,
    ui_state,
    available_models,
    available_model_details,
  } from "$lib/stores"
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
  } from "$lib/types"
  import AvailableModelsDropdown from "./available_models_dropdown.svelte"
  import RunInputForm from "./run_input_form.svelte"
  import RunOptions from "$lib/ui/run_options.svelte"
  import Collapse from "$lib/ui/collapse.svelte"
  import posthog from "posthog-js"

  let error: KilnError | null = null
  let submitting = false
  let run_complete = false

  let input_form: RunInputForm

  let prompt_method = "simple_prompt_builder"
  let model: string = $ui_state.selected_model
  let temperature: number
  let top_p: number
  let structured_output_mode: StructuredOutputMode
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
  $: requires_tools = tools.length > 0

  // Model defaults come from available_models store

  // Update structured_output_mode when model changes
  $: update_structured_output_mode(model_name, provider, $available_models)
  function update_structured_output_mode(
    model_name: string,
    provider: string,
    available_models: AvailableModels[],
  ) {
    structured_output_mode =
      available_model_details(model_name, provider, available_models)
        ?.structured_output_mode || "default"
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
          run_config_properties: {
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
        prompt_method: prompt_method,
      })
      response = data
    } catch (e) {
      error = createKilnError(e)
    } finally {
      submitting = false
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

  $: project_id = $current_project?.id || ""
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
          <PromptTypeSelector
            bind:prompt_method
            info_description="Choose a prompt. Learn more on the 'Prompts' tab."
            bind:linked_model_selection={model}
          />
        </div>
        <AvailableModelsDropdown
          bind:model
          bind:requires_structured_output
          bind:requires_tool_support={requires_tools}
          bind:error_message={model_dropdown_error_message}
          bind:this={model_dropdown}
        />
        <Collapse title="Advanced Options">
          <RunOptions
            bind:tools
            bind:temperature
            bind:top_p
            bind:structured_output_mode
            has_structured_output={requires_structured_output}
            {project_id}
          />
        </Collapse>
      </div>
    </div>
    {#if $current_task && !submitting && response != null && $current_project?.id}
      <div class="mt-10 xl:mt-24">
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
