<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import { client } from "$lib/api_client"
  import type { TaskRun } from "$lib/types"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { model_info, load_model_info, model_name } from "$lib/stores"
  import { goto } from "$app/navigation"
  import { page } from "$app/stores"

  let runs: TaskRun[] | null = null
  let error: KilnError | null = null
  let loading = true
  let sortColumn:
    | keyof TaskRun
    | "rating"
    | "inputPreview"
    | "outputPreview"
    | "repairState" = "created_at"
  let sortDirection: "asc" | "desc" = "asc"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  const columns = [
    { key: "rating", label: "Rating" },
    { key: "repairState", label: "Repair State" },
    { key: "model", label: "Model" },
    { key: "created_at", label: "Created At" },
    { key: "inputPreview", label: "Input Preview" },
    { key: "outputPreview", label: "Output Preview" },
  ]

  onMount(async () => {
    get_runs()
  })

  async function get_runs() {
    try {
      load_model_info()
      loading = true
      if (!project_id || !task_id) {
        throw new Error("Project or task ID not set.")
      }
      const { data: runs_response, error: get_error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/runs",
        {
          params: {
            path: {
              project_id,
              task_id,
            },
          },
        },
      )
      if (get_error) {
        throw get_error
      }
      runs = runs_response
      sortRuns()
    } catch (e) {
      if (e instanceof Error && e.message.includes("Load failed")) {
        error = new KilnError(
          "Could not load dataset. It may belong to a project you don't have access to.",
          null,
        )
      } else {
        error = createKilnError(e)
      }
    } finally {
      loading = false
    }
  }

  function formatRepairState(run: TaskRun): string {
    if (run.repair_instructions) {
      return "Repaired"
    } else if (run.output && !run.output.rating) {
      return "Rating needed"
    } else if (
      run.output?.rating?.value === 5.0 &&
      run.output?.rating?.type === "five_star"
    ) {
      return "No repair needed"
    } else if (run.output?.output) {
      return "Repair needed"
    } else {
      return "No output"
    }
  }

  function formatDate(dateString: string | undefined): string {
    if (!dateString) {
      return "Unknown"
    }
    const date = new Date(dateString)
    const currentYear = new Date().getFullYear()
    const options: Intl.DateTimeFormatOptions = {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }

    if (date.getFullYear() !== currentYear) {
      options.year = "numeric"
    }

    return date.toLocaleString("en-US", options)
  }

  function previewText(
    text: string | undefined | null,
    maxLength: number = 100,
  ): string | null {
    if (!text) return null
    if (text.length <= maxLength) return text
    return text.slice(0, maxLength) + "..."
  }

  function sortFunction(a: TaskRun, b: TaskRun) {
    let aValue: string | number | Date | null | undefined
    let bValue: string | number | Date | null | undefined

    switch (sortColumn) {
      case "id":
        aValue = a.id
        bValue = b.id
        break
      case "created_at":
        aValue = a[sortColumn]
        bValue = b[sortColumn]
        break
      case "rating":
        aValue = a.output.rating?.value ?? -1
        bValue = b.output.rating?.value ?? -1
        break
      case "inputPreview":
        aValue = (a.input ?? "").toLowerCase()
        bValue = (b.input ?? "").toLowerCase()
        break
      case "outputPreview":
        aValue = (a.output?.output ?? "").toLowerCase()
        bValue = (b.output?.output ?? "").toLowerCase()
        break
      case "repairState":
        aValue = formatRepairState(a)
        bValue = formatRepairState(b)
        break
      default:
        return 0
    }

    if (!aValue) return sortDirection === "asc" ? 1 : -1
    if (!bValue) return sortDirection === "asc" ? -1 : 1

    if (aValue < bValue) return sortDirection === "asc" ? -1 : 1
    if (aValue > bValue) return sortDirection === "asc" ? 1 : -1
    return 0
  }

  function handleSort(columnString: string) {
    const column = columnString as typeof sortColumn
    if (sortColumn === column) {
      sortDirection = sortDirection === "asc" ? "desc" : "asc"
    } else {
      sortColumn = column
      sortDirection = "desc"
    }
    sortRuns()
  }

  function sortRuns() {
    runs = runs ? [...runs].sort(sortFunction) : null
  }
</script>

<AppPage
  title="Dataset"
  subtitle="Explore your runs, sample data, and ratings for this task."
  action_button="Add Data"
  action_button_href="/run"
>
  {#if loading}
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else if runs}
    <div class="overflow-x-auto">
      <table class="table">
        <thead>
          <tr>
            {#each columns as { key, label }}
              <th
                on:click={() => handleSort(key)}
                class="hover:bg-base-200 cursor-pointer"
              >
                {label}
                {sortColumn === key
                  ? sortDirection === "asc"
                    ? "▲"
                    : "▼"
                  : ""}
              </th>
            {/each}
          </tr>
        </thead>
        <tbody>
          {#each runs as run}
            <tr
              class="hover cursor-pointer"
              on:click={() => {
                goto(`/dataset/${project_id}/${task_id}/${run.id}/run`)
              }}
            >
              <td>
                {run.output.rating && run.output.rating.value
                  ? run.output.rating.type === "five_star"
                    ? "★".repeat(run.output.rating.value)
                    : run.output.rating.value + "(custom score)"
                  : "Unrated"}
              </td>
              <td>{formatRepairState(run)}</td>
              <td>
                {model_name(
                  "" + run.output?.source?.properties["model_name"],
                  $model_info,
                )}
              </td>
              <td>{formatDate(run.created_at)}</td>
              <td>{previewText(run.input) || "No input"}</td>
              <td>
                {previewText(
                  run.repaired_output?.output || run.output?.output,
                ) || "No output"}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {:else if error}
    <div
      class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
    >
      <div class="font-medium">Error Loading Dataset</div>
      <div class="text-error text-sm">
        {error.getMessage() || "An unknown error occurred"}
      </div>
    </div>
  {/if}
</AppPage>
