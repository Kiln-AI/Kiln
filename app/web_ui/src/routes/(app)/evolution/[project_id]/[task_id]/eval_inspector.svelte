<script lang="ts">
  import { createEventDispatcher, onMount } from "svelte"
  import { client } from "$lib/api_client"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import type { components } from "$lib/api_schema"
  import type { EvalConfig, Trace } from "$lib/types"
  import {
    formatDate,
    eval_config_to_detailed_ui_name,
  } from "$lib/utils/formatters"
  import {
    getV2TypeFromEvalConfig,
    extractV2Props,
  } from "$lib/utils/eval_types/registry"
  import { score_key_label } from "$lib/utils/evolution/score_lens"
  import Output from "$lib/ui/output.svelte"
  import ChatTrace from "$lib/ui/trace/chat_trace.svelte"
  import CloseIcon from "$lib/ui/icons/close_icon.svelte"
  import EvalTypeIcon from "$lib/components/eval_types/eval_type_icon.svelte"
  import EvalConfigInstruction from "$lib/components/eval_config_instruction.svelte"
  import CodeEditor from "$lib/components/code_editor.svelte"

  type EvalRun = components["schemas"]["EvalRun"]
  type EvalRunResult = components["schemas"]["EvalRunResult"]

  export let project_id: string
  export let task_id: string
  export let eval_id: string
  export let eval_config_id: string
  export let run_config_id: string
  export let eval_name: string
  export let run_config_name: string | null = null

  const dispatch = createEventDispatcher<{ close: undefined }>()

  let dialog_el: HTMLDialogElement | null = null

  let active_tab: "method" | "runs" = "method"

  let eval_config: EvalConfig | null = null
  let eval_config_error: KilnError | null = null
  let eval_config_loading = true

  let results: EvalRunResult | null = null
  let results_error: KilnError | null = null
  let results_loading = false
  let results_fetched = false

  // Inline run drill-down within the Runs tab
  let selected_run: EvalRun | null = null

  onMount(() => {
    if (dialog_el && !dialog_el.open) {
      dialog_el.showModal()
    }
    dialog_el?.focus()
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
  async function fetch_results() {
    if (results_fetched || results_loading) {
      return
    }
    results_loading = true
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
          },
        },
      )
      if (error) {
        throw error
      }
      results = data
      results_fetched = true
    } catch (err) {
      results_error = createKilnError(err)
    } finally {
      results_loading = false
    }
  }

  function open_runs_tab() {
    active_tab = "runs"
    fetch_results()
  }

  function parse_trace(run: EvalRun): Trace | null {
    if (!run.task_run_trace) {
      return null
    }
    try {
      return JSON.parse(run.task_run_trace) as Trace
    } catch {
      return null
    }
  }

  function format_reference_data(run: EvalRun): string | null {
    if (!run.reference_data) {
      return null
    }
    return JSON.stringify(run.reference_data, null, 2)
  }

  $: v2_type = eval_config ? getV2TypeFromEvalConfig(eval_config) : null
  $: code_props = eval_config ? extractV2Props(eval_config, "code_eval") : null
</script>

<dialog
  bind:this={dialog_el}
  class="modal"
  tabindex="-1"
  on:close={() => dispatch("close")}
>
  <div
    class="modal-box w-11/12 max-w-6xl h-[85vh] max-h-[85vh] flex flex-col text-base-content"
  >
    <!-- Header -->
    <div class="flex items-start gap-3 flex-none">
      <div class="min-w-0 flex-1">
        <h3 class="text-lg font-medium truncate" title={eval_name}>
          {eval_name}
        </h3>
        <div class="text-sm text-gray-500 flex items-center gap-1.5 flex-wrap">
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
      </div>
      <button
        type="button"
        class="w-7 h-7 rounded-full flex items-center justify-center p-1.5 text-gray-500 hover:bg-gray-200 hover:text-gray-900 transition-colors flex-none"
        title="Close"
        on:click={() => dialog_el?.close()}
      >
        <CloseIcon />
      </button>
    </div>

    <!-- Tabs -->
    <div class="tabs tabs-boxed my-3 flex-none self-start">
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
            {#each Object.entries(selected_run.scores) as [key, value] (key)}
              <span class="badge badge-ghost badge-sm">
                {score_key_label(key)}: {value.toFixed(2)}
              </span>
            {/each}
            {#if selected_run.skipped_reason}
              <span class="badge badge-warning badge-sm">
                Skipped: {selected_run.skipped_reason}
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
            {#if reference_json}
              <div
                class="collapse collapse-arrow border border-gray-200 rounded-lg"
              >
                <input type="checkbox" />
                <div class="collapse-title text-sm font-medium">
                  Reference Data
                </div>
                <div class="collapse-content">
                  <Output raw_output={reference_json} max_height="300px" />
                </div>
              </div>
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
          {#if results.results.length === 0}
            <div class="text-sm text-gray-500 py-4">
              No eval runs recorded for this run config.
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
                {#each results.results as run (run.id)}
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
                        {#each Object.entries(run.scores) as [key, value] (key)}
                          <span class="badge badge-ghost badge-xs">
                            {score_key_label(key)}: {value.toFixed(2)}
                          </span>
                        {/each}
                        {#if run.skipped_reason}
                          <span class="badge badge-warning badge-xs">
                            Skipped: {run.skipped_reason}
                          </span>
                        {/if}
                      </div>
                    </td>
                    <td class="whitespace-nowrap">
                      {run.created_at ? formatDate(run.created_at) : "—"}
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {/if}
        {/if}
      {/if}
    </div>
  </div>
  <form method="dialog" class="modal-backdrop">
    <button>close</button>
  </form>
</dialog>
