<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import { client } from "$lib/api_client"
  import { current_task } from "$lib/stores"
  import type { Task } from "$lib/types"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { page } from "$app/stores"
  import type { SampleDataNode } from "./gen_model"
  import GeneratedDataNode from "./generated_data_node.svelte"
  import AvailableModelsDropdown from "../../../run/available_models_dropdown.svelte"
  import { ui_state } from "$lib/stores"
  import PromptTypeSelector from "../../../run/prompt_type_selector.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import { type SampleData } from "./gen_model"
  import { indexedDBStore } from "$lib/stores/index_db_store"
  import { writable, type Writable } from "svelte/store"
  import DataGenIntro from "./data_gen_intro.svelte"
  import { SynthDataGuidanceDataModel } from "./synth_data_guidance_datamodel"
  import SynthDataGuidance from "./synth_data_guidance.svelte"
  import { onDestroy } from "svelte"
  import { get_splits_from_url_param } from "$lib/utils/splits_util"
  import DataGenDescription from "./data_gen_description.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import { get } from "svelte/store"
  import posthog from "posthog-js"
  import type { TaskRunOutput } from "$lib/types"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"

  let session_id = Math.floor(Math.random() * 1000000000000).toString()

  let guidance_data: SynthDataGuidanceDataModel =
    new SynthDataGuidanceDataModel()
  onDestroy(() => {
    guidance_data.destroy()
  })
  // Local instance for dynamic reactive updates
  const loading_error = guidance_data.loading_error
  const splits = guidance_data.splits
  const selected_template = guidance_data.selected_template

  let task: Task | null = null
  let task_error: KilnError | null = null
  let task_loading = true

  $: error = $loading_error || task_error

  let synth_data_loading = false

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id
  let is_setup = false

  let prompt_method = "simple_prompt_builder"
  let model: string = $ui_state.selected_model

  // Shared vars for all nodes, so UI saves last used value
  let num_subtopics_to_generate: number = 8
  let num_samples_to_generate: number = 8

  type SavedDataGenState = {
    gen_type: "training" | "eval" | null
    template_id: string | null
    eval_id: string | null
    splits: Record<string, number>
    root_node: SampleDataNode
  }
  // Empty to start but will be populated from IndexedDB after task is loaded
  // Note: load the state vars into the guidance_data model and use that, this is just for the initial load/persistence
  let saved_state: Writable<SavedDataGenState> = writable({
    gen_type: null,
    template_id: null,
    eval_id: null,
    splits: {},
    root_node: { topic: "", samples: [], sub_topics: [] },
  })
  // Reactivity: update state in indexedDB when splits is modified
  $: saved_state.update((s) => ({
    ...s,
    splits: $splits,
  }))

  function clear_all_with_confirm() {
    let msg =
      "Are you sure you want to clear all synthetic data gen state? This cannot be undone."

    if (confirm(msg)) {
      clear_all_state()
      // Load the page again with clear URL params to get fresh state
      window.location.href = `/generate/${project_id}/${task_id}`
    }
  }

  function clear_all_state() {
    saved_state.update((s) => ({
      ...s,
      root_node: {
        topic: "",
        samples: [],
        sub_topics: [],
      },
      gen_type: null,
      template_id: null,
      eval_id: null,
      splits: {},
    }))
  }

  function clear_state_and_reload() {
    clear_all_state()
    // reload the window keeping the same URL
    window.location.reload()
    return true
  }

  // Function to trigger save when data changes
  function triggerSaveUiState() {
    saved_state.update((s) => s)
  }

  function saveUiStateAndUpdateStatus() {
    triggerSaveUiState()
    update_status()
  }

  onMount(async () => {
    await get_task()
    if (!task) {
      task_error = new KilnError(
        "Could not load task. It may belong to a project you don't have access to.",
        null,
      )
      return
    }

    if (project_id && task_id) {
      // Setup the root node store
      const synth_data_key = `synth_data_${project_id}_${task_id}_v2`
      const { store, initialized } = indexedDBStore(synth_data_key, {
        gen_type: null,
        template_id: null,
        eval_id: null,
        splits: {},
        root_node: { topic: "", samples: [], sub_topics: [] },
      })
      // Wait for the store to be initialized, then set the state
      await initialized
      saved_state = store

      // Special case: if we have some state (goal) but no root_node data, we should reset the state
      // Cleaner to give the user a fresh UI since there's very little data saved, and the clean UI is about picking goal
      if (
        $saved_state.root_node.samples.length === 0 &&
        $saved_state.root_node.sub_topics.length === 0
      ) {
        clear_all_state()
      }
    }

    load_initial_state()
    update_status()
    load_initial_step()
  })

  let clear_all_dialog: Dialog | null = null
  let clear_existing_state_no_url_dialog: Dialog | null = null

  function load_initial_state() {
    // Complicated logic, but we want to handle all 5 loading states:
    // 1. There is no saved state and URL has state: setup the URL state
    // 2. URL state matches saved state: load the saved state
    // 3. Saved state and URL state are different: show an alert to the user asking if they want to replace the saved state with the URL state
    // 4. There's no URL state and there is saved state: setup the saved state (with a UI option to clear it)
    // 5. No state, don't setup, and wait for the user to setup via UI

    // The URL params can specify a specific setup for the data gen.
    const reason_param = $page.url.searchParams.get("reason")
    // Map "fine_tune" (user facing string) to "training" (pre-existing internal value)
    const gen_type = reason_param === "fine_tune" ? "training" : reason_param
    if (gen_type === "training" || gen_type === "eval") {
      // These are optional, only gen_type is required.
      const eval_id: string | null = $page.url.searchParams.get("eval_id")
      const template_id: string | null =
        $page.url.searchParams.get("template_id")
      const splitsParam = $page.url.searchParams.get("splits")
      const splits = get_splits_from_url_param(splitsParam)

      const has_saved_state = $saved_state.gen_type !== null
      if (!has_saved_state) {
        // Case 1: No saved state: setup the URL state
        setup(gen_type, template_id, eval_id, project_id, task_id, splits)
        return
      } else {
        if (
          $saved_state.gen_type === gen_type &&
          $saved_state.template_id === template_id &&
          $saved_state.eval_id === eval_id
        ) {
          // Case 2: URL state matches saved state: load the saved state
          setup(
            $saved_state.gen_type,
            $saved_state.template_id,
            $saved_state.eval_id,
            project_id,
            task_id,
            $saved_state.splits,
          )
          return
        } else {
          // Case 3: Saved state and URL state are different.
          // Show a dialog to the user asking if they want to replace the saved state with the URL state
          clear_all_dialog?.show()
          return
        }
      }
    } else if ($saved_state.gen_type) {
      // Case 4: There's no URL state and there is saved state, load saved state
      setup(
        $saved_state.gen_type,
        $saved_state.template_id,
        $saved_state.eval_id,
        project_id,
        task_id,
        $saved_state.splits,
      )
      clear_existing_state_no_url_dialog?.show()
      return
    }
    // Case 5: No state - wait for the user to setup via UI
  }

  function load_initial_step() {
    // Load which step to start on based on status

    // Nothing! Start at step 1 for topics
    if ($saved_state.root_node.sub_topics.length === 0) {
      set_current_step(1)
      return
    }

    // Has topics, but some inputs are missing
    if (leaf_topics_missing_inputs > 0) {
      set_current_step(2)
      return
    }

    // Has topics, but some inputs are missing
    if (samples_to_generate.length > 0) {
      set_current_step(3)
      return
    }

    // Made it this far!
    set_current_step(4)
  }

  function setup(
    gen_type: "training" | "eval",
    template_id: string | null,
    eval_id: string | null,
    project_id: string,
    task_id: string,
    splits: Record<string, number>,
  ) {
    if (!gen_type || !task) {
      return
    }
    if (is_setup) {
      console.error("Setup already called. This should not happen.")
    }
    is_setup = true
    guidance_data.load(
      template_id,
      eval_id,
      project_id,
      task_id,
      gen_type,
      task,
      splits,
    )
    // Trigger reactivity
    guidance_data = guidance_data
    // Update state with the vars
    saved_state.update((s) => ({
      ...s,
      gen_type,
      template_id,
      eval_id,
      splits,
    }))

    posthog.capture("setup_data_gen", {
      gen_type,
      template: template_id,
    })
  }

  async function get_task() {
    try {
      task_loading = true
      if (!project_id || !task_id) {
        throw new Error("Project or task ID not set.")
      }
      if ($current_task?.id === task_id) {
        task = $current_task
        return
      }
      const { data: task_response, error: get_error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}",
        {
          params: {
            path: {
              project_id,
              task_id,
            },
          },
        },
      )
      if (get_error) {
        throw get_error
      }
      task = task_response
    } catch (e) {
      if (e instanceof Error && e.message.includes("Load failed")) {
        task_error = new KilnError(
          "Could not load task. It may belong to a project you don't have access to.",
          null,
        )
      } else {
        task_error = createKilnError(e)
      }
    } finally {
      task_loading = false
    }
  }

  function show_generate_all_modal() {
    // Reset the modal state unless it was already running
    if (!generate_all_running) {
      generate_all_completed = false
      generate_all_error = null
      update_status()
    }

    // @ts-expect-error showModal is not a method on HTMLElement
    document.getElementById("generate_all_dialog")?.showModal()
  }

  function show_save_all_modal() {
    // Reset the modal state unless it was already running
    if (!save_all_running) {
      save_all_completed = false
      save_all_error = null
      update_status()
    }

    // @ts-expect-error showModal is not a method on HTMLElement
    document.getElementById("save_all_dialog")?.showModal()
  }

  // Two functions for recursive collection of data to save.
  let already_generated_count = 0
  let samples_to_generate: SampleData[] = []
  let already_saved_count = 0
  let samples_to_save: SampleData[] = []
  let input_generated_count = 0
  let leaf_topics_missing_inputs = 0
  let leaf_topics_has_inputs = 0
  function visit_node_for_collection(node: SampleDataNode, path: string[]) {
    const topic_path = node.topic ? [...path, node.topic] : path
    node.samples.forEach((sample) => {
      // Rare case: already saved on old UI so saved_id is set, but no output
      if (sample.output || sample.saved_id) {
        already_generated_count++
      } else {
        // Path may not have been set yet
        sample.topic_path = topic_path
        samples_to_generate.push(sample)
      }
      if (sample.saved_id) {
        already_saved_count++
      } else if (sample.output) {
        samples_to_save.push(sample)
      }
      // All samples have inputs
      input_generated_count++
    })
    if (node.sub_topics.length === 0 && node.samples.length === 0) {
      leaf_topics_missing_inputs++
    }
    if (node.sub_topics.length === 0 && node.samples.length > 0) {
      leaf_topics_has_inputs++
    }
    node.sub_topics.forEach((sub_topic) => {
      visit_node_for_collection(sub_topic, topic_path)
    })
  }

  function update_status() {
    already_generated_count = 0
    samples_to_generate = []
    already_saved_count = 0
    samples_to_save = []
    leaf_topics_missing_inputs = 0
    leaf_topics_has_inputs = 0
    input_generated_count = 0
    visit_node_for_collection($saved_state.root_node, [])
  }

  let generate_all_running = false
  let generate_all_error: KilnError | null = null
  let generate_all_sub_errors: KilnError[] = []
  let generate_all_completed = false
  let save_all_running = false
  let save_all_error: KilnError | null = null
  let save_all_sub_errors: KilnError[] = []
  let save_all_completed = false
  let ui_show_errors = false

  // Worker function that processes items until queue is empty
  async function generate_worker(
    queue: SampleData[],
    model_name: string,
    provider: string,
    prompt_method: string,
  ) {
    while (queue.length > 0) {
      const sample = queue.shift()!
      const result = await generate_sample(
        sample,
        model_name,
        provider,
        prompt_method,
        sample.topic_path,
      )

      if (result.error) {
        generate_all_sub_errors.push(result.error)
        // Trigger reactivity
        generate_all_sub_errors = generate_all_sub_errors
      } else if (!result.output) {
        generate_all_sub_errors.push(
          new KilnError("No output returned from server"),
        )
        // Trigger reactivity
        generate_all_sub_errors = generate_all_sub_errors
      } else {
        sample.output = result.output
        generated_count++
        triggerSaveUiState()
      }
    }
  }

  let generated_count = 0
  async function generate_all_samples() {
    try {
      generated_count = 0
      generate_all_running = true
      generate_all_error = null
      generate_all_completed = false
      generate_all_sub_errors = []
      const provider = model.split("/")[0]
      const model_name = model.split("/").slice(1).join("/")

      const queue = [...samples_to_generate]

      // Create and start 5 workers
      // 5 because browsers can only handle 6 concurrent requests. The 6th is for the rest of the UI to keep working.
      const workers = Array(5)
        .fill(null)
        .map(() => generate_worker(queue, model_name, provider, prompt_method))

      // Wait for all workers to complete
      await Promise.all(workers)
    } catch (e) {
      generate_all_error = createKilnError(e)
    } finally {
      generate_all_running = false
      generate_all_completed = true
      update_status()
    }
  }

  let saved_count = 0
  async function save_all_samples() {
    try {
      saved_count = 0
      save_all_running = true
      save_all_error = null
      save_all_completed = false
      save_all_sub_errors = []
      for (const sample of samples_to_save) {
        try {
          if (!sample.output) {
            continue
          }
          const { data, error } = await client.POST(
            "/api/projects/{project_id}/tasks/{task_id}/save_sample",
            {
              params: {
                path: { project_id, task_id },
              },
              body: sample.output,
            },
          )

          if (error) {
            save_all_sub_errors.push(createKilnError(error))
            // Trigger reactivity
            save_all_sub_errors = save_all_sub_errors
          } else if (!data || !data.id) {
            save_all_sub_errors.push(
              new KilnError("Unknow error saving sample"),
            )
            // Trigger reactivity
            save_all_sub_errors = save_all_sub_errors
          } else {
            sample.saved_id = data.id
            saved_count++
            triggerSaveUiState()
          }
        } catch (e) {
          save_all_sub_errors.push(createKilnError(e))
          // Trigger reactivity
          save_all_sub_errors = save_all_sub_errors
        }
      }
    } catch (e) {
      save_all_error = createKilnError(e)
    } finally {
      save_all_running = false
      save_all_completed = true
      update_status()
      triggerSaveUiState()
    }
  }

  type GenerateSampleResponse = {
    output: TaskRunOutput | null
    error: KilnError | null
  }

  async function generate_sample(
    sample: SampleData,
    model_name: string,
    provider: string,
    prompt_method: string,
    topic_path: string[] | undefined,
  ): Promise<GenerateSampleResponse> {
    try {
      const formatted_input = task?.input_json_schema
        ? JSON.parse(sample.input)
        : sample.input
      const save_sample_guidance = guidance_data.guidance_for_type("outputs")
      // Get a random split tag, if splits are defined
      const split_tag = get_random_split_tag()
      const tags = split_tag ? [split_tag] : []
      const {
        error: post_error,
        data,
        response,
      } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/generate_sample",
        {
          params: {
            path: {
              project_id,
              task_id,
            },
            query: {
              session_id,
            },
          },
          body: {
            input: formatted_input,
            input_model_name: sample.model_name,
            input_provider: sample.model_provider,
            output_model_name: model_name,
            output_provider: provider,
            prompt_method,
            topic_path: topic_path || [],
            guidance: save_sample_guidance ? save_sample_guidance : undefined, // clear empty string
            tags,
          },
        },
      )
      if (post_error) {
        throw post_error
      }
      if (response.status !== 200 || !data.id) {
        throw new KilnError("Failed to save sample")
      }
      posthog.capture("save_synthetic_data", {
        model_name: model_name,
        provider: provider,
        prompt_method: prompt_method,
      })

      return { output: data, error: null }
    } catch (e) {
      const error = createKilnError(e)
      return { output: null, error }
    }
  }

  $: is_empty =
    $saved_state.root_node.samples.length == 0 &&
    $saved_state.root_node.sub_topics.length == 0
  let root_node_component: GeneratedDataNode | null = null

  function get_random_split_tag() {
    const splits = get(guidance_data.splits)
    if (Object.keys(splits).length === 0) return undefined

    const random = Math.random()
    let cumulative = 0

    for (const [tag, probability] of Object.entries(splits)) {
      cumulative += probability
      if (random <= cumulative) {
        return tag
      }
    }

    // Fallback (should never reach here if splits sum to 1)
    return Object.keys(splits)[0]
  }

  type StepNumber = 1 | 2 | 3 | 4
  const step_numbers: StepNumber[] = [1, 2, 3, 4]
  let current_step: StepNumber = 1
  const step_names: Record<StepNumber, string> = {
    1: "Add Topics",
    2: "Generate Inputs",
    3: "Generate Outputs",
    4: "Save Data",
  }
  const step_descriptions: Record<StepNumber, string> = {
    1: "Add topics to ensure synthetic data is diverse",
    2: "Generate synthetic inputs: data provided as input to the task",
    3: "Run the task on synthetic inputs, generating outputs",
    4: "Save this data into your dataset",
  }
  const learn_more_step_links: Record<StepNumber, string> = {
    1: "https://docs.kiln.tech/docs/synthetic-data-generation#topic-generation-for-content-breadth",
    2: "https://docs.kiln.tech/docs/synthetic-data-generation#generate-model-inputs",
    3: "https://docs.kiln.tech/docs/synthetic-data-generation#generate-model-outputs",
    4: "https://docs.kiln.tech/docs/synthetic-data-generation#save-synthetic-data-into-dataset",
  }
  function set_current_step(step: StepNumber) {
    current_step = step
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Synthetic Data Generation"
    no_y_padding
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/synthetic-data-generation"
    action_buttons={[
      ...(is_setup
        ? [
            {
              label: "Reset",
              handler: clear_all_with_confirm,
            },
          ]
        : []),
      {
        label: "Docs & Guide",
        href: "https://docs.kiln.tech/docs/synthetic-data-generation",
      },
    ]}
  >
    {#if task_loading || synth_data_loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if error || !task}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="font-medium">Error Loading Task</div>
        <div class="text-error text-sm">
          {error?.getMessage() ||
            "An unknown error occurred loading the task. You may not have access to it."}
        </div>
      </div>
    {:else if task}
      <DataGenDescription bind:guidance_data />
      {#if is_empty}
        <div
          class="flex flex-col items-center justify-center min-h-[50vh] mt-12"
        >
          <DataGenIntro
            generate_subtopics={() => {
              root_node_component?.open_generate_subtopics_modal()
            }}
            generate_samples={() => {
              root_node_component?.open_generate_samples_modal()
            }}
            {project_id}
            {task_id}
            on_setup={setup}
            bind:is_setup
          />
        </div>
      {:else}
        <div
          class="py-1 mt-12 mb-4 gap-2 sticky top-0 z-2 backdrop-blur bg-white/70 z-10"
        >
          <div class="flex flex-col">
            <div class="flex justify-center">
              <ul class="steps">
                {#each step_numbers as step}
                  <li class="step {current_step >= step ? 'step-primary' : ''}">
                    <button
                      class="px-4 text-sm {current_step == step
                        ? 'font-medium cursor-default'
                        : 'text-gray-500 hover:underline hover:text-gray-700'}"
                      on:click={() => set_current_step(step)}
                      aria-label={`Go to step ${step} - ${step_names[step]}`}
                    >
                      {step_names[step]}
                    </button>
                  </li>
                {/each}
              </ul>
            </div>
            <div class="max-w-3xl mx-auto mt-6 text-center">
              <div class="font-light">
                <span class="font-medium">Step {current_step}:</span>
                {step_descriptions[current_step]}
                {#if learn_more_step_links[current_step]}
                  <a
                    href={learn_more_step_links[current_step]}
                    target="_blank"
                    class="link pl-1">Learn More</a
                  >
                {/if}
              </div>
              <div class="mt-2">
                {#if current_step == 1}
                  {#if $saved_state.root_node.sub_topics.length == 0}
                    <button
                      class="btn btn-sm btn-outline btn-primary mr-2"
                      on:click={() =>
                        root_node_component?.open_generate_subtopics_modal()}
                    >
                      Add Topics
                    </button>
                  {/if}
                  <button
                    class="btn btn-sm btn-primary"
                    on:click={() => set_current_step(2)}
                  >
                    Next Step
                  </button>
                {:else if current_step == 2}
                  {@const done_generating =
                    input_generated_count > 0 &&
                    leaf_topics_missing_inputs === 0}
                  {#if leaf_topics_missing_inputs > 0 && leaf_topics_has_inputs > 0}
                    <!-- Only show the error if partly populated but missing some. New/empty shouldn't be an error. -->
                    <div class="text-error text-sm my-2">
                      {leaf_topics_missing_inputs}
                      {leaf_topics_missing_inputs === 1
                        ? "topic has"
                        : "topics have"}
                      no inputs
                    </div>
                  {/if}
                  {#if !done_generating}
                    <button
                      class="btn btn-sm btn-primary"
                      on:click={() => {
                        root_node_component?.open_generate_samples_modal(true)
                      }}
                    >
                      Generate Inputs
                    </button>
                  {:else}
                    <button
                      class="btn btn-sm btn-primary"
                      on:click={() => set_current_step(3)}
                    >
                      Next Step
                    </button>
                    <div class="mt-1 text-sm font-light">
                      or <button
                        on:click={() => {
                          root_node_component?.open_generate_samples_modal(true)
                        }}
                        class="link"
                      >
                        generate additional inputs on all topics</button
                      >
                    </div>
                  {/if}
                {:else if current_step == 3}
                  {@const no_inputs = input_generated_count === 0}
                  {@const output_gen_complete =
                    samples_to_generate.length === 0}
                  {#if no_inputs}
                    <div class="text-error text-sm my-2">
                      No inputs available. Return to <button
                        on:click={() => set_current_step(2)}
                        class="link">step 2</button
                      > to add inputs.
                    </div>
                  {:else if output_gen_complete}
                    <button
                      class="btn btn-sm btn-primary"
                      on:click={() => set_current_step(4)}
                    >
                      Next Step
                    </button>
                  {:else}
                    <button
                      class="btn btn-sm btn-primary {output_gen_complete
                        ? 'hidden'
                        : ''}"
                      on:click={show_generate_all_modal}
                    >
                      Generate Outputs
                    </button>
                  {/if}
                {:else if current_step == 4}
                  {#if samples_to_generate.length > 0}
                    <div class="text-error text-sm my-2">
                      {samples_to_generate.length}
                      {samples_to_generate.length === 1
                        ? "item has"
                        : "items have"}
                      no outputs. Return to
                      <button on:click={() => set_current_step(3)} class="link"
                        >step 3</button
                      > to generate outputs.
                    </div>
                  {:else if samples_to_save.length > 0}
                    <button
                      class="btn btn-sm btn-primary"
                      on:click={show_save_all_modal}
                    >
                      Save All
                    </button>
                  {:else if already_saved_count === 0}
                    <div class="text-error text-sm my-2">
                      No items to save. Return to <button
                        on:click={() => set_current_step(2)}
                        class="link">step 2</button
                      > to generate data.
                    </div>
                  {:else}
                    <div class="flex flex-row justify-center">
                      <Warning
                        warning_message="All items saved into the dataset!"
                        warning_color="success"
                        warning_icon="check"
                        tight
                      />
                    </div>
                  {/if}
                {/if}
              </div>
            </div>
          </div>
        </div>
      {/if}
      <div class={is_empty ? "" : "rounded-lg border"}>
        <table class={is_empty ? "" : "table table-fixed"}>
          <thead
            class="text-center {is_empty
              ? 'hidden'
              : ''} {input_generated_count === 0 ? 'hidden-header' : ''}"
          >
            <tr>
              <!-- 70 + 110 = 180 (the width of the last two columns)-->
              <th style="width: calc(50% - 70px)"
                >Input <InfoTooltip
                  tooltip_text="The input to the task. This will be passed to the task to generate the output."
                  position="bottom"
                /></th
              >
              <th style="width: calc(50% - 110px)"
                >Output <InfoTooltip
                  tooltip_text="The output from the task. This is the data that was generated by the task."
                  position="bottom"
                /></th
              >
              <th style="width: 140px">Status</th>
              <th style="width: 40px"></th>
            </tr>
          </thead>
          <tbody>
            <GeneratedDataNode
              data={$saved_state.root_node}
              path={[]}
              {guidance_data}
              triggerSave={saveUiStateAndUpdateStatus}
              bind:num_subtopics_to_generate
              bind:num_samples_to_generate
              bind:this={root_node_component}
            />
          </tbody>
        </table>
      </div>
      {#if !is_empty}
        <div class="font-light my-6 text-center">
          <button
            class="link"
            on:click={() =>
              root_node_component?.open_generate_subtopics_modal()}
          >
            Add top level topics
          </button>
          or
          <button
            class="link"
            on:click={() => root_node_component?.open_generate_samples_modal()}
          >
            add top level inputs
          </button>.
        </div>
      {/if}
    {/if}
  </AppPage>
</div>

<dialog id="generate_all_dialog" class="modal">
  <div class="modal-box">
    <form method="dialog">
      <button
        class="btn btn-sm text-xl btn-circle btn-ghost absolute right-2 top-2 focus:outline-none"
        >✕</button
      >
    </form>

    {#if generate_all_running}
      <div class="min-h-[200px] flex flex-col justify-center items-center">
        <div class="loading loading-spinner loading-lg mb-6 text-success"></div>
        <progress
          class="progress w-56 progress-success"
          value={generated_count}
          max={samples_to_generate.length}
        ></progress>
        <div class="font-light text-xs text-center mt-1">
          {generated_count} of {samples_to_generate.length}
          {#if generate_all_sub_errors && generate_all_sub_errors.length > 0}
            complete — {generate_all_sub_errors.length} failed
          {/if}
        </div>
      </div>
    {:else if generate_all_completed}
      <div
        class="text-center flex flex-col items-center justify-center min-h-[150px] p-12"
      >
        {#if generated_count > 0}
          <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools -->
          <svg
            fill="currentColor"
            class="size-10 text-success mb-2"
            viewBox="0 0 56 56"
            xmlns="http://www.w3.org/2000/svg"
            ><path
              d="M 27.9999 51.9063 C 41.0546 51.9063 51.9063 41.0781 51.9063 28 C 51.9063 14.9453 41.0312 4.0937 27.9765 4.0937 C 14.8983 4.0937 4.0937 14.9453 4.0937 28 C 4.0937 41.0781 14.9218 51.9063 27.9999 51.9063 Z M 27.9999 47.9219 C 16.9374 47.9219 8.1014 39.0625 8.1014 28 C 8.1014 16.9609 16.9140 8.0781 27.9765 8.0781 C 39.0155 8.0781 47.8983 16.9609 47.9219 28 C 47.9454 39.0625 39.0390 47.9219 27.9999 47.9219 Z M 25.0468 39.7188 C 25.8202 39.7188 26.4530 39.3437 26.9452 38.6172 L 38.5234 20.4063 C 38.8046 19.9375 39.0858 19.3984 39.0858 18.8828 C 39.0858 17.8047 38.1483 17.1484 37.1640 17.1484 C 36.5312 17.1484 35.9452 17.5 35.5234 18.2031 L 24.9296 35.1484 L 19.4921 28.1172 C 18.9765 27.4141 18.4140 27.1563 17.7812 27.1563 C 16.7499 27.1563 15.9296 28 15.9296 29.0547 C 15.9296 29.5703 16.1405 30.0625 16.4687 30.5078 L 23.0312 38.6172 C 23.6640 39.3906 24.2733 39.7188 25.0468 39.7188 Z"
            /></svg
          >
        {/if}
        <div class="font-medium">Generated {generated_count} new items</div>
        <div class="font-light text-sm">
          You can view them and delete any you don't want to save. Once ready,
          select "Save All".
        </div>
        {#if generate_all_sub_errors.length > 0}
          <div class="text-error font-light text-sm mt-4">
            {generate_all_sub_errors.length} samples failed to generate. Running
            again may resolve transient issues.
            <button
              class="link"
              on:click={() => (ui_show_errors = !ui_show_errors)}
            >
              {ui_show_errors ? "Hide Errors" : "Show Errors"}
            </button>
          </div>
          <div
            class="flex flex-col gap-2 mt-4 text-xs text-error {ui_show_errors
              ? ''
              : 'hidden'}"
          >
            {#each generate_all_sub_errors as error}
              <div>{error.getMessage()}</div>
            {/each}
          </div>
        {/if}
        {#if generate_all_error}
          <div class="text-error font-light text-sm mt-4">
            Error message: {generate_all_error.getMessage() ||
              "An unknown error occurred"}
          </div>
        {/if}
      </div>
    {:else if samples_to_generate.length == 0}
      <div
        class="flex flex-col items-center justify-center min-h-[150px] gap-2"
      >
        <div class="font-medium">No Model Inputs</div>
        <div class="font-light">
          Generate model inputs before generating model outputs.
        </div>
        {#if already_generated_count > 0}
          <div class="font-light text-sm">
            {already_generated_count} existing items already generated.
          </div>
        {/if}
      </div>
    {:else}
      <h3 class="text-lg font-bold">Generate Model Outputs</h3>
      <p class="text-sm font-light mb-5">
        Run your task on each generated model input to generate model outputs.
      </p>
      <FormContainer
        submit_label="Generate"
        bind:submitting={generate_all_running}
        bind:error={generate_all_error}
        on:submit={generate_all_samples}
      >
        <div>
          <div class="font-medium text-sm">Status</div>
          <div class="font-light">
            {samples_to_generate.length} items pending
            {#if already_generated_count > 0}
              / {already_generated_count} already generated
            {/if}
          </div>
        </div>
        <AvailableModelsDropdown
          requires_data_gen={true}
          requires_uncensored_data_gen={guidance_data.suggest_uncensored(
            $selected_template,
          )}
          requires_structured_output={task?.output_json_schema ? true : false}
          suggested_mode={guidance_data.suggest_uncensored($selected_template)
            ? "uncensored_data_gen"
            : "data_gen"}
          bind:model
        />
        <div>
          <SynthDataGuidance guidance_type="outputs" {guidance_data} />
        </div>

        <div class="mb-2">
          <PromptTypeSelector bind:prompt_method />
        </div>
      </FormContainer>
    {/if}
  </div>
  <form method="dialog" class="modal-backdrop">
    <button>close</button>
  </form>
</dialog>

<dialog id="save_all_dialog" class="modal">
  <div class="modal-box">
    <form method="dialog">
      <button
        class="btn btn-sm text-xl btn-circle btn-ghost absolute right-2 top-2 focus:outline-none"
        >✕</button
      >
    </form>

    {#if save_all_running}
      <div class="min-h-[200px] flex flex-col justify-center items-center">
        <div class="loading loading-spinner loading-lg mb-6 text-success"></div>
        <progress
          class="progress w-56 progress-success"
          value={saved_count}
          max={samples_to_save.length}
        ></progress>
        <div class="font-light text-xs text-center mt-1">
          {saved_count} of {samples_to_save.length}
          {#if save_all_sub_errors && save_all_sub_errors.length > 0}
            complete — {save_all_sub_errors.length} failed
          {/if}
        </div>
      </div>
    {:else if save_all_completed}
      <div
        class="text-center flex flex-col items-center justify-center min-h-[150px] p-12"
      >
        {#if saved_count > 0}
          <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools -->
          <svg
            fill="currentColor"
            class="size-10 text-success mb-2"
            viewBox="0 0 56 56"
            xmlns="http://www.w3.org/2000/svg"
            ><path
              d="M 27.9999 51.9063 C 41.0546 51.9063 51.9063 41.0781 51.9063 28 C 51.9063 14.9453 41.0312 4.0937 27.9765 4.0937 C 14.8983 4.0937 4.0937 14.9453 4.0937 28 C 4.0937 41.0781 14.9218 51.9063 27.9999 51.9063 Z M 27.9999 47.9219 C 16.9374 47.9219 8.1014 39.0625 8.1014 28 C 8.1014 16.9609 16.9140 8.0781 27.9765 8.0781 C 39.0155 8.0781 47.8983 16.9609 47.9219 28 C 47.9454 39.0625 39.0390 47.9219 27.9999 47.9219 Z M 25.0468 39.7188 C 25.8202 39.7188 26.4530 39.3437 26.9452 38.6172 L 38.5234 20.4063 C 38.8046 19.9375 39.0858 19.3984 39.0858 18.8828 C 39.0858 17.8047 38.1483 17.1484 37.1640 17.1484 C 36.5312 17.1484 35.9452 17.5 35.5234 18.2031 L 24.9296 35.1484 L 19.4921 28.1172 C 18.9765 27.4141 18.4140 27.1563 17.7812 27.1563 C 16.7499 27.1563 15.9296 28 15.9296 29.0547 C 15.9296 29.5703 16.1405 30.0625 16.4687 30.5078 L 23.0312 38.6172 C 23.6640 39.3906 24.2733 39.7188 25.0468 39.7188 Z"
            /></svg
          >
        {/if}
        <div class="font-medium">Saved {saved_count} new items.</div>
        <div class="font-light text-sm">
          These are now available in the <a
            href={`/dataset/${project_id}/${task_id}`}
            class="link">dataset tab</a
          >.
        </div>
        <div class="font-light text-xs mt-4 text-gray-500">
          All items are tagged with &quot;synthetic_session_{session_id}&quot;
        </div>
        {#if save_all_sub_errors.length > 0}
          <div class="text-error font-light text-sm mt-4">
            {save_all_sub_errors.length} samples failed to save. Running again may
            resolve transient issues.
            <button
              class="link"
              on:click={() => (ui_show_errors = !ui_show_errors)}
            >
              {ui_show_errors ? "Hide Errors" : "Show Errors"}
            </button>
          </div>
          <div
            class="flex flex-col gap-2 mt-4 text-xs text-error {ui_show_errors
              ? ''
              : 'hidden'}"
          >
            {#each save_all_sub_errors as error}
              <div>{error.getMessage()}</div>
            {/each}
          </div>
        {/if}
        {#if save_all_error}
          <div class="text-error font-light text-sm mt-4">
            Error message: {save_all_error.getMessage() ||
              "An unknown error occurred"}
          </div>
        {/if}
      </div>
    {:else if samples_to_save.length == 0}
      <div
        class="flex flex-col items-center justify-center min-h-[150px] gap-2"
      >
        <div class="font-medium">No Items to Save</div>
        <div class="font-light">
          Generate synthetic inputs and outputs before attempting to save.
        </div>
        {#if already_saved_count > 0}
          <div class="font-light text-sm">
            {already_saved_count} existing items already saved.
          </div>
        {/if}
      </div>
    {:else}
      <h3 class="text-lg font-bold">Save Synthetic Data to Dataset</h3>
      <p class="text-sm font-light mb-5">
        Save the synthetic data below into your dataset.
      </p>
      <FormContainer
        submit_label="Save All"
        bind:submitting={save_all_running}
        bind:error={save_all_error}
        on:submit={save_all_samples}
      >
        <div>
          <div class="font-medium text-sm">Status</div>
          <div class="font-light">
            {samples_to_save.length} items pending
            {#if already_saved_count > 0}
              / {already_saved_count} already saved
            {/if}
          </div>
        </div>
      </FormContainer>
    {/if}
  </div>
  <form method="dialog" class="modal-backdrop">
    <button>close</button>
  </form>
</dialog>

<Dialog
  title="Clear Existing Session?"
  bind:this={clear_all_dialog}
  action_buttons={[
    {
      label: "Keep Current Session",
      action: () => {
        // Load the page without URL params to get fresh state
        window.location.href = `/generate/${project_id}/${task_id}`
        return true
      },
    },
    {
      label: "New Session (Clear Existing)",
      isWarning: true,
      action: clear_state_and_reload,
    },
  ]}
>
  <div class="flex flex-col gap-2">
    <div class="font-light flex flex-col gap-2">
      <p>
        Your existing synthetic data gen session is incompatible with your
        current goal. You'll need to clear it's data to start a new session for
        this goal.
      </p>
      <Warning warning_message="This action cannot be undone." />
    </div>
    <div class="flex flex-row gap-2"></div>
  </div></Dialog
>

<Dialog
  title="Existing Session"
  bind:this={clear_existing_state_no_url_dialog}
  action_buttons={[
    {
      label: "New Session",
      action: () => {
        clear_all_with_confirm()
        return true
      },
    },
    {
      label: "Continue Session",
      isPrimary: true,
      action: () => {
        clear_existing_state_no_url_dialog?.close()
        return true
      },
    },
  ]}
>
  <div class="flex flex-col gap-2">
    <div class="font-light flex flex-col gap-2">
      <p>A synthetic data generation session is already in progress.</p>
    </div>
    <div class="flex flex-row gap-2"></div>
  </div></Dialog
>

<style>
  .hidden-header {
    height: 0;
    overflow: hidden;
    visibility: hidden;
  }
  .hidden-header th,
  .hidden-header th *,
  .hidden-header th * * {
    display: none !important;
    visibility: hidden !important;
    height: 0 !important;
  }
</style>
