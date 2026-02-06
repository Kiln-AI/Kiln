<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import OptimizeCard from "$lib/ui/optimize_card.svelte"
  import { get_optimizers } from "./optimizers"
  import { page } from "$app/stores"
  import { onMount, tick } from "svelte"
  import {
    available_tools,
    get_task_composite_id,
    load_available_tools,
    load_model_info,
    load_task,
    model_info,
  } from "$lib/stores"
  import { load_task_prompts } from "$lib/stores/prompts_store"
  import {
    load_task_run_configs,
    run_configs_by_task_composite_id,
  } from "$lib/stores/run_configs_store"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import type { Task, TaskRunConfig } from "$lib/types"
  import { prompts_by_task_composite_id } from "$lib/stores/prompts_store"
  import {
    getDetailedModelName,
    getRunConfigPromptDisplayName,
  } from "$lib/utils/run_config_formatters"
  import { formatDate } from "$lib/utils/formatters"
  import { get_tools_property_info } from "$lib/stores/tools_store"
  import { goto } from "$app/navigation"
  import TableButton from "../../../generate/[project_id]/[task_id]/table_button.svelte"
  import RunConfigDetailsDialog from "$lib/ui/run_config_component/run_config_details_dialog.svelte"
  import CreateNewRunConfigDialog from "$lib/ui/run_config_component/create_new_run_config_dialog.svelte"
  import { load_task_run_configs as reload_run_configs } from "$lib/stores/run_configs_store"

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!
  $: optimizers = get_optimizers(project_id, task_id)

  let loading = true
  let error: KilnError | null = null
  let task: Task | null = null

  type SortableColumn = "name" | "prompt" | "model" | "created_at"
  let sortColumn: SortableColumn = "created_at"
  let sortDirection: "asc" | "desc" = "desc"

  let selected_run_config: TaskRunConfig | null = null
  let run_config_details_dialog: RunConfigDetailsDialog | null = null
  let create_run_config_dialog: CreateNewRunConfigDialog | null = null

  const MAX_SELECTIONS = 6
  let select_mode: boolean = false
  let selected_run_configs: Set<string> = new Set()

  function toggle_selection(config_id: string) {
    if (selected_run_configs.has(config_id)) {
      selected_run_configs.delete(config_id)
    } else if (selected_run_configs.size < MAX_SELECTIONS) {
      selected_run_configs.add(config_id)
    }
    selected_run_configs = selected_run_configs
  }

  function handleCompare() {
    if (selected_run_configs.size === 0) return
    const modelIds = Array.from(selected_run_configs).join(",")
    goto(
      `/specs/${project_id}/${task_id}/compare?models=${modelIds}&columns=${selected_run_configs.size}&from=optimize`,
    )
  }

  function cancelSelection() {
    select_mode = false
    selected_run_configs = new Set()
  }

  async function handleNewRunConfigCreated() {
    await reload_run_configs(project_id, task_id, true)
  }

  onMount(async () => {
    loading = true
    try {
      await Promise.all([
        load_model_info(),
        load_available_tools(project_id),
        load_task_prompts(project_id, task_id),
        load_task_run_configs(project_id, task_id),
      ])
      task = await load_task(project_id, task_id)
      if (!task) {
        throw new Error("Task not found")
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

  $: run_configs =
    $run_configs_by_task_composite_id[
      get_task_composite_id(project_id, task_id)
    ] || []

  $: default_run_config_id = task?.default_run_config_id

  $: sorted_run_configs = sortRunConfigs(
    run_configs,
    sortColumn,
    sortDirection,
    default_run_config_id,
  )

  function sortRunConfigs(
    configs: TaskRunConfig[],
    column: SortableColumn,
    direction: "asc" | "desc",
    default_id: string | null | undefined,
  ): TaskRunConfig[] {
    if (!configs || configs.length === 0) return []

    return [...configs].sort((a, b) => {
      if (default_id) {
        if (a.id === default_id) return -1
        if (b.id === default_id) return 1
      }

      let aValue: string | number | Date | null | undefined
      let bValue: string | number | Date | null | undefined

      switch (column) {
        case "name":
          aValue = (a.name || "").toLowerCase()
          bValue = (b.name || "").toLowerCase()
          break
        case "prompt":
          aValue = getRunConfigPromptDisplayName(a, task_prompts).toLowerCase()
          bValue = getRunConfigPromptDisplayName(b, task_prompts).toLowerCase()
          break
        case "model":
          aValue = getDetailedModelName(a, $model_info).toLowerCase()
          bValue = getDetailedModelName(b, $model_info).toLowerCase()
          break
        case "created_at":
          aValue = a.created_at ? new Date(a.created_at).getTime() : 0
          bValue = b.created_at ? new Date(b.created_at).getTime() : 0
          break
        default:
          return 0
      }

      if (!aValue && aValue !== 0) return direction === "asc" ? 1 : -1
      if (!bValue && bValue !== 0) return direction === "asc" ? -1 : 1

      if (aValue < bValue) return direction === "asc" ? -1 : 1
      if (aValue > bValue) return direction === "asc" ? 1 : -1
      return 0
    })
  }

  function handleSort(column: SortableColumn) {
    if (sortColumn === column) {
      sortDirection = sortDirection === "asc" ? "desc" : "asc"
    } else {
      sortColumn = column
      sortDirection = "desc"
    }
  }

  function getToolsDisplay(config: TaskRunConfig): {
    value: string | string[]
    links: (string | null)[] | undefined
  } {
    const tool_ids = config.run_config_properties.tools_config?.tools || []
    return $available_tools
      ? get_tools_property_info(tool_ids, project_id, $available_tools)
      : { value: "Loading...", links: undefined }
  }

  function handleRowClick(config: TaskRunConfig) {
    selected_run_config = config
    run_config_details_dialog?.show()
  }

  function handleClone(config: TaskRunConfig, event: Event) {
    event.stopPropagation()
    create_run_config_dialog?.showClone(config)
  }

  type TableColumn = {
    key: string
    label: string
    sortable: boolean
    sortKey?: SortableColumn
  }

  const tableColumns: TableColumn[] = [
    { key: "name", label: "Name", sortable: true, sortKey: "name" },
    { key: "prompt", label: "Prompt", sortable: true, sortKey: "prompt" },
    { key: "model", label: "Model", sortable: true, sortKey: "model" },
    { key: "tools", label: "Tools", sortable: false },
    {
      key: "created_at",
      label: "Date Created",
      sortable: true,
      sortKey: "created_at",
    },
  ]
</script>

<AppPage
  title="Optimize"
  subtitle="Optimize and compare different run configurations for your task."
  sub_subtitle="Read the Docs"
  sub_subtitle_link="https://docs.kiln.tech/docs/optimize"
  action_buttons={[
    {
      label: "Add Run Configuration",
      handler: () => create_run_config_dialog?.show(),
    },
  ]}
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
    <div class="flex flex-col gap-4">
      <div>
        <h2 class="text-lg font-medium text-gray-900">
          Optimization Strategies
        </h2>
        <p class="text-sm text-gray-500">
          Strategies for optimizing your task, highlighting tradeoffs between
          impact, cost efficiency, and simplicity.
        </p>
      </div>
      <div
        class="grid gap-6"
        style="grid-template-columns: repeat(auto-fit, minmax(300px, 350px));"
      >
        {#each optimizers as optimizer}
          <OptimizeCard
            title={optimizer.title}
            description={optimizer.description}
            metrics={optimizer.metrics}
            onClick={optimizer.on_click}
          />
        {/each}
      </div>
      <div class="flex flex-col sm:flex-row gap-4 sm:gap-8 mt-4">
        <div class="grow">
          <h2 class="text-lg font-medium text-gray-900">Run Configurations</h2>
          <div class="text-sm text-gray-500">
            Select one or more configurations to compare their evaluation
            results, or pick an optimization strategy below to create a new
            configuration from an existing one.
          </div>
        </div>
        <div class="flex flex-row items-center gap-3">
          {#if select_mode}
            <div class="font-light text-sm">
              {selected_run_configs.size} selected{#if selected_run_configs.size >= MAX_SELECTIONS}
                <span class="text-gray-400">{` (max)`}</span>
              {/if}
            </div>
            <button class="btn btn-mid" on:click={cancelSelection}>
              Cancel Selection
            </button>
          {:else}
            <button class="btn btn-mid" on:click={() => (select_mode = true)}>
              Select
            </button>
          {/if}
          {#if selected_run_configs.size > 0}
            <button class="btn btn-primary btn-mid" on:click={handleCompare}>
              Compare
            </button>
          {/if}
        </div>
      </div>
      {#if sorted_run_configs.length === 0}
        <div class="text-gray-500 rounded-lg border p-4 text-sm">
          No run configurations yet. Create one by clicking "Add Run
          Configuration" above.
        </div>
      {:else}
        <div class="overflow-auto max-h-96 rounded-lg border">
          <table class="table">
            <thead>
              <tr>
                {#if select_mode}
                  <th></th>
                {/if}
                {#each tableColumns as column}
                  {#if column.sortable && column.sortKey}
                    {@const sortKey = column.sortKey}
                    <th
                      on:click={() => handleSort(sortKey)}
                      class="hover:bg-base-200 cursor-pointer"
                    >
                      {column.label}
                      <span class="inline-block w-3 text-center">
                        {sortColumn === sortKey
                          ? sortDirection === "asc"
                            ? "▲"
                            : "▼"
                          : "\u200B"}
                      </span>
                    </th>
                  {:else}
                    <th>
                      {column.label}
                    </th>
                  {/if}
                {/each}
                <th></th>
              </tr>
            </thead>
            <tbody>
              {#each sorted_run_configs as config}
                {@const tools_info = getToolsDisplay(config)}
                {@const is_default = config.id === task?.default_run_config_id}
                {@const is_selected =
                  config.id && selected_run_configs.has(config.id)}
                <tr
                  class="{select_mode ? '' : 'hover'} cursor-pointer {is_default
                    ? 'bg-base-200'
                    : ''} {select_mode && is_selected ? 'bg-base-200' : ''}"
                  on:click={() => {
                    if (select_mode && config.id) {
                      toggle_selection(config.id)
                    } else {
                      handleRowClick(config)
                    }
                  }}
                >
                  {#if select_mode}
                    <td>
                      <input
                        type="checkbox"
                        class="checkbox checkbox-sm"
                        checked={is_selected || false}
                        disabled={!is_selected &&
                          selected_run_configs.size >= MAX_SELECTIONS}
                      />
                    </td>
                  {/if}
                  <td class="font-medium">
                    <div class="flex items-center gap-2">
                      {config.name || "Unnamed"}
                      {#if is_default}
                        <span class="badge badge-sm badge-primary">Default</span
                        >
                      {/if}
                    </div>
                  </td>
                  <td class="text-gray-500">
                    {getRunConfigPromptDisplayName(config, task_prompts)}
                  </td>
                  <td class="text-gray-500">
                    {getDetailedModelName(config, $model_info)}
                  </td>
                  <td class="text-gray-500">
                    {#if Array.isArray(tools_info.value)}
                      <div class="flex flex-wrap gap-1">
                        {#each tools_info.value as tool_name, i}
                          {@const link = tools_info.links?.[i]}
                          {#if link}
                            <a
                              href={link}
                              class="badge badge-outline hover:bg-base-200"
                              on:click|stopPropagation
                            >
                              {tool_name}
                            </a>
                          {:else}
                            <span class="badge badge-outline">{tool_name}</span>
                          {/if}
                        {/each}
                      </div>
                    {:else}
                      {tools_info.value}
                    {/if}
                  </td>
                  <td class="text-sm text-gray-500">
                    {formatDate(config.created_at)}
                  </td>
                  <td class="p-0" on:click|stopPropagation>
                    <div class="dropdown dropdown-end dropdown-hover">
                      <TableButton />
                      <!-- svelte-ignore a11y-no-noninteractive-tabindex -->
                      <ul
                        tabindex="0"
                        class="dropdown-content menu bg-base-100 rounded-box z-[1] w-52 p-2 shadow"
                      >
                        <li>
                          <button on:click={(e) => handleClone(config, e)}>
                            Clone
                          </button>
                        </li>
                      </ul>
                    </div>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
    </div>
  {/if}
</AppPage>

{#if selected_run_config}
  <RunConfigDetailsDialog
    bind:this={run_config_details_dialog}
    {project_id}
    {task_id}
    task_run_config={selected_run_config}
  />
{/if}

<CreateNewRunConfigDialog
  bind:this={create_run_config_dialog}
  {project_id}
  {task}
  new_run_config_created={handleNewRunConfigCreated}
/>
