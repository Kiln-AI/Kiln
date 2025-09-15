<script lang="ts">
  import { page } from "$app/stores"
  import { client } from "$lib/api_client"
  import type { ChunkerType, RagConfigWithSubConfigs } from "$lib/types"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import AppPage from "../../../../../app_page.svelte"
  import PropertyList from "$lib/ui/property_list.svelte"
  import { onMount } from "svelte"
  import {
    chunker_type_format,
    extractor_output_format,
    formatDate,
  } from "$lib/utils/formatters"
  import {
    embedding_model_name,
    load_available_embedding_models,
    load_available_models,
    model_name,
    provider_name_from_id,
  } from "$lib/stores"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
  import Output from "../../../../../run/output.svelte"
  import EditDialog from "$lib/ui/edit_dialog.svelte"

  $: project_id = $page.params.project_id
  $: rag_config_id = $page.params.rag_config_id

  let loading: boolean = false
  let error: KilnError | null = null
  let rag_config: RagConfigWithSubConfigs | null = null

  let edit_dialog: EditDialog | null = null

  // Search state
  let searchQuery: string = ""
  let searchLoading: boolean = false
  let searchError: KilnError | null = null
  let lastSearchQuery: string | null = null
  let searchResults: Array<{
    document_id: string
    chunk_idx: number
    chunk_text: string
    similarity: number | null
  }> = []

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

  function tooltip_for_chunker_type(chunker_type: ChunkerType): string {
    const friendly_chunker_type = chunker_type_format(chunker_type)
    switch (chunker_type) {
      case "fixed_window":
        return `The ${friendly_chunker_type} chunking algorithm splits the text into fixed-size chunks of a specified number of words, while respecting sentence boundaries.`
      default: {
        // trigger a type error if there is a new output format, but don't handle it
        // in the switch
        const exhaustiveCheck: never = chunker_type
        return exhaustiveCheck
      }
    }
  }

  async function performSearch() {
    if (!searchQuery.trim() || !rag_config) {
      return
    }

    try {
      searchLoading = true
      searchError = null

      const { error: search_error, data: search_data } = await client.POST(
        "/api/projects/{project_id}/rag_configs/{rag_config_id}/search",
        {
          params: {
            path: {
              project_id,
              rag_config_id,
            },
          },
          body: {
            query: searchQuery.trim(),
          },
        },
      )

      if (search_error) {
        searchError = createKilnError(search_error)
        return
      }

      searchResults = search_data?.results || []
      lastSearchQuery = searchQuery
    } catch (err) {
      searchError = createKilnError(err)
    } finally {
      searchLoading = false
    }
  }

  async function handleSearchSubmit(event: Event) {
    event.preventDefault()
    await performSearch()
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Search Tool (RAG)"
    subtitle={rag_config?.name ? `Name: ${rag_config.name}` : undefined}
    breadcrumbs={[
      {
        label: "Docs & Search",
        href: `/docs/${project_id}`,
      },
      {
        label: "Search Tools",
        href: `/docs/rag_configs/${project_id}`,
      },
    ]}
    action_buttons={[
      {
        label: "Edit",
        handler: () => {
          edit_dialog?.show()
        },
      },
    ]}
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
      <div class="flex flex-col lg:flex-row gap-8 xl:gap-12">
        <!-- Main Content - Search Section -->
        <div class="flex-1">
          <div class="text-xl font-bold mb-1">Test Search Tool</div>
          <div class="font-light mb-2">
            Experiment with your search tool, without running an AI task.
            <span class="text-gray-500">
              <InfoTooltip
                tooltip_text="This UI runs your search tool (RAG) without sending the results to an AI task. You can use the search tool in an AI task by selecting it from the 'Tools' dropdown in the 'Advanced' section of the 'Run' page."
                no_pad={true}
              />
            </span>
          </div>
          <div class="mb-8">
            <form on:submit={handleSearchSubmit}>
              <div class="form-control">
                <div class="flex gap-2">
                  <input
                    id="search-query"
                    type="text"
                    bind:value={searchQuery}
                    placeholder="Enter your search query..."
                    class="input input-bordered flex-1"
                    disabled={searchLoading}
                  />
                  <button
                    type="submit"
                    class="btn btn-primary"
                    disabled={searchLoading || !searchQuery.trim()}
                  >
                    {#if searchLoading}
                      <span class="loading loading-spinner loading-sm"></span>
                    {:else}
                      Search
                    {/if}
                  </button>
                </div>
              </div>
            </form>

            {#if searchError}
              <div class="alert alert-error mt-4">
                <span>{searchError.getMessage() || "Search failed"}</span>
              </div>
            {/if}

            {#if searchResults.length > 0}
              <div class="mt-12">
                <div class="flex flex-row justify-between items-center mb-6">
                  <h3 class="text-xl font-bold">
                    Search Results for "{lastSearchQuery}"
                  </h3>
                  <div class="text-sm text-gray-500">
                    {searchResults.length > 1
                      ? `${searchResults.length} results found`
                      : "1 result found"}
                  </div>
                </div>

                <div class="space-y-12">
                  {#each searchResults as result}
                    <div>
                      <div class="mb-2 flex flex-row text-sm text-gray-500">
                        <div class="flex-grow">
                          <a
                            href={`/docs/library/${project_id}/${result.document_id}`}
                            class="hover:link"
                          >
                            Document: {result.document_id}
                          </a>
                          (Chunk #{result.chunk_idx})
                        </div>
                        <div>
                          Score: {result.similarity !== null
                            ? result.similarity.toFixed(2)
                            : "N/A"}
                        </div>
                      </div>
                      <Output
                        raw_output={result.chunk_text}
                        max_height="300px"
                      />
                    </div>
                  {/each}
                </div>
              </div>
            {:else if lastSearchQuery && searchResults.length === 0}
              <div class="text-center text-gray-500 mt-6">
                No results found for "{lastSearchQuery}"
              </div>
            {/if}
          </div>
        </div>

        <!-- Right Sidebar - Configuration Details -->
        <div class="w-full lg:w-80 xl:w-96 flex-shrink-0">
          <div class="flex flex-col gap-6">
            <PropertyList
              title="Properties"
              properties={[
                { name: "ID", value: rag_config.id || "N/A" },
                { name: "Name", value: rag_config.name || "N/A" },
                { name: "Description", value: rag_config.description || "N/A" },
                {
                  name: "Created At",
                  value: formatDate(rag_config.created_at),
                },
                { name: "Created By", value: rag_config.created_by || "N/A" },
              ]}
            />

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
                    (model_name(
                      rag_config.extractor_config?.model_name,
                      null,
                    ) || "N/A"),
                },
                {
                  name: "Output Format",
                  value:
                    extractor_output_format(
                      rag_config.extractor_config.output_format,
                    ) || "N/A",
                },
                {
                  name: "Configuration",
                  value: "View Extractor",
                  link: `/docs/extractors/${project_id}/${rag_config.extractor_config.id}/extractor`,
                },
              ]}
            />

            <PropertyList
              title="Chunker"
              properties={[
                {
                  name: "Strategy",
                  value:
                    chunker_type_format(
                      rag_config.chunker_config.chunker_type,
                    ) || "N/A",
                  tooltip: tooltip_for_chunker_type(
                    rag_config.chunker_config.chunker_type,
                  ),
                },
                {
                  name: "Chunk Size",
                  value: rag_config.chunker_config.properties?.chunk_size
                    ? `${String(rag_config.chunker_config.properties.chunk_size)} words`
                    : "N/A",
                  tooltip:
                    "The approximate number of words to include in each chunk",
                },
                {
                  name: "Overlap",
                  value: rag_config.chunker_config.properties?.chunk_overlap
                    ? `${String(rag_config.chunker_config.properties.chunk_overlap)} words`
                    : "N/A",
                  tooltip:
                    "The approximate number of words to overlap between chunks",
                },
              ]}
            />

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

            <PropertyList
              title="Vector Store"
              properties={[
                {
                  name: "Type",
                  value:
                    rag_config.vector_store_config.store_type === "lancedb_fts"
                      ? "Full Text Search"
                      : rag_config.vector_store_config.store_type ===
                          "lancedb_vector"
                        ? "Vector Search"
                        : "Hybrid Search",
                  tooltip:
                    rag_config.vector_store_config.store_type === "lancedb_fts"
                      ? "Search using text matching only - fastest for keyword searches"
                      : rag_config.vector_store_config.store_type ===
                          "lancedb_vector"
                        ? "Search using semantic similarity vectors - best for meaning-based searches"
                        : "Combines text and vector search - best overall accuracy",
                },
                {
                  name: "Top K",
                  value: String(
                    rag_config.vector_store_config.properties
                      .similarity_top_k || 10,
                  ),
                  tooltip: "The number of top search results returned",
                },
              ]}
            />
          </div>
        </div>
      </div>
    {/if}
  </AppPage>
</div>

<EditDialog
  bind:this={edit_dialog}
  name="Search Tool"
  patch_url={`/api/projects/${project_id}/rag_configs/${rag_config_id}`}
  fields={[
    {
      label: "Search Tool Name",
      description: "A name to identify this search tool.",
      api_name: "name",
      value: rag_config?.name || "",
      input_type: "input",
    },
    {
      label: "Description",
      description: "A description of the search tool for you and your team.",
      api_name: "description",
      value: rag_config?.description || "",
      input_type: "textarea",
      optional: true,
    },
  ]}
/>
