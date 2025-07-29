<script lang="ts">
  import { page } from "$app/stores"
  import { client } from "$lib/api_client"
  import type {
    ExtractorConfig,
    RagConfig,
    ChunkerConfig,
    EmbeddingConfig,
  } from "$lib/types"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import AppPage from "../../../../../app_page.svelte"
  import PropertyList from "$lib/ui/property_list.svelte"
  import { onMount } from "svelte"
  import { formatDate } from "$lib/utils/formatters"

  $: project_id = $page.params.project_id
  $: rag_config_id = $page.params.rag_config_id

  let loading: boolean = false
  let error: KilnError | null = null
  let rag_config: RagConfig | null = null
  let extractor_config: ExtractorConfig | null = null
  let chunker_config: ChunkerConfig | null = null
  let embedding_config: EmbeddingConfig | null = null

  // Mock config progress - modify these states to test different scenarios
  let config_progress = {
    extraction: {
      state: "completed", // "pending" | "blocked" | "completed" | "error"
      progress: 100,
      message: "Successfully extracted content from 245 documents",
      documents_processed: 245,
      total_documents: 245,
      last_updated: "2024-01-15T10:30:00Z",
    },
    chunking: {
      state: "completed", // "pending" | "blocked" | "completed" | "error"
      progress: 100,
      message: "Generated 1,247 chunks from extracted content",
      chunks_created: 1247,
      avg_chunk_size: 512,
      last_updated: "2024-01-15T10:45:00Z",
    },
    embedding: {
      state: "error", // "pending" | "blocked" | "completed" | "error"
      progress: 65,
      message:
        "Embedding failed after processing 812 of 1,247 chunks. Quota exceeded for embedding provider.",
      chunks_embedded: 812,
      total_chunks: 1247,
      error_details: "Rate limit exceeded. Retry in 30 minutes.",
      last_updated: "2024-01-15T11:15:00Z",
    },
    indexing: {
      state: "pending", // "pending" | "blocked" | "completed" | "error"
      progress: 0,
      message: "Ready to index 812 embedded chunks into vector store",
      chunks_to_index: 812,
      last_updated: "2024-01-15T11:15:00Z",
    },
  }

  function get_step_indicator_class(step_key: keyof typeof config_progress) {
    const step = config_progress[step_key]
    if (!step) return "bg-gray-300"

    switch (step.state) {
      case "completed":
        return "bg-green-500"
      case "pending":
        return "bg-blue-500 animate-pulse"
      case "blocked":
        return "bg-gray-400"
      case "error":
        return "bg-red-500"
      default:
        return "bg-gray-300"
    }
  }

  function get_progress_icon(step_key: keyof typeof config_progress) {
    const step = config_progress[step_key]
    if (!step) return ""

    switch (step.state) {
      case "completed":
        return "✓"
      case "pending":
        return "●"
      case "blocked":
        return "⏸"
      case "error":
        return "!"
      default:
        return "?"
    }
  }

  function get_status_badge_class(state: string) {
    switch (state) {
      case "completed":
        return "badge-success"
      case "pending":
        return "badge-info"
      case "blocked":
        return "badge-warning"
      case "error":
        return "badge-error"
      default:
        return "badge-ghost"
    }
  }

  function get_status_text(state: string) {
    switch (state) {
      case "completed":
        return "Completed"
      case "pending":
        return "In Progress"
      case "blocked":
        return "Blocked"
      case "error":
        return "Error"
      default:
        return "Unknown"
    }
  }

  onMount(async () => {
    await get_rag_config()
    await get_rag_sub_configs()
  })

  async function get_rag_sub_configs() {
    await get_extractor_config()
    await get_chunker_config()
    await get_embedding_config()
  }

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

  async function get_extractor_config() {
    if (!rag_config?.extractor_config_id) {
      return
    }

    const { error: get_extractor_config_error, data: extractor_config_data } =
      await client.GET(
        "/api/projects/{project_id}/extractor_configs/{extractor_config_id}",
        {
          params: {
            path: {
              project_id,
              extractor_config_id: rag_config.extractor_config_id,
            },
          },
        },
      )

    if (get_extractor_config_error) {
      error = createKilnError(get_extractor_config_error)
      return
    }

    extractor_config = extractor_config_data
  }

  async function get_chunker_config() {
    if (!rag_config?.chunker_config_id) {
      return
    }

    const { error: get_chunker_config_error, data: chunker_config_data } =
      await client.GET(
        "/api/projects/{project_id}/chunker_configs/{chunker_config_id}",
        {
          params: {
            path: {
              project_id,
              chunker_config_id: rag_config.chunker_config_id,
            },
          },
        },
      )

    if (get_chunker_config_error) {
      error = createKilnError(get_chunker_config_error)
      return
    }

    chunker_config = chunker_config_data
  }

  async function get_embedding_config() {
    if (!rag_config?.embedding_config_id) {
      return
    }

    const { error: get_embedding_config_error, data: embedding_config_data } =
      await client.GET(
        "/api/projects/{project_id}/embedding_configs/{embedding_config_id}",
        {
          params: {
            path: {
              project_id,
              embedding_config_id: rag_config.embedding_config_id,
            },
          },
        },
      )

    if (get_embedding_config_error) {
      error = createKilnError(get_embedding_config_error)
      return
    }

    embedding_config = embedding_config_data
  }

  async function run_rag_config() {
    console.info("Running RAG config")
    await client.POST(
      "/api/projects/{project_id}/rag_configs/{rag_config_id}/run",
      {
        params: { path: { project_id, rag_config_id } },
      },
    )
    console.info("RAG config run")
  }
</script>

<AppPage
  title="RAG Pipeline"
  subtitle={loading ? "" : rag_config?.name || "Unknown"}
  action_buttons={[
    {
      label: "Run Pipeline",
      handler: run_rag_config,
    },
  ]}
>
  {#if loading}
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else}
    <div class="flex flex-col xl:flex-row gap-8 xl:gap-16">
      <div class="grow">
        <!-- Pipeline Flow with Timeline -->
        <div class="relative">
          <!-- Vertical timeline line -->
          <div class="absolute left-3 top-0 bottom-0 w-0.5 bg-neutral"></div>

          <!-- Stage 1: Extractor -->
          <div class="relative pl-16 mb-12">
            <!-- Timeline indicator with progress -->
            <div
              class="absolute left-0 top-2 flex items-center justify-center w-6 h-6 {get_step_indicator_class(
                'extraction',
              )} rounded-full border-4 border-white text-white text-xs font-bold"
            >
              {get_progress_icon("extraction")}
            </div>

            <div class="flex items-center gap-3 mb-4">
              <h3 class="text-lg font-medium">Content Extraction</h3>
              {#if extractor_config}
                <a
                  href={`/docs/extractors/${project_id}/${extractor_config.id}/extractor`}
                  class="text-sm text-gray-600 hover:text-gray-800 underline"
                >
                  View Extractor Details
                </a>
              {/if}
            </div>
            <div class="text-sm text-gray-500 mb-6">
              The Extractor is used to extract content from your documents.
            </div>

            {#if extractor_config}
              <PropertyList
                title="Configuration"
                properties={[
                  { name: "Name", value: extractor_config.name },
                  {
                    name: "Type",
                    value: extractor_config.extractor_type,
                    tooltip: "The extraction method used to process documents",
                  },
                  {
                    name: "Model",
                    value:
                      "" + extractor_config.properties?.model_name || "N/A",
                    tooltip: "The AI model used for extraction tasks",
                  },
                  {
                    name: "Output Format",
                    value: extractor_config.output_format,
                    tooltip:
                      "The format of the extracted content (e.g., text, markdown, json)",
                  },
                  {
                    name: "Description",
                    value: extractor_config.description || "None",
                  },
                ]}
              />

              <!-- Extraction Status -->
              <div class="mt-4 p-4 bg-gray-50 rounded-lg border">
                <div class="flex items-center justify-between mb-2">
                  <div class="flex items-center gap-2">
                    <span
                      class="badge {get_status_badge_class(
                        config_progress.extraction.state,
                      )}"
                    >
                      {get_status_text(config_progress.extraction.state)}
                    </span>
                    {#if config_progress.extraction.state === "pending"}
                      <div class="text-sm text-gray-500">
                        {config_progress.extraction.progress}% complete
                      </div>
                    {/if}
                  </div>
                  {#if config_progress.extraction.state === "pending"}
                    <button class="btn btn-sm btn-primary">
                      <div
                        class="loading loading-spinner loading-xs mr-1"
                      ></div>
                      Running...
                    </button>
                  {:else if config_progress.extraction.state === "error"}
                    <button class="btn btn-sm btn-error btn-outline">
                      Retry Extraction
                    </button>
                  {/if}
                </div>
                <div class="text-sm text-gray-600">
                  {config_progress.extraction.message}
                </div>
                {#if config_progress.extraction.state === "completed" && config_progress.extraction.documents_processed}
                  <div class="text-xs text-gray-500 mt-1">
                    Processed {config_progress.extraction.documents_processed}
                    of {config_progress.extraction.total_documents} documents
                  </div>
                {/if}
                {#if config_progress.extraction.state === "error" && "error_details" in config_progress.extraction && config_progress.extraction.error_details}
                  <div class="text-xs text-error mt-1">
                    {config_progress.extraction.error_details}
                  </div>
                {/if}
              </div>
            {:else}
              <div class="text-gray-500 text-sm">No extractor configured</div>
            {/if}
          </div>

          <!-- Stage 2: Chunker -->
          <div class="relative pl-16 mb-12">
            <!-- Timeline indicator with progress -->
            <div
              class="absolute left-0 top-2 flex items-center justify-center w-6 h-6 {get_step_indicator_class(
                'chunking',
              )} rounded-full border-4 border-white text-white text-xs font-bold"
            >
              {get_progress_icon("chunking")}
            </div>

            <h3 class="text-lg font-medium mb-4">Text Chunking</h3>
            <div class="text-sm text-gray-500 mb-6">
              The Chunker is used to split the content extracted from your
              documents into smaller chunks suitable for embedding.
            </div>

            {#if chunker_config}
              <PropertyList
                title="Configuration"
                properties={[
                  { name: "Name", value: chunker_config.name },
                  {
                    name: "Strategy",
                    value: chunker_config.chunker_type,
                    tooltip: "The method used to split text into chunks",
                  },
                  {
                    name: "Chunk Size",
                    value: chunker_config.properties?.chunk_size
                      ? `${String(chunker_config.properties.chunk_size)} tokens`
                      : "N/A",
                    tooltip:
                      "The maximum number of tokens per chunk. Larger chunks provide more context but may exceed model limits.",
                  },
                  {
                    name: "Overlap",
                    value: chunker_config.properties?.chunk_overlap
                      ? `${String(chunker_config.properties.chunk_overlap)} tokens`
                      : "N/A",
                    tooltip:
                      "Number of tokens that overlap between adjacent chunks to maintain context continuity",
                  },
                  {
                    name: "Description",
                    value: chunker_config.description || "None",
                  },
                ]}
              />

              <!-- Chunking Status -->
              <div class="mt-4 p-4 bg-gray-50 rounded-lg border">
                <div class="flex items-center justify-between mb-2">
                  <div class="flex items-center gap-2">
                    <span
                      class="badge {get_status_badge_class(
                        config_progress.chunking.state,
                      )}"
                    >
                      {get_status_text(config_progress.chunking.state)}
                    </span>
                    {#if config_progress.chunking.state === "pending"}
                      <div class="text-sm text-gray-500">
                        {config_progress.chunking.progress}% complete
                      </div>
                    {/if}
                  </div>
                  {#if config_progress.chunking.state === "pending"}
                    <button class="btn btn-sm btn-primary">
                      <div
                        class="loading loading-spinner loading-xs mr-1"
                      ></div>
                      Running...
                    </button>
                  {:else if config_progress.chunking.state === "error"}
                    <button class="btn btn-sm btn-error btn-outline">
                      Retry Chunking
                    </button>
                  {/if}
                </div>
                <div class="text-sm text-gray-600">
                  {config_progress.chunking.message}
                </div>
                {#if config_progress.chunking.state === "completed" && config_progress.chunking.chunks_created}
                  <div class="text-xs text-gray-500 mt-1">
                    Created {config_progress.chunking.chunks_created} chunks, avg
                    size {config_progress.chunking.avg_chunk_size} tokens
                  </div>
                {/if}
              </div>
            {:else}
              <div class="text-gray-500 text-sm">No chunker configured</div>
            {/if}
          </div>

          <!-- Stage 3: Embedding -->
          <div class="relative pl-16 mb-12">
            <!-- Timeline indicator with progress -->
            <div
              class="absolute left-0 top-2 flex items-center justify-center w-6 h-6 {get_step_indicator_class(
                'embedding',
              )} rounded-full border-4 border-white text-white text-xs font-bold"
            >
              {get_progress_icon("embedding")}
            </div>

            <h3 class="text-lg font-medium mb-4">Vector Embedding</h3>
            <div class="text-sm text-gray-500 mb-6">
              Your document chunks are turned into vector embeddings for
              similarity search.
            </div>

            {#if embedding_config}
              <PropertyList
                title="Configuration"
                properties={[
                  { name: "Name", value: embedding_config.name || "Unknown" },
                  {
                    name: "Provider",
                    value: embedding_config.model_provider_name || "Unknown",
                    tooltip:
                      "The AI service provider hosting the embedding model",
                  },
                  {
                    name: "Model",
                    value: String(
                      embedding_config.properties?.model_name || "N/A",
                    ),
                    tooltip:
                      "The specific embedding model used to convert text into numerical vectors",
                  },
                  {
                    name: "Description",
                    value: embedding_config.description || "None",
                  },
                ]}
              />

              <!-- Embedding Status -->
              <div class="mt-4 p-4 bg-gray-50 rounded-lg border">
                <div class="flex items-center justify-between mb-2">
                  <div class="flex items-center gap-2">
                    <span
                      class="badge {get_status_badge_class(
                        config_progress.embedding.state,
                      )}"
                    >
                      {get_status_text(config_progress.embedding.state)}
                    </span>
                    {#if config_progress.embedding.state === "pending"}
                      <div class="text-sm text-gray-500">
                        {config_progress.embedding.progress}% complete
                      </div>
                    {:else if config_progress.embedding.state === "error"}
                      <div class="text-sm text-error">
                        {config_progress.embedding.progress}% complete (failed)
                      </div>
                    {/if}
                  </div>
                  {#if config_progress.embedding.state === "pending"}
                    <button class="btn btn-sm btn-primary">
                      <div
                        class="loading loading-spinner loading-xs mr-1"
                      ></div>
                      Running...
                    </button>
                  {:else if config_progress.embedding.state === "error"}
                    <button class="btn btn-sm btn-error btn-outline">
                      Resume Embedding
                    </button>
                  {/if}
                </div>
                <div class="text-sm text-gray-600">
                  {config_progress.embedding.message}
                </div>
                {#if (config_progress.embedding.state === "completed" || config_progress.embedding.state === "error") && config_progress.embedding.chunks_embedded}
                  <div class="text-xs text-gray-500 mt-1">
                    Embedded {config_progress.embedding.chunks_embedded} of {config_progress
                      .embedding.total_chunks} chunks
                  </div>
                {/if}
                {#if config_progress.embedding.state === "error" && "error_details" in config_progress.embedding && config_progress.embedding.error_details}
                  <div class="text-xs text-error mt-1">
                    {config_progress.embedding.error_details}
                  </div>
                {/if}
              </div>
            {:else}
              <div class="text-gray-500 text-sm">
                No embedding model configured
              </div>
            {/if}
          </div>

          <!-- Stage 4: Indexing -->
          <div class="relative pl-16">
            <!-- Timeline indicator with progress -->
            <div
              class="absolute left-0 top-2 flex items-center justify-center w-6 h-6 {get_step_indicator_class(
                'indexing',
              )} rounded-full border-4 border-white text-white text-xs font-bold"
            >
              {get_progress_icon("indexing")}
            </div>

            <h3 class="text-lg font-medium mb-4">Vector Store Indexing</h3>
            <div class="text-sm text-gray-500 mb-6">
              The transformed chunks are indexed in a local vector store for
              similarity search.
            </div>

            <PropertyList
              title="Configuration"
              properties={[
                { name: "Vector Store", value: "Local LanceDB" },
                {
                  name: "Index Type",
                  value: "HNSW",
                },
                {
                  name: "Distance Metric",
                  value: "Cosine Similarity",
                },
              ]}
            />

            <!-- Indexing Status -->
            <div class="mt-4 p-4 bg-gray-50 rounded-lg border">
              <div class="flex items-center justify-between mb-2">
                <div class="flex items-center gap-2">
                  <span
                    class="badge {get_status_badge_class(
                      config_progress.indexing.state,
                    )}"
                  >
                    {get_status_text(config_progress.indexing.state)}
                  </span>
                  {#if config_progress.indexing.state === "pending"}
                    <div class="text-sm text-gray-500">
                      {config_progress.indexing.progress}% complete
                    </div>
                  {/if}
                </div>
                {#if config_progress.indexing.state === "pending"}
                  <button class="btn btn-sm btn-primary">
                    <div class="loading loading-spinner loading-xs mr-1"></div>
                    Indexing...
                  </button>
                {:else if config_progress.indexing.state === "completed"}
                  <button class="btn btn-sm btn-outline"> Reindex </button>
                {:else}
                  <button class="btn btn-sm btn-primary">
                    Start Indexing
                  </button>
                {/if}
              </div>
              <div class="text-sm text-gray-600">
                {config_progress.indexing.message}
              </div>
              {#if config_progress.indexing.chunks_to_index}
                <div class="text-xs text-gray-500 mt-1">
                  {config_progress.indexing.chunks_to_index} chunks ready for indexing
                </div>
              {/if}
            </div>
          </div>
        </div>
      </div>

      <div class="w-72 2xl:w-96 flex-none flex flex-col gap-4">
        {#if rag_config}
          <PropertyList
            title="Configuration Details"
            properties={[
              { name: "ID", value: rag_config.id || "Unknown" },
              { name: "Name", value: rag_config.name || "Unknown" },
              { name: "Created At", value: formatDate(rag_config.created_at) },
              { name: "Created By", value: rag_config.created_by || "Unknown" },
              { name: "Description", value: rag_config.description || "None" },
            ]}
          />
        {/if}
      </div>
    </div>

    {#if error}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="text-error text-sm">
          {error.getMessage() || "An unknown error occurred"}
        </div>
      </div>
    {/if}
  {/if}
</AppPage>
