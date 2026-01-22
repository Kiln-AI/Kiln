<script lang="ts">
  import { onMount, createEventDispatcher } from "svelte"
  import type { TaskRun } from "$lib/types"
  import {
    type FewShotExample,
    type AutoSelectType,
    fetch_few_shot_candidates,
    task_run_to_example,
  } from "./few_shot_example"
  import FormElement from "$lib/utils/form_element.svelte"
  import Output from "$lib/ui/output.svelte"
  import Collapse from "$lib/ui/collapse.svelte"
  import Dialog from "$lib/ui/dialog.svelte"

  export let project_id: string
  export let task_id: string
  export let selected_example: FewShotExample | null = null

  const dispatch = createEventDispatcher<{
    change: { example: FewShotExample | null }
  }>()

  // Data from API
  let available_runs: TaskRun[] = []
  let auto_select_type: AutoSelectType = null
  let error: string | null = null

  // UI states
  let loading = true
  let manual_input: string = ""
  let manual_output: string = ""
  let show_manual_entry: boolean = false
  let is_changing_selection: boolean = false
  let user_made_selection: boolean = false // tracks if user explicitly selected/entered

  // Selection status for badge display (derived from state)
  type SelectionStatus =
    | "auto_selected_highly_rated"
    | "auto_selected_recent"
    | "user_selected"
    | "manual_entry"
    | null

  $: selection_status = ((): SelectionStatus => {
    if (!selected_example) return null
    if (user_made_selection) {
      return show_manual_entry || !available_runs.length
        ? "manual_entry"
        : "user_selected"
    }
    if (auto_select_type === "highly_rated") return "auto_selected_highly_rated"
    if (auto_select_type === "most_recent") return "auto_selected_recent"
    return null
  })()

  // Pagination
  const PAGE_SIZE = 5
  let current_page = 0
  $: total_pages = Math.ceil(available_runs.length / PAGE_SIZE)
  $: page_start = current_page * PAGE_SIZE
  $: page_end = Math.min(page_start + PAGE_SIZE, available_runs.length)
  $: paged_runs = available_runs.slice(page_start, page_end)

  // Preview dialog
  let preview_dialog: Dialog
  let previewing_run: TaskRun | null = null

  function show_preview(run: TaskRun, event: MouseEvent) {
    // Don't show preview if clicking on a button
    if ((event.target as HTMLElement).closest("button")) return
    previewing_run = run
    preview_dialog?.show()
  }

  // Handle run selection
  function select_run(run: TaskRun) {
    selected_example = task_run_to_example(run)
    show_manual_entry = false
    is_changing_selection = false
    user_made_selection = true
    dispatch("change", { example: selected_example })
  }

  // Start changing selection (shows table without clearing current selection)
  function start_changing_selection() {
    is_changing_selection = true
    show_manual_entry = false
    current_page = 0
  }

  // Start manual entry from the selected example view
  function start_manual_entry() {
    is_changing_selection = true
    show_manual_entry = true
  }

  // Cancel changing selection (go back to viewing current selection)
  function cancel_changing_selection() {
    is_changing_selection = false
    show_manual_entry = false
    manual_input = ""
    manual_output = ""
  }

  // Handle manual entry save
  function save_manual_entry() {
    if (manual_input.trim() && manual_output.trim()) {
      selected_example = {
        input: manual_input.trim(),
        output: manual_output.trim(),
      }
      is_changing_selection = false
      show_manual_entry = true // keep this true so we know it was manual entry
      user_made_selection = true
      dispatch("change", { example: selected_example })
    }
  }

  onMount(async () => {
    try {
      const result = await fetch_few_shot_candidates(project_id, task_id)
      auto_select_type = result.auto_select_type
      available_runs = result.available_runs
      selected_example = result.selected_example

      // Auto-show manual entry when no samples exist
      if (available_runs.length === 0) {
        show_manual_entry = true
      }

      if (result.selected_example) {
        dispatch("change", { example: result.selected_example })
      }
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to load dataset samples"
    } finally {
      loading = false
    }
  })

  $: has_valid_manual_entry = manual_input.trim() && manual_output.trim()

  function badge_for_status(status: SelectionStatus): string | null {
    switch (status) {
      case "auto_selected_highly_rated":
        return "Autoselected Highly Rated"
      case "auto_selected_recent":
        return "Autoselected Recent"
    }
    return null
  }

  function badge_data_tip_for_status(status: SelectionStatus): string | null {
    switch (status) {
      case "auto_selected_highly_rated":
        return "A 5-star rated sample was found and selected automatically."
      case "auto_selected_recent":
        return "Your most recent dataset sample was selected automatically."
    }
    return null
  }
</script>

<Collapse
  title="Input & Output Example"
  badge={badge_for_status(selection_status)}
  badge_position="right"
  badge_data_tip={badge_data_tip_for_status(selection_status)}
  description="This example will be used to help our AI better understand your task when generating synthetic data."
  open={!loading && selection_status !== "auto_selected_highly_rated"}
>
  <div class="few-shot-selector">
    {#if loading}
      <div class="flex items-center gap-2 py-4">
        <div class="loading loading-spinner loading-sm"></div>
        <span class="text-sm text-gray-500">Loading...</span>
      </div>
    {:else if error}
      <div class="text-error text-sm py-2">
        {error}
      </div>
    {:else if selected_example && !is_changing_selection}
      <!-- Selected example view - shared across all statuses -->
      <div class="flex flex-col gap-4">
        <div>
          <div class="text-sm font-medium text-left">Input</div>
          <div class="mt-1">
            <Output
              raw_output={selected_example.input}
              show_border={true}
              background_color="white"
            />
          </div>
        </div>
        <div>
          <div class="text-sm font-medium text-left">Output</div>
          <div class="mt-1">
            <Output
              raw_output={selected_example.output}
              show_border={true}
              background_color="white"
            />
          </div>
        </div>
        <div class="flex gap-2">
          {#if available_runs.length > 0}
            <button
              type="button"
              class="btn btn-sm btn-outline"
              on:click={start_changing_selection}
            >
              Select Example
            </button>
          {/if}
          <button
            type="button"
            class="btn btn-sm btn-ghost"
            on:click={start_manual_entry}
          >
            Create Example
          </button>
        </div>
      </div>
    {:else}
      <!-- Selection/Manual entry view -->
      <div class="space-y-3">
        {#if show_manual_entry}
          <!-- Manual entry form -->
          <div class="flex flex-col gap-3">
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
            <div class="flex gap-2">
              {#if is_changing_selection}
                <button
                  type="button"
                  class="btn btn-sm btn-outline"
                  on:click={cancel_changing_selection}
                >
                  Cancel
                </button>
              {/if}
              <button
                type="button"
                class="btn btn-sm {has_valid_manual_entry
                  ? 'btn-primary'
                  : 'btn-outline'}"
                disabled={!has_valid_manual_entry}
                on:click={save_manual_entry}
              >
                Save
              </button>
            </div>
          </div>
        {:else}
          <!-- Selection table -->
          {#if available_runs.length > 0}
            <div class="overflow-x-auto rounded-lg border bg-white">
              <table class="table">
                <thead>
                  <tr>
                    <th>Input Preview</th>
                    <th>Output Preview</th>
                    <th class="w-[100px]"></th>
                  </tr>
                </thead>
                <tbody>
                  {#each paged_runs as run (run.id)}
                    <tr
                      class="hover cursor-pointer"
                      on:click={(e) => show_preview(run, e)}
                    >
                      <td class="text-xs text-gray-600">
                        <div class="truncate w-0 min-w-full">{run.input}</div>
                      </td>
                      <td class="text-xs text-gray-600">
                        <div class="truncate w-0 min-w-full">
                          {run.output?.output || ""}
                        </div>
                      </td>
                      <td class="text-center">
                        <button
                          type="button"
                          class="btn btn-xs btn-outline"
                          on:click={() => select_run(run)}
                        >
                          Select
                        </button>
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
            {#if available_runs.length > PAGE_SIZE}
              <div
                class="flex items-center justify-center gap-2 text-xs text-gray-500"
              >
                <span
                  >{page_start + 1}-{page_end} of {available_runs.length}</span
                >
                <div class="flex gap-1">
                  <button
                    type="button"
                    class="btn btn-xs btn-ghost"
                    disabled={current_page === 0}
                    on:click={() => (current_page = current_page - 1)}
                  >
                    ←
                  </button>
                  <button
                    type="button"
                    class="btn btn-xs btn-ghost"
                    disabled={current_page >= total_pages - 1}
                    on:click={() => (current_page = current_page + 1)}
                  >
                    →
                  </button>
                </div>
              </div>
            {/if}

            {#if is_changing_selection}
              <div class="mt-3">
                <button
                  type="button"
                  class="btn btn-sm btn-outline"
                  on:click={cancel_changing_selection}
                >
                  Cancel
                </button>
              </div>
            {/if}
          {/if}
        {/if}
      </div>
    {/if}
  </div>
</Collapse>

<Dialog bind:this={preview_dialog} title="Example" width="wide">
  {#if previewing_run}
    <div class="flex flex-col gap-4">
      <div>
        <div class="text-sm font-medium text-left mb-1">Input</div>
        <Output raw_output={previewing_run.input} />
      </div>
      <div>
        <div class="text-sm font-medium text-left mb-1">Output</div>
        <Output raw_output={previewing_run.output?.output || ""} />
      </div>
    </div>
  {/if}
</Dialog>
