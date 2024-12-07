<script lang="ts">
  import type { SampleDataNode, SampleData } from "./gen_model"
  import AvailableModelsDropdown from "../../../run/available_models_dropdown.svelte"
  import { tick } from "svelte"
  import { client } from "$lib/api_client"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import { ui_state } from "$lib/stores"
  import { createEventDispatcher } from "svelte"
  import IncrementUi from "./increment_ui.svelte"
  import DataGenIntro from "./data_gen_intro.svelte"

  export let data: SampleDataNode
  export let path: string[]
  $: depth = path.length
  export let project_id: string
  export let task_id: string
  export let human_guidance: string | null = null

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

  let topic_generation_error: KilnError | null = null
  let generate_subtopics: boolean = false
  let num_subtopics_to_generate: number = 6
  let custom_topics_string: string = ""
  async function open_generate_subtopics_modal() {
    // Avoid having a trillion of these hidden in the DOM
    generate_subtopics = true
    // Clear any previous error
    topic_generation_error = null
    await tick()
    const modal = document.getElementById(`${id}-generate-subtopics`)
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
      const { data: generate_response, error: generate_error } =
        await client.POST(
          "/api/projects/{project_id}/tasks/{task_id}/generate_categories",
          {
            body: {
              node_path: path,
              num_subtopics: num_subtopics_to_generate,
              model_name: model_name,
              provider: model_provider,
              human_guidance: human_guidance ? human_guidance : null, // clear empty string
              existing_topics:
                existing_topics.length > 0 ? existing_topics : null, // clear empty array
            },
            params: {
              path: {
                project_id,
                task_id,
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
  async function open_generate_samples_modal() {
    // Avoid having a trillion of these hidden in the DOM
    generate_samples_modal = true
    // Clear any previous error
    sample_generation_error = null
    await tick()
    const modal = document.getElementById(`${id}-generate-samples`)
    // @ts-expect-error dialog is not a standard element
    modal?.showModal()
  }

  function add_synthetic_samples(
    samples: unknown[],
    model_name: string,
    model_provider: string,
  ) {
    // Add ignoring dupes and empty strings
    for (const sample of samples) {
      if (!sample) {
        continue
      }
      let input: string | null = null
      if (typeof sample == "string") {
        input = sample
      } else if (typeof sample == "object" || Array.isArray(sample)) {
        input = JSON.stringify(sample)
      }
      if (input) {
        data.samples.push({
          input: input,
          saved_id: null,
          model_name,
          model_provider,
        })
      }
    }

    // trigger reactivity
    data = data

    // Close modal
    const modal = document.getElementById(`${id}-generate-samples`)
    // @ts-expect-error dialog is not a standard element
    modal?.close()

    // Optional: remove it from DOM
    generate_samples_modal = false

    // Scroll to bottom of added samples
    scroll_to_bottom_of_element_by_id(`${id}-samples`)
  }

  let num_samples_to_generate: number = 8
  let sample_generating: boolean = false
  let sample_generation_error: KilnError | null = null
  async function generate_samples() {
    try {
      sample_generating = true
      sample_generation_error = null
      if (!model) {
        throw new KilnError("No model selected.", null)
      }
      const model_provider = model.split("/")[0]
      const model_name = model.split("/").slice(1).join("/")
      if (!model_name || !model_provider) {
        throw new KilnError("Invalid model selected.", null)
      }
      const { data: generate_response, error: generate_error } =
        await client.POST(
          "/api/projects/{project_id}/tasks/{task_id}/generate_samples",
          {
            body: {
              topic: path,
              num_samples: num_samples_to_generate,
              model_name: model_name,
              provider: model_provider,
              human_guidance: human_guidance ? human_guidance : null, // clear empty string
            },
            params: {
              path: {
                project_id,
                task_id,
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
        !response.generated_samples ||
        !Array.isArray(response.generated_samples)
      ) {
        throw new KilnError("No options returned.", null)
      }
      // Add new samples
      add_synthetic_samples(
        response.generated_samples,
        model_name,
        model_provider,
      )
    } catch (e) {
      if (e instanceof Error && e.message.includes("Load failed")) {
        sample_generation_error = new KilnError(
          "Could not generate samples, unknown error. If it persists, try another model.",
          null,
        )
      } else {
        sample_generation_error = createKilnError(e)
      }
    } finally {
      sample_generating = false
    }
  }

  const dispatch = createEventDispatcher<{
    delete_topic: { node_to_delete: SampleDataNode }
  }>()

  function delete_topic() {
    dispatch("delete_topic", { node_to_delete: data })
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
  }

  function delete_sample(sample_to_delete: SampleData) {
    data.samples = data.samples.filter((s) => s !== sample_to_delete)
    collapseAll()

    // Trigger reactivity
    data = data
  }

  $: is_empty = data.sub_topics.length == 0 && data.samples.length == 0
</script>

{#if path.length == 0}
  <!-- Root node -->
  <div class="flex flex-col md:flex-row gap-32 justify-center items-center">
    {#if is_empty}
      <div class="flex flex-col items-center justify-center min-h-[60vh]">
        <DataGenIntro />
      </div>
    {/if}
    <div
      class="flex flex-row justify-center {is_empty
        ? ' flex-col gap-6'
        : 'mb-6 gap-8'}"
    >
      <button
        class="btn {is_empty ? 'btn-primary' : ''}"
        on:click={() => open_generate_subtopics_modal()}
      >
        Add Top Level Topics
      </button>
      <button
        class="btn {is_empty ? 'btn-primary' : ''}"
        on:click={() => open_generate_samples_modal()}
      >
        Add Top Level Data
      </button>
    </div>
  </div>
{:else}
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
        Add subtopics
      </button>
      <button class="link" on:click={() => open_generate_samples_modal()}>
        Add data
      </button>
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
        {project_id}
        {task_id}
        {human_guidance}
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
      <h3 class="text-lg font-bold">Add Subtopics</h3>
      <p class="text-sm font-light mb-8">
        Add a list of subtopics
        {#if path.length > 0}
          to {path.join(" → ")}
        {/if}
      </p>
      {#if topic_generating}
        <div class="flex flex-row justify-center">
          <div class="loading loading-spinner loading-lg my-12"></div>
        </div>
      {:else}
        <div class="flex flex-col gap-2">
          {#if topic_generation_error}
            <div class="alert alert-error">
              {topic_generation_error.message}
            </div>
          {/if}
          <div class="flex-grow font-medium">Generate topics</div>
          <div class="flex flex-row items-center gap-4 mt-4 mb-2">
            <div class="flex-grow font-medium text-sm">Topic Count</div>
            <IncrementUi bind:value={num_subtopics_to_generate} />
          </div>
          <AvailableModelsDropdown requires_data_gen={true} bind:model />
          <button
            class="btn btn-sm {custom_topics_string ? '' : 'btn-primary'}"
            on:click={generate_topics}
          >
            Generate {num_subtopics_to_generate} Topics
          </button>
          <div class="divider">OR</div>
          <div class="flex flex-col">
            <div class="flex-grow font-medium">Custom topics</div>
            <div class="text-xs text-gray-500">Comma separated list</div>
          </div>
          <input
            type="text"
            bind:value={custom_topics_string}
            class="input input-bordered input-sm"
          />
          <button
            class="btn btn-sm {custom_topics_string ? 'btn-primary' : ''}"
            on:click={add_custom_topics}>Add Custom Topics</button
          >
        </div>
      {/if}
    </div>
    <form method="dialog" class="modal-backdrop">
      <button>close</button>
    </form>
  </dialog>
{/if}

{#if generate_samples_modal}
  <dialog id={`${id}-generate-samples`} class="modal">
    <div class="modal-box">
      <form method="dialog">
        <button
          class="btn btn-sm text-xl btn-circle btn-ghost absolute right-2 top-2 focus:outline-none"
          >✕</button
        >
      </form>
      <h3 class="text-lg font-bold">Generate Samples</h3>
      <p class="text-sm font-light mb-8">
        Add synthetic data samples
        {#if path.length > 0}
          to {path.join(" → ")}
        {/if}
      </p>
      {#if sample_generating}
        <div class="flex flex-row justify-center">
          <div class="loading loading-spinner loading-lg my-12"></div>
        </div>
      {:else}
        <div class="flex flex-col gap-2">
          {#if sample_generation_error}
            <div class="alert alert-error">
              {sample_generation_error.message}
            </div>
          {/if}
          <div class="flex flex-row items-center gap-4 mt-4 mb-2">
            <div class="flex-grow font-medium text-sm">Sample Count</div>
            <IncrementUi bind:value={num_samples_to_generate} />
          </div>
          <AvailableModelsDropdown requires_data_gen={true} bind:model />
          <button
            class="btn mt-6 {custom_topics_string ? '' : 'btn-primary'}"
            on:click={generate_samples}
          >
            Generate {num_samples_to_generate} Samples
          </button>
        </div>
      {/if}
    </div>
    <form method="dialog" class="modal-backdrop">
      <button>close</button>
    </form>
  </dialog>
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

  .divider {
    display: flex;
    align-items: center;
    text-align: center;
    color: #666;
    font-size: 0.875rem;
    margin: 0.5rem 0;
    padding: 2.5rem 0 1.5rem 0;
  }

  .divider::before,
  .divider::after {
    content: "";
    flex: 1;
    border-bottom: 1px solid #ddd;
    margin: 0 0.75rem;
  }
</style>
