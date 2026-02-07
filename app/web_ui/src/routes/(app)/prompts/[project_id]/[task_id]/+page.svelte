<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import { current_task, get_task_composite_id, load_task } from "$lib/stores"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import { formatDate } from "$lib/utils/formatters"
  import TableButton from "../../../generate/[project_id]/[task_id]/table_button.svelte"
  import Output from "$lib/ui/output.svelte"
  import {
    load_task_prompts,
    prompts_by_task_composite_id,
  } from "$lib/stores/prompts_store"
  import { onMount } from "svelte"
  import type { Task } from "$lib/types"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!

  let loading = true
  let error: KilnError | null = null
  let task: Task | null = null

  onMount(async () => {
    try {
      await load_task_prompts(project_id, task_id, true)
      task = await load_task(project_id, task_id)
    } catch (e) {
      error = createKilnError(e)
    } finally {
      loading = false
    }
  })

  $: task_prompts =
    $prompts_by_task_composite_id[get_task_composite_id(project_id, task_id)] ||
    null

  $: prompts = task_prompts?.prompts || []
  $: has_prompts = prompts.length > 0

  type SortableColumn = "name" | "type" | "created_at"
  let sortColumn: SortableColumn = "created_at"
  let sortDirection: "asc" | "desc" = "desc"

  function handleSort(column: SortableColumn) {
    if (sortColumn === column) {
      sortDirection = sortDirection === "asc" ? "desc" : "asc"
    } else {
      sortColumn = column
      sortDirection = "desc"
    }
  }

  function getPromptType(
    prompt_id: string,
  ): "Custom" | "Fine Tuning Prompt" | "Frozen Prompt" | "Unknown" {
    if (prompt_id.startsWith("id::")) return "Custom"
    if (prompt_id.startsWith("fine_tune_prompt::")) return "Fine Tuning Prompt"
    if (prompt_id.startsWith("task_run_config::")) return "Frozen Prompt"
    return "Unknown"
  }

  $: sorted_prompts = (() => {
    if (prompts.length === 0) return []
    return [...prompts].sort((a, b) => {
      let aValue: string | number
      let bValue: string | number
      switch (sortColumn) {
        case "name":
          aValue = (a.name || "").toLowerCase()
          bValue = (b.name || "").toLowerCase()
          break
        case "type":
          aValue = getPromptType(a.id).toLowerCase()
          bValue = getPromptType(b.id).toLowerCase()
          break
        case "created_at":
          aValue = a.created_at ? new Date(a.created_at).getTime() : 0
          bValue = b.created_at ? new Date(b.created_at).getTime() : 0
          break
        default:
          return 0
      }
      if (aValue < bValue) return sortDirection === "asc" ? -1 : 1
      if (aValue > bValue) return sortDirection === "asc" ? 1 : -1
      return 0
    })
  })()

  function handleSetBasePrompt(prompt_text: string) {
    sessionStorage.setItem("pending_base_prompt", prompt_text)
    goto(`/prompts/${project_id}/${task_id}/edit_base_prompt`)
  }

  type TableColumn = {
    key: string
    label: string
    sortable: boolean
    sortKey?: SortableColumn
  }

  const tableColumns: TableColumn[] = [
    { key: "name", label: "Name", sortable: true, sortKey: "name" },
    { key: "type", label: "Type", sortable: true, sortKey: "type" },
    { key: "prompt_preview", label: "Prompt Preview", sortable: false },
    {
      key: "created_at",
      label: "Created At",
      sortable: true,
      sortKey: "created_at",
    },
  ]
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Prompts"
    subtitle="Manage the instructions that tell models how to run your task."
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/prompts"
    breadcrumbs={[
      {
        label: "Optimize",
        href: `/optimize/${project_id}/${task_id}`,
      },
    ]}
    action_buttons={[
      {
        label: "Create Prompt",
        href: `/prompts/${project_id}/${task_id}/prompt_generators`,
        primary: true,
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
    {:else if $current_task?.id != task_id}
      <div class="flex flex-col gap-4 text-error">
        This link is to another task's prompts. Either select that task in the
        sidebar, or click prompts in the sidebar to load the current task's
        prompts.
      </div>
    {:else}
      <div class="flex flex-col gap-8">
        <div>
          <div class="flex items-center justify-between mb-2">
            <div>
              <h2 class="text-lg font-medium text-gray-900">Base Prompt</h2>
              <p class="text-sm text-gray-500">
                Task base prompt used by prompt generators (Basic, Few-shot,
                etc.).
              </p>
            </div>
            <button
              class="btn btn-sm"
              on:click={() =>
                goto(`/prompts/${project_id}/${task_id}/edit_base_prompt`)}
            >
              Edit
            </button>
          </div>
          {#if task?.instruction}
            <Output raw_output={task.instruction} max_height="200px" />
          {:else}
            <div class="text-gray-400 text-sm italic">
              No base prompt set. Click Edit to add one.
            </div>
          {/if}
        </div>

        <div>
          <h2 class="text-lg font-medium text-gray-900">Saved Prompts</h2>
          <p class="text-sm text-gray-500 mb-2">
            Saved prompts include custom prompts, frozen prompts from saved run
            configurations, and fine-tuning prompts.
          </p>
          {#if !has_prompts}
            <div class="text-gray-500 rounded-lg border p-4 text-sm">
              No saved prompts yet. Create one by clicking "Create Prompt"
              above.
            </div>
          {:else}
            <div class="overflow-x-auto overflow-y-hidden rounded-lg border">
              <table class="table">
                <thead>
                  <tr>
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
                        <th>{column.label}</th>
                      {/if}
                    {/each}
                    <th style="width: 3%;"></th>
                  </tr>
                </thead>
                <tbody>
                  {#each sorted_prompts as prompt}
                    <tr
                      class="hover:bg-base-200 cursor-pointer"
                      on:click={() =>
                        goto(
                          `/prompts/${project_id}/${task_id}/saved/${prompt.id}`,
                        )}
                    >
                      <td class="font-medium">
                        {prompt.name}
                      </td>
                      <td class="whitespace-nowrap">
                        {getPromptType(prompt.id)}
                      </td>
                      <td>
                        <div class="max-w-[400px] truncate">
                          {prompt.prompt.length > 200
                            ? prompt.prompt.slice(0, 200) + "..."
                            : prompt.prompt}
                        </div>
                      </td>
                      <td class="text-sm text-gray-500 whitespace-nowrap">
                        {formatDate(prompt.created_at || undefined)}
                      </td>
                      <td class="p-0" on:click|stopPropagation>
                        <div class="dropdown dropdown-end dropdown-hover">
                          <TableButton />
                          <!-- svelte-ignore a11y-no-noninteractive-tabindex -->
                          <ul
                            tabindex="0"
                            class="dropdown-content menu bg-base-100 rounded-box z-[1] w-56 p-2 shadow"
                          >
                            <li>
                              <button
                                on:click={() =>
                                  goto(
                                    `/optimize/${project_id}/${task_id}/create_run_config?prompt_id=${encodeURIComponent(prompt.id)}`,
                                  )}
                              >
                                Create Run Configuration
                              </button>
                            </li>
                            <li>
                              <button
                                on:click={() =>
                                  handleSetBasePrompt(prompt.prompt)}
                              >
                                Set as Base Prompt
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
      </div>
    {/if}
  </AppPage>
</div>
