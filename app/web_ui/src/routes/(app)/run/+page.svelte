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
  import FormElement from "$lib/utils/form_element.svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
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
  import { tick } from "svelte"

  let error: KilnError | null = null
  let submitting = false
  let run_complete = false

  let input_form: RunInputForm
  let output_section: HTMLElement | null = null

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

  let prompt_type_selector: PromptTypeSelector
  let response: TaskRun | null = null
  $: run_focus = !response

  // Quick start state
  let selected_tab: "default" | "new" | "saved" = "new"
  let selected_saved_config: string | null = null
  let dropdown_open: boolean = false
  let selectedElement: HTMLElement
  let dropdownElement: HTMLElement

  // Create select options with section headers
  const quick_start_options: OptionGroup[] = [
    {
      label: "Task Default",
      options: [{ value: "default", label: "Run options 2" }],
    },
    {
      label: "Saved Run Options",
      options: [
        { value: "saved_config1", label: "Run options 1" },
        { value: "saved_config3", label: "Run options 3" },
      ],
    },
  ]

  // Handle changes to selected_tab from the fancy select
  $: if (selected_tab) {
    if (selected_tab.startsWith("saved_")) {
      selected_saved_config = selected_tab
      selected_tab = "saved"
    } else if (selected_tab === "default") {
      selected_saved_config = null
    } else if (selected_tab === "new") {
      selected_saved_config = null
    }
  }

  function getSavedConfigName(): string {
    if (!selected_saved_config) return "Saved Configuration"

    // Find the saved config name from the options
    for (const group of quick_start_options) {
      for (const option of group.options) {
        if (option.value === selected_saved_config) {
          return option.label
        }
      }
    }
    return "Saved Configuration"
  }

  // Handle click outside to close dropdown
  function handleDocumentClick(event: MouseEvent) {
    if (
      dropdown_open &&
      selectedElement &&
      !selectedElement.contains(event.target as Node) &&
      dropdownElement &&
      !dropdownElement.contains(event.target as Node)
    ) {
      dropdown_open = false
    }
  }

  // Add/remove event listener when dropdown state changes
  $: if (dropdown_open) {
    document.addEventListener("click", handleDocumentClick)
  } else {
    document.removeEventListener("click", handleDocumentClick)
  }

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
        <div class="text-xl font-bold">Run Options</div>

        <!-- Run Options Container with Border -->
        <div
          class="rounded-lg border border-base-300 p-4 flex flex-col gap-4 min-w-[400px]"
        >
          <div>
            <PromptTypeSelector
              bind:prompt_method
              info_description="Choose a prompt. Learn more on the 'Prompts' tab."
              bind:linked_model_selection={model}
              bind:this={prompt_type_selector}
              read_only={selected_tab === "default" || selected_tab === "saved"}
            />
          </div>
          <div>
            <AvailableModelsDropdown
              bind:model
              bind:requires_structured_output
              bind:requires_tool_support={requires_tools}
              bind:error_message={model_dropdown_error_message}
              bind:this={model_dropdown}
              read_only={selected_tab === "default" || selected_tab === "saved"}
            />
          </div>
          {#if $current_project?.id}
            <div
              class={selected_tab === "default" || selected_tab === "saved"
                ? "pointer-events-auto"
                : ""}
            >
              <Collapse
                title="Advanced Options"
                badge={tools.length > 0 ? "" + tools.length : null}
              >
                <div>
                  <RunOptions
                    bind:tools
                    bind:temperature
                    bind:top_p
                    bind:structured_output_mode
                    has_structured_output={requires_structured_output}
                    project_id={$current_project?.id}
                    task_id={$current_task?.id || ""}
                    read_only={selected_tab === "default" ||
                      selected_saved_config}
                  />
                </div>
              </Collapse>
            </div>
          {/if}
        </div>

        <!-- Action Buttons -->
        <div class="flex justify-end items-center gap-2 min-w-[400px]">
          <button
            class="btn btn-sm flex-1 {selected_tab === 'new'
              ? 'btn-primary'
              : 'btn-disabled'}"
            disabled={selected_tab !== "new"}
          >
            Save Configuration
          </button>
          <button
            class="btn btn-sm flex-1 {selected_tab === 'new' ||
            selected_tab === 'saved'
              ? 'hover:btn-error active:btn-error'
              : 'btn-disabled'}"
            disabled={selected_tab !== "new" && selected_tab !== "saved"}
          >
            Promote to Default
          </button>
        </div>

        <!-- Quick Select -->
        <div class="mt-4 min-w-[400px]">
          <div class="text-sm font-medium mb-1">Quick Select</div>
          <div
            class="text-xs text-gray-500 mb-2 flex items-center justify-between"
          >
            <span
              >Select a saved configuration to override the current options.</span
            >
            <div class="text-gray-500">
              <InfoTooltip
                tooltip_text="Selected options will be read-only."
                position="bottom"
              />
            </div>
          </div>

          <!-- Custom dropdown with clear button inside -->
          <div class="dropdown w-full relative">
            <div
              tabindex="0"
              role="listbox"
              class="select select-bordered w-full flex items-center cursor-pointer"
              bind:this={selectedElement}
              on:click={() => {
                dropdown_open = !dropdown_open
              }}
            >
              <span class="truncate flex-1">
                {#if selected_tab === "new"}
                  Select an option
                {:else if selected_tab === "default"}
                  Task Default: Run options 2
                {:else if selected_tab === "saved"}
                  Saved Run Options: {selected_saved_config ||
                    "Saved configuration"}
                {:else}
                  Select an option
                {/if}
              </span>
            </div>

            {#if dropdown_open}
              <div
                bind:this={dropdownElement}
                class="bg-base-100 rounded-box z-[1000] p-2 shadow border flex flex-col fixed mt-1"
                style="width: {selectedElement?.offsetWidth || 0}px;"
              >
                <!-- Clear button at the top -->
                {#if selected_tab === "default" || selected_tab === "saved"}
                  <div class="p-2 border-b border-base-200">
                    <button
                      class="pointer-events-auto w-full text-left px-2 py-1 hover:bg-base-200 rounded text-sm flex items-center"
                      on:click={() => {
                        selected_tab = "new"
                        selected_saved_config = null
                        dropdown_open = false
                      }}
                    >
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        width="14"
                        height="14"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        class="mr-2"
                      >
                        <line x1="18" y1="6" x2="6" y2="18"></line>
                        <line x1="6" y1="6" x2="18" y2="18"></line>
                      </svg>
                      Clear Selection
                    </button>
                  </div>
                {/if}

                <!-- Options -->
                <ul class="menu overflow-y-auto flex-1">
                  {#each quick_start_options as option_group}
                    {#if option_group.label}
                      <li class="menu-title pl-1">
                        {option_group.label}
                      </li>
                    {/if}
                    {#each option_group.options as option}
                      <li>
                        <button
                          class="pointer-events-auto {(selected_tab ===
                            'saved' &&
                            selected_saved_config === option.label) ||
                          selected_tab === option.value
                            ? 'active'
                            : ''}"
                          on:click={() => {
                            if (option.value.startsWith("saved_")) {
                              selected_tab = "saved"
                              selected_saved_config = option.label
                            } else {
                              selected_tab = option.value
                              selected_saved_config = null
                            }
                            dropdown_open = false
                          }}
                        >
                          {option.label}
                        </button>
                      </li>
                    {/each}
                  {/each}
                </ul>
              </div>
            {/if}
          </div>
        </div>
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
