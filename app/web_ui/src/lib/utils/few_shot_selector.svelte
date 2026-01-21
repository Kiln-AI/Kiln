<script lang="ts">
  import { onMount, createEventDispatcher } from "svelte"
  import type { TaskRun } from "$lib/types"
  import {
    type FewShotExample,
    type FewShotStatus,
    fetch_few_shot_candidates,
    task_run_to_example,
  } from "./few_shot_example"
  import FormElement from "$lib/utils/form_element.svelte"

  export let project_id: string
  export let task_id: string
  export let selected_example: FewShotExample | null = null
  export let optional: boolean = false

  const dispatch = createEventDispatcher<{
    change: { example: FewShotExample | null }
  }>()

  let status: FewShotStatus = "loading"
  let available_runs: TaskRun[] = []
  let error: string | null = null

  // For user selection mode
  let selected_run_id: string | null = null

  // For manual entry mode
  let manual_input: string = ""
  let manual_output: string = ""
  let show_manual_entry: boolean = false

  // Truncate text for preview
  function truncate(
    text: string | null | undefined,
    max_length: number = 80,
  ): string {
    if (!text) return ""
    if (text.length <= max_length) return text
    return text.slice(0, max_length) + "…"
  }

  // Get rating display for a run
  function get_rating_display(run: TaskRun): string {
    if (run.repaired_output) return "★★★★★ (Repaired)"
    const rating = run.output?.rating
    if (!rating || rating.value === null || rating.value === undefined)
      return "Unrated"
    if (rating.type === "five_star") {
      return "★".repeat(Math.round(rating.value))
    }
    return `${rating.value}`
  }

  // Handle run selection
  function select_run(run: TaskRun) {
    selected_run_id = run.id ?? null
    selected_example = task_run_to_example(run)
    show_manual_entry = false
    dispatch("change", { example: selected_example })
  }

  // Handle manual entry save
  function save_manual_entry() {
    if (manual_input.trim() && manual_output.trim()) {
      selected_example = {
        input: manual_input.trim(),
        output: manual_output.trim(),
      }
      selected_run_id = null
      dispatch("change", { example: selected_example })
    }
  }

  // Clear selection
  function clear_selection() {
    selected_example = null
    selected_run_id = null
    manual_input = ""
    manual_output = ""
    show_manual_entry = false
    dispatch("change", { example: null })
  }

  // Toggle manual entry mode
  function toggle_manual_entry() {
    show_manual_entry = !show_manual_entry
    if (!show_manual_entry) {
      manual_input = ""
      manual_output = ""
    }
  }

  onMount(async () => {
    try {
      const result = await fetch_few_shot_candidates(project_id, task_id)
      status = result.status
      available_runs = result.available_runs
      selected_example = result.selected_example

      if (result.selected_example) {
        dispatch("change", { example: result.selected_example })
      }
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to load dataset samples"
    }
  })

  $: has_valid_manual_entry = manual_input.trim() && manual_output.trim()
</script>

<div class="few-shot-selector">
  {#if status === "loading"}
    <div class="flex items-center gap-2 py-4">
      <div class="loading loading-spinner loading-sm"></div>
      <span class="text-sm text-gray-500">Loading dataset samples...</span>
    </div>
  {:else if error}
    <div class="text-error text-sm py-2">
      {error}
    </div>
  {:else if status === "auto_selected"}
    <div class="border rounded-lg p-4 bg-base-200">
      <div class="flex items-center gap-2 mb-2">
        <span class="badge badge-success badge-sm">Auto-selected</span>
        <span class="text-sm text-gray-500"
          >A 5-star rated example was found</span
        >
      </div>
      {#if selected_example}
        <div class="space-y-2 text-sm">
          <div>
            <span class="font-medium">Input:</span>
            <span class="text-gray-600"
              >{truncate(selected_example.input, 150)}</span
            >
          </div>
          <div>
            <span class="font-medium">Output:</span>
            <span class="text-gray-600"
              >{truncate(selected_example.output, 150)}</span
            >
          </div>
        </div>
      {/if}
      <div class="flex gap-2 mt-3">
        <button
          type="button"
          class="btn btn-xs btn-outline"
          on:click={() => (status = "user_select")}
        >
          Choose different example
        </button>
        {#if optional}
          <button
            type="button"
            class="btn btn-xs btn-ghost text-gray-500"
            on:click={clear_selection}
          >
            Don't use an example
          </button>
        {/if}
      </div>
    </div>
  {:else if status === "user_select"}
    <div class="space-y-3">
      {#if selected_example && selected_run_id}
        <div class="border rounded-lg p-4 bg-base-200">
          <div class="flex items-center gap-2 mb-2">
            <span class="badge badge-primary badge-sm">Selected</span>
          </div>
          <div class="space-y-2 text-sm">
            <div>
              <span class="font-medium">Input:</span>
              <span class="text-gray-600"
                >{truncate(selected_example.input, 150)}</span
              >
            </div>
            <div>
              <span class="font-medium">Output:</span>
              <span class="text-gray-600"
                >{truncate(selected_example.output, 150)}</span
              >
            </div>
          </div>
          <button
            type="button"
            class="btn btn-xs btn-outline mt-3"
            on:click={clear_selection}
          >
            Change selection
          </button>
        </div>
      {:else if selected_example && show_manual_entry}
        <div class="border rounded-lg p-4 bg-base-200">
          <div class="flex items-center gap-2 mb-2">
            <span class="badge badge-primary badge-sm">Manual Entry</span>
          </div>
          <div class="space-y-2 text-sm">
            <div>
              <span class="font-medium">Input:</span>
              <span class="text-gray-600"
                >{truncate(selected_example.input, 150)}</span
              >
            </div>
            <div>
              <span class="font-medium">Output:</span>
              <span class="text-gray-600"
                >{truncate(selected_example.output, 150)}</span
              >
            </div>
          </div>
          <button
            type="button"
            class="btn btn-xs btn-outline mt-3"
            on:click={clear_selection}
          >
            Change
          </button>
        </div>
      {:else}
        <div class="text-sm text-gray-500 mb-2">
          Select an example from your dataset to help the AI understand your
          task better.
        </div>

        {#if available_runs.length > 0}
          <div class="border rounded-lg overflow-hidden">
            <table class="table table-sm">
              <thead>
                <tr class="bg-base-200">
                  <th class="w-16">Rating</th>
                  <th>Input Preview</th>
                  <th>Output Preview</th>
                  <th class="w-24">Action</th>
                </tr>
              </thead>
              <tbody>
                {#each available_runs.slice(0, 10) as run}
                  <tr class="hover">
                    <td class="text-xs">{get_rating_display(run)}</td>
                    <td class="text-xs text-gray-600 max-w-48 truncate">
                      {truncate(run.input, 60)}
                    </td>
                    <td class="text-xs text-gray-600 max-w-48 truncate">
                      {truncate(run.output?.output, 60)}
                    </td>
                    <td>
                      <button
                        type="button"
                        class="btn btn-xs btn-primary btn-outline"
                        on:click={() => select_run(run)}
                      >
                        Select
                      </button>
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
            {#if available_runs.length > 10}
              <div class="text-xs text-gray-500 p-2 bg-base-200">
                Showing top 10 of {available_runs.length} samples
              </div>
            {/if}
          </div>
        {/if}

        <div class="mt-3">
          <button
            type="button"
            class="btn btn-sm btn-ghost text-gray-500"
            on:click={toggle_manual_entry}
          >
            {show_manual_entry ? "Cancel manual entry" : "Or enter manually"}
          </button>
        </div>

        {#if show_manual_entry}
          <div class="border rounded-lg p-4 mt-2 space-y-3">
            <FormElement
              id="manual_input"
              label="Example Input"
              inputType="textarea"
              height="base"
              bind:value={manual_input}
              placeholder="Enter an example input for your task"
            />
            <FormElement
              id="manual_output"
              label="Example Output"
              inputType="textarea"
              height="base"
              bind:value={manual_output}
              placeholder="Enter the expected output for this input"
            />
            <button
              type="button"
              class="btn btn-sm btn-primary"
              disabled={!has_valid_manual_entry}
              on:click={save_manual_entry}
            >
              Use this example
            </button>
          </div>
        {/if}

        {#if optional && !show_manual_entry}
          <div class="mt-2">
            <button
              type="button"
              class="btn btn-xs btn-ghost text-gray-500"
              on:click={() => dispatch("change", { example: null })}
            >
              Continue without an example
            </button>
          </div>
        {/if}
      {/if}
    </div>
  {:else if status === "manual_entry"}
    <div class="space-y-3">
      {#if selected_example}
        <div class="border rounded-lg p-4 bg-base-200">
          <div class="flex items-center gap-2 mb-2">
            <span class="badge badge-primary badge-sm">Manual Entry</span>
          </div>
          <div class="space-y-2 text-sm">
            <div>
              <span class="font-medium">Input:</span>
              <span class="text-gray-600"
                >{truncate(selected_example.input, 150)}</span
              >
            </div>
            <div>
              <span class="font-medium">Output:</span>
              <span class="text-gray-600"
                >{truncate(selected_example.output, 150)}</span
              >
            </div>
          </div>
          <button
            type="button"
            class="btn btn-xs btn-outline mt-3"
            on:click={clear_selection}
          >
            Edit
          </button>
        </div>
      {:else}
        <div class="text-sm text-gray-500 mb-2">
          No samples in your dataset yet. Enter an example input/output pair to
          help the AI understand your task.
        </div>
        <div class="border rounded-lg p-4 space-y-3">
          <FormElement
            id="manual_input"
            label="Example Input"
            inputType="textarea"
            height="base"
            bind:value={manual_input}
            {optional}
            placeholder="Enter an example input for your task"
          />
          <FormElement
            id="manual_output"
            label="Example Output"
            inputType="textarea"
            height="base"
            bind:value={manual_output}
            {optional}
            placeholder="Enter the expected output for this input"
          />
          <div class="flex gap-2">
            <button
              type="button"
              class="btn btn-sm btn-primary"
              disabled={!has_valid_manual_entry}
              on:click={save_manual_entry}
            >
              Use this example
            </button>
            {#if optional}
              <button
                type="button"
                class="btn btn-sm btn-ghost text-gray-500"
                on:click={() => dispatch("change", { example: null })}
              >
                Skip
              </button>
            {/if}
          </div>
        </div>
      {/if}
    </div>
  {/if}
</div>
