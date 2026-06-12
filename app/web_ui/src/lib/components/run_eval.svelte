<script lang="ts">
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import Dialog from "$lib/ui/dialog.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import { base_url } from "$lib/api_client"
  import { jobs } from "$lib/stores/jobs_store"
  import {
    filter_by_tag,
    ongoing,
    compute_run_state,
  } from "$lib/stores/job_selectors"
  import { is_terminal } from "$lib/stores/job_status"
  import { onDestroy } from "svelte"
  import posthog from "posthog-js"

  export let btn_size: "normal" | "mid" | "small" | "xs" = "mid"
  export let btn_primary: boolean = true
  export let btn_class: string = ""
  export let on_run_complete: () => void = () => {}
  export let eval_state:
    | "not_started"
    | "running"
    | "complete"
    | "complete_with_errors" = "not_started"

  export let eval_type: "eval_config" | "run_config"
  export let project_id: string
  export let task_id: string
  export let eval_id: string
  export let current_eval_config_id: string | null = null
  export let run_all: boolean = false
  export let run_config_ids: string[] = []
  // Optional: route-bound callers pass spec_id from $page.params so the
  // resulting jobs carry it on their tag and the jobs widget can link back
  // to the compare_run_configs page. Callers without a spec_id (e.g. the
  // Jobs-panel dialog) leave it null; jobs then link back to the task page.
  export let spec_id: string | null = null
  let run_url: string = ""
  $: {
    if (eval_type === "run_config") {
      const params = new URLSearchParams()

      if (run_all) {
        params.append("all_run_configs", "true")
      } else {
        params.append("all_run_configs", "false")
        // FastAPI expects multiple query parameters with the same name for list[str]
        run_config_ids.forEach((id) => {
          params.append("run_config_ids", id)
        })
      }

      if (spec_id) {
        params.append("spec_id", spec_id)
      }

      // run_comparison is now a one-shot JSON endpoint that spawns tracked
      // jobs and returns their ids. Live progress comes from the jobs SSE
      // store, not this endpoint.
      run_url = `${base_url}/api/projects/${encodeURIComponent(project_id)}/tasks/${encodeURIComponent(task_id)}/evals/${encodeURIComponent(eval_id)}/eval_config/${encodeURIComponent(current_eval_config_id!)}/run_comparison?${params.toString()}`
    } else if (eval_type === "eval_config") {
      // Eval config (calibration) is still SSE-driven — not yet upgraded to
      // the job system. Kept here unchanged so the eval_configs page works.
      run_all = true
      run_url = `${base_url}/api/projects/${encodeURIComponent(project_id)}/tasks/${encodeURIComponent(task_id)}/evals/${encodeURIComponent(eval_id)}/run_calibration`
    }
  }

  let run_dialog: Dialog | null = null
  let running_progress_dialog: Dialog | null = null
  let eval_run_error: KilnError | null = null

  // Job ids returned by the run_comparison call. Live progress is summed
  // from these specific records in $jobs so prior succeeded runs of the same
  // (eval, eval_config, run_config) don't pollute the counters. Cleared on
  // each fresh launch.
  let active_job_ids: string[] = []
  let calibration_complete_count = 0
  let calibration_total_count = 0
  let calibration_error_count = 0

  $: active_jobs = active_job_ids.length
    ? $jobs.filter((j) => active_job_ids.includes(j.id))
    : []
  $: eval_complete_count =
    eval_type === "run_config"
      ? active_jobs.reduce((s, j) => s + (j.progress?.success ?? 0), 0)
      : calibration_complete_count
  $: eval_total_count =
    eval_type === "run_config"
      ? active_jobs.reduce((s, j) => s + (j.progress?.total ?? 0), 0)
      : calibration_total_count
  $: eval_error_count =
    eval_type === "run_config"
      ? active_jobs.reduce((s, j) => s + (j.progress?.error ?? 0), 0)
      : calibration_error_count
  // Track which tracked jobs we've actually observed in $jobs at least once,
  // so we can tell "not appeared yet" (still launching) apart from "appeared
  // then vanished" (superseded/deleted out from under an open dialog).
  let seen_job_ids = new Set<string>()
  $: {
    let changed = false
    for (const id of active_job_ids) {
      if (!seen_job_ids.has(id) && $jobs.some((j) => j.id === id)) {
        seen_job_ids.add(id)
        changed = true
      }
    }
    if (changed) seen_job_ids = seen_job_ids
  }
  // All spawned jobs reached a terminal state — drive the dialog from
  // "running" to "complete" / "complete_with_errors". A job that was seen and
  // then disappeared (e.g. superseded by another run) counts as terminal, so a
  // still-open dialog doesn't hang forever waiting on a row that no longer
  // exists. Jobs that haven't appeared yet keep us in "running".
  $: all_active_terminal =
    eval_type === "run_config" &&
    active_job_ids.length > 0 &&
    active_job_ids.every((id) => {
      const j = $jobs.find((job) => job.id === id)
      if (j) return is_terminal(j.status)
      return seen_job_ids.has(id)
    })
  $: if (all_active_terminal && eval_state === "running") {
    eval_state = eval_error_count > 0 ? "complete_with_errors" : "complete"
    on_run_complete()
  }

  // Awareness via the project-scoped jobs store. The store is authoritative
  // for "is it running" (paused & terminals are NOT ongoing), so a stuck
  // local "running" — e.g. an SSE that never received its terminal sentinel
  // because the user paused the job via the widget — is overridden and the
  // button returns to "Run Eval". Local terminal states (complete /
  // complete_with_errors) still display when no jobs are ongoing.
  $: matching =
    eval_type === "run_config" && current_eval_config_id !== null
      ? filter_by_tag(
          $jobs,
          "eval",
          (t) =>
            t.eval_id === eval_id &&
            t.eval_config_id === current_eval_config_id &&
            (run_all || run_config_ids.includes(t.run_config_id)),
        )
      : []
  $: store_running = ongoing(matching).length > 0

  // `initiating` bridges the click-to-store-update window so the button
  // doesn't flicker between "Run Eval" -> "Running…" -> "Run Eval" -> "Running…"
  // while the EventSource opens and the server publishes the first job events.
  // Cleared as soon as the store actually sees an ongoing job, or after a
  // safety timeout.
  let initiating = false
  let initiating_timer: ReturnType<typeof setTimeout> | null = null
  function start_initiating() {
    initiating = true
    if (initiating_timer) clearTimeout(initiating_timer)
    initiating_timer = setTimeout(() => {
      initiating = false
      initiating_timer = null
    }, 5000)
  }
  function clear_initiating() {
    initiating = false
    if (initiating_timer) {
      clearTimeout(initiating_timer)
      initiating_timer = null
    }
  }
  $: if (store_running && initiating) clear_initiating()
  onDestroy(() => {
    if (initiating_timer) clearTimeout(initiating_timer)
  })

  $: effective_eval_state = compute_run_state(
    store_running,
    initiating,
    eval_state,
  )

  function run_eval(): boolean {
    if (eval_type === "run_config" && !current_eval_config_id) {
      eval_run_error = new KilnError(
        "Select all options needed to run the eval.",
        null,
      )
      eval_state = "complete_with_errors"
      // True to close the run dialog, and then show the error in the progress dialog
      running_progress_dialog?.show()
      return true
    }

    if (
      eval_type === "run_config" &&
      !run_all &&
      (!run_config_ids || run_config_ids.length === 0)
    ) {
      eval_run_error = new KilnError(
        "Select at least one run config to run the eval.",
        null,
      )
      eval_state = "complete_with_errors"
      // True to close the run dialog, and then show the error in the progress dialog
      running_progress_dialog?.show()
      return true
    }

    eval_state = "running"
    eval_run_error = null
    active_job_ids = []
    seen_job_ids = new Set()
    calibration_complete_count = 0
    calibration_total_count = 0
    calibration_error_count = 0
    start_initiating()

    posthog.capture("run_eval", {
      eval_type: eval_type,
      run_all: run_all,
    })

    if (eval_type === "run_config") {
      // Job-system path: one HTTP call returns the spawned job ids. The
      // jobs-store SSE stream drives the live counters via $jobs.
      spawn_run_config_eval()
    } else {
      // Calibration is still streaming SSE (not yet migrated to the job
      // system). Kept inline so this component covers both flows.
      stream_calibration_eval()
    }

    // Switch over to the progress dialog, closing the run dialog
    running_progress_dialog?.show()
    return true
  }

  async function spawn_run_config_eval(): Promise<void> {
    try {
      const response = await fetch(run_url)
      if (!response.ok) {
        const body = await response.text()
        throw new Error(
          `Eval run failed: ${response.status} ${body || response.statusText}`,
        )
      }
      const data = (await response.json()) as {
        kiln_job_tracking_ids: string[]
      }
      active_job_ids = data.kiln_job_tracking_ids
      // Empty list = no work to do (no run configs matched, or supersede tore
      // everything down). Either way: nothing to wait for.
      if (active_job_ids.length === 0) {
        eval_state = "complete"
        on_run_complete()
      }
    } catch (error) {
      eval_run_error = createKilnError(error)
      eval_state = "complete_with_errors"
      on_run_complete()
    }
  }

  function stream_calibration_eval(): void {
    const eventSource = new EventSource(run_url)
    eventSource.onmessage = (event) => {
      try {
        if (event.data === "complete") {
          eventSource.close()
          eval_state =
            calibration_error_count > 0 ? "complete_with_errors" : "complete"
          on_run_complete()
        } else {
          const data = JSON.parse(event.data)
          calibration_complete_count = data.progress
          calibration_total_count = data.total
          calibration_error_count = data.errors
          eval_state = "running"
        }
      } catch (error) {
        eventSource.close()
        eval_run_error = createKilnError(error)
        console.error(eval_run_error)
        eval_state = "complete_with_errors"
        on_run_complete()
      }
    }
    eventSource.onerror = (error) => {
      eventSource.close()
      eval_state = "complete_with_errors"
      eval_run_error = createKilnError(error)
      on_run_complete()
    }
  }

  // Returns false so the dialog isn't closed
  function re_run_eval(): boolean {
    run_eval()
    return false
  }

  function run_dialog_buttons(eval_state: string) {
    let buttons = []

    if (eval_state === "complete" || eval_state === "complete_with_errors") {
      buttons.push({
        label: "Close",
        isCancel: true,
        isPrimary: false,
      })
    }

    if (eval_state === "complete_with_errors") {
      buttons.push({
        label: "Re-run Eval",
        isPrimary: true,
        action: re_run_eval,
      })
    }

    return buttons
  }

  function run_button_style_class() {
    if (btn_size === "small") {
      return "btn-sm rounded-full"
    } else if (btn_size === "mid") {
      return "btn-mid"
    } else if (btn_size === "xs") {
      return "btn-xs rounded-full"
    }
    return ""
  }
</script>

{#if effective_eval_state === "not_started"}
  <button
    class="btn {run_button_style_class()} {btn_primary
      ? 'btn-primary'
      : 'btn-outline'} whitespace-nowrap {btn_class}"
    on:click={() => {
      run_dialog?.show()
    }}>Run {run_all ? "All Evals" : "Eval"}</button
  >
{:else}
  <button
    class="btn {run_button_style_class()} whitespace-nowrap {btn_class}"
    on:click={() => {
      running_progress_dialog?.show()
    }}
  >
    {#if effective_eval_state === "running"}
      <div class="loading loading-spinner loading-xs"></div>
      Running...
    {:else if effective_eval_state === "complete"}
      Eval Complete
    {:else if effective_eval_state === "complete_with_errors"}
      Eval Errors
    {:else}
      Eval Status
    {/if}
  </button>
{/if}

<Dialog
  bind:this={running_progress_dialog}
  title=""
  action_buttons={run_dialog_buttons(effective_eval_state)}
>
  <div
    class="mt-12 mb-6 flex flex-col items-center justify-center min-h-[100px] text-center"
  >
    {#if effective_eval_state === "complete" && eval_complete_count == 0}
      <div class="font-medium">No Data Needed to be Evaluated</div>
      <div class="text-gray-500 text-sm mt-2 flex flex-col gap-2">
        <div>
          If you want to add more data to your eval,
          <a
            href="https://docs.kiln.tech/docs/evaluations#create-your-eval-datasets"
            target="_blank"
            class="link">read the docs</a
          > for instructions.
        </div>
      </div>
    {:else if effective_eval_state === "complete"}
      <div class="font-medium">Eval Complete 🎉</div>
    {:else if effective_eval_state === "complete_with_errors"}
      <div class="font-medium">Eval Complete with Errors</div>
    {:else if effective_eval_state === "running"}
      <div class="loading loading-spinner loading-lg text-success"></div>
      <div class="font-medium mt-4">Running...</div>
    {/if}
    <div class="text-sm font-light min-w-[120px]">
      {#if eval_total_count > 0}
        <div>
          {eval_complete_count + eval_error_count} of {eval_total_count}
        </div>
      {/if}
      {#if eval_error_count > 0}
        <div class="text-error font-light text-xs">
          {eval_error_count} error{eval_error_count === 1 ? "" : "s"}
        </div>
      {/if}
      {#if eval_run_error}
        <div class="text-error font-light text-xs mt-2">
          {eval_run_error.getMessage() || "An unknown error occurred"}
        </div>
      {/if}
    </div>
  </div>
</Dialog>

<Dialog
  bind:this={run_dialog}
  title="Run Eval"
  action_buttons={[
    {
      label: "Cancel",
      isCancel: true,
    },
    {
      label: "Run Eval",
      action: run_eval,
      isPrimary: true,
    },
  ]}
>
  <div class="flex flex-col gap-2 font-light mt-4">
    <div>Run this eval with the selected configuration?</div>
    <div>
      Runs in the background — you can leave this page and check progress later
      in the Jobs panel.
    </div>
    <Warning
      warning_color="warning"
      warning_message="This may use considerable compute/credits."
      tight={true}
    />
  </div>
</Dialog>
