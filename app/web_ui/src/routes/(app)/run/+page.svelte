<script lang="ts">
  import AppPage from "../app_page.svelte"
  import { current_task, current_project } from "$lib/stores"
  import { createKilnError } from "$lib/utils/error_handlers"
  import FormContainer from "$lib/utils/form_container.svelte"
  import { KilnError } from "$lib/utils/error_handlers"
  import Run from "./run.svelte"
  import { client } from "$lib/api_client"
  import type { TaskRun, TaskRunConfig } from "$lib/types"
  import RunInputForm from "./run_input_form.svelte"
  import posthog from "posthog-js"
  import { tick } from "svelte"
  import RunConfigComponent from "$lib/ui/run_config_component/run_config_component.svelte"
  import SavedRunConfigurationsDropdown from "$lib/ui/run_config_component/saved_run_configs_dropdown.svelte"

  let run_error: KilnError | null = null
  let submitting = false
  let run_complete = false

  let input_form: RunInputForm
  let output_section: HTMLElement | null = null
  let model_name: string = ""
  let provider: string = ""
  let selected_run_config_id: string | null = null

  let run_config_component: RunConfigComponent
  let save_config_error: KilnError | null = null
  let set_default_error: KilnError | null = null

  let response: TaskRun | null = null
  $: run_focus = !response

  $: project_id = $current_project?.id ?? ""
  $: task_id = $current_task?.id ?? ""
  $: input_schema = $current_task?.input_json_schema

  $: subtitle = $current_task ? "Task: " + $current_task.name : ""

  async function run_task() {
    try {
      submitting = true
      run_error = null
      response = null
      run_complete = false
      if (!run_config_component) {
        throw new Error(
          "Task configuration is still loading. Please wait a moment and try again.",
        )
      }
      run_config_component.clear_run_options_errors()
      run_config_component.clear_model_dropdown_error()
      if (!run_config_component.get_selected_model()) {
        run_config_component.set_model_dropdown_error("Required")
        throw new Error("You must select a model before running")
      }
      const {
        data, // only present if 2XX response
        error: fetch_error, // only present if 4XX or 5XX response
      } = await client.POST("/api/projects/{project_id}/tasks/{task_id}/run", {
        params: {
          path: {
            project_id: project_id,
            task_id: task_id,
          },
        },
        body: {
          run_config_properties:
            run_config_component.run_options_as_run_config_properties(),
          plaintext_input: input_form.get_plaintext_input_data(),
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
        prompt_method: run_config_component.get_prompt_method(),
        tool_count: run_config_component.get_tools().length,
        search_tools: run_config_component
          .get_tools()
          .filter((tool) => tool.startsWith("kiln_tool::rag::")).length,
        mcp_tools: run_config_component
          .get_tools()
          .filter((tool) => tool.startsWith("mcp::")).length,
        kiln_task_tools: run_config_component
          .get_tools()
          .filter((tool) => tool.startsWith("kiln_task::")).length,
      })
      response = data
    } catch (e) {
      run_error = createKilnError(e)
    } finally {
      submitting = false
      await tick() // ensure {#if !submitting && response} has rendered
      if (response) scroll_to_output_if_needed()
      run_complete = true
    }
  }

  function clear_all() {
    input_form.clear_input()
    response = null
    run_complete = false
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

  async function handle_save_new_run_config(): Promise<TaskRunConfig | null> {
    try {
      if (!run_config_component) {
        throw new Error("Run configuration component is not loaded")
      }
      return await run_config_component.save_new_run_config()
    } catch (e) {
      save_config_error = createKilnError(e)
    }
    return null
  }

  function handle_input_change() {
    if (response) {
      response = null
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
          bind:error={run_error}
          bind:submitting
          bind:primary={run_focus}
          bind:keyboard_submit={run_focus}
        >
          <RunInputForm
            bind:input_schema
            bind:this={input_form}
            onInputChange={handle_input_change}
          />
        </FormContainer>
      </div>
      {#if $current_task}
        <div class="w-72 2xl:w-96 flex-none flex flex-col gap-4">
          <div class="text-xl font-bold">Options</div>
          <SavedRunConfigurationsDropdown
            {project_id}
            current_task={$current_task}
            bind:selected_run_config_id
            bind:save_config_error
            bind:set_default_error
            save_new_run_config={handle_save_new_run_config}
          />
          <RunConfigComponent
            bind:this={run_config_component}
            {project_id}
            current_task={$current_task}
            requires_structured_output={!!$current_task.output_json_schema}
            bind:selected_run_config_id
            bind:save_config_error
            bind:set_default_error
          />
        </div>
      {/if}
    </div>
    {#if $current_task && !submitting && response != null && project_id}
      <div class="mt-8 xl:mt-12" bind:this={output_section} id="output-section">
        <Run
          initial_run={response}
          task={$current_task}
          {project_id}
          bind:model_name
          bind:provider
          bind:run_complete
          focus_repair_on_appear={true}
        />
      </div>
    {/if}
  </AppPage>
</div>
