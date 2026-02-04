<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import OptimizeCard from "$lib/ui/optimize_card.svelte"
  import { get_optimizers } from "./optimizers"
  import { page } from "$app/stores"
  import SettingsHeader from "$lib/ui/settings_header.svelte"
  import { onMount } from "svelte"
  import {
    available_tools,
    get_task_composite_id,
    load_available_prompts,
    load_available_tools,
    load_model_info,
    load_task,
    model_info,
  } from "$lib/stores"
  import {
    load_task_run_configs,
    run_configs_by_task_composite_id,
  } from "$lib/stores/run_configs_store"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import type { Task, TaskRunConfig } from "$lib/types"
  import PropertyList from "$lib/ui/property_list.svelte"
  import { prompts_by_task_composite_id } from "$lib/stores/prompts_store"
  import { getRunConfigUiProperties } from "$lib/utils/run_config_formatters"
  import type { UiProperty } from "$lib/ui/property_list"

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!
  $: optimizers = get_optimizers(project_id, task_id)

  let loading = true
  let error: KilnError | null = null
  let task: Task | null = null
  let default_run_config: TaskRunConfig | null = null
  let default_run_config_properties: UiProperty[] | null = null

  onMount(async () => {
    loading = true
    try {
      await Promise.all([
        load_model_info(),
        load_available_tools(project_id),
        load_available_prompts(),
      ])
      task = await load_task(project_id, task_id)
      if (!task) {
        throw new Error("Task not found")
      }
      if (task.default_run_config_id) {
        await load_task_run_configs(project_id, task_id)
        const run_configs =
          $run_configs_by_task_composite_id[
            get_task_composite_id(project_id, task_id)
          ]
        default_run_config =
          run_configs.find(
            (run_config) => run_config.id === task?.default_run_config_id,
          ) ?? null
      }
    } catch (e) {
      error = createKilnError(e)
    } finally {
      loading = false
    }
  })

  $: task_prompts =
    $prompts_by_task_composite_id[get_task_composite_id(project_id, task_id)] ||
    null

  $: default_run_config_properties = default_run_config
    ? getRunConfigUiProperties(
        project_id,
        task_id,
        default_run_config,
        $model_info,
        task_prompts,
        $available_tools,
      )
    : null
</script>

<AppPage
  title="Optimize"
  subtitle="Optimize your current task for better performance with prompts, models and more."
  sub_subtitle="Read the Docs"
  sub_subtitle_link="https://docs.kiln.tech/docs/optimize"
>
  {#if loading}
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else if error}
    <div class="text-error text-sm">
      {error?.getMessage() || "An unknown error occurred"}
    </div>
  {:else}
    <div class="flex flex-col gap-6">
      <SettingsHeader title="Default Run Configuration" />
      {#if default_run_config_properties}
        <div class="px-4 flex flex-col gap-2">
          <PropertyList properties={default_run_config_properties} />
        </div>
      {/if}
      <SettingsHeader title="Optimization Techniques" />
      <div
        class="grid gap-6"
        style="grid-template-columns: repeat(auto-fit, minmax(300px, 350px));"
      >
        {#each optimizers as optimizer}
          <OptimizeCard
            title={optimizer.title}
            description={optimizer.description}
            cost={optimizer.cost}
            effort={optimizer.effort}
            onClick={optimizer.onClick}
          />
        {/each}
      </div>
      <SettingsHeader title="Manage Run Configurations" />
      <!-- TODO: Add run configurations table with buttons like promote to default, edit, delete, clone, optimize, etc. -->
      <!-- Fine tune models can be shown here as "virtual" entries with prompt: "missing" or something etc. GEPA prompts can appear with model "missing" or there can be an unfinished tag or something. -->
      <!-- All Optimization Techniques should create a new run configuration at the end using the default? -->
    </div>
  {/if}
</AppPage>
