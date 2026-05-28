<script lang="ts">
  import AppPage from "../app_page.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import RunEvalDialog from "./run_eval_dialog.svelte"
  import JobsIcon from "$lib/ui/icons/jobs_icon.svelte"
  import { jobs, synced, connection } from "$lib/stores/jobs_store"
  import {
    available_actions,
    is_terminal,
    job_status_badge_class,
    job_status_display,
    progress_label,
    progress_percent,
    type JobAction,
  } from "$lib/stores/job_status"
  import {
    cancel_job,
    create_job,
    delete_job,
    get_job_errors,
    get_job_result,
    pause_job,
    resume_job,
    type JobError,
    type JobErrorEntry,
    type JobRecord,
  } from "$lib/stores/jobs_api"
  import { formatDate } from "$lib/utils/formatters"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { capitalize } from "$lib/utils/formatters"
  import { agentInfo } from "$lib/agent"
  import { ui_state } from "$lib/stores"

  agentInfo.set({
    name: "Background Jobs",
    description:
      "Background job panel. Lists jobs (evals and others) with status, progress, and lifecycle controls.",
  })

  let action_error: KilnError | null = null
  let in_flight: Record<string, boolean> = {}
  let creating_test_job = false

  // Kicks off a no-op job: a simulated long-running task (sleeps per step,
  // streams progress, logs a couple of non-fatal errors) for exercising the
  // panel end-to-end. The new job appears via the SSE stream — no local mutation.
  async function start_test_job() {
    action_error = null
    creating_test_job = true
    try {
      await create_job(
        "noop",
        {
          steps: 20,
          sleep_per_step_seconds: 1,
          error_at_steps: [4, 12],
        },
        null,
        $ui_state.current_project_id,
      )
    } catch (e) {
      action_error = createKilnError(e)
    } finally {
      creating_test_job = false
    }
  }

  let run_eval_dialog: RunEvalDialog

  $: action_buttons = [
    {
      label: "Run eval",
      handler: () => run_eval_dialog?.show(),
    },
    {
      label: creating_test_job ? "Starting…" : "Start test job",
      handler: start_test_job,
      primary: true,
      loading: creating_test_job,
      disabled: creating_test_job,
    },
  ]

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

  function job_type_display(type: string): string {
    if (type === "noop") {
      return "No-op"
    }
    return capitalize(type)
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
</script>

<AppPage
  title="Jobs"
  subtitle="Background work for the current project."
  sub_subtitle="Jobs keep running even if you navigate away or close this panel."
  {action_buttons}
>
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
    <div
      class="flex flex-col items-center justify-center min-h-[55vh] text-center max-w-md mx-auto"
    >
      <div class="w-12 h-12 text-gray-400 mb-4" aria-hidden="true">
        <JobsIcon />
      </div>
      <h3 class="text-lg font-medium">No jobs yet</h3>
      <p class="text-sm text-gray-500 mt-2">
        Long-running work like eval runs shows up here. Jobs run in the
        background — you can leave this page and they'll keep going. Come back
        any time to check progress, pause, or cancel them.
      </p>
    </div>
  {:else}
    <div class="overflow-x-auto rounded-lg border">
      <table class="table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Type</th>
            <th>Status</th>
            <th>Progress</th>
            <th>Message</th>
            <th>Created</th>
            <th class="text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {#each $jobs as job (job.id)}
            <tr>
              <td class="font-mono text-xs text-gray-500 whitespace-nowrap"
                >{job.id}</td
              >
              <td class="font-medium">{job_type_display(job.type)}</td>
              <td>
                <span class="badge {job_status_badge_class(job.status)}">
                  {job_status_display(job.status)}
                </span>
              </td>
              <td>
                <div class="flex flex-col gap-1 min-w-32">
                  <span class="text-sm">{progress_label(job.progress)}</span>
                  {#if job.progress?.total}
                    <progress
                      class="progress progress-primary w-32 h-1.5"
                      value={progress_percent(job.progress)}
                      max="100"
                    ></progress>
                  {/if}
                </div>
              </td>
              <td class="text-sm text-gray-500 max-w-48">
                {#if failure_error(job)?.error}
                  <span
                    class="text-error block truncate"
                    title={failure_error(job)?.error}
                    >{failure_error(job)?.error}</span
                  >
                {:else}
                  <span class="block truncate"
                    >{job.progress?.message || ""}</span
                  >
                {/if}
              </td>
              <td class="text-sm text-gray-500 whitespace-nowrap">
                {formatDate(job.created_at)}
              </td>
              <td>
                <div class="flex flex-row gap-1 justify-end flex-wrap">
                  {#if has_result(job)}
                    <button
                      class="btn btn-xs btn-ghost"
                      on:click={() => open_result(job)}
                    >
                      Result
                    </button>
                  {/if}
                  {#if has_errors(job)}
                    <button
                      class="btn btn-xs btn-ghost"
                      on:click={() => open_errors(job)}
                    >
                      Errors
                    </button>
                  {/if}
                  {#each available_actions(job) as action}
                    <button
                      class="btn btn-xs {action === 'delete' ||
                      action === 'cancel'
                        ? 'btn-ghost text-error'
                        : 'btn-ghost'}"
                      disabled={in_flight[job.id]}
                      on:click={() => run_action(action, job.id)}
                    >
                      {action_labels[action]}
                    </button>
                  {/each}
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</AppPage>

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

<RunEvalDialog bind:this={run_eval_dialog} />
