<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import { page } from "$app/stores"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import { client } from "$lib/api_client"
  import { onMount } from "svelte"
  import Intro from "$lib/ui/intro.svelte"
  import type { Spec } from "$lib/types"
  import { formatDate, capitalize } from "$lib/utils/formatters"
  import { goto } from "$app/navigation"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  let specs: Spec[] | null = null
  let specs_error: KilnError | null = null
  let specs_loading = true
  let sortColumn: "name" | "type" | "priority" | "status" | "created_at" =
    "created_at"
  let sortDirection: "asc" | "desc" = "desc"
  let sorted_specs: Spec[] | null = null

  $: is_empty = !specs || specs.length == 0
  $: {
    if (specs && sortColumn && sortDirection) {
      sorted_specs = [...specs].sort(sortFunction)
    } else {
      sorted_specs = null
    }
  }

  onMount(async () => {
    await load_specs()
  })

  async function load_specs() {
    try {
      specs_loading = true
      specs_error = null
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/specs",
        {
          params: {
            path: { project_id, task_id },
          },
        },
      )
      if (error) {
        throw error
      }
      specs = data
    } catch (error) {
      specs_error = createKilnError(error)
    } finally {
      specs_loading = false
    }
  }

  function formatPriority(priority: number): string {
    return `P${priority}`
  }

  function getStatusSortOrder(status: string): number {
    if (status === "complete") return 0
    if (status === "in_progress") return 1
    if (status === "not_started") return 2
    return 3 // status === "deprecated"
  }

  function sortFunction(a: Spec, b: Spec) {
    let aValue: string | number | Date | null | undefined
    let bValue: string | number | Date | null | undefined

    switch (sortColumn) {
      case "name":
        aValue = a.name.toLowerCase()
        bValue = b.name.toLowerCase()
        break
      case "type":
        aValue = a.type
        bValue = b.type
        break
      case "priority":
        aValue = a.priority
        bValue = b.priority
        break
      case "status":
        aValue = getStatusSortOrder(a.status)
        bValue = getStatusSortOrder(b.status)
        break
      case "created_at":
        aValue = a.created_at ? new Date(a.created_at).getTime() : 0
        bValue = b.created_at ? new Date(b.created_at).getTime() : 0
        break
      default:
        return 0
    }

    if (!aValue && aValue !== 0) return sortDirection === "asc" ? 1 : -1
    if (!bValue && bValue !== 0) return sortDirection === "asc" ? -1 : 1

    if (aValue < bValue) return sortDirection === "asc" ? -1 : 1
    if (aValue > bValue) return sortDirection === "asc" ? 1 : -1
    return 0
  }

  function handleSort(
    column: "name" | "type" | "priority" | "status" | "created_at",
  ) {
    if (sortColumn === column) {
      sortDirection = sortDirection === "asc" ? "desc" : "asc"
    } else {
      sortColumn = column
      sortDirection = "desc"
    }
  }
</script>

<AppPage
  limit_max_width={true}
  title="Specs"
  subtitle="Define the specs you want your task to follow"
  sub_subtitle={is_empty ? undefined : "Read the Docs"}
  sub_subtitle_link="https://docs.kiln.tech/docs/evaluations"
  action_buttons={is_empty
    ? []
    : [
        {
          label: "New Spec",
          href: `/specs/${project_id}/${task_id}/create_spec`,
          primary: true,
        },
      ]}
>
  <div class="flex flex-col gap-4">
    {#if specs_loading}
      <div class="flex justify-center items-center h-full">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if specs_error}
      <div class="text-error text-sm">
        {specs_error.getMessage() || "An unknown error occurred"}
      </div>
    {:else if is_empty}
      <div class="max-w-[300px] mx-auto flex flex-col gap-2 mt-[10vh]">
        <Intro
          title="Specs"
          description_paragraphs={[
            "Specs are used to define how you want your task to behave.",
          ]}
          action_buttons={[
            {
              label: "Define a Spec",
              href: `/specs/${project_id}/${task_id}/create_spec`,
              is_primary: true,
            },
          ]}
        />
      </div>
    {:else if sorted_specs}
      <div class="overflow-x-auto rounded-lg border">
        <table class="table">
          <thead>
            <tr>
              <th
                on:click={() => handleSort("name")}
                class="hover:bg-base-200 cursor-pointer"
              >
                Name
                <span class="inline-block w-3 text-center">
                  {sortColumn === "name"
                    ? sortDirection === "asc"
                      ? "▲"
                      : "▼"
                    : "\u200B"}
                </span>
              </th>
              <th>Definition</th>
              <th
                on:click={() => handleSort("type")}
                class="hover:bg-base-200 cursor-pointer"
              >
                Type
                <span class="inline-block w-3 text-center">
                  {sortColumn === "type"
                    ? sortDirection === "asc"
                      ? "▲"
                      : "▼"
                    : "\u200B"}
                </span>
              </th>
              <th
                on:click={() => handleSort("priority")}
                class="hover:bg-base-200 cursor-pointer"
              >
                Priority
                <span class="inline-block w-3 text-center">
                  {sortColumn === "priority"
                    ? sortDirection === "asc"
                      ? "▲"
                      : "▼"
                    : "\u200B"}
                </span>
              </th>
              <th
                on:click={() => handleSort("status")}
                class="hover:bg-base-200 cursor-pointer"
              >
                Status
                <span class="inline-block w-3 text-center">
                  {sortColumn === "status"
                    ? sortDirection === "asc"
                      ? "▲"
                      : "▼"
                    : "\u200B"}
                </span>
              </th>
              <th
                on:click={() => handleSort("created_at")}
                class="hover:bg-base-200 cursor-pointer"
              >
                Created At
                <span class="inline-block w-3 text-center">
                  {sortColumn === "created_at"
                    ? sortDirection === "asc"
                      ? "▲"
                      : "▼"
                    : "\u200B"}
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            {#each sorted_specs as spec}
              <tr
                class="hover cursor-pointer"
                on:click={() => {
                  goto(`/specs/${project_id}/${task_id}/${spec.id}`)
                }}
              >
                <td class="font-medium">{spec.name}</td>
                <td class="max-w-md truncate">{spec.definition}</td>
                <td>
                  {spec.type
                    .replace(/_/g, " ")
                    .split(" ")
                    .map((word) => capitalize(word))
                    .join(" ")}
                </td>
                <td>{formatPriority(spec.priority)}</td>
                <td>
                  {spec.status === "not_started"
                    ? "Not Started"
                    : spec.status === "in_progress"
                      ? "In Progress"
                      : capitalize(spec.status)}
                </td>
                <td class="text-sm text-gray-500">
                  {formatDate(spec.created_at)}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </div>
</AppPage>
