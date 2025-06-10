<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import { base_url, client } from "$lib/api_client"
  import type { ExtractorConfig, ExtractionProgress } from "$lib/types"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { load_model_info } from "$lib/stores"
  import { page } from "$app/stores"
  import { replaceState } from "$app/navigation"
  import EmptyIntro from "./empty_intro.svelte"
  import { formatDate } from "$lib/utils/formatters"
  import RunExtractor from "./run_extractor.svelte"

  let extractor_configs: ExtractorConfig[] | null = null
  let extractor_progress: Record<string, ExtractionProgress> = {}
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
      await get_all_progress()
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

  async function get_progress(extractor_config_id: string) {
    try {
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/extractor_configs/{extractor_config_id}/progress",
        {
          params: { path: { project_id, extractor_config_id } },
        },
      )
      if (!error && data) {
        extractor_progress = {
          ...extractor_progress,
          [extractor_config_id]: data,
        }
      }
    } catch (e) {
      // ignore progress errors for now
    }
  }

  async function get_all_progress() {
    extractor_progress = {}
    await Promise.all(
      (extractor_configs || []).map((cfg) => get_progress(cfg.id || "")),
    )
  }

  function completed_ratio(extractor_config_id: string) {
    const progress = extractor_progress[extractor_config_id]
    if (!progress) return 0
    return progress.document_count_successful / progress.document_count_total
  }
</script>

<AppPage
  title="Document Extractors"
  subtitle="Manage your document extractors"
  sub_subtitle="Read the docs"
  sub_subtitle_link="#"
  no_y_padding
  action_buttons={[
    {
      label: "Add Extractor",
      href: `/documents/${project_id}/processors/create_processor`,
      primary: true,
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
              <th>Run</th>
            </tr>
          </thead>
          <tbody>
            {#each (extractor_configs || []).slice((page_number - 1) * page_size, page_number * page_size) as extractor_config}
              <tr>
                <td class="flex flex-col gap-2">
                  <div class="font-medium">
                    {extractor_config.name}
                  </div>

                  <div class="text-sm text-gray-500">
                    Description: {extractor_config.description || "N/A"}
                  </div>

                  <div class="text-sm text-gray-500">
                    ID:{extractor_config.id}
                  </div>

                  <div class="text-sm text-gray-500">
                    Output: {extractor_config.output_format}
                  </div>

                  {#if (completed_ratio(extractor_config.id || "") || 0) < 1}
                    <div class="flex flex-col gap-1 text-error">
                      <div>
                        Progress: {(
                          completed_ratio(extractor_config.id || "") * 100.0
                        ).toFixed(1)}%
                      </div>
                      <div>
                        {extractor_progress[extractor_config.id || ""]
                          .document_count_successful} /
                        {extractor_progress[extractor_config.id || ""]
                          .document_count_total} documents
                      </div>
                    </div>
                  {:else}
                    <div class="flex flex-col gap-1 text-success">
                      <div>
                        Completed ({completed_ratio(extractor_config.id || "") *
                          100}%)
                      </div>
                      <div>
                        {extractor_progress[extractor_config.id || ""]
                          .document_count_successful} /
                        {extractor_progress[extractor_config.id || ""]
                          .document_count_total} documents
                      </div>
                    </div>
                  {/if}
                </td>
                <td>{formatDate(extractor_config.created_at)}</td>
                {#if completed_ratio(extractor_config.id || "") < 1}
                  <td>
                    <RunExtractor
                      btn_size="mid"
                      on_run_complete={() => get_all_progress()}
                      run_url={`${base_url}/api/projects/${project_id}/extractor_configs/${extractor_config.id}/run_extractor_config`}
                    />
                  </td>
                {/if}
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
      <div class="font-medium">Error Loading Extractors</div>
      <div class="text-error text-sm">
        {error.getMessage() || "An unknown error occurred"}
      </div>
    </div>
  {/if}
</AppPage>
