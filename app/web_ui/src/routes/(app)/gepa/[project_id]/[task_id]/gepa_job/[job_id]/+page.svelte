<script lang="ts">
  import AppPage from "../../../../../app_page.svelte"
  import { page } from "$app/stores"
  import { onMount } from "svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import type { GepaJob } from "$lib/types"
  import { formatDate } from "$lib/utils/formatters"
  import Output from "$lib/ui/output.svelte"
  import { get_task_composite_id } from "$lib/stores"
  import {
    load_task_run_configs,
    run_configs_by_task_composite_id,
  } from "$lib/stores/run_configs_store"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id
  $: gepa_job_id = $page.params.job_id

  let gepa_job: GepaJob | null = null
  let gepa_job_error: KilnError | null = null
  let gepa_job_loading = true

  $: running =
    gepa_job?.latest_status === "pending" ||
    gepa_job?.latest_status === "running"

  onMount(async () => {
    await load_task_run_configs(project_id, task_id)
    get_gepa_job()
  })

  const get_gepa_job = async () => {
    try {
      gepa_job_loading = true
      gepa_job_error = null
      gepa_job = null

      const { data: gepa_job_response, error: get_error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/gepa_jobs/{gepa_job_id}",
        {
          params: {
            path: {
              project_id,
              task_id,
              gepa_job_id,
            },
          },
        },
      )

      if (get_error) {
        throw get_error
      }
      gepa_job = gepa_job_response
      build_properties()
    } catch (error) {
      gepa_job_error = createKilnError(error)
    } finally {
      gepa_job_loading = false
    }
  }

  type Property = {
    name: string
    value: string | null | undefined
    link?: string
  }

  let properties: Property[] = []

  $: run_configs =
    $run_configs_by_task_composite_id[
      get_task_composite_id(project_id, task_id)
    ] || []

  function get_run_config_name(run_config_id: string): string {
    const config = run_configs.find((rc) => rc.id === run_config_id)
    return config?.name || run_config_id
  }

  function build_properties() {
    if (!gepa_job) {
      properties = []
      return
    }
    properties = [
      { name: "Kiln ID", value: gepa_job.id },
      { name: "Name", value: gepa_job.name },
      { name: "Description", value: gepa_job.description },
      { name: "Remote Job ID", value: gepa_job.job_id },
      {
        name: "Token Budget",
        value:
          gepa_job.token_budget.charAt(0).toUpperCase() +
          gepa_job.token_budget.slice(1),
      },
      {
        name: "Target Run Config",
        value: get_run_config_name(gepa_job.target_run_config_id),
      },
      { name: "Created At", value: formatDate(gepa_job.created_at) },
      { name: "Created By", value: gepa_job.created_by },
    ]
    properties = properties.filter((property) => !!property.value)
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="GEPA Job"
    subtitle={gepa_job_loading ? undefined : `Name: ${gepa_job?.name}`}
    breadcrumbs={[
      {
        label: "GEPA Jobs",
        href: `/gepa/${project_id}/${task_id}`,
      },
    ]}
    action_buttons={gepa_job?.created_prompt_id
      ? [
          {
            label: "View Generated Prompt",
            href: `/prompts/${project_id}/${task_id}/saved/${gepa_job.created_prompt_id}`,
          },
        ]
      : []}
  >
    {#if gepa_job_loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if gepa_job_error || !gepa_job}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="font-medium">Error Loading GEPA Job</div>
        <div class="text-error text-sm">
          {gepa_job_error?.getMessage() || "An unknown error occurred"}
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
                {#if property.link}
                  <a href={property.link} target="_blank" class="link">
                    {property.value}
                  </a>
                {:else}
                  {property.value}
                {/if}
              </div>
            {/each}
          </div>

          {#if gepa_job.optimized_prompt}
            <div class="text-xl font-bold mt-8">Optimized Prompt</div>
            <Output raw_output={gepa_job.optimized_prompt} />
          {/if}
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
              {gepa_job.latest_status.charAt(0).toUpperCase() +
                gepa_job.latest_status.slice(1)}
              <button class="link ml-2 font-medium" on:click={get_gepa_job}>
                Reload Status
              </button>
            </div>

            {#if gepa_job.created_prompt_id}
              <div class="flex items-center">Generated Prompt</div>
              <div class="flex items-center text-gray-500">
                <a
                  href={`/prompts/${project_id}/${task_id}/saved/${gepa_job.created_prompt_id}`}
                  class="link"
                >
                  View Prompt
                </a>
              </div>
            {/if}
          </div>
        </div>
      </div>
    {/if}
  </AppPage>
</div>
