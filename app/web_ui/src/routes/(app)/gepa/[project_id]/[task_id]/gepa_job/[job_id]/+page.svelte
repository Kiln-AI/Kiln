<script lang="ts">
  import AppPage from "../../../../../app_page.svelte"
  import { page } from "$app/stores"
  import { onMount, onDestroy } from "svelte"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import type { GepaJob } from "$lib/types"
  import { formatDate } from "$lib/utils/formatters"
  import Output from "$lib/ui/output.svelte"
  import { get_task_composite_id } from "$lib/stores"
  import {
    load_task_run_configs,
    run_configs_by_task_composite_id,
  } from "$lib/stores/run_configs_store"
  import { prompt_link } from "$lib/utils/link_builder"
  import { load_gepa_job } from "$lib/stores/gepa_store"

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!
  $: gepa_job_id = $page.params.job_id!

  let gepa_job: GepaJob | null = null
  let gepa_job_error: KilnError | null = null
  let gepa_job_loading = true
  let polling_timer: ReturnType<typeof setTimeout> | null = null

  $: running =
    gepa_job?.latest_status === "pending" ||
    gepa_job?.latest_status === "running"

  // Set up polling when running state changes
  $: {
    if (running && !polling_timer) {
      start_polling()
    } else if (!running && polling_timer) {
      stop_polling()
    }
  }

  function start_polling() {
    stop_polling()
    polling_timer = setInterval(() => {
      get_gepa_job(false)
    }, 60000)
  }

  function stop_polling() {
    if (polling_timer) {
      clearInterval(polling_timer)
      polling_timer = null
    }
  }

  onMount(async () => {
    await load_task_run_configs(project_id, task_id)
    await get_gepa_job()
  })

  onDestroy(() => {
    stop_polling()
  })

  const get_gepa_job = async (show_loading = true) => {
    try {
      if (show_loading) {
        gepa_job_loading = true
        gepa_job_error = null
        gepa_job = null
      }

      gepa_job = await load_gepa_job(project_id, task_id, gepa_job_id)
      build_properties()
    } catch (error) {
      if (show_loading) {
        gepa_job_error = createKilnError(error)
      }
    } finally {
      if (show_loading) {
        gepa_job_loading = false
      }
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

  $: view_prompt_action_buttons = gepa_job?.created_prompt_id
    ? (() => {
        const href = prompt_link(
          project_id,
          task_id,
          gepa_job!.created_prompt_id!,
        )
        return href ? [{ label: "View Optimized Prompt", href }] : []
      })()
    : []

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
          { light: "Low", medium: "Medium", heavy: "High" }[
            gepa_job.token_budget
          ] || gepa_job.token_budget,
      },
      {
        name: "Target Run Config",
        value: get_run_config_name(gepa_job.target_run_config_id),
      },
      {
        name: "Eval IDs",
        value:
          gepa_job.eval_ids && gepa_job.eval_ids.length > 0
            ? gepa_job.eval_ids.join(", ")
            : "None",
      },
      { name: "Created At", value: formatDate(gepa_job.created_at) },
      { name: "Created By", value: gepa_job.created_by },
    ]
    properties = properties.filter((property) => !!property.value)
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Prompt Optimizer Job"
    subtitle={gepa_job_loading ? undefined : `Name: ${gepa_job?.name}`}
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/prompts/automatic-prompt-optimizer"
    breadcrumbs={[
      {
        label: "Optimize",
        href: `/optimize/${project_id}/${task_id}`,
      },
      {
        label: "Prompts",
        href: `/prompts/${project_id}/${task_id}`,
      },
      {
        label: "Optimizer Jobs",
        href: `/gepa/${project_id}/${task_id}`,
      },
    ]}
    action_buttons={view_prompt_action_buttons}
  >
    {#if gepa_job_loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if gepa_job_error || !gepa_job}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="font-medium">
          Error Loading Kiln Prompt Optimization Job
        </div>
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
              <button
                class="link ml-2 font-medium"
                on:click={() => get_gepa_job(false)}
              >
                Reload Status
              </button>
            </div>

            {#if gepa_job.created_prompt_id}
              {@const created_prompt_href = prompt_link(
                project_id,
                task_id,
                gepa_job.created_prompt_id,
              )}
              {#if created_prompt_href}
                <div class="flex items-center">Optimized Prompt</div>
                <div class="flex items-center text-gray-500">
                  <a href={created_prompt_href} class="link"> View Prompt </a>
                </div>
              {/if}
            {/if}

            {#if gepa_job.created_run_config_id}
              <div class="flex items-center">Generated Run Config</div>
              <div class="flex items-center text-gray-500">
                {get_run_config_name(gepa_job.created_run_config_id)} (ID:
                {gepa_job.created_run_config_id})
              </div>
            {/if}
          </div>
        </div>
      </div>
    {/if}
  </AppPage>
</div>
