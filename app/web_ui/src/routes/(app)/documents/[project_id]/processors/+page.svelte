<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import { client } from "$lib/api_client"
  import type { ExtractorConfig } from "$lib/types"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { load_model_info } from "$lib/stores"
  import { page } from "$app/stores"
  import { goto, replaceState } from "$app/navigation"
  import EmptyIntro from "./empty_intro.svelte"
  import { formatDate } from "$lib/utils/formatters"

  let extractor_configs: ExtractorConfig[] | null = null
  let error: KilnError | null = null
  let loading = true
  let sortColumn = ($page.url.searchParams.get("sort") || "created_at") as
    | keyof ExtractorConfig
    | "id"
    | "name"
    | "description"
    | "created_at"
  let sortDirection = ($page.url.searchParams.get("order") || "desc") as
    | "asc"
    | "desc"
  let page_number: number = parseInt(
    $page.url.searchParams.get("page") || "1",
    10,
  )
  const page_size = 1000
  $: {
    // Update based on live URL
    const url = new URL(window.location.href)
    sortColumn = (url.searchParams.get("sort") ||
      "created_at") as typeof sortColumn
    sortDirection = (url.searchParams.get("order") ||
      "desc") as typeof sortDirection
    page_number = parseInt(url.searchParams.get("page") || "1", 10)
    sortExtractorConfigs()
  }

  $: project_id = $page.params.project_id

  const columns = [
    { key: "id", label: "ID" },
    { key: "name", label: "Name" },
    { key: "description", label: "Description" },
    { key: "created_at", label: "Created At" },
  ]

  onMount(async () => {
    get_extractor_configs()
  })

  async function get_extractor_configs() {
    try {
      load_model_info()
      loading = true
      if (!project_id) {
        throw new Error("Project ID not set.")
      }
      const { data: extractor_configs_response, error: get_error } =
        await client.GET("/api/projects/{project_id}/extractor_configs", {
          params: {
            path: {
              project_id,
            },
          },
        })
      if (get_error) {
        throw get_error
      }
      extractor_configs = extractor_configs_response
      sortExtractorConfigs()
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

  function sortFunction(a: ExtractorConfig, b: ExtractorConfig) {
    let aValue: string | number | Date | null | undefined
    let bValue: string | number | Date | null | undefined

    switch (sortColumn) {
      case "id":
        aValue = a.id
        bValue = b.id
        break
      case "created_at":
        aValue = a.created_at
        bValue = b.created_at
        break
      case "name":
        aValue = a.name
        bValue = b.name
        break
      case "description":
        aValue = a.description
        bValue = b.description
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
    const new_column = columnString as typeof sortColumn
    let new_direction = "desc"
    if (sortColumn === new_column) {
      new_direction = sortDirection === "asc" ? "desc" : "asc"
    } else {
      new_direction = "desc"
    }
    updateURL({
      sort: new_column,
      order: new_direction,
    })
  }

  function sortExtractorConfigs() {
    if (!extractor_configs) return
    extractor_configs = extractor_configs
      ? [...extractor_configs].sort(sortFunction)
      : null
  }

  function updateURL(params: Record<string, string | string[] | number>) {
    // update the URL so you can share links
    const url = new URL(window.location.href)

    // Add new params to the URL (keep current params)
    Object.entries(params).forEach(([key, value]) => {
      if (Array.isArray(value)) {
        value.forEach((v) => url.searchParams.append(key, v))
      } else {
        url.searchParams.set(key, value.toString())
      }
    })

    // Update state manually
    if (params.sort) {
      sortColumn = params.sort as typeof sortColumn
    }
    if (params.order) {
      sortDirection = params.order as typeof sortDirection
    }
    if (params.page) {
      page_number = params.page as number
    }

    // Use replaceState to avoid adding new entries to history
    replaceState(url, {})

    sortExtractorConfigs()
  }

  function row_clicked(extractor_config_id: string | null) {
    if (!extractor_config_id) return
    open_extractor_config(extractor_config_id)
  }

  function open_extractor_config(extractor_config_id: string) {
    const url = `/documents/${project_id}/processors/${extractor_config_id}/processor`
    goto(url)
  }
</script>

<AppPage
  title="Processors"
  sub_subtitle="Read the Docs"
  sub_subtitle_link="#"
  no_y_padding
  action_buttons={[
    {
      label: "Create Processor",
      href: `/documents/${project_id}/processors/create_processor`,
    },
  ]}
>
  {#if loading}
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else if extractor_configs && extractor_configs.length == 0}
    <div class="flex flex-col items-center justify-center min-h-[75vh]">
      <EmptyIntro />
    </div>
  {:else if extractor_configs}
    <div class="my-4">
      <div class="overflow-x-auto rounded-lg border">
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
            {#each (extractor_configs || []).slice((page_number - 1) * page_size, page_number * page_size) as extractor_config}
              <tr
                class="hover cursor-pointer"
                on:click={() => {
                  row_clicked(extractor_config.id || null)
                }}
              >
                <td class="font-mono text-gray-500">
                  {extractor_config.id}
                </td>
                <td>{extractor_config.name}</td>
                <td>{extractor_config.description || "N/A"}</td>
                <td>{formatDate(extractor_config.created_at)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>

    {#if page_number > 1 || (extractor_configs && extractor_configs.length > page_size)}
      <div class="flex flex-row justify-center mt-10">
        <div class="join">
          {#each Array.from({ length: Math.ceil(extractor_configs.length / page_size) }, (_, i) => i + 1) as page}
            <button
              class="join-item btn {page_number == page ? 'btn-active' : ''}"
              on:click={() => updateURL({ page: page })}
            >
              {page}
            </button>
          {/each}
        </div>
      </div>
    {/if}
  {:else if error}
    <div
      class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
    >
      <div class="font-medium">Error Loading Processors</div>
      <div class="text-error text-sm">
        {error.getMessage() || "An unknown error occurred"}
      </div>
    </div>
  {/if}
</AppPage>
