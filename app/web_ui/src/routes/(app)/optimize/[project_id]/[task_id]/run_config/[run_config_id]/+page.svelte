<script lang="ts">
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import {
    available_tools,
    get_task_composite_id,
    load_available_models,
    load_available_tools,
    load_model_info,
    load_task,
    model_info,
  } from "$lib/stores"
  import {
    load_task_prompts,
    prompts_by_task_composite_id,
  } from "$lib/stores/prompts_store"
  import {
    load_task_run_configs,
    run_configs_by_task_composite_id,
  } from "$lib/stores/run_configs_store"
  import type { Task, TaskRunConfig } from "$lib/types"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import { getRunConfigUiProperties } from "$lib/utils/run_config_formatters"
  import { onMount } from "svelte"
  import AppPage from "../../../../../app_page.svelte"
  import EditDialog from "$lib/ui/edit_dialog.svelte"
  import PropertyList from "$lib/ui/property_list.svelte"
  import CreateNewRunConfigDialog from "$lib/ui/run_config_component/create_new_run_config_dialog.svelte"

  import { agentInfo } from "$lib/agent"
  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!
  $: run_config_id = $page.params.run_config_id!
  $: agentInfo.set({
    name: "Run Config Detail",
    description: `Run configuration detail for config ID ${run_config_id} in project ID ${project_id}, task ID ${task_id}. Config name: ${run_config?.name ?? "[loading]"}. Shows model, prompt, and tool settings.`,
  })

  let run_config: TaskRunConfig | null = null
  let task: Task | null = null
  let error: KilnError | null = null
  let loading = true

  let edit_dialog: EditDialog | null = null
  let create_run_config_dialog: CreateNewRunConfigDialog | null = null

  onMount(async () => {
    try {
      load_available_tools(project_id)
      await Promise.all([load_model_info(), load_available_models()])
      await Promise.all([
        load_task_prompts(project_id, task_id),
        load_task_run_configs(project_id, task_id),
      ])
      task = await load_task(project_id, task_id)
    } catch (e) {
      error = createKilnError(e)
    }
    loading = false
  })

  $: run_config =
    $run_configs_by_task_composite_id[
      get_task_composite_id(project_id, task_id)
    ]?.find((config) => config.id === run_config_id) || null

  $: task_prompts =
    $prompts_by_task_composite_id[get_task_composite_id(project_id, task_id)] ||
    null

  $: properties = run_config
    ? getRunConfigUiProperties(
        project_id,
        task_id,
        run_config,
        $model_info,
        task_prompts,
        $available_tools,
      )
    : null

  function handleClone() {
    if (run_config) {
      create_run_config_dialog?.showClone(run_config)
    }
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Run Configuration"
    subtitle={run_config?.name || "Untitled"}
    breadcrumbs={[
      {
        label: "Optimize",
        href: `/optimize/${project_id}/${task_id}`,
      },
    ]}
    action_buttons={[
      {
        label: "Clone",
        disabled: loading || error !== null || !run_config,
        handler: handleClone,
      },
      {
        label: "Edit",
        disabled: loading || error !== null,
        handler: () => {
          edit_dialog?.show()
        },
      },
    ]}
  >
    {#if loading}
      <div class="flex justify-center items-center h-full">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if error}
      <div class="text-error text-sm">
        {error.getMessage() || "An unknown error occurred"}
      </div>
    {:else if !properties}
      <div class="text-error text-sm">
        Failed to load run config, please refresh the page and try again.
      </div>
    {:else}
      <PropertyList {properties} />
    {/if}
  </AppPage>
</div>

<EditDialog
  bind:this={edit_dialog}
  name="Run Configuration"
  patch_url={`/api/projects/${project_id}/tasks/${task_id}/run_configs/${run_config_id}`}
  fields={[
    {
      label: "Run Configuration Name",
      description: "A name to identify this run config.",
      api_name: "name",
      value: run_config?.name || "",
      input_type: "input",
      max_length: 120,
    },
  ]}
/>

<CreateNewRunConfigDialog
  bind:this={create_run_config_dialog}
  {project_id}
  {task}
  new_run_config_created={async (new_config) => {
    await load_task_run_configs(project_id, task_id, true)
    goto(`/optimize/${project_id}/${task_id}/run_config/${new_config.id}`)
  }}
/>
