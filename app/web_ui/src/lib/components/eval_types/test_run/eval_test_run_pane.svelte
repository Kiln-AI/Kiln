<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import type { TaskRunOutput } from "$lib/types"
  import type { KilnError } from "$lib/utils/error_handlers"
  import type { TestV2EvalResponse } from "$lib/api/v2_eval_api"
  import TestRunInputCard from "./test_run_input_card.svelte"
  import TestRunBrowseDialog from "./test_run_browse_dialog.svelte"
  import ReferenceDataField from "./reference_data_field.svelte"

  export let runs_loading: boolean = false
  export let runs_error: KilnError | null = null
  export let available_runs: TaskRunOutput[] = []
  export let selected_run: TaskRunOutput | null = null
  export let reference_data: string = ""
  export let test_loading: boolean = false
  export let test_result: TestV2EvalResponse | null = null
  export let test_error: KilnError | null = null
  export let test_shape_warning: string | null = null
  export let test_score_range_warning: string | null = null
  export let test_has_valid_run: boolean = false
  export let is_llm_judge: boolean = false
  export let can_submit_llm: boolean = false

  let browse_dialog: TestRunBrowseDialog

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
</script>

<div class="flex flex-col gap-3" data-testid="test-run-pane">
  <div>
    <div class="text-xl font-bold">Test Run</div>
    <p class="text-sm text-gray-500 mt-0.5" data-testid="test-run-subtitle">
      Test your judge on real data before saving.
    </p>
  </div>

  {#if runs_loading}
    <div
      class="flex items-center gap-2 text-sm text-base-content/40 py-4"
      data-testid="runs-loading"
    >
      <span class="loading loading-spinner loading-xs"></span>
      Loading task runs...
    </div>
  {:else if runs_error}
    <div class="alert alert-error text-sm" data-testid="runs-error">
      <i class="bi bi-exclamation-triangle-fill"></i>
      <span>{runs_error.getMessage()}</span>
    </div>
  {:else if !has_runs}
    <!-- State 1: Empty dataset -->
    <div
      class="flex flex-col items-center gap-3 py-8 text-center"
      data-testid="empty-state"
    >
      <div
        class="flex items-center justify-center w-12 h-12 rounded-full bg-base-200"
      >
        <i class="bi bi-inbox text-xl text-base-content/40"></i>
      </div>
      <div class="text-sm font-medium text-base-content/70">
        No sample inputs yet
      </div>
      <p class="text-xs text-base-content/40 max-w-[240px]">
        Run your task to generate inputs in the dataset, then test against them
        here.
      </p>
      <a href="/run" class="btn btn-sm btn-outline mt-1"> Go to Run </a>
    </div>
  {:else if test_loading}
    <!-- State 3: Running -->
    <TestRunInputCard
      run={selected_run || available_runs[0]}
      variant="selected"
      disabled={true}
    />
    <div
      class="flex flex-col items-center gap-3 py-8"
      data-testid="running-state"
    >
      <span class="loading loading-spinner loading-md text-primary"></span>
      <div class="text-sm font-medium">Running...</div>
      <p class="text-xs text-base-content/40">
        Executing the scorer on your input
      </p>
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
      />
    {/if}

    {#if test_result.skipped_reason}
      <div class="alert alert-warning text-sm" data-testid="skipped-result">
        <i class="bi bi-skip-forward-fill"></i>
        <div>
          <div class="font-medium">Skipped</div>
          <div>
            {test_result.skipped_detail || test_result.skipped_reason}
          </div>
        </div>
      </div>
    {:else if test_result.scores}
      <div class="flex flex-col gap-2" data-testid="scores-section">
        <div class="flex items-center justify-between">
          <span class="text-sm font-medium">Scores</span>
          <span class="text-xs text-base-content/40 italic"
            >preview &middot; not saved</span
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
      <div class="alert alert-error text-sm" data-testid="test-error">
        <i class="bi bi-exclamation-triangle-fill"></i>
        <span>{test_error.getMessage()}</span>
      </div>
    {/if}

    {#if test_shape_warning}
      <div class="alert alert-warning text-sm" data-testid="shape-warning">
        <i class="bi bi-exclamation-triangle-fill"></i>
        <div>
          <div class="font-medium">Score Shape Mismatch</div>
          <div class="text-xs">{test_shape_warning}</div>
        </div>
      </div>
    {/if}

    {#if test_score_range_warning}
      <div
        class="alert alert-warning text-sm"
        data-testid="score-range-warning"
      >
        <i class="bi bi-exclamation-triangle-fill"></i>
        <div>
          <div class="font-medium">Score Out of Range</div>
          <div class="text-xs">{test_score_range_warning}</div>
        </div>
      </div>
    {/if}

    <button
      type="button"
      class="btn btn-sm btn-primary btn-outline"
      on:click={() => dispatch("runAgain")}
      data-testid="run-again"
    >
      Run again
    </button>
  {:else if selected_run}
    <!-- State 2: Ready -->
    <TestRunInputCard
      run={selected_run}
      variant="selected"
      disabled={false}
      on:change={() => browse_dialog?.show()}
    />

    <ReferenceDataField
      {reference_data}
      on:change={(e) => dispatch("updateReferenceData", e.detail)}
    />

    <button
      type="button"
      class="btn btn-primary btn-outline btn-sm w-full"
      disabled={is_llm_judge && !can_submit_llm}
      on:click={() => dispatch("run")}
      data-testid="run-test-btn"
    >
      <i class="bi bi-play-fill"></i>
      Run
    </button>

    {#if test_error}
      <div class="alert alert-error text-sm" data-testid="test-error">
        <i class="bi bi-exclamation-triangle-fill"></i>
        <span>{test_error.getMessage()}</span>
      </div>
    {/if}
  {:else}
    <!-- Fallback: has runs but none selected (shouldn't happen with auto-select) -->
    <p class="text-sm text-base-content/40">Select a run to get started.</p>
  {/if}
</div>

<TestRunBrowseDialog
  bind:this={browse_dialog}
  {available_runs}
  on:select={handle_browse_select}
/>
