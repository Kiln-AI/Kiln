<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import EmptyGepa from "./empty_gepa.svelte"
  import { client } from "$lib/api_client"
  import type { GepaJob } from "$lib/types"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { goto } from "$app/navigation"
  import { page } from "$app/stores"
  import { formatDate } from "$lib/utils/formatters"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id
  $: is_empty = !gepa_jobs || gepa_jobs.length == 0

  let gepa_jobs: GepaJob[] | null = null
  let gepa_jobs_error: KilnError | null = null
  let gepa_jobs_loading = true

  onMount(async () => {
    get_gepa_jobs()
  })

  async function get_gepa_jobs() {
    try {
      gepa_jobs_loading = true
      if (!project_id || !task_id) {
        throw new Error("Project or task ID not set.")
      }
      const { data: gepa_jobs_response, error: get_error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/gepa_jobs",
        {
          params: {
            path: {
              project_id,
              task_id,
            },
            query: {
              update_status: true,
            },
          },
        },
      )
      if (get_error) {
        throw get_error
      }
      const sorted_gepa_jobs = gepa_jobs_response.sort((a, b) => {
        return (
          new Date(b.created_at || "").getTime() -
          new Date(a.created_at || "").getTime()
        )
      })
      gepa_jobs = sorted_gepa_jobs
    } catch (e) {
      if (e instanceof Error && e.message.includes("Load failed")) {
        gepa_jobs_error = new KilnError(
          "Could not load GEPA jobs. This task may belong to a project you don't have access to.",
          null,
        )
      } else {
        gepa_jobs_error = createKilnError(e)
      }
    } finally {
      gepa_jobs_loading = false
    }
  }

  const status_map: Record<string, string> = {
    pending: "Pending",
    running: "Running",
    succeeded: "Succeeded",
    failed: "Failed",
    cancelled: "Cancelled",
  }
  function format_status(status: string) {
    return status_map[status] || status
  }

  function format_token_budget(budget: string): string {
    return budget.charAt(0).toUpperCase() + budget.slice(1)
  }
</script>

<AppPage
  title="GEPA Jobs"
  subtitle="Generate Eval Prompts and Augmented data jobs for the current task."
  action_buttons={is_empty
    ? []
    : [
        {
          label: "Create GEPA Job",
          href: `/gepa/${project_id}/${task_id}/create_gepa`,
          primary: true,
        },
      ]}
>
  {#if gepa_jobs_loading}
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else if is_empty}
    <div class="flex flex-col items-center justify-center min-h-[60vh]">
      <EmptyGepa {project_id} {task_id} />
    </div>
  {:else if gepa_jobs}
    <div class="overflow-x-auto rounded-lg border">
      <table class="table">
        <thead>
          <tr>
            <th> Name </th>
            <th> Token Budget </th>
            <th> Status </th>
            <th> Created At </th>
          </tr>
        </thead>
        <tbody>
          {#each gepa_jobs as gepa_job}
            <tr
              class="hover cursor-pointer"
              on:click={() => {
                goto(`/gepa/${project_id}/${task_id}/gepa_job/${gepa_job.id}`)
              }}
            >
              <td> {gepa_job.name} </td>
              <td> {format_token_budget(gepa_job.token_budget)} </td>
              <td>
                {#if gepa_job.latest_status === "pending" || gepa_job.latest_status === "running"}
                  <span class="loading loading-spinner mr-2 h-[14px] w-[14px]"
                  ></span>
                {/if}
                {format_status(gepa_job.latest_status)}
              </td>
              <td> {formatDate(gepa_job.created_at)} </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {:else if gepa_jobs_error}
    <div
      class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
    >
      <div class="font-medium">Error Loading GEPA Jobs</div>
      <div class="text-error text-sm">
        {gepa_jobs_error.getMessage() || "An unknown error occurred"}
      </div>
    </div>
  {/if}
</AppPage>
