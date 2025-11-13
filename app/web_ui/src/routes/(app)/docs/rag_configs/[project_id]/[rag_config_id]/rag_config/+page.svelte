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
    available_model_details,
    available_models,
    reranker_name,
    load_available_reranker_models,
  } from "$lib/stores"
  import type { AvailableModels } from "$lib/types"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
  import Output from "../../../../../run/output.svelte"
  import EditDialog from "$lib/ui/edit_dialog.svelte"
  import { mime_type_to_string } from "$lib/utils/formatters"
  import { update_rag_config_archived_state } from "$lib/stores/rag_progress_store"
  import Warning from "$lib/ui/warning.svelte"
  import posthog from "posthog-js"
  import { uncache_available_tools } from "$lib/stores"
  import { goto } from "$app/navigation"
  import {
    fixedWindowChunkerProperties,
    semanticChunkerProperties,
  } from "$lib/utils/properties_cast"
  import FixedWindowChunkerPropertyList from "./fixed_window_chunker_property_list.svelte"
  import SemanticChunkerPropertyList from "./semantic_chunker_property_list.svelte"

  $: project_id = $page.params.project_id
  $: rag_config_id = $page.params.rag_config_id

  let loading: boolean = false
  let error: KilnError | null = null
  let update_error: KilnError | null = null
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
    await Promise.all([
      load_available_models(),
      load_available_embedding_models(),
      load_available_reranker_models(),
      get_rag_config(),
    ])
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

  async function update_archived_state(is_archived: boolean) {
    try {
      update_error = null
      const { error: update_archived_state_error } = await client.PATCH(
        "/api/projects/{project_id}/rag_configs/{rag_config_id}",
        {
          body: { is_archived },
          params: {
            path: {
              project_id,
              rag_config_id,
            },
          },
        },
      )

      if (update_archived_state_error) {
        throw update_archived_state_error
      }

      // update the store to make sure state gets reflected everywhere
      await update_rag_config_archived_state(
        project_id,
        rag_config_id,
        is_archived,
      )

      await get_rag_config()
    } catch (e) {
      update_error = createKilnError(e)
    } finally {
      loading = false
    }

    uncache_available_tools(project_id)

    posthog.capture(
      is_archived ? "archive_rag_config" : "unarchive_rag_config",
      {},
    )
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

  $: sorted_tags = rag_config?.tags ? rag_config.tags.toSorted() : null

  function build_supported_file_types(
    available_models: AvailableModels[],
    model_name: string | undefined,
    model_provider_name: string | undefined,
  ) {
    if (!model_name || !model_provider_name || !available_models) {
      return []
    }
    const model_details = available_model_details(
      model_name,
      model_provider_name,
      available_models,
    )
    const mime_types = model_details?.multimodal_mime_types || []
    return mime_types.map(mime_type_to_string)
  }
  $: supported_file_types = build_supported_file_types(
    $available_models,
    rag_config?.extractor_config?.model_name,
    rag_config?.extractor_config?.model_provider_name,
  )

  $: fixed_window_properties =
    rag_config?.chunker_config.chunker_type === "fixed_window"
      ? fixedWindowChunkerProperties(rag_config.chunker_config)
      : null
  $: semantic_properties =
    rag_config?.chunker_config.chunker_type === "semantic"
      ? semanticChunkerProperties(rag_config.chunker_config)
      : null
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Search Tool (RAG)"
    subtitle={rag_config?.name ? `Name: ${rag_config.name}` : undefined}
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
    ]}
    action_buttons={[
      ...(rag_config?.is_archived
        ? []
        : [
            {
              label: "Edit",
              handler: () => {
                edit_dialog?.show()
              },
            },
          ]),
      {
        label: "Clone",
        handler: () => {
          goto(
            `/docs/rag_configs/${project_id}/${rag_config_id}/rag_config/clone`,
          )
        },
      },
      {
        label: rag_config?.is_archived ? "Unarchive" : "Archive",
        primary: rag_config?.is_archived,
        handler: () => {
          if (!rag_config) {
            return
          }

          // flip the archived state
          const new_is_archived = !rag_config.is_archived
          update_archived_state(new_is_archived)
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
        <div class="text-error text-sm">
          Search Tool configuration not found
        </div>
      </div>
    {:else}
      {#if update_error}
        <div class="my-4 text-error">
          <span>{update_error.getMessage() || "Update failed"}</span>
        </div>
      {/if}
      {#if rag_config?.is_archived}
        <Warning
          warning_message="This Search Tool is archived. You may unarchive it to use it again."
          large_icon={true}
          warning_color="warning"
          outline={true}
        />
      {/if}
      <div class="flex flex-col lg:flex-row gap-8 xl:gap-12">
        <!-- Main Content - Search Section -->
        <div class="flex-1">
          <div class="text-xl font-bold mb-1">Test Search Tool</div>
          <div class="text-sm text-gray-500 mb-2">
            Run your search tool, without connecting it to an AI task.
            <span class="text-gray-500">
              <InfoTooltip
                tooltip_text="This UI runs your search tool (RAG) and shows the search results (chunks), without sending the results to an AI task. To use it in an AI task, select this search tool from the 'Tools' dropdown in the 'Advanced' section of the 'Run' page."
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
                    disabled={searchLoading || rag_config?.is_archived}
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
                {
                  name: "Tool Name",
                  value: rag_config.tool_name,
                  tooltip: "The tool name the model sees and calls.",
                },
                {
                  name: "Tool Description",
                  value: rag_config.tool_description,
                  tooltip: "The tool description the model sees.",
                },
                {
                  name: "Reference Name",
                  tooltip:
                    "A name to identify this RAG configuration for your own reference, not seen by the model.",
                  value: rag_config.name || "N/A",
                },
                {
                  name: "Reference Description",
                  tooltip:
                    "A description of the RAG configuration for your own reference, not seen by the model.",
                  value: rag_config.description || "N/A",
                },
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
                ...(supported_file_types.length > 0
                  ? [
                      {
                        name: "Supported File Types",
                        value:
                          supported_file_types.length == 1
                            ? "1 file type"
                            : `${supported_file_types.length} file types`,
                        tooltip: supported_file_types.join(", "),
                      },
                    ]
                  : []),
              ]}
            />

            {#if semantic_properties}
              <SemanticChunkerPropertyList
                {project_id}
                buffer_size={semantic_properties.buffer_size}
                breakpoint_percentile_threshold={semantic_properties.breakpoint_percentile_threshold}
                embedding_config_id={semantic_properties.embedding_config_id}
              />
            {/if}

            {#if fixed_window_properties}
              <FixedWindowChunkerPropertyList
                chunk_size={fixed_window_properties.chunk_size}
                chunk_overlap={fixed_window_properties.chunk_overlap}
              />
            {/if}

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
                  tooltip:
                    "The number of top search results returned. If a reranker is used, this will be the number of results passed to the reranker. If no reranker is used, this will be the number of results returned to the LLM.",
                },
              ]}
            />
            {#if rag_config.reranker_config}
              <PropertyList
                title="Reranker"
                properties={[
                  {
                    name: "Model Provider",
                    value:
                      provider_name_from_id(
                        rag_config.reranker_config.model_provider_name,
                      ) || "N/A",
                  },
                  {
                    name: "Model",
                    value:
                      reranker_name(
                        rag_config.reranker_config.model_name,
                        rag_config.reranker_config.model_provider_name,
                      ) || "N/A",
                  },
                  {
                    name: "Top N",
                    value: String(rag_config.reranker_config.top_n || 5),
                    tooltip:
                      "The number of chunks to return after reranking. The results from the vector store are reranked by the reranker model and the top N results are returned and passed to the LLM.",
                  },
                ]}
              />
            {:else}
              <div>
                <div class="text-xl font-bold mb-1">Reranker</div>
                <div class="flex flex-row flex-wrap gap-2 text-sm items-center">
                  No reranker configured.
                </div>
              </div>
            {/if}
            <div>
              <div class="text-xl font-bold mb-1">Documents</div>
              <div class="flex flex-row flex-wrap gap-2 text-sm items-center">
                {#if sorted_tags && sorted_tags.length > 0}
                  Documents with the {sorted_tags.length == 1 ? "tag" : "tags"}
                  {#each sorted_tags as tag}
                    <div
                      class="badge bg-gray-200 text-gray-500 py-3 px-3 max-w-full"
                    >
                      <span class="truncate">{tag}</span>
                    </div>
                  {/each}
                {:else}
                  All documents in library.
                {/if}
              </div>
            </div>
          </div>
        </div>
      </div>
    {/if}
  </AppPage>
</div>

<EditDialog
  bind:this={edit_dialog}
  after_save={() => {
    uncache_available_tools(project_id)
  }}
  name="Search Tool"
  subtitle="You can't edit the tool name/description that the model sees, which are different from reference name/description below. If that's your goal, create a new search tool with the same configuration and new name/description."
  patch_url={`/api/projects/${project_id}/rag_configs/${rag_config_id}`}
  fields={[
    {
      label: "Reference Name",
      description:
        "A name to identify this search tool for your own reference, not seen by the model.",
      api_name: "name",
      value: rag_config?.name || "",
      input_type: "input",
    },
    {
      label: "Reference Description",
      description:
        "A description of the search tool for your own reference, not seen by the model.",
      api_name: "description",
      value: rag_config?.description || "",
      input_type: "textarea",
      optional: true,
    },
  ]}
/>
