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
  let page_number: number = parseInt(
    $page.url.searchParams.get("page") || "1",
    10,
  )
  const page_size = 1000
  $: {
    // Update based on live URL
    const url = new URL(window.location.href)
    page_number = parseInt(url.searchParams.get("page") || "1", 10)
  }

  $: project_id = $page.params.project_id

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
      extractor_configs = sortExtractorConfigs(extractor_configs || [])
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

  function sortExtractorConfigs(extractor_configs: ExtractorConfig[] | null) {
    if (!extractor_configs) return null
    return extractor_configs.sort((a, b) => {
      const aValue = a.created_at || ""
      const bValue = b.created_at || ""
      if (!bValue) return 1
      if (!aValue) return -1
      if (bValue < aValue) return -1
      if (bValue > aValue) return 1
      return 0
    })
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
    if (params.page) {
      page_number = params.page as number
    }

    // Use replaceState to avoid adding new entries to history
    replaceState(url, {})
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
    loading = true
    extractor_progress = {}
    await Promise.all(
      (extractor_configs || []).map((cfg) => get_progress(cfg.id || "")),
    )

    // trigger reactive update
    extractor_progress = extractor_progress
    loading = false
  }

  function status(
    extractor_config_id: string,
  ): "not_started" | "incomplete" | "complete" {
    const progress = extractor_progress[extractor_config_id]
    if (progress.document_count_successful === 0) {
      return "not_started"
    }

    if (progress.document_count_successful < progress.document_count_total) {
      return "incomplete"
    }

    return "complete"
  }

  function format_progress_percentage(progress: ExtractionProgress | null) {
    if (!progress) {
      return "0%"
    }

    if (progress.document_count_total === 0) {
      return "0%"
    }

    return `${(
      (progress.document_count_successful / progress.document_count_total) *
      100
    ).toFixed(1)}%`
  }

  $: status_map = Object.fromEntries(
    Object.entries(extractor_progress).map(([id]) => [id, status(id)]),
  )
</script>

<AppPage
  title="Document Extractors"
  subtitle="Manage your document extractors"
  sub_subtitle="Read the docs"
  sub_subtitle_link="#"
  action_buttons={[
    {
      label: "Add Extractor",
      href: `/documents/${project_id}/extractors/create_extractor`,
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
      <EmptyIntro {project_id} />
    </div>
  {:else if extractor_configs}
    <div class="my-4">
      <div class="overflow-x-auto rounded-lg border">
        <table class="table">
          <thead>
            <tr>
              <th></th>
              <th>Type</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {#each (extractor_configs || []).slice((page_number - 1) * page_size, page_number * page_size) as extractor_config}
              <tr>
                <td class="flex flex-col gap-1">
                  <div class="font-medium">
                    <a
                      href={`/documents/${project_id}/extractors/${extractor_config.id}/extractor`}
                      class="link"
                    >
                      {extractor_config.name}
                    </a>
                  </div>

                  <div class="text-sm text-gray-500">
                    Description: {extractor_config.description || "N/A"}
                  </div>

                  <div class="text-sm text-gray-500">
                    Output: {extractor_config.output_format}
                  </div>

                  <div class="text-sm text-gray-500">
                    Created: {formatDate(extractor_config.created_at)}
                  </div>
                </td>
                <td>{extractor_config.extractor_type}</td>
                <td>
                  <div class="flex flex-col gap-1">
                    {#if extractor_config.is_archived}
                      <div
                        class="badge badge-neutral badge-outline py-3 font-medium"
                      >
                        Archived
                      </div>
                    {:else if status_map[extractor_config.id || ""] == "complete"}
                      <div
                        class="badge badge-primary badge-outline py-3 font-medium"
                      >
                        Complete
                      </div>
                    {:else if status_map[extractor_config.id || ""] == "incomplete"}
                      <div
                        class="badge badge-error badge-outline py-3 font-medium"
                      >
                        Incomplete ({format_progress_percentage(
                          extractor_progress[extractor_config.id || ""],
                        )})
                      </div>
                    {:else if status_map[extractor_config.id || ""] == "not_started"}
                      <div
                        class="badge badge-warning badge-outline py-3 font-medium"
                      >
                        Not Started
                      </div>
                    {/if}
                  </div>
                </td>
                <td>
                  {#if !extractor_config.is_archived && (status_map[extractor_config.id || ""] === "not_started" || status_map[extractor_config.id || ""] === "incomplete")}
                    <RunExtractor
                      btn_size="mid"
                      on_run_complete={() => get_all_progress()}
                      run_url={`${base_url}/api/projects/${project_id}/extractor_configs/${extractor_config.id}/run_extractor_config`}
                    />
                  {/if}
                </td>
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
