<script lang="ts">
  import Rating from "./rating.svelte"
  import type {
    TaskRun,
    Task,
    Feedback,
    RequirementRating,
    TaskRequirement,
    Trace,
  } from "$lib/types"
  import { client } from "$lib/api_client"
  import Output from "$lib/ui/output.svelte"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { bounceOut } from "svelte/easing"
  import { fly } from "svelte/transition"
  import { onMount } from "svelte"
  import TagPicker from "../../../lib/ui/tag_picker.svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import {
    rating_options_for_sample,
    current_task_rating_options,
  } from "$lib/stores"
  import posthog from "posthog-js"
  import TraceComponent from "$lib/ui/trace/trace.svelte"
  import PropertyList from "$lib/ui/property_list.svelte"

  type SubtaskReference = {
    project_id: string
    task_id: string
    run_id: string
  }

  function extract_subtask_references(trace: Trace): SubtaskReference[] {
    const references: SubtaskReference[] = []
    for (const message of trace) {
      if (
        "kiln_task_tool_data" in message &&
        message.kiln_task_tool_data &&
        typeof message.kiln_task_tool_data === "string"
      ) {
        const [project_id, , task_id, run_id] =
          message.kiln_task_tool_data.split(":::")
        if (project_id && task_id && run_id) {
          references.push({ project_id, task_id, run_id })
        }
      }
    }
    return references
  }

  async function calculate_subtask_usage(
    trace: Trace | null | undefined,
    visited: Set<string> = new Set(),
  ): Promise<{ cost: number; tokens: number }> {
    if (!trace) return { cost: 0, tokens: 0 }

    const references = extract_subtask_references(trace)
    let total_cost = 0
    let total_tokens = 0

    for (const ref of references) {
      const key = `${ref.project_id}:${ref.task_id}:${ref.run_id}`
      if (visited.has(key)) continue
      visited.add(key)

      try {
        const response = await client.GET(
          "/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}",
          {
            params: {
              path: {
                project_id: ref.project_id,
                task_id: ref.task_id,
                run_id: ref.run_id,
              },
            },
          },
        )

        if (!response.error && response.data) {
          total_cost += response.data.usage?.cost ?? 0
          total_tokens += response.data.usage?.total_tokens ?? 0
          const subtask_usage = await calculate_subtask_usage(
            response.data.trace,
            visited,
          )
          total_cost += subtask_usage.cost
          total_tokens += subtask_usage.tokens
        }
      } catch (error) {
        console.warn(
          "Failed to fetch subtask usage, continuing on error as subtask run may have been deleted.",
          {
            project_id: ref.project_id,
            task_id: ref.task_id,
            run_id: ref.run_id,
            error,
          },
        )
      }
    }

    return { cost: total_cost, tokens: total_tokens }
  }

  let subtask_cost: number | null = null
  let subtask_tokens: number | null = null
  let subtask_usage_loading = false
  // Counter to prevent race conditions: when run changes rapidly, multiple async requests
  // may be in flight. We only update state if this request is still the latest one.

  let subtask_usage_request_id = 0

  async function load_subtask_usage(trace: Trace | null | undefined) {
    const request_id = ++subtask_usage_request_id

    if (!trace || extract_subtask_references(trace).length === 0) {
      if (request_id === subtask_usage_request_id) {
        subtask_cost = null
        subtask_tokens = null
        subtask_usage_loading = false
      }
      return
    }

    subtask_usage_loading = true
    try {
      const usage = await calculate_subtask_usage(trace)
      if (request_id === subtask_usage_request_id) {
        subtask_cost = usage.cost
        subtask_tokens = usage.tokens
      }
    } catch {
      if (request_id === subtask_usage_request_id) {
        subtask_cost = null
        subtask_tokens = null
      }
    } finally {
      if (request_id === subtask_usage_request_id) {
        subtask_usage_loading = false
      }
    }
  }

  export let project_id: string
  export let task: Task
  export let initial_run: TaskRun
  let updated_run: TaskRun | null = null
  $: run = updated_run || initial_run
  export let run_complete: boolean = false

  // Dynamic rating requirements based on tags
  $: rating_requirements = rating_options_for_sample(
    $current_task_rating_options,
    run?.tags || [],
  )

  $: rate_focus = run && overall_rating === null
  $: run_complete = overall_rating !== null

  let show_raw_data = false
  let save_rating_error: KilnError | null = null

  type RatingValue = number | null
  let overall_rating: RatingValue = null
  let requirement_ratings: RatingValue[] = []

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
        body: patch_body,
      },
    )
    if (fetch_error) {
      throw fetch_error
    }
    return data
  }

  let tags_error: KilnError | null = null

  async function save_tags(tags: string[]) {
    try {
      let patch_body = {
        tags: tags,
      }
      updated_run = await patch_run(patch_body)
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

  function get_intermediate_output_title(name: string): string {
    return (
      {
        reasoning: "Model Reasoning Output",
        chain_of_thought: "Chain of Thought Output",
      }[name] || name
    )
  }

  function get_usage_properties(
    run: TaskRun | null,
    subtask_cost: number | null,
    subtask_usage_loading: boolean,
    subtask_tokens: number | null,
  ) {
    let properties = []

    const run_cost = run?.usage?.cost ?? 0
    const run_tokens = run?.usage?.total_tokens ?? 0

    if (subtask_usage_loading) {
      properties.push({
        name: "Total Cost",
        value: "Loading...",
      })
    } else {
      const total_cost = run_cost + (subtask_cost ?? 0)
      if (total_cost > 0) {
        properties.push({
          name: "Total Cost",
          value: `$${total_cost.toFixed(6)}`,
        })
      }
    }

    if (subtask_usage_loading) {
      properties.push({
        name: "Subtasks Cost",
        value: "Loading...",
      })
    } else if (subtask_cost && subtask_cost > 0) {
      properties.push({
        name: "Subtasks Cost",
        value: `$${subtask_cost.toFixed(6)}`,
      })
    }

    if (subtask_usage_loading) {
      properties.push({
        name: "Total Tokens",
        value: "Loading...",
      })
    } else {
      const total_tokens = run_tokens + (subtask_tokens ?? 0)
      if (total_tokens > 0) {
        properties.push({
          name: "Total Tokens",
          value: total_tokens,
        })
      }
    }

    if (subtask_usage_loading) {
      properties.push({
        name: "Subtasks Tokens",
        value: "Loading...",
      })
    } else if (subtask_tokens && subtask_tokens > 0) {
      properties.push({
        name: "Subtasks Tokens",
        value: subtask_tokens,
      })
    }

    return properties
  }

  $: load_subtask_usage(run?.trace)
  $: usage_properties = get_usage_properties(
    run,
    subtask_cost,
    subtask_usage_loading,
    subtask_tokens,
  )

  // Feedback
  let feedbacks: Feedback[] = []
  let feedback_loading = false
  let feedback_error: KilnError | null = null
  let add_feedback_dialog: Dialog
  let add_feedback_open = false
  let view_feedback_dialog: Dialog
  let new_feedback_text = ""
  let add_feedback_submitting = false

  const MAX_VISIBLE_FEEDBACKS = 3

  type FeedbackSortColumn = "created_by" | "created_at"
  let feedback_sort_column: FeedbackSortColumn = "created_at"
  let feedback_sort_direction: "asc" | "desc" = "desc"

  function handle_feedback_sort(column: FeedbackSortColumn) {
    if (feedback_sort_column === column) {
      feedback_sort_direction =
        feedback_sort_direction === "asc" ? "desc" : "asc"
    } else {
      feedback_sort_column = column
      feedback_sort_direction = column === "created_at" ? "desc" : "asc"
    }
  }

  $: sorted_feedbacks = [...feedbacks].sort((a, b) => {
    const dir = feedback_sort_direction === "asc" ? 1 : -1
    if (feedback_sort_column === "created_by") {
      return dir * (a.created_by ?? "").localeCompare(b.created_by ?? "")
    }
    return dir * (a.created_at ?? "").localeCompare(b.created_at ?? "")
  })

  async function load_feedback() {
    if (!task.id || !run?.id) return
    feedback_loading = true
    try {
      const { data, error: fetch_error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}/feedback",
        {
          params: {
            path: {
              project_id,
              task_id: task.id,
              run_id: run.id,
            },
          },
        },
      )
      if (fetch_error) throw fetch_error
      feedbacks = data
      feedback_error = null
    } catch (err) {
      feedback_error = createKilnError(err)
    } finally {
      feedback_loading = false
    }
  }

  let add_feedback_error: KilnError | null = null

  async function submit_feedback() {
    if (!task.id || !run?.id || !new_feedback_text.trim()) return
    try {
      const { data, error: fetch_error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}/feedback",
        {
          params: {
            path: {
              project_id,
              task_id: task.id,
              run_id: run.id,
            },
          },
          body: {
            feedback: new_feedback_text.trim(),
            source: "run-page",
          },
        },
      )
      if (fetch_error) throw fetch_error
      feedbacks = [...feedbacks, data]
      new_feedback_text = ""
      add_feedback_dialog.close()
      add_feedback_error = null
    } catch (err) {
      add_feedback_error = createKilnError(err)
    } finally {
      add_feedback_submitting = false
    }
  }

  function format_date(date_str: string | undefined): string {
    if (!date_str) return ""
    return new Date(date_str).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    })
  }

  $: if (run?.id && task.id) load_feedback()
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
          <div class="font-bold mt-6 mb-2">Message Trace</div>
          <TraceComponent trace={run.trace} {project_id} />
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
    </div>

    <div class="w-72 2xl:w-96 flex-none">
      <div class="text-xl font-bold mt-10 lg:mt-0 mb-6">
        Rating and Feedback
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
        <div
          class="flex items-center flex items-center text-nowrap 2xl:min-w-32"
        >
          <div class="font-medium">Overall Rating:</div>
          <div class="text-gray-500">
            <InfoTooltip tooltip_text="The overall rating of the output." />
          </div>
        </div>
        <div class="flex items-center">
          <Rating
            bind:rating={overall_rating}
            type="five_star"
            size={7}
            on:rating_changed={save_ratings}
          />
        </div>
        <div class="font-medium flex items-center text-nowrap">Feedback:</div>
        <div class="flex items-center">
          <button
            type="button"
            class="link text-sm text-gray-500"
            on:click={() => {
              new_feedback_text = ""
              add_feedback_error = null
              add_feedback_open = true
              add_feedback_dialog.show()
            }}>Add Feedback</button
          >
        </div>
        {#if feedback_error}
          <div></div>
          <p class="text-error text-xs">{feedback_error.getMessage()}</p>
        {/if}
        {#if feedback_loading}
          <div></div>
          <div>
            <span class="loading loading-spinner loading-xs"></span>
          </div>
        {:else if feedbacks.length > 0}
          <div class="-mb-3"></div>
          <!-- svelte-ignore a11y-no-static-element-interactions -->
          <div
            tabindex="0"
            role="button"
            class="-mt-3 text-left cursor-pointer hover:bg-base-200 focus-visible:bg-base-200 rounded-lg p-2 -ml-2 transition-colors outline-none"
            on:click={(e) => {
              const el = e.currentTarget
              if (el instanceof HTMLElement) el.blur()
              view_feedback_dialog.show()
            }}
            on:keydown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault()
                const el = e.currentTarget
                if (el instanceof HTMLElement) el.blur()
                view_feedback_dialog.show()
              }
            }}
          >
            {#each feedbacks.slice(0, MAX_VISIBLE_FEEDBACKS) as fb}
              <div class="mb-2 last:mb-0">
                <div class="text-xs text-gray-500">
                  {fb.created_by || "Unknown"}
                </div>
                <div class="text-sm line-clamp-2">
                  {fb.feedback}
                </div>
              </div>
            {/each}
            {#if feedbacks.length > MAX_VISIBLE_FEEDBACKS}
              <div class="text-xs text-gray-400 mt-1">
                {feedbacks.length - MAX_VISIBLE_FEEDBACKS} more…
              </div>
            {/if}
          </div>
        {/if}
      </div>
      <div class="mt-8 mb-4">
        <div class="text-xl font-bold">Tags</div>
        {#if tags_error}
          <p class="text-error text-sm">
            {tags_error.getMessage()}
          </p>
        {/if}
        <TagPicker
          tags={run.tags}
          tag_type="task_run"
          {project_id}
          task_id={task.id || null}
          initial_expanded={false}
          on:tags_changed={(event) => {
            const { current } = event.detail
            run.tags = current
            save_tags(current)
          }}
        />
      </div>
      <div>
        {#if usage_properties && usage_properties.length > 0}
          <PropertyList properties={usage_properties} title="Usage" />
        {/if}
      </div>
    </div>
  </div>
</div>

<Dialog
  bind:this={add_feedback_dialog}
  title="Add Feedback"
  on:close={() => (add_feedback_open = false)}
>
  {#if add_feedback_open}
    <FormContainer
      submit_label="Add"
      on:submit={submit_feedback}
      bind:submitting={add_feedback_submitting}
      bind:error={add_feedback_error}
    >
      <FormElement
        id="new_feedback_input"
        label="Feedback"
        info_description="Feedback you have on the output."
        inputType="textarea"
        bind:value={new_feedback_text}
      />
    </FormContainer>
  {/if}
</Dialog>

<Dialog bind:this={view_feedback_dialog} title="All Feedback" width="wide">
  {#if feedbacks.length === 0}
    <p class="text-sm text-gray-500">No feedback yet.</p>
  {:else}
    <div class="rounded-lg border overflow-hidden">
      <table class="table table-sm w-full table-fixed">
        <thead>
          <tr>
            <th
              class="w-[15%] hover:bg-base-200 cursor-pointer"
              on:click={() => handle_feedback_sort("created_by")}
            >
              Created By
              <span class="inline-block w-3 text-center">
                {feedback_sort_column === "created_by"
                  ? feedback_sort_direction === "asc"
                    ? "▲"
                    : "▼"
                  : "\u200B"}
              </span>
            </th>
            <th>Feedback</th>
            <th
              class="w-[25%] hover:bg-base-200 cursor-pointer"
              on:click={() => handle_feedback_sort("created_at")}
            >
              Created At
              <span class="inline-block w-3 text-center">
                {feedback_sort_column === "created_at"
                  ? feedback_sort_direction === "asc"
                    ? "▲"
                    : "▼"
                  : "\u200B"}
              </span>
            </th>
          </tr>
        </thead>
        <tbody>
          {#each sorted_feedbacks as fb}
            <tr>
              <td class="whitespace-nowrap align-top"
                >{fb.created_by || "Unknown"}</td
              >
              <td class="whitespace-pre-wrap break-words align-top"
                >{fb.feedback}</td
              >
              <td class="whitespace-nowrap align-top"
                >{format_date(fb.created_at)}</td
              >
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</Dialog>
