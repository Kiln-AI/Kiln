<script lang="ts">
  import { onDestroy, onMount, tick } from "svelte"
  import { client } from "$lib/api_client"
  import type { components } from "$lib/api_schema"
  import { isKilnAgentRunConfig } from "$lib/types"
  import type { KilnAgentRunConfigProperties } from "$lib/types"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import RunConfigComponent from "$lib/ui/run_config_component/run_config_component.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
  import StarsIcon from "$lib/ui/icons/stars_icon.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import TableActionMenu from "$lib/ui/table_action_menu.svelte"
  import FloatingMenu from "$lib/ui/floating_menu.svelte"
  import KilnProPlanSummary from "./kiln_pro_plan_summary.svelte"
  import KilnProPlansTable from "./kiln_pro_plans_table.svelte"
  import { SynthDataGuidanceDataModel } from "./synth_data_guidance_datamodel"
  import {
    runInputsBatch,
    runOutputsBatch,
    type BatchRun,
    type InputsBatchStatus,
    type OutputsBatchStatus,
  } from "$lib/stores/kiln_pro_batch_store"
  // TODO: remove the dev mocks — this import and the two KILN_PRO_DEV_MOCKS
  // branches in run_inputs and start_outputs.
  import {
    KILN_PRO_DEV_MOCKS,
    mock_inputs_batch,
    mock_outputs_batch,
  } from "./kiln_pro_dev_mocks"

  export let plan: { prompts: string[]; summary: string }
  export let project_id: string
  export let task_id: string
  export let guidance_data: SynthDataGuidanceDataModel
  // The user already chose the model/data-guide in the modal on the plan page;
  // generation starts on mount with these.
  export let run_config_properties: KilnAgentRunConfigProperties
  export let data_guide: string | null
  export let summary_out_of_sync = false
  // Returns to the plan — the only way out once every sample is removed.
  export let on_back: () => void

  type TaskRun = components["schemas"]["TaskRun-Output"]
  type Row = {
    prompt: string
    input: string | Record<string, unknown> | null
    output: string | null
    task_run: TaskRun | null
    input_error: string | null
    output_error: string | null
    // Set once persisted; also the dataset id the "Saved" status links to.
    saved_id: string | null
  }

  let rows: Row[] = plan.prompts.map((p) => ({
    prompt: p,
    input: null,
    output: null,
    task_run: null,
    input_error: null,
    output_error: null,
    saved_id: null,
  }))

  $: task = guidance_data.task

  const plan_dialog_id = "kiln_pro_plan_dialog"

  let inputs_status: "running" | "complete" | "error" | null = null
  let outputs_started = false
  let outputs_status: "running" | "complete" | "error" | null = null
  let batch_error: KilnError | null = null

  // Rows the current output batch is still working on. Without this, a row
  // whose output was removed after a batch finished would spin forever.
  let outputs_pending = new Set<number>()

  let inputs_run: BatchRun<InputsBatchStatus> | null = null
  let outputs_run: BatchRun<OutputsBatchStatus> | null = null
  let inputs_unsub: (() => void)[] = []
  let outputs_unsub: (() => void)[] = []

  let saving = false
  let save_progress = 0
  let save_target = 0
  let save_errors: KilnError[] = []
  let total_saved = 0
  let save_completed = false
  let show_save_errors = false

  $: total = rows.length
  $: generated_inputs = rows.filter((r) => r.input !== null).length
  $: generated_outputs = rows.filter((r) => r.output !== null).length
  $: input_errors = rows.filter((r) => r.input_error !== null).length
  $: inputs_done = inputs_status !== null && inputs_status !== "running"
  $: outputs_done = outputs_status !== null && outputs_status !== "running"
  $: outputs_savable = rows.filter(
    (r) => r.task_run !== null && !r.saved_id,
  ).length
  // Rows that have an input but no output — the targets of Generate Outputs,
  // whether they've never been run, failed, or had their output removed.
  $: outputs_missing = rows.filter(
    (r) => r.input !== null && r.task_run === null,
  ).length
  $: generating = !inputs_done || (outputs_started && !outputs_done)
  // A full reset would orphan anything already written to the dataset.
  $: any_saved = rows.some((r) => r.saved_id)

  // The input-plan panel mirrors the surviving rows, so trimming samples
  // trims the plan too. Statuses describe the input plan, not the sample.
  $: input_plans = rows.map((r) => r.prompt)
  $: plan_statuses = rows.map((r) => {
    if (r.input_error) return "Failed"
    if (r.input !== null) return "Input Generated"
    return "Generating…"
  })
  // Before outputs run, warn about failed input plans — they're hidden from the
  // samples table, so nothing else surfaces them. Once the user has clicked
  // Generate Outputs they've accepted those failures, and the useful warning
  // becomes the samples still missing an output.
  type WarningState = { message: string; color: "warning" | "error" }
  function build_warning(
    started_outputs: boolean,
    failed_inputs: number,
    ok_inputs: number,
    missing_outputs: number,
    savable: number,
  ): WarningState | null {
    if (!started_outputs) {
      if (failed_inputs === 0) return null
      return {
        message: `${failed_inputs} input ${failed_inputs === 1 ? "plan" : "plans"} failed to generate. Use Generate Inputs → Retry Failed.`,
        color: ok_inputs > 0 ? "warning" : "error",
      }
    }
    if (missing_outputs === 0) return null
    return {
      message: `${missing_outputs} ${missing_outputs === 1 ? "item is" : "items are"} missing outputs. Use Generate Outputs to run them.`,
      color: savable > 0 ? "warning" : "error",
    }
  }
  $: active_warning = build_warning(
    outputs_started,
    input_errors,
    generated_inputs,
    outputs_missing,
    outputs_savable,
  )
  // Only rendered once generation is done — see the provenance line below.
  $: plan_summary_line = `${generated_inputs} of ${total} inputs generated${
    input_errors > 0 ? ` — ${input_errors} failed` : ""
  }`

  const outputs_dialog_id = "kiln_pro_outputs_dialog"
  let outputs_run_config: RunConfigComponent | null = null
  let outputs_submitting = false

  // Re-running inputs re-asks for the model rather than silently reusing the
  // one picked on the plan page. `active_rcp` is whatever was chosen last.
  const inputs_dialog_id = "kiln_pro_regen_inputs_dialog"
  const selected_template = guidance_data.selected_template
  let inputs_run_config: RunConfigComponent | null = null
  let inputs_submitting = false
  let inputs_action: "retry" | "regenerate" = "regenerate"
  let active_rcp: KilnAgentRunConfigProperties = run_config_properties

  $: inputs_pending =
    inputs_action === "retry" ? input_errors : generated_inputs + input_errors
  $: inputs_already_generated = inputs_action === "retry" ? generated_inputs : 0

  function open_inputs_dialog(action: "retry" | "regenerate") {
    inputs_action = action
    batch_error = null
    open_dialog(inputs_dialog_id)
  }

  function submit_inputs_config() {
    inputs_submitting = false
    const rcp =
      inputs_run_config?.run_options_as_run_config_properties() ?? null
    if (!rcp || !isKilnAgentRunConfig(rcp)) {
      batch_error = new KilnError(
        "Synthetic data generation requires a model with a kiln_agent run config.",
        null,
      )
      return
    }
    active_rcp = rcp
    close_dialog(inputs_dialog_id)
    if (inputs_action === "retry") {
      retry_failed()
    } else {
      regenerate_inputs()
    }
  }

  // Per-row popup showing the input plan that produced an input.
  const prompt_dialog_id = "kiln_pro_prompt_dialog"
  let active_prompt = ""
  function show_prompt(p: string) {
    active_prompt = p
    open_dialog(prompt_dialog_id)
  }

  let expanded: boolean[] = new Array(rows.length).fill(false)

  function toggle_expand(index: number) {
    expanded[index] = !expanded[index]
  }

  function format_expanded(data: string): string {
    // If JSON, pretty format it
    try {
      const json = JSON.parse(data)
      return JSON.stringify(json, null, 2)
    } catch (_) {
      // Not JSON
    }

    return data
  }

  function input_text(input: string | Record<string, unknown>): string {
    return typeof input === "string" ? input : JSON.stringify(input)
  }

  function delete_row(index: number) {
    rows = rows.filter((_, i) => i !== index)
    expanded = expanded.filter((_, i) => i !== index)
  }

  // Drops the output but keeps the input, so Generate Outputs can run it again.
  function remove_output(index: number) {
    rows[index].output = null
    rows[index].task_run = null
    rows[index].output_error = null
    rows = rows
  }

  onMount(() => {
    start_inputs()
  })

  onDestroy(() => {
    inputs_run?.cancel()
    outputs_run?.cancel()
    inputs_unsub.forEach((u) => u())
    outputs_unsub.forEach((u) => u())
  })

  async function open_dialog(id: string) {
    await tick()
    // @ts-expect-error showModal is not typed on HTMLElement
    document.getElementById(id)?.showModal()
  }

  function close_dialog(id: string) {
    // @ts-expect-error close is not typed on HTMLElement
    document.getElementById(id)?.close()
  }

  function output_preview(run: TaskRun): string {
    const out = run.output?.output
    return typeof out === "string" ? out : JSON.stringify(out)
  }

  // Generates inputs for a subset of rows. The batch indexes its results by
  // position within the prompts it was given, so `row_indices` maps them back.
  function run_inputs(row_indices: number[]) {
    if (row_indices.length === 0) return
    const gen_type = guidance_data.gen_type
    const prompts = row_indices.map((i) => rows[i].prompt)

    inputs_run?.cancel()
    inputs_unsub.forEach((u) => u())
    inputs_unsub = []
    batch_error = null

    if (KILN_PRO_DEV_MOCKS) {
      inputs_status = "running"
      inputs_run = mock_inputs_batch(
        prompts,
        active_rcp.model_name,
        active_rcp.model_provider_name,
      )
    } else if (!gen_type) {
      batch_error = new KilnError("No generation type selected.", null)
      inputs_status = "error"
      return
    } else {
      inputs_status = "running"
      inputs_run = runInputsBatch(project_id, task_id, {
        prompts,
        gen_type,
        data_guide: data_guide || null,
        run_config_properties: active_rcp,
      })
    }
    inputs_unsub.push(
      inputs_run.status.subscribe((s) => {
        if (!s) return
        for (const r of s.results) {
          const row = rows[row_indices[r.index]]
          if (!row) continue
          if (r.input !== null && r.input !== undefined) {
            row.input = r.input
          }
          if (r.error) row.input_error = r.error
        }
        rows = rows
        inputs_status = s.status
      }),
    )
    inputs_unsub.push(
      inputs_run.error.subscribe((e) => {
        if (e) {
          batch_error = e
          inputs_status = "error"
        }
      }),
    )
  }

  function start_inputs() {
    run_inputs(rows.map((_, i) => i))
  }

  // Re-runs only the descriptions whose input generation failed. Non-destructive:
  // successful rows are untouched.
  function retry_failed() {
    const failed = rows
      .map((r, i) => (r.input_error ? i : -1))
      .filter((i) => i >= 0)
    for (const i of failed) {
      rows[i].input_error = null
      rows[i].input = null
    }
    rows = rows
    run_inputs(failed)
  }

  // Discards every input and generates again from the same descriptions. Only
  // offered before outputs exist, so there's no generated work to destroy.
  function regenerate_inputs() {
    rows = rows.map((r) => ({
      ...r,
      input: null,
      output: null,
      task_run: null,
      input_error: null,
      output_error: null,
    }))
    expanded = new Array(rows.length).fill(false)
    outputs_pending = new Set()
    run_inputs(rows.map((_, i) => i))
  }

  function start_outputs() {
    outputs_submitting = false
    const rcp =
      outputs_run_config?.run_options_as_run_config_properties() ?? null
    if (!rcp) {
      batch_error = new KilnError("No run config selected.", null)
      return
    }
    close_dialog(outputs_dialog_id)

    // Only rows still missing an output: never run, failed, or output removed.
    const items = rows
      .map((r, i) => ({ index: i, input: r.input, task_run: r.task_run }))
      .filter(
        (
          it,
        ): it is {
          index: number
          input: string | Record<string, unknown>
          task_run: null
        } => it.input !== null && it.task_run === null,
      )
      .map(({ index, input }) => ({ index, input }))
    if (items.length === 0) return

    outputs_run?.cancel()
    outputs_unsub.forEach((u) => u())
    outputs_unsub = []
    batch_error = null
    outputs_started = true
    outputs_status = "running"
    for (const it of items) {
      rows[it.index].output_error = null
    }
    outputs_pending = new Set(items.map((it) => it.index))
    rows = rows

    outputs_run = KILN_PRO_DEV_MOCKS
      ? mock_outputs_batch(items)
      : runOutputsBatch(project_id, task_id, {
          items,
          input_model_name: active_rcp.model_name,
          input_provider: active_rcp.model_provider_name,
          run_config_properties: rcp,
        })
    outputs_unsub.push(
      outputs_run.status.subscribe((s) => {
        if (!s) return
        for (const r of s.results) {
          if (r.task_run) {
            rows[r.index].task_run = r.task_run
            rows[r.index].output = output_preview(r.task_run)
          }
          if (r.error) rows[r.index].output_error = r.error
          if (r.task_run || r.error) outputs_pending.delete(r.index)
        }
        outputs_pending = outputs_pending
        rows = rows
        outputs_status = s.status
      }),
    )
    outputs_unsub.push(
      outputs_run.error.subscribe((e) => {
        if (e) {
          batch_error = e
          outputs_status = "error"
        }
      }),
    )
  }

  // Saving converts each generated run to a persisted TaskRun and can fail, so
  // mirror the legacy flow: show progress, collect per-item errors, and leave
  // failed rows unsaved so a re-click retries just those.
  async function save_all() {
    const to_save = rows.filter((r) => r.task_run && !r.saved_id)
    if (to_save.length === 0) return
    saving = true
    save_completed = false
    save_errors = []
    save_progress = 0
    save_target = to_save.length
    for (const row of to_save) {
      try {
        const { data, error } = await client.POST(
          "/api/projects/{project_id}/tasks/{task_id}/save_sample",
          {
            params: { path: { project_id, task_id } },
            // The batch status returns the Output variant; save_sample accepts
            // the Input variant. They round-trip the same object on the server.
            body: row.task_run as unknown as components["schemas"]["TaskRun-Input"],
          },
        )
        if (error) throw error
        if (!data?.id) throw new KilnError("Save failed: no id returned.", null)
        row.saved_id = data.id
        total_saved++
      } catch (e) {
        save_errors = [...save_errors, createKilnError(e)]
      }
      save_progress++
      rows = rows
    }
    saving = false
    save_completed = true
  }
</script>

<div class="flex flex-col gap-4 mt-4">
  <div class="flex flex-row items-center justify-between gap-4">
    <div class="min-w-0">
      {#if !generating && active_warning}
        <Warning
          warning_message={active_warning.message}
          warning_color={active_warning.color}
          warning_icon="exclaim"
          tight
        />
      {/if}
    </div>
    <!-- With no rows left, the empty state owns the only action: Back to Plan. -->
    {#if total > 0}
      <div class="flex flex-row gap-2 shrink-0">
        {#if inputs_done && !generating && !saving}
          <FloatingMenu
            width="w-72"
            items={[
              {
                label: `Retry Failed (${input_errors})`,
                description: "Re-run just the input plans that failed.",
                onclick: () => open_inputs_dialog("retry"),
                hidden: input_errors === 0,
              },
              {
                label: "Regenerate All Inputs",
                description: `Discard all ${total} and generate fresh from the plan.`,
                onclick: () => open_inputs_dialog("regenerate"),
                // A reset can't undo rows already written to the dataset.
                hidden: any_saved,
              },
            ]}
          >
            <button slot="trigger" type="button" class="btn btn-sm">
              Generate Inputs
              <svg
                class="w-4 h-4"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </button>
          </FloatingMenu>
        {/if}
        {#if inputs_done && !generating && outputs_missing > 0}
          <button
            class="btn btn-sm {outputs_savable > 0 ? '' : 'btn-primary'}"
            disabled={saving}
            on:click={() => open_dialog(outputs_dialog_id)}
          >
            Generate Outputs ({outputs_missing})
          </button>
        {/if}
        {#if !generating && outputs_savable > 0}
          <button
            class="btn btn-sm btn-primary"
            disabled={saving}
            on:click={save_all}
          >
            {saving ? "Saving…" : `Save All (${outputs_savable})`}
          </button>
        {/if}
      </div>
    {/if}
  </div>

  {#if batch_error}
    <div class="text-error text-sm">{batch_error.getMessage()}</div>
  {/if}

  {#if saving}
    <div>
      <div class="flex flex-row justify-between text-xs font-light mb-1">
        <span class="font-medium">Saving</span>
        <span class="text-gray-500">{save_progress} of {save_target}</span>
      </div>
      <progress
        class="progress progress-success w-full"
        value={save_progress}
        max={save_target}
      ></progress>
    </div>
  {/if}

  {#if save_completed && save_errors.length > 0}
    <div class="text-error text-sm">
      {save_errors.length}
      {save_errors.length === 1 ? "item" : "items"} failed to save. Click "Save All"
      to retry.
      <button
        class="link"
        on:click={() => (show_save_errors = !show_save_errors)}
      >
        {show_save_errors ? "Hide errors" : "Show errors"}
      </button>
      {#if show_save_errors}
        <div class="flex flex-col gap-1 mt-2 text-xs">
          {#each save_errors as e}
            <div>{e.getMessage()}</div>
          {/each}
        </div>
      {/if}
    </div>
  {/if}

  {#if save_completed && save_errors.length === 0 && total_saved > 0 && outputs_savable === 0}
    <Warning
      warning_message={`Saved ${total_saved} ${
        total_saved === 1 ? "item" : "items"
      } into your Dataset.`}
      warning_color="success"
      warning_icon="check"
      tight
    />
  {/if}

  {#if generating}
    {@const progress = inputs_done ? generated_outputs : generated_inputs}
    <div>
      <div class="flex flex-row justify-between text-xs font-light mb-1">
        <span class="font-medium">
          {inputs_done ? "Generating Outputs" : "Generating Inputs"}
        </span>
        <span class="text-gray-500">{progress} of {total}</span>
      </div>
      <progress
        class="progress progress-primary w-full"
        value={progress}
        max={total}
      ></progress>
    </div>
  {/if}

  <!-- Plan provenance. The plan itself lives in a dialog — by this point it's
       reference material, not something to read alongside the samples. -->
  <div
    class="rounded-lg border px-4 py-3 flex items-center justify-between text-sm"
  >
    <div class="flex items-center gap-1.5 text-gray-600">
      <span class="w-4 h-4 text-primary"><StarsIcon /></span>
      {generating ? "Generating from your" : "Generated from your"}
      <span class="font-medium text-base-content">Batch Plan</span>
      <!-- The count lives in the progress bar while it's up; showing it here too
           would duplicate it. -->
      {#if !generating}
        <span class="text-gray-400">·</span>
        {plan_summary_line}
      {/if}
    </div>
    <button class="link" on:click={() => open_dialog(plan_dialog_id)}>
      View Plan
    </button>
  </div>

  {#if total === 0}
    <div
      class="rounded-lg border px-4 py-12 flex flex-col items-center gap-3 text-center"
    >
      <div class="text-sm text-gray-500">
        You've removed every sample from this batch.
      </div>
      <button class="btn btn-sm btn-primary" on:click={on_back}>
        Back to Plan
      </button>
    </div>
  {:else}
    <div class="rounded-lg border">
      <table class="table table-fixed">
        <thead>
          <tr>
            <!-- 140 + 40 = 180 (the width of the last two columns) -->
            <th style="width: calc(50% - 70px)">
              Input <InfoTooltip
                tooltip_text="The input to the task, generated from your batch plan."
                position="bottom"
              />
            </th>
            <th style="width: calc(50% - 110px)">
              Output <InfoTooltip
                tooltip_text="The output from running the task on the input."
                position="bottom"
              />
            </th>
            <th style="width: 140px">Status</th>
            <th style="width: 40px"></th>
          </tr>
        </thead>
        <tbody>
          {#each rows as row, i}
            <!-- A prompt whose input failed has nothing to show or act on. -->
            {#if !row.input_error}
              <tr on:click={() => toggle_expand(i)} class="cursor-pointer">
                <td class="py-2 align-top">
                  {#if row.input !== null}
                    {#if expanded[i]}
                      <pre
                        class="whitespace-pre-wrap break-words">{format_expanded(
                          input_text(row.input),
                        )}</pre>
                    {:else}
                      <div class="truncate w-0 min-w-full">
                        {input_text(row.input)}
                      </div>
                    {/if}
                  {:else}
                    <span class="flex items-center gap-2 text-gray-500">
                      <span class="loading loading-spinner loading-xs"></span>
                      Generating…
                    </span>
                  {/if}
                </td>
                <td class="py-2 align-top">
                  {#if row.output !== null}
                    {#if expanded[i]}
                      <pre
                        class="whitespace-pre-wrap break-words">{format_expanded(
                          row.output,
                        )}</pre>
                    {:else}
                      <div class="truncate w-0 min-w-full">{row.output}</div>
                    {/if}
                  {:else if row.output_error}
                    <span class="text-error text-sm">Failed</span>
                  {:else if outputs_pending.has(i)}
                    <span class="flex items-center gap-2 text-gray-500">
                      <span class="loading loading-spinner loading-xs"></span>
                      Generating…
                    </span>
                  {:else}
                    <span class="text-gray-400">Not Generated</span>
                  {/if}
                </td>
                <td class="py-2 align-top">
                  {#if row.saved_id}
                    <a
                      href={`/dataset/${project_id}/${task_id}/${row.saved_id}/run`}
                      class="hover:underline">Saved</a
                    >
                  {:else if row.output}
                    Unsaved
                  {:else}
                    No Output
                  {/if}
                </td>
                <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
                <td class="p-0 align-top" on:click|stopPropagation>
                  <TableActionMenu
                    items={[
                      {
                        label: "View Input Plan",
                        onclick: () => show_prompt(row.prompt),
                      },
                      {
                        label: "Remove Output",
                        onclick: () => remove_output(i),
                        hidden: generating || !!row.saved_id || !row.task_run,
                      },
                      {
                        label: "Remove Sample",
                        onclick: () => delete_row(i),
                        hidden: generating || !!row.saved_id,
                      },
                    ]}
                  />
                </td>
              </tr>
            {/if}
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

<!-- Batch Plan popup: the summary, plus the descriptions it produced -->
<dialog id={plan_dialog_id} class="modal">
  <div class="modal-box max-w-3xl">
    <form method="dialog">
      <button
        class="btn btn-sm text-xl btn-circle btn-ghost absolute right-2 top-2 focus:outline-none"
        >✕</button
      >
    </form>
    <h3 class="text-lg font-bold mb-4">Batch Plan</h3>
    <div class="flex flex-col gap-4">
      <KilnProPlanSummary
        summary={plan.summary}
        out_of_sync={summary_out_of_sync}
      />
      <div class="rounded-lg border">
        <KilnProPlansTable prompts={input_plans} statuses={plan_statuses} />
      </div>
    </div>
  </div>
  <form method="dialog" class="modal-backdrop">
    <button>close</button>
  </form>
</dialog>

<!-- Generate Inputs modal, for retry and regenerate -->
<dialog id={inputs_dialog_id} class="modal">
  <div class="modal-box">
    <form method="dialog">
      <button
        class="btn btn-sm text-xl btn-circle btn-ghost absolute right-2 top-2 focus:outline-none"
        >✕</button
      >
    </form>
    <h3 class="text-lg font-bold">Generate Inputs</h3>
    <p class="text-sm font-light mb-5">
      Generate synthetic inputs: the data that will be passed into the task.
    </p>
    <FormContainer
      submit_label="Generate Inputs"
      bind:submitting={inputs_submitting}
      on:submit={submit_inputs_config}
    >
      <div>
        <div class="font-medium text-sm">Status</div>
        <div class="font-light">
          {inputs_pending}
          {inputs_pending === 1 ? "item" : "items"} pending
          {#if inputs_already_generated > 0}
            / {inputs_already_generated} already generated
          {/if}
        </div>
      </div>
      {#if task}
        <RunConfigComponent
          bind:this={inputs_run_config}
          {project_id}
          current_task={task}
          requires_structured_output={true}
          hide_prompt_selector={true}
          show_tools_selector_in_advanced={true}
          show_name_field={false}
          model_dropdown_settings={{
            requires_data_gen: true,
            requires_uncensored_data_gen:
              guidance_data.suggest_uncensored($selected_template),
            suggested_mode: guidance_data.suggest_uncensored($selected_template)
              ? "uncensored_data_gen"
              : "data_gen",
          }}
        />
      {/if}
    </FormContainer>
  </div>
  <form method="dialog" class="modal-backdrop">
    <button>close</button>
  </form>
</dialog>

<!-- Generate Outputs modal -->
<dialog id={outputs_dialog_id} class="modal">
  <div class="modal-box">
    <form method="dialog">
      <button
        class="btn btn-sm text-xl btn-circle btn-ghost absolute right-2 top-2 focus:outline-none"
        >✕</button
      >
    </form>
    <h3 class="text-lg font-bold">Generate Outputs</h3>
    <p class="text-sm font-light mb-5">
      Run your task on each input to generate outputs.
    </p>
    <FormContainer
      submit_label="Generate Outputs"
      bind:submitting={outputs_submitting}
      on:submit={start_outputs}
    >
      <div>
        <div class="font-medium text-sm">Status</div>
        <div class="font-light">
          {outputs_missing}
          {outputs_missing === 1 ? "item" : "items"} pending
          {#if generated_outputs > 0}
            / {generated_outputs} already generated
          {/if}
        </div>
      </div>
      {#if task}
        <RunConfigComponent
          bind:this={outputs_run_config}
          {project_id}
          current_task={task}
          requires_structured_output={!!task.output_json_schema}
          show_name_field={false}
          model_dropdown_settings={{
            requires_structured_output: !!task.output_json_schema,
          }}
        />
      {/if}
    </FormContainer>
  </div>
  <form method="dialog" class="modal-backdrop">
    <button>close</button>
  </form>
</dialog>

<!-- Prompt popup -->
<dialog id={prompt_dialog_id} class="modal">
  <div class="modal-box">
    <form method="dialog">
      <button
        class="btn btn-sm text-xl btn-circle btn-ghost absolute right-2 top-2 focus:outline-none"
        >✕</button
      >
    </form>
    <h3 class="text-lg font-bold mb-1">Input Plan</h3>
    <p class="text-sm font-light text-gray-500 mb-4">
      The input plan that generated this input.
    </p>
    <div class="rounded-lg bg-base-200 p-4 text-sm whitespace-pre-wrap">
      {active_prompt}
    </div>
  </div>
  <form method="dialog" class="modal-backdrop">
    <button>close</button>
  </form>
</dialog>
