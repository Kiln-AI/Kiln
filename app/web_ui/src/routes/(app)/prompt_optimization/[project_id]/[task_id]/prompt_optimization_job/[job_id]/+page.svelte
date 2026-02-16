<script lang="ts">
  import AppPage from "../../../../../app_page.svelte"
  import { page } from "$app/stores"
  import { onMount, onDestroy } from "svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import type { PromptOptimizationJob, Eval, TaskRunConfig } from "$lib/types"
  import { formatDate } from "$lib/utils/formatters"
  import Output from "$lib/ui/output.svelte"
  import PropertyList from "$lib/ui/property_list.svelte"
  import type { UiProperty } from "$lib/ui/property_list"
  import { get_task_composite_id } from "$lib/stores"
  import {
    load_task_run_configs,
    run_configs_by_task_composite_id,
  } from "$lib/stores/run_configs_store"
  import { prompt_link } from "$lib/utils/link_builder"

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!
  $: prompt_optimization_job_id = $page.params.job_id!

  let prompt_optimization_job: PromptOptimizationJob | null = null
  let prompt_optimization_job_error: KilnError | null = null
  let prompt_optimization_job_loading = true
  let polling_timer: ReturnType<typeof setTimeout> | null = null

  $: running =
    prompt_optimization_job?.latest_status === "pending" ||
    prompt_optimization_job?.latest_status === "running"

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
      get_prompt_optimization_job(false)
    }, 60000)
  }

  function stop_polling() {
    if (polling_timer) {
      clearInterval(polling_timer)
      polling_timer = null
    }
  }

  onMount(async () => {
    await Promise.all([
      load_task_run_configs(project_id, task_id),
      load_evals(),
    ])
    await get_prompt_optimization_job()
  })

  onDestroy(() => {
    stop_polling()
  })

  const get_prompt_optimization_job = async (show_loading = true) => {
    try {
      if (show_loading) {
        prompt_optimization_job_loading = true
        prompt_optimization_job_error = null
        prompt_optimization_job = null
      }

      const { data: prompt_optimization_job_response, error: get_error } =
        await client.GET(
          "/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/{prompt_optimization_job_id}",
          {
            params: {
              path: {
                project_id,
                task_id,
                prompt_optimization_job_id,
              },
            },
          },
        )

      if (get_error) {
        throw get_error
      }
      prompt_optimization_job = prompt_optimization_job_response
      build_properties()
    } catch (error) {
      if (show_loading) {
        prompt_optimization_job_error = createKilnError(error)
      }
    } finally {
      if (show_loading) {
        prompt_optimization_job_loading = false
      }
    }
  }

  let properties: UiProperty[] = []
  let evals: Eval[] = []

  $: run_configs =
    $run_configs_by_task_composite_id[
      get_task_composite_id(project_id, task_id)
    ] || []

  $: target_run_config_page_link = `/optimize/${project_id}/${task_id}/run_config/${prompt_optimization_job?.target_run_config_id}`
  $: created_run_config_page_link = `/optimize/${project_id}/${task_id}/run_config/${prompt_optimization_job?.created_run_config_id}`

  $: is_terminal =
    prompt_optimization_job?.latest_status === "succeeded" ||
    prompt_optimization_job?.latest_status === "failed" ||
    prompt_optimization_job?.latest_status === "cancelled"

  $: view_prompt_action_buttons = (() => {
    const buttons: { label: string; href?: string; handler?: () => void }[] = []
    if (prompt_optimization_job?.created_prompt_id) {
      const href = prompt_link(
        project_id,
        task_id,
        prompt_optimization_job.created_prompt_id,
      )
      if (href) {
        buttons.push({ label: "View Optimized Prompt", href })
      }
    }
    if (!is_terminal) {
      buttons.push({
        label: "Refresh Status",
        handler: () => get_prompt_optimization_job(false),
      })
    }
    return buttons
  })()

  async function load_evals() {
    try {
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/evals",
        {
          params: {
            path: { project_id, task_id },
          },
        },
      )
      if (error) {
        throw error
      }
      evals = data || []
    } catch {
      evals = []
    }
  }

  function get_run_config_name(
    run_config_id: string,
    run_configs: TaskRunConfig[],
  ): string {
    const config = run_configs.find((rc) => rc.id === run_config_id)
    return config?.name || run_config_id
  }

  function get_eval_name(eval_id: string): string {
    const found = evals.find((e) => e.id === eval_id)
    return found?.name || eval_id
  }

  function eval_link(eval_id: string): string {
    return `/specs/${project_id}/${task_id}/legacy/${encodeURIComponent(eval_id)}`
  }

  function format_status(s: string): string {
    if (s === "succeeded") return "Complete"
    return s.charAt(0).toUpperCase() + s.slice(1)
  }

  function build_properties() {
    if (!prompt_optimization_job) {
      properties = []
      return
    }

    let base: UiProperty[] = [
      {
        name: "Status",
        value: format_status(prompt_optimization_job.latest_status),
      },
      { name: "ID", value: prompt_optimization_job.id || "" },
      { name: "Name", value: prompt_optimization_job.name },
      {
        name: "Target Run Config",
        value: get_run_config_name(
          prompt_optimization_job.target_run_config_id,
          run_configs,
        ),
        link: target_run_config_page_link,
      },
    ]

    if (prompt_optimization_job.created_run_config_id) {
      base.push({
        name: "Optimized Run Config",
        value: get_run_config_name(
          prompt_optimization_job.created_run_config_id,
          run_configs,
        ),
        link: created_run_config_page_link,
      })
    }

    if (
      prompt_optimization_job.eval_ids &&
      prompt_optimization_job.eval_ids.length > 0
    ) {
      base.push({
        name: "Evals",
        value: prompt_optimization_job.eval_ids.map((id) => get_eval_name(id)),
        links: prompt_optimization_job.eval_ids.map((id) => eval_link(id)),
        badge: true,
      })
    } else {
      base.push({ name: "Evals", value: "None" })
    }

    base.push(
      ...[
        {
          name: "Created At",
          value: prompt_optimization_job.created_at
            ? formatDate(prompt_optimization_job.created_at)
            : "",
        },
        { name: "Created By", value: prompt_optimization_job.created_by || "" },
      ].filter((p) => !!p.value),
    )

    properties = base
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Prompt Optimizer Job"
    subtitle={prompt_optimization_job_loading
      ? undefined
      : `Name: ${prompt_optimization_job?.name}`}
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
        href: `/prompt_optimization/${project_id}/${task_id}`,
      },
    ]}
    action_buttons={view_prompt_action_buttons}
  >
    {#if prompt_optimization_job_loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if prompt_optimization_job_error || !prompt_optimization_job}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="text-error text-sm">
          {prompt_optimization_job_error?.getMessage() ||
            "An unknown error occurred"}
        </div>
      </div>
    {:else}
      <div class="flex flex-col xl:flex-row gap-8 xl:gap-16 mb-10">
        {#if prompt_optimization_job.optimized_prompt}
          <div class="flex flex-col gap-1">
            <div class="flex flex-row justify-between items-center mb-4">
              <div class="text-xl font-bold">Optimized Prompt</div>
              {#if prompt_optimization_job.created_prompt_id}
                {@const created_prompt_href = prompt_link(
                  project_id,
                  task_id,
                  prompt_optimization_job.created_prompt_id,
                )}
                <div class="flex items-center text-gray-500 text-xs">
                  <a href={created_prompt_href} class="link">
                    View Prompt Details
                  </a>
                </div>
              {/if}
            </div>
            <Output raw_output={prompt_optimization_job.optimized_prompt} />
          </div>
        {/if}
        <div class="max-w-md">
          <PropertyList title="Details" {properties} />
        </div>
      </div>
    {/if}
  </AppPage>
</div>
