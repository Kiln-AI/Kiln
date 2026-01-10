<script lang="ts">
  import AppPage from "../../../../../app_page.svelte"
  import { page } from "$app/stores"
  import { onMount } from "svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id
  $: job_id = $page.params.job_id

  interface JobStatusResponse {
    job_id: string
    status: "pending" | "running" | "succeeded" | "failed" | "cancelled"
  }

  let job_status: JobStatusResponse | null = null
  let job_status_error: KilnError | null = null
  let job_status_loading = true

  $: running =
    job_status?.status === "pending" || job_status?.status === "running"

  onMount(async () => {
    get_job_status()
  })

  const get_job_status = async () => {
    try {
      job_status_loading = true
      job_status_error = null
      job_status = null

      const { data: status_response, error: get_error } = await client.GET(
        "/api/gepa_jobs/{job_id}/status",
        {
          params: {
            path: {
              job_id,
            },
          },
        },
      )

      if (get_error) {
        throw get_error
      }
      job_status = status_response
    } catch (error) {
      job_status_error = createKilnError(error)
    } finally {
      job_status_loading = false
    }
  }

  type Property = {
    name: string
    value: string | null | undefined
  }

  $: properties = job_status
    ? ([
        { name: "Job ID", value: job_status.job_id },
        {
          name: "Status",
          value:
            job_status.status.charAt(0).toUpperCase() +
            job_status.status.slice(1),
        },
      ] as Property[])
    : []
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="GEPA Job"
    subtitle={job_status_loading ? undefined : `Job ID: ${job_status?.job_id}`}
    breadcrumbs={[
      {
        label: "Tasks",
        href: `/tasks/${project_id}`,
      },
    ]}
  >
    {#if job_status_loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if job_status_error || !job_status}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="font-medium">Error Loading GEPA Job</div>
        <div class="text-error text-sm">
          {job_status_error?.getMessage() || "An unknown error occurred"}
        </div>
      </div>
    {:else}
      <div class="flex flex-col xl:flex-row gap-8 xl:gap-16 mb-10">
        <div class="grow flex flex-col gap-4">
          <div class="text-xl font-bold">Details</div>
          <div
            class="grid grid-cols-[auto,1fr] gap-y-4 gap-x-4 text-sm 2xl:text-base"
          >
            {#each properties as property}
              <div class="flex items-center">{property.name}</div>
              <div class="flex items-center text-gray-500">
                {property.value}
              </div>
            {/each}
          </div>
        </div>

        <div class="grow flex flex-col gap-4 min-w-[400px]">
          <div class="text-xl font-bold">Status</div>
          <div
            class="grid grid-cols-[auto,1fr] gap-y-4 gap-x-4 text-sm 2xl:text-base"
          >
            <div class="flex items-center">Status</div>
            <div class="flex items-center text-gray-500">
              {#if running}
                <span class="loading loading-spinner mr-2 h-[14px] w-[14px]"
                ></span>
              {/if}
              {job_status.status.charAt(0).toUpperCase() +
                job_status.status.slice(1)}
              <button class="link ml-2 font-medium" on:click={get_job_status}>
                Refresh Status
              </button>
            </div>
          </div>
        </div>
      </div>
    {/if}
  </AppPage>
</div>
