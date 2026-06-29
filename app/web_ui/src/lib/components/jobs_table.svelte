<script lang="ts">
  import Dialog from "$lib/ui/dialog.svelte"
  import Intro from "$lib/ui/intro.svelte"
  import TableActionMenu from "$lib/ui/table_action_menu.svelte"
  import type { FloatingMenuItem } from "$lib/ui/floating_menu_types"
  import JobsIcon from "$lib/ui/icons/jobs_icon.svelte"
  import { jobs, synced, connection } from "$lib/stores/jobs_store"
  import {
    available_actions,
    completed_jobs,
    is_terminal,
    job_status_display_badge_class,
    job_status_display_label,
    progress_label,
    progress_percent,
    type JobAction,
  } from "$lib/stores/job_status"
  import {
    cancel_job,
    delete_job,
    eval_job_properties,
    get_job_errors,
    get_job_result,
    pause_job,
    resume_job,
    type JobError,
    type JobErrorEntry,
    type JobRecord,
  } from "$lib/stores/jobs_api"
  import {
    formatDate,
    capitalize,
    eval_config_to_ui_name,
  } from "$lib/utils/formatters"
  import { getDetailedModelNameFromParts } from "$lib/utils/run_config_formatters"
  import { model_info } from "$lib/stores"
  import type { EvalConfigType } from "$lib/types"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"

  let action_error: KilnError | null = null
  let in_flight: Record<string, boolean> = {}
  let clearing_completed = false

  $: completed = completed_jobs($jobs)

  const action_runners: Record<JobAction, (id: string) => Promise<void>> = {
    pause: pause_job,
    resume: resume_job,
    cancel: cancel_job,
    delete: delete_job,
  }

  const action_labels: Record<JobAction, string> = {
    pause: "Pause",
    resume: "Resume",
    cancel: "Cancel",
    delete: "Delete",
  }

  async function run_action(action: JobAction, id: string) {
    action_error = null
    in_flight = { ...in_flight, [id]: true }
    try {
      await action_runners[action](id)
      // The SSE stream reflects the resulting transition; no local mutation.
    } catch (e) {
      action_error = createKilnError(e)
    } finally {
      in_flight = { ...in_flight, [id]: false }
    }
  }

  // Best-effort delete of every terminal job. Failures are surfaced but don't
  // halt the rest; the SSE stream removes the rows as each delete lands.
  async function clear_completed() {
    action_error = null
    clearing_completed = true
    try {
      const results = await Promise.allSettled(
        completed.map((job) => delete_job(job.id)),
      )
      const failure = results.find((r) => r.status === "rejected")
      if (failure && failure.status === "rejected") {
        action_error = createKilnError(failure.reason)
      }
    } finally {
      clearing_completed = false
    }
  }

  function job_type_display(type: string): string {
    if (type === "noop") {
      return "No-op"
    }
    return capitalize(type)
  }

  // UI name for an eval job's judge algorithm. The properties dict carries it as
  // a plain string; narrow to EvalConfigType here so the markup stays cast-free.
  function judge_algorithm_display(algorithm: string): string {
    return eval_config_to_ui_name(algorithm as EvalConfigType)
  }

  function has_errors(job: JobRecord): boolean {
    return (job.progress?.error ?? 0) > 0 || job.status === "failed"
  }

  // Only show a result once the job is in a terminal state — a non-null
  // `result` mid-run would be partial and misleading.
  function has_result(job: JobRecord): boolean {
    return is_terminal(job.status) && job.result != null
  }

  // Surface the record's failure summary inline for failed jobs.
  function failure_error(job: JobRecord): JobError | null {
    return job.status === "failed" ? job.error ?? null : null
  }

  // Errors dialog state
  let errors_dialog: Dialog
  let errors_loading = false
  let errors_load_error: KilnError | null = null
  let error_entries: JobErrorEntry[] = []
  let errors_summary: JobError | null = null

  async function open_errors(job: JobRecord) {
    error_entries = []
    errors_load_error = null
    errors_summary = failure_error(job)
    errors_loading = true
    errors_dialog?.show()
    try {
      error_entries = await get_job_errors(job.id)
    } catch (e) {
      errors_load_error = createKilnError(e)
    } finally {
      errors_loading = false
    }
  }

  // Result dialog state
  let result_dialog: Dialog
  let result_loading = false
  let result_load_error: KilnError | null = null
  let result_data: Record<string, unknown> | null = null

  async function open_result(job: JobRecord) {
    result_data = null
    result_load_error = null
    result_loading = true
    result_dialog?.show()
    try {
      result_data = await get_job_result(job.id)
    } catch (e) {
      result_load_error = createKilnError(e)
    } finally {
      result_loading = false
    }
  }

  // The row's overflow menu: view actions first, then lifecycle actions.
  function row_menu_items(job: JobRecord): FloatingMenuItem[] {
    const items: FloatingMenuItem[] = []
    if (has_result(job)) {
      items.push({ label: "View results", onclick: () => open_result(job) })
    }
    if (has_errors(job)) {
      items.push({ label: "View errors", onclick: () => open_errors(job) })
    }
    for (const action of available_actions(job)) {
      items.push({
        label: action === "delete" ? "Clear" : action_labels[action],
        onclick: () => run_action(action, job.id),
      })
    }
    return items
  }
</script>

{#if action_error}
  <div role="alert" class="alert alert-error text-sm mb-4">
    <span>{action_error.getMessage() || "An action failed."}</span>
  </div>
{/if}

{#if !$synced && $connection === "errored"}
  <div
    class="flex flex-col items-center justify-center min-h-[50vh] text-center max-w-md mx-auto"
  >
    <div class="text-gray-400 mb-3">
      <span class="loading loading-spinner loading-md"></span>
    </div>
    <h3 class="text-lg font-medium">Can't connect to the job stream</h3>
    <p class="text-sm text-gray-500 mt-2">
      We lost the connection to the background job updates and are retrying
      automatically. Jobs keep running in the background — this page will
      refresh once the connection is restored.
    </p>
  </div>
{:else if !$synced}
  <div class="w-full min-h-[50vh] flex justify-center items-center">
    <div class="loading loading-spinner loading-lg"></div>
  </div>
{:else if $jobs.length === 0}
  <div class="flex justify-center items-center min-h-[55vh]">
    <Intro
      title="No jobs yet"
      description_paragraphs={[
        "Long-running workloads show up here. Manage them from this page, or leave — they'll keep running in the background.",
      ]}
    >
      <div slot="icon" class="w-12 h-12 text-gray-400" aria-hidden="true">
        <JobsIcon />
      </div>
    </Intro>
  </div>
{:else}
  <div class="flex flex-row justify-end mb-3">
    <button
      class="btn btn-xs btn-ghost"
      disabled={clearing_completed || completed.length === 0}
      on:click={clear_completed}
    >
      {#if clearing_completed}
        <span class="loading loading-spinner loading-xs"></span>
      {/if}
      Clear completed
    </button>
  </div>
  <div class="overflow-x-auto rounded-lg border">
    <table class="table">
      <thead>
        <tr>
          <th>Details</th>
          <th>Status</th>
          <th class="text-right"></th>
        </tr>
      </thead>
      <tbody>
        {#each $jobs as job (job.id)}
          <tr>
            <td class="align-top">
              <div class="flex flex-col gap-1 max-w-[280px]">
                {#if eval_job_properties(job)}
                  {@const p = eval_job_properties(job)}
                  {@const model = p?.run_config_model_name
                    ? getDetailedModelNameFromParts(
                        p.run_config_model_name,
                        p.run_config_model_provider,
                        $model_info,
                      )
                    : ""}
                  {@const judge_model = p?.judge_model_name
                    ? getDetailedModelNameFromParts(
                        p.judge_model_name,
                        p.judge_model_provider,
                        $model_info,
                      )
                    : ""}
                  <span class="font-medium truncate" title={p?.eval_name}
                    >Eval: {p?.eval_name}</span
                  >
                  <div class="space-y-1 text-xs text-gray-500">
                    <div class="truncate" title={p?.run_config_name}>
                      Run config: {p?.run_config_name}
                    </div>
                    {#if model}
                      <div class="truncate" title={model}>Model: {model}</div>
                    {/if}
                    {#if p?.run_config_prompt_name}
                      <div class="truncate" title={p.run_config_prompt_name}>
                        Prompt: {p.run_config_prompt_name}
                      </div>
                    {/if}
                    <div>
                      Tools: {p && p.run_config_tools_count > 0
                        ? `${p.run_config_tools_count} available`
                        : "None"}
                    </div>
                    <div>
                      Skills: {p && p.run_config_skills_count > 0
                        ? `${p.run_config_skills_count} available`
                        : "None"}
                    </div>
                    <div class="truncate">
                      Judge: {judge_algorithm_display(p?.judge_algorithm ?? "")}
                    </div>
                    {#if judge_model}
                      <div class="truncate" title={judge_model}>
                        Judge model: {judge_model}
                      </div>
                    {/if}
                  </div>
                {:else}
                  <span class="font-medium">{job_type_display(job.type)}</span>
                {/if}
                <span class="text-[11px] text-gray-400 mt-2"
                  >{formatDate(job.created_at)}</span
                >
                <span class="font-mono text-[11px] text-gray-400 truncate"
                  >{job.id}</span
                >
              </div>
            </td>
            <td>
              <div class="flex flex-col gap-2 w-full max-w-[360px] min-w-48">
                <span
                  class="badge h-auto px-3 py-1 self-start whitespace-normal text-center leading-tight {job_status_display_badge_class(
                    job,
                  )}"
                >
                  {job_status_display_label(job)}
                </span>
                <div class="flex items-center justify-between text-gray-500">
                  {#if job.status === "running"}
                    <span>{progress_percent(job.progress)}% Complete</span>
                  {/if}
                  {#if job.progress?.total}
                    <span>{progress_label(job.progress)}</span>
                  {/if}
                </div>
                {#if progress_percent(job.progress) < 100}
                  <progress
                    class="progress progress-primary bg-base-200 w-full h-2"
                    value={progress_percent(job.progress)}
                    max="100"
                  ></progress>
                  {#if failure_error(job)?.error}
                    <span
                      class="font-mono text-sm text-error block truncate"
                      title={failure_error(job)?.error}
                      >{failure_error(job)?.error}</span
                    >
                  {:else if job.progress?.message}
                    <span
                      class="font-mono text-sm text-gray-500 block truncate"
                      title={job.progress.message}>{job.progress.message}</span
                    >
                  {/if}
                {/if}
              </div>
            </td>
            <td class="align-top">
              <div class="flex flex-row justify-end items-start">
                <TableActionMenu items={row_menu_items(job)} />
              </div>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}

<Dialog bind:this={errors_dialog} title="Job Errors" width="wide">
  {#if errors_summary?.error}
    <div
      role="alert"
      class="alert alert-error text-sm mb-4 flex flex-col items-start gap-1"
    >
      <span class="font-medium break-words">{errors_summary.error}</span>
      {#if errors_summary.detail}
        <pre
          class="text-xs w-full bg-base-200 text-base-content rounded-md p-2 overflow-x-auto max-h-48">{JSON.stringify(
            errors_summary.detail,
            null,
            2,
          )}</pre>
      {/if}
    </div>
  {/if}
  {#if errors_loading}
    <div class="flex justify-center py-8">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else if errors_load_error}
    <div class="text-error text-sm">
      {errors_load_error.getMessage() || "Could not load errors."}
    </div>
  {:else if error_entries.length === 0}
    <p class="text-sm text-gray-500">
      No error messages recorded for this job.
    </p>
  {:else}
    <ul class="flex flex-col gap-2 max-h-[60vh] overflow-y-auto">
      {#each error_entries as entry, index (index)}
        <li class="text-sm bg-base-200 rounded-md p-3 font-mono break-words">
          {entry.error_message || JSON.stringify(entry)}
        </li>
      {/each}
    </ul>
  {/if}
</Dialog>

<Dialog bind:this={result_dialog} title="Job Result" width="wide">
  {#if result_loading}
    <div class="flex justify-center py-8">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else if result_load_error}
    <div class="text-error text-sm">
      {result_load_error.getMessage() || "Could not load result."}
    </div>
  {:else if result_data}
    <pre
      class="text-xs bg-base-200 rounded-md p-3 overflow-x-auto max-h-[60vh]">{JSON.stringify(
        result_data,
        null,
        2,
      )}</pre>
  {:else}
    <p class="text-sm text-gray-500">No result available.</p>
  {/if}
</Dialog>
