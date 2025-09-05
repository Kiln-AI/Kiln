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

  // Segmented control state
  let selected_tab: "default" | "new" | "saved" = "default"
  let show_saved_dropdown = false
  let selected_saved_config: string | null = null

  // Dummy saved run configurations
  const saved_configs = [
    { id: "config1", name: "Run config 1" },
    { id: "config2", name: "Run config 2" },
    { id: "config3", name: "Run config 3" },
  ]

  // Close dropdown when clicking outside
  function handleClickOutside(event: MouseEvent) {
    if (show_saved_dropdown) {
      show_saved_dropdown = false
    }
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
    <div
      class="flex flex-col xl:flex-row gap-8 xl:gap-16"
      on:click={handleClickOutside}
    >
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
        <div class="text-xl font-bold">Run Configuration</div>

        <!-- Segmented Control -->
        <div
          class="flex bg-base-200 rounded-xl p-1 mb-4 gap-1 shadow-sm border border-base-300/20 min-w-[400px]"
        >
          <button
            class="flex-1 px-4 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 hover:text-base-content hover:bg-base-100/50 h-12 flex items-center justify-center min-w-0 {selected_tab ===
            'default'
              ? 'text-base-content'
              : 'text-base-content/70'}"
            class:bg-base-100={selected_tab === "default"}
            class:bg-transparent={selected_tab !== "default"}
            class:shadow-sm={selected_tab === "default"}
            class:font-semibold={selected_tab === "default"}
            on:click={() => {
              selected_tab = "default"
              selected_saved_config = null
            }}
          >
            <div class="flex items-center gap-1">
              <svg
                class="w-3 h-3 opacity-60"
                viewBox="0 0 24 24"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
              >
                <circle
                  cx="12"
                  cy="12"
                  r="3"
                  stroke="currentColor"
                  stroke-width="1.5"
                />
                <path
                  d="M13.7654 2.15224C13.3978 2 12.9319 2 12 2C11.0681 2 10.6022 2 10.2346 2.15224C9.74457 2.35523 9.35522 2.74458 9.15223 3.23463C9.05957 3.45834 9.0233 3.7185 9.00911 4.09799C8.98826 4.65568 8.70226 5.17189 8.21894 5.45093C7.73564 5.72996 7.14559 5.71954 6.65219 5.45876C6.31645 5.2813 6.07301 5.18262 5.83294 5.15102C5.30704 5.08178 4.77518 5.22429 4.35436 5.5472C4.03874 5.78938 3.80577 6.1929 3.33983 6.99993C2.87389 7.80697 2.64092 8.21048 2.58899 8.60491C2.51976 9.1308 2.66227 9.66266 2.98518 10.0835C3.13256 10.2756 3.3397 10.437 3.66119 10.639C4.1338 10.936 4.43789 11.4419 4.43786 12C4.43783 12.5581 4.13375 13.0639 3.66118 13.3608C3.33965 13.5629 3.13248 13.7244 2.98508 13.9165C2.66217 14.3373 2.51966 14.8691 2.5889 15.395C2.64082 15.7894 2.87379 16.193 3.33973 17C3.80568 17.807 4.03865 18.2106 4.35426 18.4527C4.77508 18.7756 5.30694 18.9181 5.83284 18.8489C6.07289 18.8173 6.31632 18.7186 6.65204 18.5412C7.14547 18.2804 7.73556 18.27 8.2189 18.549C8.70224 18.8281 8.98826 19.3443 9.00911 19.9021C9.02331 20.2815 9.05957 20.5417 9.15223 20.7654C9.35522 21.2554 9.74457 21.6448 10.2346 21.8478C10.6022 22 11.0681 22 12 22C12.9319 22 13.3978 22 13.7654 21.8478C14.2554 21.6448 14.6448 21.2554 14.8477 20.7654C14.9404 20.5417 14.9767 20.2815 14.9909 19.902C15.0117 19.3443 15.2977 18.8281 15.781 18.549C16.2643 18.2699 16.8544 18.2804 17.3479 18.5412C17.6836 18.7186 17.927 18.8172 18.167 18.8488C18.6929 18.9181 19.2248 18.7756 19.6456 18.4527C19.9612 18.2105 20.1942 17.807 20.6601 16.9999C21.1261 16.1929 21.3591 15.7894 21.411 15.395C21.4802 14.8691 21.3377 14.3372 21.0148 13.9164C20.8674 13.7243 20.6602 13.5628 20.3387 13.3608C19.8662 13.0639 19.5621 12.558 19.5621 11.9999C19.5621 11.4418 19.8662 10.9361 20.3387 10.6392C20.6603 10.4371 20.8675 10.2757 21.0149 10.0835C21.3378 9.66273 21.4803 9.13087 21.4111 8.60497C21.3592 8.21055 21.1262 7.80703 20.6602 7C20.1943 6.19297 19.9613 5.78945 19.6457 5.54727C19.2249 5.22436 18.693 5.08185 18.1671 5.15109C17.9271 5.18269 17.6837 5.28136 17.3479 5.4588C16.8545 5.71959 16.2644 5.73002 15.7811 5.45096C15.2977 5.17191 15.0117 4.65566 14.9909 4.09794C14.9767 3.71848 14.9404 3.45833 14.8477 3.23463C14.6448 2.74458 14.2554 2.35523 13.7654 2.15224Z"
                  stroke="currentColor"
                  stroke-width="1.5"
                />
              </svg>
              <span>Default</span>
            </div>
          </button>
          <button
            class="flex-1 px-4 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 hover:text-base-content hover:bg-base-100/50 h-12 flex items-center justify-center min-w-0 relative {selected_tab ===
            'saved'
              ? 'text-base-content'
              : 'text-base-content/70'}"
            class:bg-base-100={selected_tab === "saved"}
            class:bg-transparent={selected_tab !== "saved"}
            class:shadow-sm={selected_tab === "saved"}
            class:font-semibold={selected_tab === "saved"}
            on:click|stopPropagation={() =>
              (show_saved_dropdown = !show_saved_dropdown)}
          >
            <div class="flex flex-col w-full items-center">
              <div class="flex items-center gap-1">
                <svg
                  class="w-3 h-3 opacity-60"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M19 9l-7 7-7-7"
                  />
                </svg>
                <span>Saved</span>
              </div>
              {#if selected_saved_config}
                <span
                  class="text-xs opacity-70 font-normal truncate text-center w-full"
                >
                  {saved_configs.find((c) => c.id === selected_saved_config)
                    ?.name}
                </span>
              {/if}
            </div>

            {#if show_saved_dropdown}
              <div
                class="absolute top-full left-0 mt-1 bg-white border border-base-300 rounded-lg shadow-lg z-10 min-w-[200px]"
                on:click|stopPropagation
              >
                {#each saved_configs as config}
                  <button
                    class="w-full px-4 py-2 text-left text-sm font-normal text-base-content/70 hover:bg-base-200 first:rounded-t-lg last:rounded-b-lg {selected_saved_config ===
                    config.id
                      ? 'bg-base-200'
                      : ''}"
                    on:click|stopPropagation={() => {
                      selected_saved_config = config.id
                      selected_tab = "saved"
                      show_saved_dropdown = false
                    }}
                  >
                    {config.name}
                  </button>
                {/each}
              </div>
            {/if}
          </button>
          <button
            class="flex-1 px-4 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 hover:text-base-content hover:bg-base-100/50 h-12 flex items-center justify-center min-w-0 {selected_tab ===
            'new'
              ? 'text-base-content'
              : 'text-base-content/70'}"
            class:bg-base-100={selected_tab === "new"}
            class:bg-transparent={selected_tab !== "new"}
            class:shadow-sm={selected_tab === "new"}
            class:font-semibold={selected_tab === "new"}
            on:click={() => {
              selected_tab = "new"
              selected_saved_config = null
            }}
          >
            Custom
          </button>
        </div>

        <!-- Run Configuration Container with Border -->
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
                      selected_tab === "saved"}
                  />
                </div>
              </Collapse>
            </div>
          {/if}
        </div>

        <!-- Action Buttons -->
        <div class="flex gap-2 mt-4">
          {#if selected_tab === "new"}
            <button class="btn btn-sm btn-primary"> Save </button>
          {/if}
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
