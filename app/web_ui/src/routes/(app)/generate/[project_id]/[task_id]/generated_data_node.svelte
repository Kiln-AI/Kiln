<script lang="ts">
  import type { SampleDataNode, SampleData } from "./gen_model"
  import { tick } from "svelte"
  import { client } from "$lib/api_client"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import { createEventDispatcher } from "svelte"
  import IncrementUi from "$lib/ui/increment_ui.svelte"
  import GenerateSamplesModal from "./generate_samples_modal.svelte"
  import SynthDataGuidance from "./synth_data_guidance.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { SynthDataGuidanceDataModel } from "./synth_data_guidance_datamodel"
  import { get } from "svelte/store"
  import posthog from "posthog-js"
  import TableButton from "./table_button.svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
  import RunConfigComponent from "$lib/ui/run_config_component/run_config_component.svelte"

  let custom_topic_mode: boolean = false

  export let guidance_data: SynthDataGuidanceDataModel
  // Local instance for dynamic reactive updates
  const selected_template = guidance_data.selected_template

  $: project_id = guidance_data.project_id
  let run_config_component: RunConfigComponent | null = null

  export let data: SampleDataNode
  export let path: string[]
  $: depth = path.length
  export let triggerSave: () => void

  // Unique ID for this node
  const id = crypto.randomUUID()

  let expandedSamples: boolean[] = new Array(data.samples.length).fill(false)

  function toggleExpand(index: number) {
    expandedSamples[index] = !expandedSamples[index]
  }
  function collapseAll() {
    expandedSamples = new Array(data.samples.length).fill(false)
  }

  function formatExpandedSample(data: string): string {
    // If JSON, pretty format it
    try {
      const json = JSON.parse(data)
      return JSON.stringify(json, null, 2)
    } catch (e) {
      // Not JSON
    }

    return data
  }

  function formatSampleOutput(
    response: SampleData,
    format_json: boolean,
  ): { status: string; output: string | null } {
    if (response.saved_id && !response.output) {
      // Special case for people upgrading with partly saved datasets in their indexedDB.
      // We know it's been saved and should say so, but not available for preview.
      // They can click the "Saved" link to view the output in the dataset.
      return { status: "Preview not available", output: null }
    }

    let output = response.output?.output.output || null
    if (!output) {
      return { status: "Not Generated", output: null }
    }

    let formatted_output = output
    if (format_json) {
      formatted_output = formatExpandedSample(output)
    }
    return { status: "Generated", output: formatted_output }
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
    // Grab the run config properties before it is no longer available
    const run_config_properties =
      run_config_component?.run_options_as_run_config_properties() ?? null
    try {
      topic_generating = true
      topic_generation_error = null
      if (!guidance_data.gen_type) {
        throw new KilnError("No generation type selected.", null)
      }
      if (!run_config_properties) {
        throw new KilnError("No run config properties.", null)
      }
      if (
        !run_config_properties.model_name ||
        !run_config_properties.model_provider_name
      ) {
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
              run_config_properties: run_config_properties,
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
      posthog.capture("generate_synthetic_topics", {
        num_subtopics: num_subtopics_to_generate,
        model_name: run_config_properties.model_name,
        provider: run_config_properties.model_provider_name,
        tools: run_config_properties.tools_config?.tools ?? [],
        structured_output_mode: run_config_properties.structured_output_mode,
        gen_type: guidance_data.gen_type,
      })
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

  function remove_sample_output(sample_to_remove: SampleData) {
    sample_to_remove.output = null
    collapseAll()

    // Trigger reactivity
    data = data

    // Trigger save to localStorage
    triggerSave()
  }

  function open_sample(sample_to_open: SampleData) {
    window.open(
      `/dataset/${guidance_data.project_id}/${guidance_data.task_id}/${sample_to_open.saved_id}/run`,
      "_blank",
    )
  }

  function handleGenerateSamplesCompleted() {
    // Trigger reactivity
    data = data

    // Trigger save to localStorage
    triggerSave()

    // close all modals
    generate_samples_modal = false

    // Scroll to bottom of added samples
    scroll_to_bottom_of_element_by_id(`${id}-samples-end`)
  }
</script>

<!-- Topic Header Row-->
{#if path.length != 0}
  <tr class="bg-base-200 border-t-2 border-base-100"
    ><td
      colspan="3"
      class="py-2"
      style="padding-left: {(depth - 1) * 25 + 20}px"
    >
      <div class="font-medium flex flex-row pr-4 w-full">
        <div class="flex-1">
          {#if depth > 1}
            <span class="text-xs relative" style="top: -3px">⮑</span>
          {/if}
          {data.topic}
          <span class="relative inline-block w-3 h-3">
            <div class="absolute top-[-3px] left-0">
              <InfoTooltip
                tooltip_text={"This is a topic. Content inside of it should relate to this theme." +
                  (path.length > 1
                    ? " The full topic path is: " + path.join(" → ")
                    : "")}
                position="bottom"
                no_pad={true}
              />
            </div>
          </span>
        </div>
      </div>
    </td>
    <td class="p-0">
      <div class="dropdown dropdown-end dropdown-hover">
        <TableButton />
        <!-- svelte-ignore a11y-no-noninteractive-tabindex -->
        <ul
          tabindex="0"
          class="dropdown-content menu bg-base-100 rounded-box z-[1] w-52 p-2 shadow"
        >
          <li>
            <button on:click={delete_topic}>Delete Topic</button>
          </li>
          <li>
            <button on:click={() => open_generate_subtopics_modal()}>
              Add Subtopics
            </button>
          </li>

          {#if data.sub_topics.length > 0}
            <li>
              <button on:click={() => open_generate_samples_modal()}>
                Generate Inputs (Only This Topic)
              </button>
            </li>
            <li>
              <button on:click={() => open_generate_samples_modal(true)}>
                Generate Inputs (All Subtopics)
              </button>
            </li>
          {:else}
            <li>
              <button on:click={() => open_generate_samples_modal()}>
                Generate Inputs
              </button>
            </li>
          {/if}
        </ul>
      </div>
    </td>
  </tr>
{/if}
{#each data.samples as sample, index}
  {@const { status: output_status, output: formatted_output } =
    formatSampleOutput(sample, expandedSamples[index])}
  <tr on:click={() => toggleExpand(index)} class="cursor-pointer">
    <td style="padding-left: {depth * 25 + 20}px" class="py-2">
      {#if expandedSamples[index]}
        <pre class="whitespace-pre-wrap">{formatExpandedSample(
            sample.input,
          )}</pre>
      {:else}
        <div class="truncate w-0 min-w-full">{sample.input}</div>
      {/if}
    </td>
    <td class="py-2">
      {#if !formatted_output}
        {output_status}
      {:else if expandedSamples[index]}
        <pre class="whitespace-pre-wrap">{formatted_output}</pre>
      {:else}
        <div class="truncate w-0 min-w-full">
          {formatted_output}
        </div>
      {/if}
    </td>
    <td class="py-2">
      {#if sample.saved_id}
        <a
          href={`/dataset/${guidance_data.project_id}/${guidance_data.task_id}/${sample.saved_id}/run`}
          class="hover:underline">Saved</a
        >
      {:else if sample.output}
        Unsaved
      {:else}
        No Output
      {/if}
    </td>
    <td class="p-0">
      <div class="dropdown dropdown-end dropdown-hover">
        <TableButton />
        <!-- svelte-ignore a11y-no-noninteractive-tabindex -->
        <ul
          tabindex="0"
          class="dropdown-content menu bg-base-100 rounded-box z-[1] w-52 p-2 shadow"
        >
          {#if !sample.saved_id}
            <li>
              <button on:click|stopPropagation={() => delete_sample(sample)}>
                Remove Sample
              </button>
            </li>
          {/if}
          {#if !sample.saved_id && sample.output}
            <li>
              <button
                on:click|stopPropagation={() => remove_sample_output(sample)}
              >
                Remove Output
              </button>
            </li>
          {/if}
          {#if sample.saved_id}
            <li>
              <button on:click|stopPropagation={() => open_sample(sample)}>
                View in Dataset
              </button>
            </li>
          {/if}
        </ul>
      </div>
    </td>
  </tr>
{/each}
<!-- Hidden element purely for scroll targeting, not 'hidden' as that breaks scrolling -->
<tr class="h-0" id={`${id}-samples-end`}></tr>
{#if data.sub_topics}
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
  <!-- Hidden element purely for scroll targeting, not 'hidden' as that breaks scrolling -->
  <tr class="h-0" id={`${id}-subtopics`}></tr>
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
          <RunConfigComponent
            bind:this={run_config_component}
            {project_id}
            requires_structured_output={true}
            hide_prompt_selector={true}
            show_tools_selector_in_advanced={true}
            model_dropdown_settings={{
              requires_data_gen: true,
              requires_uncensored_data_gen:
                guidance_data.suggest_uncensored($selected_template),
              suggested_mode: guidance_data.suggest_uncensored(
                $selected_template,
              )
                ? "uncensored_data_gen"
                : "data_gen",
            }}
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
    {guidance_data}
    {num_samples_to_generate}
    {custom_topics_string}
    on_completed={handleGenerateSamplesCompleted}
    cascade_mode={generate_samples_cascade_mode}
  />
{/if}
