<script lang="ts">
  import type { SampleDataNode, SampleData } from "./gen_model"
  import AvailableModelsDropdown from "../../../run/available_models_dropdown.svelte"
  import { tick } from "svelte"
  import { client } from "$lib/api_client"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import { ui_state } from "$lib/stores"
  import { createEventDispatcher } from "svelte"
  import IncrementUi from "./increment_ui.svelte"
  import GenerateSamplesModal from "./generate_samples_modal.svelte"
  import SynthDataGuidance from "./synth_data_guidance.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { SynthDataGuidanceDataModel } from "./synth_data_guidance_datamodel"
  import { get } from "svelte/store"

  let custom_topic_mode: boolean = false

  export let guidance_data: SynthDataGuidanceDataModel
  // Local instance for dynamic reactive updates
  const selected_template = guidance_data.selected_template

  export let data: SampleDataNode
  export let path: string[]
  $: depth = path.length
  export let triggerSave: () => void

  let model: string = $ui_state.selected_model

  // Unique ID for this node
  const id = crypto.randomUUID()

  let expandedSamples: boolean[] = new Array(data.samples.length).fill(false)

  function toggleExpand(index: number) {
    expandedSamples[index] = !expandedSamples[index]
  }
  function collapseAll() {
    expandedSamples = new Array(data.samples.length).fill(false)
  }

  function formatExpandedSample(sample: SampleData): string {
    // If JSON, pretty format it
    try {
      const json = JSON.parse(sample.input)
      return JSON.stringify(json, null, 2)
    } catch (e) {
      // Not JSON
    }

    return sample.input
  }

  // Export these so we can share a var across all nodes -- makes it nicer if the UI saves the last value
  export let num_subtopics_to_generate: number = 8
  export let num_samples_to_generate: number = 8

  let topic_generation_error: KilnError | null = null
  let generate_subtopics: boolean = false
  let custom_topics_string: string = ""
  export async function open_generate_subtopics_modal() {
    // Avoid having a trillion of these hidden in the DOM
    generate_subtopics = true
    // Clear any previous error
    topic_generation_error = null
    await tick()
    const modal = document.getElementById(`${id}-generate-subtopics`)
    // Always start in normal mode
    custom_topic_mode = false
    // @ts-expect-error dialog is not a standard element
    modal?.showModal()
  }

  function scroll_to_bottom_of_element_by_id(id: string) {
    // Scroll to bottom only if it's out of view
    setTimeout(() => {
      const bottom = document.getElementById(id)
      if (bottom) {
        const rect = bottom.getBoundingClientRect()
        const isOffScreen = rect.bottom > window.innerHeight
        if (isOffScreen) {
          bottom.scrollIntoView({ behavior: "smooth", block: "end" })
        }
      }
    }, 50)
  }

  function add_subtopics(subtopics: string[]) {
    // Add ignoring dupes and empty strings
    for (const topic of subtopics) {
      if (!topic) {
        continue
      }
      if (data.sub_topics.find((t) => t.topic === topic)) {
        continue
      }
      data.sub_topics.push({ topic, sub_topics: [], samples: [] })
    }

    // trigger reactivity
    data = data

    // Trigger save to localStorage
    triggerSave()

    // Close modal
    const modal = document.getElementById(`${id}-generate-subtopics`)
    // @ts-expect-error dialog is not a standard element
    modal?.close()

    // Optional: remove it from DOM
    generate_subtopics = false

    // Scroll to bottom of added topics
    scroll_to_bottom_of_element_by_id(`${id}-subtopics`)
  }

  function add_custom_topics() {
    if (!custom_topics_string) {
      return
    }
    const topics = custom_topics_string.split(",").map((t) => t.trim())
    add_subtopics(topics)

    custom_topics_string = ""
  }

  let topic_generating: boolean = false
  async function generate_topics() {
    try {
      topic_generating = true
      topic_generation_error = null
      if (!model) {
        throw new KilnError("No model selected.", null)
      }
      const model_provider = model.split("/")[0]
      const model_name = model.split("/").slice(1).join("/")
      if (!model_name || !model_provider) {
        throw new KilnError("Invalid model selected.", null)
      }
      const existing_topics = data.sub_topics.map((t) => t.topic)
      const topic_guidance = get(guidance_data.topic_guidance)
      const { data: generate_response, error: generate_error } =
        await client.POST(
          "/api/projects/{project_id}/tasks/{task_id}/generate_categories",
          {
            body: {
              node_path: path,
              num_subtopics: num_subtopics_to_generate,
              model_name: model_name,
              provider: model_provider,
              gen_type: guidance_data.gen_type,
              guidance: topic_guidance ? topic_guidance : null, // clear empty string
              existing_topics:
                existing_topics.length > 0 ? existing_topics : null, // clear empty array
            },
            params: {
              path: {
                project_id: guidance_data.project_id,
                task_id: guidance_data.task_id,
              },
            },
          },
        )
      if (generate_error) {
        throw generate_error
      }
      const response = JSON.parse(generate_response.output.output)
      if (
        !response ||
        !response.subtopics ||
        !Array.isArray(response.subtopics)
      ) {
        throw new KilnError("No options returned.", null)
      }
      // Add new topics
      add_subtopics(response.subtopics)
    } catch (e) {
      if (e instanceof Error && e.message.includes("Load failed")) {
        topic_generation_error = new KilnError(
          "Could not generate topics, unknown error. If it persists, try another model.",
          null,
        )
      } else {
        topic_generation_error = createKilnError(e)
      }
    } finally {
      topic_generating = false
    }
  }

  let generate_samples_modal: boolean = false
  let generate_samples_cascade_mode: boolean = false
  export async function open_generate_samples_modal(
    cascade_mode: boolean = false,
  ) {
    // Avoid having a trillion of these hidden in the DOM
    generate_samples_modal = true
    generate_samples_cascade_mode = cascade_mode
    await tick()
    const modal = document.getElementById(`${id}-generate-samples`)
    // @ts-expect-error dialog is not a standard element
    modal?.showModal()
  }

  const dispatch = createEventDispatcher<{
    delete_topic: { node_to_delete: SampleDataNode }
  }>()

  function delete_topic() {
    dispatch("delete_topic", { node_to_delete: data })
    // Note: The parent will handle removing this node and triggering save
  }

  function handleChildDeleteTopic(
    event: CustomEvent<{ node_to_delete: SampleDataNode }>,
  ) {
    // Remove the topic from sub_topics array
    data.sub_topics = data.sub_topics.filter(
      (t) => t !== event.detail.node_to_delete,
    )

    // Trigger reactivity
    data = data

    // Trigger save to localStorage
    triggerSave()
  }

  function delete_sample(sample_to_delete: SampleData) {
    data.samples = data.samples.filter((s) => s !== sample_to_delete)
    collapseAll()

    // Trigger reactivity
    data = data

    // Trigger save to localStorage
    triggerSave()
  }

  function handleGenerateSamplesCompleted() {
    // Trigger reactivity
    data = data

    // Trigger save to localStorage
    triggerSave()

    // close all modals
    generate_samples_modal = false

    // Scroll to bottom of added samples
    scroll_to_bottom_of_element_by_id(`${id}-samples`)
  }
</script>

{#if path.length != 0}
  <div
    class="data-row-collapsed bg-base-200 font-medium flex flex-row pr-4 border-b-2 border-base-100"
    style="padding-left: {(depth - 1) * 25 + 20}px"
  >
    <div class="flex-1 py-1">
      {#if depth > 1}
        <span class="text-xs relative" style="top: -3px">⮑</span>
      {/if}
      {data.topic}
    </div>
    <div
      class="hover-action flex flex-row gap-4 text-gray-500 font-light text-sm items-center"
    >
      <button class="link" on:click={delete_topic}>Delete</button>
      <button class="link" on:click={() => open_generate_subtopics_modal()}>
        Add Subtopics
      </button>

      {#if data.sub_topics.length > 0}
        <button class="link" on:click={() => open_generate_samples_modal()}>
          Generate Model Inputs (Only This Topic)
        </button>
        <button class="link" on:click={() => open_generate_samples_modal(true)}>
          Generate Model Inputs (All Subtopics)
        </button>
      {:else}
        <button class="link" on:click={() => open_generate_samples_modal()}>
          Generate Model Inputs
        </button>
      {/if}
    </div>
  </div>
{/if}
<div id={`${id}-samples`}>
  {#each data.samples as sample, index}
    <div
      style="padding-left: {depth * 25 + 20}px"
      class="{expandedSamples[index]
        ? 'data-row-expanded'
        : 'data-row-collapsed'} data-row flex flex-row items-center border-b-2 border-base-200"
    >
      <button
        on:click={() => toggleExpand(index)}
        class="w-full block text-left flex-1 font-mono text-sm overflow-hidden py-2"
      >
        {#if expandedSamples[index]}
          <pre class="whitespace-pre-wrap">{formatExpandedSample(sample)}</pre>
        {:else}
          <div class="truncate w-0 min-w-full">{sample.input}</div>
        {/if}
      </button>
      <div
        class="hover-action flex flex-row text-sm gap-x-4 gap-y-1 text-gray-500 font-light px-4"
        style={expandedSamples[index] ? "display: flex" : ""}
      >
        <button class="link flex" on:click={() => toggleExpand(index)}>
          {#if expandedSamples[index]}
            - Collapse
          {:else}
            + Expand
          {/if}
        </button>
        <button class="link flex" on:click={() => delete_sample(sample)}>
          Delete
        </button>
      </div>
    </div>
  {/each}
</div>
{#if data.sub_topics}
  <div id={`${id}-subtopics`}>
    {#each data.sub_topics as sub_node}
      <svelte:self
        data={sub_node}
        path={[...path, sub_node.topic]}
        {guidance_data}
        {triggerSave}
        bind:num_subtopics_to_generate
        bind:num_samples_to_generate
        on:delete_topic={handleChildDeleteTopic}
      />
    {/each}
  </div>
{/if}

{#if generate_subtopics}
  <dialog id={`${id}-generate-subtopics`} class="modal">
    <div class="modal-box">
      <form method="dialog">
        <button
          class="btn btn-sm text-xl btn-circle btn-ghost absolute right-2 top-2 focus:outline-none"
          >✕</button
        >
      </form>
      <h3 class="text-lg font-bold">
        {#if custom_topic_mode}
          Add Custom Topics
        {:else}
          Generate Topics
        {/if}
      </h3>
      <p class="text-sm font-light mb-8">
        {#if path.length == 0}
          Adding topics will help generate diverse data. They can be nested,
          forming a topic tree.
        {:else}
          Add a list of subtopics to {path.join(" → ")}
        {/if}
      </p>
      {#if topic_generating}
        <div class="flex flex-row justify-center">
          <div class="loading loading-spinner loading-lg my-12"></div>
        </div>
      {:else if custom_topic_mode}
        <div class="flex flex-col gap-4">
          <FormElement
            id="custom_topics"
            label="Custom topics"
            description="Comma separated list of topics to add to this node"
            bind:value={custom_topics_string}
          />
          <button
            class="btn btn-primary {custom_topics_string ? 'btn-primary' : ''}"
            on:click={add_custom_topics}>Add Custom Topics</button
          >
        </div>
      {:else}
        <div class="flex flex-col gap-4">
          {#if topic_generation_error}
            <div class="alert alert-error">
              {topic_generation_error.message}
            </div>
          {/if}
          <div class="flex flex-row items-center gap-4">
            <div class="flex-grow font-medium text-sm">Topic Count</div>
            <IncrementUi bind:value={num_subtopics_to_generate} />
          </div>
          <div>
            <SynthDataGuidance guidance_type="topics" {guidance_data} />
          </div>
          <AvailableModelsDropdown
            requires_data_gen={true}
            suggested_mode={guidance_data.suggest_uncensored($selected_template)
              ? "uncensored_data_gen"
              : "data_gen"}
            requires_uncensored_data_gen={guidance_data.suggest_uncensored(
              $selected_template,
            )}
            bind:model
          />
          <button class="btn mt-2 btn-primary" on:click={generate_topics}>
            Generate {num_subtopics_to_generate} Topics
          </button>
          <div class="text-center">
            <button
              class="link text-sm text-gray-500"
              on:click={() => (custom_topic_mode = true)}
              tabindex="0"
            >
              or manually add topics
            </button>
          </div>
        </div>
      {/if}
    </div>
    <form method="dialog" class="modal-backdrop">
      <button>close</button>
    </form>
  </dialog>
{/if}

{#if generate_samples_modal}
  <GenerateSamplesModal
    {id}
    {data}
    {path}
    {model}
    {guidance_data}
    {num_samples_to_generate}
    {custom_topics_string}
    on_completed={handleGenerateSamplesCompleted}
    cascade_mode={generate_samples_cascade_mode}
  />
{/if}

<style>
  .data-row-collapsed .hover-action {
    display: none;
    visibility: hidden;
  }
  .data-row-collapsed:hover .hover-action {
    display: flex;
    visibility: visible;
  }
</style>
