<script lang="ts">
  import AppPage from "../app_page.svelte"
  import JobsTable from "$lib/components/jobs_table.svelte"
  import { create_job } from "$lib/stores/jobs_api"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { agentInfo } from "$lib/agent"
  import { ui_state } from "$lib/stores"

  agentInfo.set({
    name: "Background Jobs",
    description:
      "Background job panel. Lists jobs with status, progress, and lifecycle controls.",
  })

  let action_error: KilnError | null = null
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

  $: action_buttons = [
    {
      label: creating_test_job ? "Starting…" : "Start test job",
      handler: start_test_job,
      primary: true,
      loading: creating_test_job,
      disabled: creating_test_job,
    },
  ]
</script>

<AppPage
  title="Jobs (temporary test page)"
  subtitle="This page is a placeholder test to trigger jobs - will be removed before merging"
  {action_buttons}
>
  {#if action_error}
    <div role="alert" class="alert alert-error text-sm mb-4">
      <span>{action_error.getMessage() || "An action failed."}</span>
    </div>
  {/if}

  <JobsTable />
</AppPage>
