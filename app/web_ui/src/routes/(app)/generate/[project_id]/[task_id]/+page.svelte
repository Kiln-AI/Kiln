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

  let session_id = Math.floor(Math.random() * 1000000000000).toString()

  let guidance_data: SynthDataGuidanceDataModel =
    new SynthDataGuidanceDataModel()
  onDestroy(() => {
    guidance_data.destroy()
  })
  // Local instance for dynamic reactive updates
  const loading_error = guidance_data.loading_error

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

  // Empty to start but will be populated from IndexedDB after task is loaded
  let root_node: Writable<SampleDataNode> = writable({
    topic: "",
    samples: [],
    sub_topics: [],
  })

  function clear_all() {
    let msg =
      "Are you sure you want to clear all topics and data samples? This action cannot be undone."

    if (confirm(msg)) {
      root_node.set({
        topic: "",
        samples: [],
        sub_topics: [],
      })
    }
  }

  // Function to trigger save when data changes
  function triggerSave() {
    root_node.update((n) => n)
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
      const synth_data_key = `synth_data_${project_id}_${task_id}`
      root_node = indexedDBStore(synth_data_key, {
        topic: "",
        samples: [],
        sub_topics: [],
      })
    }

    // Check if the URL has the fields we need for eval setup,
    // otherwise we'll wait for the user to setup via UI
    const reason_param = $page.url.searchParams.get("reason")
    if (reason_param === "training" || reason_param === "eval") {
      // These are optional, only gen_type is required
      const eval_id: string | null = $page.url.searchParams.get("eval_id")
      const template_id: string | null =
        $page.url.searchParams.get("template_id")
      const splitsParam = $page.url.searchParams.get("splits")
      const splits = get_splits_from_url_param(splitsParam)
      setup(reason_param, template_id, eval_id, project_id, task_id, splits)
    }
  })

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

  function show_save_all_modal() {
    // Reset the modal state unless it was already running
    if (!save_all_running) {
      save_all_completed = false
      save_all_error = null
      update_data_for_save()
    }

    // @ts-expect-error showModal is not a method on HTMLElement
    document.getElementById("save_all_dialog")?.showModal()
  }

  // Two functions for recursive collection of data to save.
  let already_saved_count = 0
  let samples_to_save: SampleData[] = []
  let saved_count = 0
  function visit_node_for_collection(node: SampleDataNode, path: string[]) {
    const topic_path = node.topic ? [...path, node.topic] : path
    node.samples.forEach((sample) => {
      if (sample.saved_id) {
        already_saved_count++
      } else {
        // Path may not have been set yet
        sample.topic_path = topic_path
        samples_to_save.push(sample)
      }
    })
    node.sub_topics.forEach((sub_topic) => {
      visit_node_for_collection(sub_topic, topic_path)
    })
  }

  function update_data_for_save() {
    saved_count = 0
    already_saved_count = 0
    samples_to_save = []
    visit_node_for_collection($root_node, [])
  }

  let save_all_running = false
  let save_all_error: KilnError | null = null
  let save_all_sub_errors: KilnError[] = []
  let save_all_completed = false
  let ui_show_errors = false

  // Worker function that processes items until queue is empty
  async function worker(
    queue: SampleData[],
    model_name: string,
    provider: string,
    prompt_method: string,
  ) {
    while (queue.length > 0) {
      const sample = queue.shift()!
      const result = await save_sample(
        sample,
        model_name,
        provider,
        prompt_method,
        sample.topic_path,
      )

      if (result.error) {
        save_all_sub_errors.push(result.error)
        // Trigger reactivity
        save_all_sub_errors = save_all_sub_errors
      } else if (!result.saved_id) {
        save_all_sub_errors.push(new KilnError("No ID returned from server"))
        // Trigger reactivity
        save_all_sub_errors = save_all_sub_errors
      } else {
        sample.saved_id = result.saved_id
        saved_count++
        triggerSave()
      }
    }
  }

  async function save_all_samples() {
    try {
      save_all_running = true
      save_all_error = null
      save_all_completed = false
      save_all_sub_errors = []
      const provider = model.split("/")[0]
      const model_name = model.split("/").slice(1).join("/")

      const queue = [...samples_to_save]

      // Create and start 5 workers
      // 5 because browsers can only handle 6 concurrent requests. The 6th is for the rest of the UI to keep working.
      const workers = Array(5)
        .fill(null)
        .map(() => worker(queue, model_name, provider, prompt_method))

      // Wait for all workers to complete
      await Promise.all(workers)
    } catch (e) {
      save_all_error = createKilnError(e)
    } finally {
      save_all_running = false
      save_all_completed = true
    }
  }

  type SaveSampleResponse = {
    saved_id: string | null
    error: KilnError | null
  }

  async function save_sample(
    sample: SampleData,
    model_name: string,
    provider: string,
    prompt_method: string,
    topic_path: string[] | undefined,
  ): Promise<SaveSampleResponse> {
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
        "/api/projects/{project_id}/tasks/{task_id}/save_sample",
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

      return { saved_id: data.id, error: null }
    } catch (e) {
      const error = createKilnError(e)
      return { saved_id: null, error }
    }
  }

  $: is_empty =
    $root_node.samples.length == 0 && $root_node.sub_topics.length == 0
  let root_node_component: GeneratedDataNode | null = null

  function get_random_split_tag() {
    const splits = guidance_data.splits
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
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Synthetic Data Generation"
    no_y_padding
    action_buttons={[
      {
        label: "Read the Docs",
        href: "https://docs.getkiln.ai/docs/synthetic-data-generation",
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
          class="flex flex-row py-1 mb-4 gap-2 justify-end sticky top-0 z-10 backdrop-blur"
        >
          <button class="btn btn-mid" on:click={clear_all}>Clear</button>
          <button
            class="btn btn-mid"
            on:click={() => {
              root_node_component?.open_generate_samples_modal(true)
            }}
          >
            {#if $root_node.sub_topics.length > 0}
              Generate Model Inputs (All Topics)
            {:else}
              Generate Model Inputs (Root Topic)
            {/if}
          </button>
          <button class="btn btn-mid" on:click={show_save_all_modal}>
            Save Model Outputs
          </button>
        </div>
      {/if}
      <div class="flex flex-col">
        <GeneratedDataNode
          data={$root_node}
          path={[]}
          {guidance_data}
          {triggerSave}
          bind:num_subtopics_to_generate
          bind:num_samples_to_generate
          bind:this={root_node_component}
        />
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
            add top level samples
          </button>.
        </div>
      {/if}
    {/if}
  </AppPage>
</div>

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
          Use the <a href={`/dataset/${project_id}/${task_id}`} class="link"
            >dataset tab</a
          > to review and manage.
        </div>
        <div class="font-light text-xs mt-4 text-gray-500">
          Set tagged with &quot;synthetic_session_{session_id}&quot;
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
        <div class="font-light">Generate some data to get started.</div>
        {#if already_saved_count > 0}
          <div class="font-light text-sm">
            {already_saved_count} existing items already saved.
          </div>
        {/if}
      </div>
    {:else}
      <h3 class="text-lg font-bold">Generate Model Outputs</h3>
      <p class="text-sm font-light mb-8">
        Run your task on each generated model input, saving the resulting
        input/output pairs to your dataset.
      </p>
      <FormContainer
        submit_label="Generate and Save"
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
        <AvailableModelsDropdown
          requires_structured_output={task?.output_json_schema ? true : false}
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
