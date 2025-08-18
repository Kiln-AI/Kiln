<script lang="ts">
  import { page } from "$app/stores"
  import { client } from "$lib/api_client"
  import type { RagConfigWithSubConfigs } from "$lib/types"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import AppPage from "../../../../../app_page.svelte"
  import PropertyList from "$lib/ui/property_list.svelte"
  import { onMount } from "svelte"
  import { extractor_output_format, formatDate } from "$lib/utils/formatters"
  import {
    embedding_model_name,
    load_available_embedding_models,
    load_available_models,
    model_name,
    provider_name_from_id,
  } from "$lib/stores"

  $: project_id = $page.params.project_id
  $: rag_config_id = $page.params.rag_config_id

  let loading: boolean = false
  let error: KilnError | null = null
  let rag_config: RagConfigWithSubConfigs | null = null

  onMount(async () => {
    // need to load available models to get the model store populated
    await load_available_models()
    await load_available_embedding_models()

    await get_rag_config()
  })

  async function get_rag_config() {
    try {
      loading = true
      const { error: get_rag_config_error, data: rag_config_data } =
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
        error = createKilnError(get_rag_config_error)
        return
      }

      rag_config = rag_config_data
    } finally {
      loading = false
    }
  }
</script>

<AppPage
  title="Search Tool (RAG)"
  subtitle={loading ? "" : `Name: ${rag_config?.name}` || "Unknown"}
  action_buttons={[]}
>
  {#if loading}
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else if error}
    <div
      class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
    >
      <div class="text-error text-sm">
        {error.getMessage() || "An unknown error occurred"}
      </div>
    </div>
  {:else if !rag_config}
    <div
      class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
    >
      <div class="text-error text-sm">RAG config not found</div>
    </div>
  {:else}
    <div class="flex flex-col gap-6 max-w-4xl">
      <!-- RAG Config Details -->
      <div>
        <PropertyList
          title="Details"
          properties={[
            { name: "ID", value: rag_config.id || "N/A" },
            { name: "Name", value: rag_config.name || "N/A" },
            { name: "Description", value: rag_config.description || "N/A" },
            { name: "Created At", value: formatDate(rag_config.created_at) },
            { name: "Created By", value: rag_config.created_by || "N/A" },
          ]}
        />
      </div>

      <!-- Separator -->
      <div class="border-t border-gray-200"></div>

      <!-- RAG Steps -->
      <div class="flex flex-col gap-6">
        <!-- Extraction Step -->
        <div>
          <PropertyList
            title="Extractor"
            properties={[
              {
                name: "Model Provider",
                value:
                  provider_name_from_id(
                    rag_config.extractor_config.model_provider_name,
                  ) || "N/A",
              },
              {
                name: "Model",
                value:
                  "" +
                  (model_name(rag_config.extractor_config?.model_name, null) ||
                    "N/A"),
              },
              {
                name: "Output Format",
                value:
                  extractor_output_format(
                    rag_config.extractor_config.output_format,
                  ) || "N/A",
              },
              {
                name: "Details",
                value: "View Extractor Configuration",
                link: `/docs/extractors/${project_id}/${rag_config.extractor_config.id}/extractor`,
              },
            ]}
          />
        </div>

        <!-- Chunking Step -->
        <div>
          <PropertyList
            title="Chunker"
            properties={[
              {
                name: "Strategy",
                value: rag_config.chunker_config.chunker_type || "N/A",
              },
              {
                name: "Chunk Size",
                value: rag_config.chunker_config.properties?.chunk_size
                  ? `${String(rag_config.chunker_config.properties.chunk_size)} words`
                  : "N/A",
                tooltip: "The number of words to include in each chunk",
              },
              {
                name: "Overlap",
                value: rag_config.chunker_config.properties?.chunk_overlap
                  ? `${String(rag_config.chunker_config.properties.chunk_overlap)} words`
                  : "N/A",
                tooltip: "The number of words to overlap between chunks",
              },
            ]}
          />
        </div>

        <!-- Embedding Step -->
        <div>
          <PropertyList
            title="Embedding Model"
            properties={[
              {
                name: "Provider",
                value:
                  provider_name_from_id(
                    rag_config.embedding_config.model_provider_name,
                  ) || "N/A",
              },
              {
                name: "Model",
                value:
                  embedding_model_name(
                    rag_config.embedding_config.model_name,
                    rag_config.embedding_config.model_provider_name,
                  ) || "N/A",
              },
            ]}
          />
        </div>
      </div>
    </div>
  {/if}
</AppPage>
