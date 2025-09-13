<script lang="ts">
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import Rating from "./rating.svelte"
  let repair_instructions: string | null = null
  import type {
    TaskRun,
    Task,
    RequirementRating,
    TaskRequirement,
  } from "$lib/types"
  import { client } from "$lib/api_client"
  import Output from "./output.svelte"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { bounceOut } from "svelte/easing"
  import { fly } from "svelte/transition"
  import { onMount } from "svelte"
  import TagDropdown from "./tag_dropdown.svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
  import type { components } from "../../../lib/api_schema"
  import Warning from "../../../lib/ui/warning.svelte"
  import OutputRepairEditForm from "./output_repair_edit_form.svelte"
  import {
    rating_options_for_sample,
    current_task_rating_options,
  } from "$lib/stores"
  import posthog from "posthog-js"
  import TraceComponent from "$lib/ui/trace/trace.svelte"
  import PropertyList from "$lib/ui/property_list.svelte"

  const REPAIR_ENABLED_FOR_SOURCES: Array<
    components["schemas"]["DataSourceType"]
  > = ["human", "synthetic"]

  export let project_id: string
  export let task: Task
  export let initial_run: TaskRun
  let updated_run: TaskRun | null = null
  $: run = updated_run || initial_run
  export let model_name: string | null = null
  export let provider: string | null = null
  export let run_complete: boolean = false
  export let focus_repair_on_appear: boolean = false

  // Dynamic rating requirements based on tags
  $: rating_requirements = rating_options_for_sample(
    $current_task_rating_options,
    run?.tags || [],
  )

  // note: this run is NOT the main run, but a repair run TaskRun
  let repair_run: TaskRun | null = null

  $: rate_focus = run && overall_rating === null
  // True if this "Run" has everything we want: a rating and a repaired output (or 5-star rating and no repair is needed)
  $: run_complete = overall_rating === 5 || !!run?.repaired_output?.output

  let show_raw_data = false
  let save_rating_error: KilnError | null = null
  let show_create_tag = false

  type RatingValue = number | null
  let overall_rating: RatingValue = null
  let requirement_ratings: RatingValue[] = []

  // Repair is available if the run has an overall rating but it's not 5 stars, and it doesn't yet have a repaired output
  $: should_offer_repair =
    run &&
    overall_rating !== null &&
    overall_rating !== 5 &&
    !run?.repaired_output?.output && // model already repaired
    !repair_run // repair generated, should show repair evaluation instead
  $: repair_review_available = !!repair_run && !run?.repaired_output
  $: repair_complete = !!run?.repaired_output?.output
  $: repair_enabled_for_source = REPAIR_ENABLED_FOR_SOURCES.some(
    (s) => s === run?.output?.source?.type,
  )

  $: repair_source =
    run?.repaired_output?.source?.type === "human"
      ? { type: "user", name: run.repaired_output.source.properties.created_by }
      : run?.repaired_output?.source?.type === "synthetic"
        ? { type: "synthetic" }
        : null

  // Use for some animations on first mount
  let mounted = false
  onMount(() => {
    setTimeout(() => {
      mounted = true
    }, 50) // Short delay to ensure component is fully mounted
  })

  function load_server_ratings(
    new_run: TaskRun | null,
    reqs: TaskRequirement[],
  ) {
    // Skip if run or requirements are missing
    if (!reqs || !new_run) {
      return
    }
    // Fill ratings with nulls
    requirement_ratings = Array(reqs.length).fill(null)
    if (!new_run) {
      return
    }
    overall_rating = (new_run.output.rating?.value || null) as RatingValue
    Object.entries(new_run.output.rating?.requirement_ratings || {}).forEach(
      ([req_id, rating]) => {
        let index = reqs.findIndex((req) => req.id === req_id)
        if (index !== -1) {
          const task_req = reqs[index]
          // Only load if the task requirement type matches the rating type. Technically users can switch the rating type, and we don't want to assume a 1 star rating is a "pass"
          if (task_req.type === rating.type) {
            requirement_ratings[index] = rating.value
          }
        }
      },
    )
  }
  // Load ratings anytime the run or rating requirements change
  $: load_server_ratings(run, rating_requirements)

  async function patch_run(
    patch_body: Record<string, unknown>,
  ): Promise<TaskRun> {
    const {
      data, // only present if 2XX response
      error: fetch_error, // only present if 4XX or 5XX response
    } = await client.PATCH(
      "/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}",
      {
        params: {
          path: {
            project_id: project_id,
            task_id: task.id || "",
            run_id: run?.id || "",
          },
        },
        // @ts-expect-error type checking and PATCH don't mix
        body: patch_body,
      },
    )
    if (fetch_error) {
      throw fetch_error
    }
    return data
  }

  let tags_error: KilnError | null = null
  function add_tags(tags: string[]) {
    let prior_tags = run.tags
    let new_tags = [...prior_tags, ...tags]
    let unique_tags = [...new Set(new_tags)]
    save_tags(unique_tags)
  }

  function remove_tag(tag: string) {
    let prior_tags = run.tags
    let new_tags = prior_tags.filter((t) => t !== tag)
    save_tags(new_tags)
  }

  async function save_tags(tags: string[]) {
    try {
      let patch_body = {
        tags: tags,
      }
      updated_run = await patch_run(patch_body)
      show_create_tag = false
      tags_error = null
    } catch (err) {
      tags_error = createKilnError(err)
    }
  }

  async function save_ratings() {
    try {
      let requirement_ratings_obj: Record<string, RequirementRating | null> = {}
      rating_requirements.forEach((req, index) => {
        if (!req.id) {
          return
        }
        if (
          requirement_ratings[index] !== null &&
          requirement_ratings[index] !== undefined
        ) {
          requirement_ratings_obj[req.id] = {
            value: requirement_ratings[index],
            type: req.type,
          }
        } else {
          requirement_ratings_obj[req.id] = null
        }
      })
      let patch_body = {
        output: {
          rating: {
            value: overall_rating,
            type: "five_star",
            requirement_ratings: requirement_ratings_obj,
          },
        },
      }
      updated_run = await patch_run(patch_body)
      save_rating_error = null
      posthog.capture("save_ratings", {})
    } catch (err) {
      save_rating_error = createKilnError(err)
    }
  }

  let repair_submitting = false
  let repair_error: KilnError | null = null
  async function attempt_repair() {
    try {
      repair_submitting = true
      if (!repair_instructions) {
        throw new KilnError("Repair instructions are required", null)
      }
      if (!task.id || !run?.id) {
        throw new KilnError(
          "This task run isn't saved. Enable Auto-save. You can't repair unsaved runs.",
          null,
        )
      }
      const {
        data: repair_data, // only present if 2XX response
        error: fetch_error, // only present if 4XX or 5XX response
      } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}/run_repair",
        {
          params: {
            path: {
              project_id: project_id,
              task_id: task.id,
              run_id: run?.id,
            },
          },
          body:
            model_name && provider
              ? {
                  evaluator_feedback: repair_instructions,
                  model_name: model_name,
                  provider: provider,
                }
              : {
                  evaluator_feedback: repair_instructions,
                },
        },
      )
      if (fetch_error) {
        throw fetch_error
      }
      repair_run = repair_data
      repair_error = null
    } catch (err) {
      repair_error = createKilnError(err)
    } finally {
      repair_submitting = false
    }
  }

  function toggle_raw_data() {
    show_raw_data = !show_raw_data
    if (show_raw_data) {
      // Scroll to the raw data section when it's shown
      setTimeout(() => {
        const rawDataElement = document.getElementById("raw_data")
        if (rawDataElement) {
          rawDataElement.scrollIntoView({ behavior: "smooth", block: "start" })
        }
      }, 100)
    }
  }

  let accept_repair_error: KilnError | null = null
  let accept_repair_submitting = false
  async function accept_repair() {
    try {
      accept_repair_error = null
      accept_repair_submitting = true
      if (!repair_run) {
        throw new KilnError("No repair to accept", null)
      }
      if (!task.id || !run?.id) {
        throw new KilnError(
          "This task run isn't saved. Enable Auto-save. You can't accept repairs for unsaved runs.",
          null,
        )
      }
      const {
        data, // only present if 2XX response
        error: fetch_error, // only present if 4XX or 5XX response
      } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}/repair",
        {
          params: {
            path: {
              project_id: project_id,
              task_id: task.id,
              run_id: run?.id,
            },
          },
          body: {
            repair_run: repair_run,
            evaluator_feedback: repair_instructions || "",
          },
        },
      )
      if (fetch_error) {
        throw fetch_error
      }
      updated_run = data
      repair_run = null
    } catch (err) {
      accept_repair_error = createKilnError(err)
    } finally {
      accept_repair_submitting = false
    }
  }

  let delete_repair_error: KilnError | null = null
  let delete_repair_submitting = false
  async function delete_repair() {
    if (
      !confirm(
        "Are you sure you want to delete this repair?\n\nThis action cannot be undone.",
      )
    ) {
      return
    }
    try {
      repair_run = null
      delete_repair_error = null
      delete_repair_submitting = true
      let original_repair_instructions = run?.repair_instructions
      let patch_body = {
        repair_instructions: null,
        repaired_output: null,
      }
      updated_run = await patch_run(patch_body)

      // Pull in the instructions from the original repair, so they can edit them if wanted
      if (!repair_instructions && original_repair_instructions) {
        repair_instructions = original_repair_instructions
      }
    } catch (err) {
      delete_repair_error = createKilnError(err)
    } finally {
      delete_repair_submitting = false
    }
  }

  function get_intermediate_output_title(name: string): string {
    return (
      {
        reasoning: "Model Reasoning Output",
        chain_of_thought: "Chain of Thought Output",
      }[name] || name
    )
  }

  function retry_repair() {
    repair_run = null
    accept_repair_error = null
  }

  let repair_edit_mode = false
  function show_repair_edit() {
    repair_edit_mode = true
  }

  function handle_manual_edit_cancel() {
    repair_edit_mode = false
  }

  function handle_manual_edit_submit(repair_run_edited: TaskRun) {
    repair_run = repair_run_edited
    repair_edit_mode = false
    updated_run = repair_run_edited
    repair_run = null
  }

  function get_usage_properties(run: TaskRun | null) {
    let properties = []

    if (run?.usage?.cost) {
      properties.push({
        name: "Cost",
        value: `$${run.usage.cost.toFixed(6)}`,
      })
    }

    if (run?.usage?.total_tokens) {
      properties.push({
        name: "Tokens",
        value: run.usage.total_tokens,
      })
    }

    return properties
  }
</script>

<div>
  <div class="flex flex-col xl:flex-row gap-8 xl:gap-16">
    <div class="grow min-w-0 overflow-hidden">
      <div class="text-xl font-bold mb-1">Output</div>
      {#if task.output_json_schema}
        <div class="text-xs font-medium text-gray-500 flex flex-row mb-2">
          <svg
            fill="currentColor"
            class="w-4 h-4 mr-[2px]"
            viewBox="0 0 56 56"
            xmlns="http://www.w3.org/2000/svg"
            ><path
              d="M 27.9999 51.9063 C 41.0546 51.9063 51.9063 41.0781 51.9063 28 C 51.9063 14.9453 41.0312 4.0937 27.9765 4.0937 C 14.8983 4.0937 4.0937 14.9453 4.0937 28 C 4.0937 41.0781 14.9218 51.9063 27.9999 51.9063 Z M 24.7655 40.0234 C 23.9687 40.0234 23.3593 39.6719 22.6796 38.8750 L 15.9296 30.5312 C 15.5780 30.0859 15.3671 29.5234 15.3671 29.0078 C 15.3671 27.9063 16.2343 27.0625 17.2655 27.0625 C 17.9452 27.0625 18.5077 27.3203 19.0702 28.0469 L 24.6718 35.2890 L 35.5702 17.8281 C 36.0155 17.1016 36.6249 16.75 37.2343 16.75 C 38.2655 16.75 39.2733 17.4297 39.2733 18.5547 C 39.2733 19.0703 38.9687 19.6328 38.6640 20.1016 L 26.7577 38.8750 C 26.2421 39.6484 25.5858 40.0234 24.7655 40.0234 Z"
            /></svg
          >
          Structure Valid
        </div>
      {/if}
      {#if run.trace}
        <!-- Render the output, but leave the COT and other intermediate output rendering to the trace -->
        <Output raw_output={run.output.output} />
        <div>
          <div class="font-bold mt-6 mb-1">All Messages</div>
          <TraceComponent trace={run.trace} />
        </div>
      {:else}
        <Output raw_output={run.output.output} />
        {#if run.intermediate_outputs}
          {#each Object.entries(run.intermediate_outputs) as [name, intermediate_output]}
            <div
              class="text-xs font-bold text-gray-500 mt-4 mb-1 flex flex-row items-center gap-1"
            >
              {get_intermediate_output_title(name)}
              <InfoTooltip
                tooltip_text={`This is intermediate output from the model, and not considered part of the final answer. This thinking helped formulate the final answer above. This is known as 'chain of thought', 'thinking output', or 'inference time compute'.`}
              />
            </div>
            <Output raw_output={intermediate_output} />
          {/each}
        {/if}
      {/if}
      <div>
        <div class="mt-2">
          <button class="text-xs link" on:click={toggle_raw_data}
            >{show_raw_data ? "Hide" : "Show"} Raw Data</button
          >
        </div>

        <div class={show_raw_data ? "" : "hidden"}>
          <h1 class="text-xl font-bold mt-2 mb-2" id="raw_data">Raw Data</h1>
          <div class="text-sm">
            <Output raw_output={JSON.stringify(run, null, 2)} />
          </div>
        </div>
      </div>

      {#if !repair_enabled_for_source && (should_offer_repair || repair_review_available || repair_complete)}
        <div class="grow mt-10">
          <Warning
            warning_message="Repair is not available for runs from {run.output
              .source?.type || 'unknown'} sources."
            warning_color="warning"
            tight={true}
          />
        </div>
      {/if}

      {#if repair_enabled_for_source && (should_offer_repair || repair_review_available || repair_complete)}
        <div class="grow mt-10">
          <div class="text-xl font-bold mb-2">Repair Output</div>
          {#if should_offer_repair}
            <p class="text-sm text-gray-500 mb-4">
              Since the output isn't 5-star, provide instructions for the model
              on how to fix it.
            </p>
            <FormContainer
              submit_label="Attempt Repair"
              on:submit={attempt_repair}
              bind:submitting={repair_submitting}
              bind:error={repair_error}
              focus_on_mount={focus_repair_on_appear}
            >
              <FormElement
                id="repair_instructions"
                label="Repair Instructions"
                inputType="textarea"
                bind:value={repair_instructions}
              />
            </FormContainer>
          {:else if repair_edit_mode && repair_run}
            <p class="text-sm text-gray-500 mb-4">
              Manually improve or correct the response.
            </p>
            <OutputRepairEditForm
              {task}
              {run}
              {repair_run}
              {project_id}
              repair_instructions={repair_instructions || ""}
              on_submit={handle_manual_edit_submit}
              on_cancel={handle_manual_edit_cancel}
            />
          {:else if repair_review_available}
            <p class="text-sm text-gray-500 mb-4">
              The model has attempted to fix the output given <span
                class="tooltip link"
                data-tip="The instructions you provided to the model: {repair_instructions ||
                  'No instruction provided'}">your instructions</span
              >. Review the result.
            </p>
            <Output raw_output={repair_run?.output.output || ""} />
          {:else if repair_complete}
            {#if repair_source?.type === "user"}
              <p class="text-sm text-gray-500 mb-4">
                This repaired output was provided by {repair_source.name}.
              </p>
            {:else}
              <p class="text-sm text-gray-500 mb-4">
                The model has fixed the output given <span
                  class="tooltip link"
                  data-tip="The instructions you provided to the model: {repair_instructions ||
                    'No instruction provided'}">your instructions</span
                >.
              </p>
            {/if}
            <Output raw_output={run?.repaired_output?.output || ""} />
            <div class="mt-2 text-xs text-gray-500 text-right">
              {#if delete_repair_submitting}
                <span class="loading loading-spinner loading-sm"></span>
              {:else if delete_repair_error}
                <p class="text-error">
                  Error Deleting Repair:
                  {delete_repair_error.getMessage()}
                </p>
              {:else}
                <button class="link" on:click={delete_repair}
                  >Delete Repair</button
                >
              {/if}
            </div>
          {/if}
        </div>
        {#if repair_review_available && !repair_edit_mode}
          <div class="mt-4">
            <div class="flex flex-row gap-4 justify-between">
              <button class="btn" on:click={show_repair_edit}>Edit</button>
              <div class="flex flex-row gap-4">
                <button class="btn" on:click={retry_repair}>Retry Repair</button
                >
                <button
                  class="btn btn-primary"
                  on:click={accept_repair}
                  disabled={accept_repair_submitting}
                >
                  {#if accept_repair_submitting}
                    <span class="loading loading-spinner loading-sm"></span>
                  {:else}
                    Accept Repair (5 Stars)
                  {/if}
                </button>
              </div>
            </div>

            {#if accept_repair_error}
              <p class="mt-2 text-error font-medium text-sm">
                Error Accepting Repair<br />
                <span class="text-error text-xs font-normal">
                  {accept_repair_error.getMessage()}</span
                >
              </p>
            {/if}
          </div>
        {/if}
      {/if}
    </div>

    <div class="w-72 2xl:w-96 flex-none">
      <div class="text-xl font-bold mt-10 lg:mt-0 mb-6">
        Output Rating
        {#if save_rating_error}
          <button class="tooltip" data-tip={save_rating_error.getMessage()}>
            <svg
              class="w-5 h-5 ml-1 text-error inline"
              viewBox="0 0 1024 1024"
              xmlns="http://www.w3.org/2000/svg"
              ><path
                fill="currentColor"
                d="M512 64a448 448 0 1 1 0 896 448 448 0 0 1 0-896zm0 192a58.432 58.432 0 0 0-58.24 63.744l23.36 256.384a35.072 35.072 0 0 0 69.76 0l23.296-256.384A58.432 58.432 0 0 0 512 256zm0 512a51.2 51.2 0 1 0 0-102.4 51.2 51.2 0 0 0 0 102.4z"
              /></svg
            >
          </button>
        {:else if rate_focus && mounted}
          <div class="w-7 h-7 ml-3 inline text-primary">
            <svg
              in:fly={{
                delay: 50,
                duration: 1000,
                easing: bounceOut,
                y: "-20px",
                opacity: 1,
              }}
              fill="currentColor"
              class="w-7 h-7 inline"
              viewBox="0 0 512 512"
              xmlns="http://www.w3.org/2000/svg"
              ><path
                d="M256,464c114.87,0,208-93.13,208-208S370.87,48,256,48,48,141.13,48,256,141.13,464,256,464ZM164.64,251.35a16,16,0,0,1,22.63-.09L240,303.58V170a16,16,0,0,1,32,0V303.58l52.73-52.32A16,16,0,1,1,347.27,274l-80,79.39a16,16,0,0,1-22.54,0l-80-79.39A16,16,0,0,1,164.64,251.35Z"
              /></svg
            >
          </div>
        {/if}
        <p class="text-xs text-gray-500 mt-1 font-light">
          Ratings are defined in the <a
            href={`/settings/edit_task/${project_id}/${task.id}`}
            class="link">task settings</a
          >.
        </p>
      </div>

      <div class="grid grid-cols-[auto,1fr] gap-4 text-sm 2xl:text-base">
        {#if rating_requirements}
          {#each rating_requirements as requirement, index}
            <div class="flex items-center">
              {requirement.name}:
              <InfoTooltip
                tooltip_text={`Requirement #${index + 1} - ${requirement.instruction || "No instruction provided"}${requirement.type === "pass_fail_critical" ? " Use 'critical' rating for responses which are never tolerable, beyond a typical failure." : ""}`}
              />
            </div>
            <div class="flex items-center">
              <Rating
                bind:rating={requirement_ratings[index]}
                type={requirement.type}
                size={6}
                on:rating_changed={save_ratings}
              />
            </div>
          {/each}
        {/if}
        <div class="font-medium flex items-center text-nowrap 2xl:min-w-32">
          Overall Rating:
        </div>
        <div class="flex items-center">
          <Rating
            bind:rating={overall_rating}
            type="five_star"
            size={7}
            on:rating_changed={save_ratings}
          />
        </div>
      </div>
      <div class="mt-8 mb-4">
        <div class="text-xl font-bold">Tags</div>
        {#if tags_error}
          <p class="text-error text-sm">
            {tags_error.getMessage()}
          </p>
        {/if}
        <div class="flex flex-row flex-wrap gap-2 mt-2">
          {#each run.tags.sort() as tag}
            <div class="badge bg-gray-200 text-gray-500 py-3 px-3 max-w-full">
              <span class="truncate">{tag}</span>
              <button
                class="pl-3 font-medium shrink-0"
                on:click={() => remove_tag(tag)}>✕</button
              >
            </div>
          {/each}
          <button
            class="badge bg-gray-200 text-gray-500 p-3 font-medium {show_create_tag
              ? 'hidden'
              : ''}"
            on:click={() => (show_create_tag = true)}>+</button
          >
        </div>
        {#if show_create_tag}
          <div
            class="mt-3 flex flex-row gap-2 items-center {show_create_tag
              ? ''
              : 'hidden'}"
          >
            <TagDropdown
              on_select={(tag) => add_tags([tag])}
              on_escape={() => (show_create_tag = false)}
              focus_on_mount={true}
            />
            <div class="flex-none">
              <button
                class="btn btn-sm btn-circle text-xl font-medium"
                on:click={() => (show_create_tag = false)}>✕</button
              >
            </div>
          </div>
        {/if}
      </div>
      <div>
        <PropertyList properties={get_usage_properties(run)} title="Usage" />
      </div>
    </div>
  </div>
</div>
