<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import { KilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import {
    load_available_embedding_models,
    load_available_models,
  } from "$lib/stores"
  import { page } from "$app/stores"
  import { replaceState } from "$app/navigation"
  import EmptyRagConfigsIntro from "./empty_rag_configs_intro.svelte"
  import TableRagConfigRow from "./table_rag_config_row.svelte"
  import {
    load_all_rag_config_progress,
    ragProgressStore,
    load_rag_configs,
    allRagConfigs,
  } from "$lib/stores/rag_progress_store"

  let error: KilnError | null = $ragProgressStore.error
  let loading = true
  let page_number: number = parseInt(
    $page.url.searchParams.get("page") || "1",
    10,
  )
  const page_size = 1000
  $: {
    const url = new URL(window.location.href)
    page_number = parseInt(url.searchParams.get("page") || "1", 10)
  }

  $: project_id = $page.params.project_id

  onMount(async () => {
    // need to ensure the store is populated for friendly name resolution
    await Promise.all([
      load_available_models(),
      load_available_embedding_models(),
      load_all_rag_config_progress(project_id),
      load_rag_configs(project_id),
    ])
    loading = false
  })

  $: rag_configs = $allRagConfigs

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
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Search Tools (RAG)"
    subtitle="Make knowledge from your documents searchable by your tasks."
    no_y_padding={!!(rag_configs && rag_configs.length == 0)}
    action_buttons={rag_configs && rag_configs.length == 0
      ? []
      : [
          {
            label: "Add Search Tool",
            href: `/docs/rag_configs/${project_id}/create_rag_config`,
          },
        ]}
  >
    {#if loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if rag_configs && rag_configs.length == 0}
      <div class="flex flex-col items-center justify-center min-h-[75vh]">
        <EmptyRagConfigsIntro {project_id} />
      </div>
    {:else if rag_configs}
      <div class="my-4">
        <div class="overflow-x-auto rounded-lg border">
          <table class="table">
            <thead>
              <tr>
                <th>Details</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {#each (rag_configs || []).slice((page_number - 1) * page_size, page_number * page_size) as rag_config}
                <TableRagConfigRow {rag_config} {project_id} />
              {/each}
            </tbody>
          </table>
        </div>
      </div>

      {#if page_number > 1 || (rag_configs && rag_configs.length > page_size)}
        <div class="flex flex-row justify-center mt-10">
          <div class="join">
            {#each Array.from({ length: Math.ceil(rag_configs.length / page_size) }, (_, i) => i + 1) as page}
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
        <div class="font-medium">Error Loading RAG Configurations</div>
        <div class="text-error text-sm">
          {error.getMessage() || "An unknown error occurred"}
        </div>
      </div>
    {/if}
  </AppPage>
</div>
