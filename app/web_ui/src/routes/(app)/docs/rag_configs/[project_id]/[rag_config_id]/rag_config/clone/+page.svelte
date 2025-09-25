<script lang="ts">
  import { page } from "$app/stores"
  import AppPage from "../../../../../../app_page.svelte"
  import { goto } from "$app/navigation"
  import { client } from "$lib/api_client"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import type { RagConfigWithSubConfigs } from "$lib/types"
  import { onMount } from "svelte"
  import EditRagConfigForm from "../../../create_rag_config/edit_rag_config_form.svelte"

  $: project_id = $page.params.project_id
  $: rag_config_id = $page.params.rag_config_id

  let loading: boolean = true
  let error: KilnError | null = null
  let rag_config: RagConfigWithSubConfigs | null = null

  onMount(async () => {
    await get_rag_config()
  })

  async function get_rag_config() {
    try {
      loading = true
      const { data: rag_config_data, error: get_rag_config_error } =
        await client.GET(
          "/api/projects/{project_id}/rag_configs/{rag_config_id}",
          {
            params: {
              path: {
                project_id,
                rag_config_id,
              },
            },
          },
        )

      if (get_rag_config_error) {
        throw get_rag_config_error
      }

      rag_config = rag_config_data
    } catch (e) {
      error = createKilnError(e)
    } finally {
      loading = false
    }
  }
</script>

<div class="max-w-[900px]">
  <AppPage
    title="Create Search Tool (RAG)"
    subtitle="Define parameters for how this tool will search and retrieve your documents"
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/documents-and-search-rag#building-a-search-tool"
    breadcrumbs={[
      {
        label: "Docs & Search",
        href: `/docs/${project_id}`,
      },
      {
        label: "Search Tools",
        href: `/docs/rag_configs/${project_id}`,
      },
      {
        label: "Add Search Tool",
        href: `/docs/rag_configs/${project_id}/add_search_tool`,
      },
    ]}
  >
    {#if loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if error}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="text-red-500">{error.message}</div>
      </div>
    {:else}
      <EditRagConfigForm
        initial_rag_config={rag_config}
        on:success={() => {
          goto(`/docs/rag_configs/${project_id}`)
        }}
      />
    {/if}
  </AppPage>
</div>
