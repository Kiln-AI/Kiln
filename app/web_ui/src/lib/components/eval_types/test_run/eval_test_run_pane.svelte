<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import type { TaskRunOutput } from "$lib/types"
  import type { KilnError } from "$lib/utils/error_handlers"
  import type { TestV2EvalResponse } from "$lib/api/v2_eval_api"
  import TestRunInputCard from "./test_run_input_card.svelte"
  import TestRunBrowseDialog from "./test_run_browse_dialog.svelte"
  import ReferenceDataField from "./reference_data_field.svelte"
  import SeeAllDialog from "$lib/ui/see_all_dialog.svelte"
  import Warning from "$lib/ui/warning.svelte"

  export let project_id: string
  export let task_id: string
  export let runs_loading: boolean = false
  export let runs_error: KilnError | null = null
  export let available_runs: TaskRunOutput[] = []
  export let selected_run: TaskRunOutput | null = null
  export let reference_data: string = ""
  export let required_reference_fields: string[] = []
  export let test_loading: boolean = false
  export let test_result: TestV2EvalResponse | null = null
  export let test_error: KilnError | null = null
  export let test_shape_warning: string | null = null
  export let test_score_range_warning: string | null = null
  export let test_has_valid_run: boolean = false
  export let is_llm_judge: boolean = false
  export let can_submit_llm: boolean = false
  export let manual_example_supported: boolean = true

  let browse_dialog: TestRunBrowseDialog
  let see_all_dialog: SeeAllDialog

  $: has_runs = available_runs.length > 0

  const dispatch = createEventDispatcher<{
    select: TaskRunOutput
    run: void
    cancel: void
    updateReferenceData: string
    runAgain: void
  }>()

  function handle_browse_select(e: CustomEvent<TaskRunOutput>) {
    dispatch("select", e.detail)
  }

  function handle_see_all(e: CustomEvent<{ title: string; content: string }>) {
    see_all_dialog.show(e.detail.title, e.detail.content)
  }
</script>

<div class="flex flex-col gap-3" data-testid="test-run-pane">
  <div>
    <div class="text-xl font-bold">Test Judge</div>
    <p class="text-sm text-gray-500 mt-0.5" data-testid="test-run-subtitle">
      Test your judge on real data before saving.
    </p>
  </div>

  {#if runs_loading}
    <div
      class="flex items-center gap-2 text-sm text-gray-500 py-4"
      data-testid="runs-loading"
    >
      <span class="loading loading-spinner loading-xs"></span>
      Loading task runs...
    </div>
  {:else if runs_error}
    <div data-testid="runs-error">
      <Warning
        warning_color="error"
        tight
        warning_message={runs_error.getMessage()}
      />
    </div>
  {:else if !has_runs}
    <!-- State 1: Empty dataset -->
    <div class="flex flex-col gap-3" data-testid="empty-state">
      <div
        class="rounded-lg border border-base-300 bg-base-200/50 p-3 flex flex-col gap-1"
      >
        <span class="text-sm">No sample inputs yet</span>
        <p class="text-xs text-gray-500">
          Run your task to generate inputs/output pairs in the dataset, then
          test against them here.
        </p>
      </div>
      <a href="/run" class="btn btn-primary btn-outline btn-sm w-full">
        Go to Run
      </a>
    </div>
  {:else if test_loading}
    <!-- State 3: Running -->
    <TestRunInputCard
      run={selected_run || available_runs[0]}
      variant="selected"
      disabled={true}
      on:see_all={handle_see_all}
    />
    <div
      class="flex flex-col items-center gap-3 py-8"
      data-testid="running-state"
    >
      <span class="loading loading-spinner loading-md text-primary"></span>
      <div class="text-sm font-medium">Running...</div>
      <p class="text-xs text-gray-500">Executing the scorer on your input</p>
      <button
        type="button"
        class="btn btn-sm btn-outline mt-1"
        on:click={() => dispatch("cancel")}
        data-testid="cancel-run"
      >
        Cancel
      </button>
    </div>
  {:else if test_result}
    <!-- State 4: Results -->
    {#if selected_run}
      <TestRunInputCard
        run={selected_run}
        variant="selected"
        disabled={false}
        on:change={() => browse_dialog?.show()}
        on:see_all={handle_see_all}
      />
    {/if}

    <ReferenceDataField
      {reference_data}
      {required_reference_fields}
      on:change={(e) => dispatch("updateReferenceData", e.detail)}
    />

    <button
      type="button"
      class="btn btn-primary btn-outline btn-sm w-full"
      on:click={() => dispatch("runAgain")}
      data-testid="run-again"
    >
      Run Again
    </button>

    {#if test_result.skipped_reason}
      <div data-testid="skipped-result">
        <Warning
          warning_color="warning"
          tight
          trusted
          warning_message={test_result.skipped_detail ||
            test_result.skipped_reason}
        />
      </div>
    {:else if test_result.scores}
      <div class="flex flex-col gap-2" data-testid="scores-section">
        <div class="flex items-center justify-between">
          <span class="text-sm font-medium">Scores</span>
          <span class="text-xs text-gray-500"
            >Preview only &middot; not saved</span
          >
        </div>
        <div class="flex flex-col gap-1.5">
          {#each Object.entries(test_result.scores) as [name, value]}
            <div
              class="flex items-center justify-between text-sm py-1 px-2 rounded bg-base-200/50"
            >
              <span class="font-mono text-xs font-medium">{name}</span>
              <span class="text-xs">{value}</span>
            </div>
          {/each}
        </div>
      </div>
    {/if}

    {#if test_error}
      <div data-testid="test-error">
        <Warning
          warning_color="error"
          tight
          warning_message={test_error.getMessage()}
        />
      </div>
    {/if}

    {#if test_shape_warning}
      <div data-testid="shape-warning">
        <Warning
          warning_color="warning"
          tight
          trusted
          warning_message={`Score Shape Mismatch\n${test_shape_warning}`}
        />
      </div>
    {/if}

    {#if test_score_range_warning}
      <div data-testid="score-range-warning">
        <Warning
          warning_color="warning"
          tight
          trusted
          warning_message={`Score Out of Range\n${test_score_range_warning}`}
        />
      </div>
    {/if}
  {:else if selected_run}
    <!-- State 2: Ready -->
    <TestRunInputCard
      run={selected_run}
      variant="selected"
      disabled={false}
      on:change={() => browse_dialog?.show()}
      on:see_all={handle_see_all}
    />

    <ReferenceDataField
      {reference_data}
      {required_reference_fields}
      on:change={(e) => dispatch("updateReferenceData", e.detail)}
    />

    <button
      type="button"
      class="btn btn-primary btn-outline btn-sm w-full"
      disabled={is_llm_judge && !can_submit_llm}
      on:click={() => dispatch("run")}
      data-testid="run-test-btn"
    >
      Run Test
    </button>

    {#if test_error}
      <div data-testid="test-error">
        <Warning
          warning_color="error"
          tight
          warning_message={test_error.getMessage()}
        />
      </div>
    {/if}
  {:else}
    <!-- Fallback: has runs but none selected (shouldn't happen with auto-select) -->
    <p class="text-sm text-gray-500">Select a run to get started.</p>
  {/if}
</div>

<TestRunBrowseDialog
  bind:this={browse_dialog}
  {project_id}
  {task_id}
  {available_runs}
  {manual_example_supported}
  on:select={handle_browse_select}
/>

<SeeAllDialog bind:this={see_all_dialog} />
