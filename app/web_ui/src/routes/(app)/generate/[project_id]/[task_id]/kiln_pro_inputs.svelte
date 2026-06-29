<script lang="ts">
  import { onDestroy, onMount, tick } from "svelte"
  import { client } from "$lib/api_client"
  import type { components } from "$lib/api_schema"
  import type { KilnAgentRunConfigProperties } from "$lib/types"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import RunConfigComponent from "$lib/ui/run_config_component/run_config_component.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import StarsIcon from "$lib/ui/icons/stars_icon.svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
  import TrashIcon from "$lib/ui/icons/trash_icon.svelte"
  import KilnProPlanSummary from "./kiln_pro_plan_summary.svelte"
  import { SynthDataGuidanceDataModel } from "./synth_data_guidance_datamodel"
  import {
    runInputsBatch,
    runOutputsBatch,
    type BatchRun,
    type InputsBatchStatus,
    type OutputsBatchStatus,
  } from "$lib/stores/kiln_pro_batch_store"

  export let plan: { prompts: string[]; summary: string }
  export let project_id: string
  export let task_id: string
  export let guidance_data: SynthDataGuidanceDataModel
  // The user already chose the model/data-guide in the modal on the plan page;
  // generation starts on mount with these.
  export let run_config_properties: KilnAgentRunConfigProperties
  export let data_guide: string | null
  export let summary_out_of_sync = false

  type TaskRun = components["schemas"]["TaskRun-Output"]
  type Row = {
    prompt: string
    input: string | Record<string, unknown> | null
    output: string | null
    task_run: TaskRun | null
    input_error: string | null
    output_error: string | null
    saved: boolean
  }

  let rows: Row[] = plan.prompts.map((p) => ({
    prompt: p,
    input: null,
    output: null,
    task_run: null,
    input_error: null,
    output_error: null,
    saved: false,
  }))

  $: task = guidance_data.task

  let show_plan = false

  let inputs_status: "running" | "complete" | "error" | null = null
  let outputs_started = false
  let outputs_status: "running" | "complete" | "error" | null = null
  let batch_error: KilnError | null = null

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
    (r) => r.task_run !== null && !r.saved,
  ).length
  $: generating = !inputs_done || (outputs_started && !outputs_done)

  const outputs_dialog_id = "kiln_pro_outputs_dialog"
  let outputs_run_config: RunConfigComponent | null = null
  let outputs_submitting = false

  // Per-row "Prompt" popup showing the plan prompt that produced an input.
  const prompt_dialog_id = "kiln_pro_prompt_dialog"
  let active_prompt = ""
  function show_prompt(p: string) {
    active_prompt = p
    open_dialog(prompt_dialog_id)
  }

  function delete_row(index: number) {
    rows = rows.filter((_, i) => i !== index)
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

  function start_inputs() {
    if (!guidance_data.gen_type) {
      batch_error = new KilnError("No generation type selected.", null)
      inputs_status = "error"
      return
    }
    inputs_status = "running"
    inputs_run = runInputsBatch(project_id, task_id, {
      prompts: plan.prompts,
      gen_type: guidance_data.gen_type,
      data_guide: data_guide || null,
      run_config_properties,
    })
    inputs_unsub.push(
      inputs_run.status.subscribe((s) => {
        if (!s) return
        for (const r of s.results) {
          if (r.input !== null && r.input !== undefined) {
            rows[r.index].input = r.input
          }
          if (r.error) rows[r.index].input_error = r.error
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

  function start_outputs() {
    outputs_submitting = false
    const rcp =
      outputs_run_config?.run_options_as_run_config_properties() ?? null
    if (!rcp) {
      batch_error = new KilnError("No run config selected.", null)
      return
    }
    close_dialog(outputs_dialog_id)

    const items = rows
      .map((r, i) => ({ index: i, input: r.input }))
      .filter(
        (
          it,
        ): it is { index: number; input: string | Record<string, unknown> } =>
          it.input !== null,
      )

    outputs_run?.cancel()
    outputs_unsub.forEach((u) => u())
    outputs_unsub = []
    batch_error = null
    outputs_started = true
    outputs_status = "running"

    outputs_run = runOutputsBatch(project_id, task_id, {
      items,
      input_model_name: run_config_properties.model_name,
      input_provider: run_config_properties.model_provider_name,
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
        }
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
    const to_save = rows.filter((r) => r.task_run && !r.saved)
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
        row.saved = true
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
  <div class="flex flex-col md:flex-row md:items-start gap-4">
    <div class="flex-grow">
      <div class="text-xl font-bold">Inputs</div>
      <div class="text-sm font-light text-gray-500">
        {#if !inputs_done}
          {generated_inputs} of {total} generated…
        {:else}
          {generated_inputs} of {total} inputs generated{input_errors > 0
            ? ` — ${input_errors} failed`
            : ""}
        {/if}
      </div>
    </div>
    <div class="flex flex-row gap-2 shrink-0">
      {#if inputs_done && !outputs_done}
        <button
          class="btn btn-sm btn-primary"
          disabled={generated_inputs === 0 || generating}
          on:click={() => open_dialog(outputs_dialog_id)}
        >
          Generate Outputs
        </button>
      {:else if outputs_done && outputs_savable > 0}
        <button
          class="btn btn-sm btn-primary"
          disabled={saving}
          on:click={save_all}
        >
          {saving ? "Saving…" : `Save All (${outputs_savable})`}
        </button>
      {/if}
    </div>
  </div>

  {#if generating}
    <progress
      class="progress progress-primary w-full"
      value={inputs_done ? generated_outputs : generated_inputs}
      max={total}
    ></progress>
  {/if}

  {#if batch_error}
    <div class="text-error text-sm">{batch_error.getMessage()}</div>
  {/if}

  {#if saving}
    <div>
      <progress
        class="progress progress-success w-full"
        value={save_progress}
        max={save_target}
      ></progress>
      <div class="text-xs font-light text-gray-500 mt-1">
        Saving {save_progress} of {save_target}…
      </div>
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
    <div
      class="rounded-lg bg-success/10 border border-success/30 px-4 py-3 text-sm"
    >
      Saved {total_saved} items into your dataset. They're available in the
      <a href={`/dataset/${project_id}/${task_id}`} class="link">dataset tab</a
      >.
    </div>
  {/if}

  <!-- Plan provenance banner -->
  <div
    class="rounded-lg bg-primary/5 border border-primary/20 px-4 py-3 flex items-center justify-between text-sm"
  >
    <div class="flex items-center gap-1.5 text-gray-600">
      <span class="w-4 h-4 text-primary"><StarsIcon /></span>
      Generated from your
      <span class="font-medium text-base-content">Batch Plan</span>
      <span class="text-gray-400">·</span>
      {total} prompts
    </div>
    <button class="link" on:click={() => (show_plan = !show_plan)}>
      {show_plan ? "Hide plan summary" : "Show plan summary"}
    </button>
  </div>

  {#if show_plan}
    <KilnProPlanSummary
      summary={plan.summary}
      out_of_sync={summary_out_of_sync}
    />
  {/if}

  <div class="rounded-lg border">
    <table class="table table-fixed">
      <thead>
        <tr>
          <th style="width: calc(50% - 90px)">
            Input <InfoTooltip
              tooltip_text="The input to the task, generated from your batch plan."
              position="bottom"
            />
          </th>
          <th style="width: calc(50% - 90px)">
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
          <tr>
            <td class="whitespace-normal align-top">
              {#if row.input !== null}
                <div>
                  {typeof row.input === "string"
                    ? row.input
                    : JSON.stringify(row.input)}
                </div>
                <button
                  class="link text-xs text-gray-400 mt-0.5"
                  on:click={() => show_prompt(row.prompt)}
                >
                  Prompt
                </button>
              {:else if row.input_error}
                <span class="text-error text-sm">Failed</span>
              {:else}
                <span class="flex items-center gap-2 text-gray-500">
                  <span class="loading loading-spinner loading-xs"></span>
                  Generating…
                </span>
              {/if}
            </td>
            <td class="whitespace-normal align-top">
              {#if row.output !== null}
                {row.output}
              {:else if row.output_error}
                <span class="text-error text-sm">Failed</span>
              {:else if outputs_started && row.input !== null}
                <span class="flex items-center gap-2 text-gray-500">
                  <span class="loading loading-spinner loading-xs"></span>
                  Generating…
                </span>
              {:else}
                <span class="text-gray-400">Not Generated</span>
              {/if}
            </td>
            <td class="align-top">
              {#if row.saved}
                <span
                  class="inline-flex items-center gap-1.5 text-xs text-success"
                >
                  <span class="w-1.5 h-1.5 rounded-full bg-success"></span>
                  Saved
                </span>
              {:else if row.input_error || row.output_error}
                <span
                  class="inline-flex items-center gap-1.5 text-xs text-error"
                >
                  <span class="w-1.5 h-1.5 rounded-full bg-error"></span>
                  Error
                </span>
              {:else if row.output !== null}
                <span
                  class="inline-flex items-center gap-1.5 text-xs text-gray-600"
                >
                  <span class="w-1.5 h-1.5 rounded-full bg-gray-500"></span>
                  Generated
                </span>
              {:else if row.input !== null}
                <span
                  class="inline-flex items-center gap-1.5 text-xs text-gray-500"
                >
                  <span class="w-1.5 h-1.5 rounded-full bg-gray-400"></span>
                  No output
                </span>
              {:else}
                <span class="text-gray-400">—</span>
              {/if}
            </td>
            <td class="align-top">
              <button
                class="btn btn-ghost btn-xs text-gray-400 hover:text-error"
                aria-label="Delete row"
                disabled={generating}
                on:click={() => delete_row(i)}
              >
                <span class="w-4 h-4"><TrashIcon /></span>
              </button>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</div>

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
    <h3 class="text-lg font-bold mb-1">Plan Prompt</h3>
    <p class="text-sm font-light text-gray-500 mb-4">
      The prompt from your batch plan that generated this input.
    </p>
    <div class="rounded-lg bg-base-200 p-4 text-sm whitespace-pre-wrap">
      {active_prompt}
    </div>
  </div>
  <form method="dialog" class="modal-backdrop">
    <button>close</button>
  </form>
</dialog>
