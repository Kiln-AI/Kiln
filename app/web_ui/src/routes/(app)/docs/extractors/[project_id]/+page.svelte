<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import { client } from "$lib/api_client"
  import type { ExtractorConfig } from "$lib/types"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { load_model_info } from "$lib/stores"
  import { page } from "$app/stores"
  import { replaceState } from "$app/navigation"
  import EmptyIntro from "./empty_intro.svelte"
  import { extractorProgressStore } from "$lib/stores/extractor_progress_store"
  import TableExtractorRow from "./table_extractor_row.svelte"

  let extractor_configs: ExtractorConfig[] | null = null
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

  async function get_all_progress() {
    loading = true
    extractorProgressStore.reset()
    if (extractor_configs) {
      await extractorProgressStore.getAllProgress(
        project_id,
        extractor_configs.map((cfg) => cfg.id || "").filter(Boolean),
      )
    }
    loading = false
  }
</script>

<AppPage
  title="Document Extractors"
  subtitle="Manage your document extractors"
  sub_subtitle="Read the docs"
  sub_subtitle_link="#"
  no_y_padding
  action_buttons={extractor_configs && extractor_configs.length == 0
    ? []
    : [
        {
          label: "Add Extractor",
          href: `/docs/extractors/${project_id}/create_extractor`,
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
              <TableExtractorRow {extractor_config} {project_id} />
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
