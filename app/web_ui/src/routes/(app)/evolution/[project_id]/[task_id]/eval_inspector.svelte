<script lang="ts">
  import { createEventDispatcher, onMount } from "svelte"
  import { client } from "$lib/api_client"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import type {
    EvalConfig,
    EvalRunResult,
    EvalRunWithTrace,
    Trace,
  } from "$lib/types"
  import {
    formatDate,
    eval_config_to_detailed_ui_name,
    score_key_label,
  } from "$lib/utils/formatters"
  import {
    getV2TypeFromEvalConfig,
    extractV2Props,
  } from "$lib/utils/eval_types/registry"
  import Collapse from "$lib/ui/collapse.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import Output from "$lib/ui/output.svelte"
  import ChatTrace from "$lib/ui/trace/chat_trace.svelte"
  import EvalTypeIcon from "$lib/components/eval_types/eval_type_icon.svelte"
  import EvalConfigInstruction from "$lib/components/eval_config_instruction.svelte"
  import CodeEditor from "$lib/components/code_editor.svelte"

  export let project_id: string
  export let task_id: string
  export let eval_id: string
  export let eval_config_id: string
  export let run_config_id: string
  export let eval_name: string
  export let run_config_name: string | null = null
  // Named splits this eval has a filter for, from the page's summary. Only
  // these are offered: asking the API for one the eval does not have is a 422,
  // and an option that can only fail is not an option.
  export let declared_splits: string[] = []

  const dispatch = createEventDispatcher<{ close: undefined }>()

  let dialog: Dialog | null = null

  let active_tab: "method" | "runs" = "method"

  let eval_config: EvalConfig | null = null
  let eval_config_error: KilnError | null = null
  let eval_config_loading = true

  let results: EvalRunResult | null = null
  let results_error: KilnError | null = null
  let results_loading = false
  let results_fetched = false

  // Which split's runs the Runs tab lists.
  //
  // ALL by default, and deliberately not the page's split: the page is a
  // comparison, where mixing slices would make the columns incomparable, while
  // this is one config's own record and the question it answers is "what has
  // this thing actually been run on". Starting it filtered would hide runs
  // that exist behind a control the reader has no reason to look for.
  const RUN_SPLITS = ["all", "test", "train", "val"] as const
  type RunSplit = (typeof RUN_SPLITS)[number]
  const RUN_SPLIT_LABELS: Record<RunSplit, string> = {
    all: "All",
    test: "Test",
    train: "Train",
    val: "Val",
  }
  let run_split: RunSplit = "all"
  // "all" is the unfiltered request, so it is always offered; the rest have to
  // be backed by a filter on the eval.
  $: split_options = RUN_SPLITS.filter(
    (split) => split === "all" || declared_splits.includes(split),
  )

  // Inline run drill-down within the Runs tab
  let selected_run: EvalRunWithTrace | null = null

  onMount(() => {
    dialog?.show()
    fetch_eval_config()
  })

  async function fetch_eval_config() {
    eval_config_loading = true
    try {
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/eval_config/{eval_config_id}",
        {
          params: {
            path: { project_id, task_id, eval_id, eval_config_id },
          },
        },
      )
      if (error) {
        throw error
      }
      eval_config = data
    } catch (err) {
      eval_config_error = createKilnError(err)
    } finally {
      eval_config_loading = false
    }
  }

  // The results payload embeds full traces, so it's only fetched when the
  // Runs tab is opened, not when the modal opens.
  async function fetch_results(force: boolean = false) {
    if ((results_fetched && !force) || results_loading) {
      return
    }
    const requested_split = run_split
    results_loading = true
    results_error = null
    try {
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/eval_config/{eval_config_id}/run_config/{run_config_id}/results",
        {
          params: {
            path: {
              project_id,
              task_id,
              eval_id,
              eval_config_id,
              run_config_id,
            },
            // "all" is a value the endpoint takes: every run this config has under
            // this judge, whatever selected the item.
            query: { split: requested_split },
          },
        },
      )
      if (error) {
        throw error
      }
      if (requested_split !== run_split) {
        return
      }
      results = data
      results_fetched = true
    } catch (err) {
      if (requested_split === run_split) {
        results_error = createKilnError(err)
      }
    } finally {
      if (requested_split === run_split) {
        results_loading = false
      }
    }
  }

  function select_split(split: RunSplit) {
    if (split === run_split) {
      return
    }
    run_split = split
    // The open run belongs to the list that is going away
    selected_run = null
    fetch_results(true)
  }

  function open_runs_tab() {
    active_tab = "runs"
    fetch_results()
  }

  function parse_trace(run: EvalRunWithTrace): Trace | null {
    if (!run.task_run_trace) {
      return null
    }
    try {
      return JSON.parse(run.task_run_trace) as Trace
    } catch {
      return null
    }
  }

  function format_reference_data(run: EvalRunWithTrace): string | null {
    const reference_data = run.eval_run.reference_answer
    if (!reference_data) {
      return null
    }
    return JSON.stringify(reference_data, null, 2)
  }

  // Same key precedence as llm_judge_result.svelte and the run_result page:
  // judges store their rationale in intermediate_outputs under "reasoning"
  // (or "chain_of_thought" for older G-Eval configs). Code evals store
  // neither, so the collapse simply doesn't render for them.
  function judge_reasoning(run: EvalRunWithTrace): string | null {
    return (
      run.eval_run.intermediate_outputs?.reasoning ||
      run.eval_run.intermediate_outputs?.chain_of_thought ||
      null
    )
  }

  $: v2_type = eval_config ? getV2TypeFromEvalConfig(eval_config) : null
  $: code_props = eval_config ? extractV2Props(eval_config, "code_eval") : null
</script>

<Dialog
  bind:this={dialog}
  title={eval_name}
  width="full"
  fill_height={true}
  on:close={() => dispatch("close")}
>
  <div
    slot="subtitle"
    class="text-sm text-gray-500 flex items-center gap-1.5 flex-wrap"
  >
    {#if v2_type}
      <span class="w-4 h-4 flex-none">
        <EvalTypeIcon evalType={v2_type} />
      </span>
    {/if}
    {#if eval_config}
      <span>{eval_config.name}</span>
      <span>·</span>
      <span>{eval_config_to_detailed_ui_name(eval_config)}</span>
    {:else if eval_config_loading}
      <span class="loading loading-spinner loading-xs"></span>
    {/if}
    {#if run_config_name}
      <span>·</span>
      <span class="truncate" title={run_config_name}>
        Run config: {run_config_name}
      </span>
    {/if}
  </div>

  <!-- Tabs -->
  <div class="tabs tabs-boxed mb-3 flex-none self-start">
    <button
      class="tab {active_tab === 'method' ? 'tab-active' : ''}"
      on:click={() => (active_tab = "method")}
    >
      Method
    </button>
    <button
      class="tab {active_tab === 'runs' ? 'tab-active' : ''}"
      on:click={open_runs_tab}
    >
      Runs
    </button>
  </div>

  <div class="flex-1 overflow-y-auto min-h-0">
    {#if active_tab === "method"}
      {#if eval_config_loading}
        <div class="flex justify-center py-12">
          <div class="loading loading-spinner loading-md"></div>
        </div>
      {:else if eval_config_error}
        <div class="text-error text-sm py-4">
          {eval_config_error.getMessage() || "Failed to load eval config"}
        </div>
      {:else if eval_config}
        <!-- For code evals the instruction summary IS the code, so the
               CodeMirror view replaces it rather than duplicating it. -->
        {#if code_props?.code}
          <div>
            <div class="text-sm font-medium mb-1">Code</div>
            <CodeEditor
              value={code_props.code}
              readonly={true}
              min_height="300px"
            />
          </div>
        {:else}
          <EvalConfigInstruction {eval_config} />
        {/if}
      {/if}
    {:else if active_tab === "runs"}
      {#if selected_run}
        {@const trace = parse_trace(selected_run)}
        {@const reference_json = format_reference_data(selected_run)}
        {@const reasoning = judge_reasoning(selected_run)}
        <!-- Single run drill-down. Compact sticky header, then the trace as
               the primary content: these tasks are multi-turn, so the trace's
               last assistant message IS the output. -->
        <div
          class="sticky top-0 z-10 bg-base-100 border-b border-gray-200 pb-2 mb-3 flex items-center gap-1.5 flex-wrap"
        >
          <button
            type="button"
            class="btn btn-xs btn-outline flex-none"
            on:click={() => (selected_run = null)}
          >
            Back
          </button>
          {#each Object.entries(selected_run.eval_run.scores) as [key, value] (key)}
            <span class="badge badge-ghost badge-sm">
              {score_key_label(key)}: {value.toFixed(2)}
            </span>
          {/each}
          {#if selected_run.eval_run.skipped_reason}
            <span class="badge badge-warning badge-sm">
              Skipped: {selected_run.eval_run.skipped_reason}
            </span>
          {/if}
        </div>
        <div class="flex flex-col gap-4">
          {#if trace}
            <ChatTrace {trace} {project_id} />
          {:else if selected_run.output}
            <!-- Single-turn task: no trace, so the stored output stands in -->
            <Output raw_output={selected_run.output} max_height={null} />
          {:else}
            <div class="text-sm text-gray-500">No trace stored.</div>
          {/if}
          {#if reasoning}
            <Collapse title="Judge Reasoning" outlined={true}>
              <Output raw_output={reasoning} max_height="300px" />
            </Collapse>
          {/if}
          {#if reference_json}
            <Collapse title="Reference Data" outlined={true}>
              <Output raw_output={reference_json} max_height="300px" />
            </Collapse>
          {/if}
        </div>
      {:else if results_loading}
        <div class="flex justify-center py-12">
          <div class="loading loading-spinner loading-md"></div>
        </div>
      {:else if results_error}
        <div class="text-error text-sm py-4">
          {results_error.getMessage() || "Failed to load eval runs"}
        </div>
      {:else if results}
        <!-- Which slice of the dataset these runs came from. The count is next
             to it because it is the answer to the question the control raises:
             "all" against "train" is how a reader sees that a config was
             iterated on train and measured on test. -->
        {#if split_options.length > 1}
          <div class="flex items-center gap-2 mb-3">
            <div class="join" role="group" aria-label="Dataset split">
              {#each split_options as split_option}
                <button
                  type="button"
                  class="join-item btn btn-xs font-normal {run_split ===
                  split_option
                    ? 'btn-active'
                    : ''}"
                  aria-pressed={run_split === split_option}
                  on:click={() => select_split(split_option)}
                >
                  {RUN_SPLIT_LABELS[split_option]}
                </button>
              {/each}
            </div>
            <span class="text-xs text-gray-500">
              {results.results.length}
              {results.results.length === 1 ? "run" : "runs"}
            </span>
          </div>
        {/if}
        {#if results.results.length === 0}
          <div class="text-sm text-gray-500 py-4">
            {run_split === "all"
              ? "No eval runs recorded for this run config."
              : `No eval runs on the ${RUN_SPLIT_LABELS[
                  run_split
                ].toLowerCase()} split for this run config.`}
          </div>
        {:else}
          <table class="table table-xs w-full">
            <thead>
              <tr>
                <th class="text-gray-500 font-normal w-2/5">Input</th>
                <th class="text-gray-500 font-normal">Scores</th>
                <th class="text-gray-500 font-normal">Created</th>
              </tr>
            </thead>
            <tbody>
              {#each results.results as run (run.eval_run.id)}
                <tr
                  class="hover cursor-pointer"
                  on:click={() => (selected_run = run)}
                >
                  <td>
                    <div class="line-clamp-1 break-all" title={run.input}>
                      {run.input}
                    </div>
                  </td>
                  <td>
                    <div class="flex flex-wrap gap-1">
                      {#each Object.entries(run.eval_run.scores) as [key, value] (key)}
                        <span class="badge badge-ghost badge-xs">
                          {score_key_label(key)}: {value.toFixed(2)}
                        </span>
                      {/each}
                      {#if run.eval_run.skipped_reason}
                        <span class="badge badge-warning badge-xs">
                          Skipped: {run.eval_run.skipped_reason}
                        </span>
                      {/if}
                    </div>
                  </td>
                  <td class="whitespace-nowrap">
                    {run.eval_run.created_at
                      ? formatDate(run.eval_run.created_at)
                      : "—"}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}
      {/if}
    {/if}
  </div>
</Dialog>
