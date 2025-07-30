<script lang="ts">
  import { page } from "$app/stores"
  import { client } from "$lib/api_client"
  import type {
    ExtractorConfig,
    RagConfig,
    ChunkerConfig,
    EmbeddingConfig,
    RagProgress,
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

  let config_progress: RagProgress | null = null

  // Logs state
  let extraction_logs_expanded = false
  let chunking_logs_expanded = false
  let embedding_logs_expanded = false
  let logs_error: string | null = null

  // Placeholder logs for demonstration
  const extraction_logs = `[2024-01-15 10:30:15] INFO - Starting document extraction process
[2024-01-15 10:30:16] INFO - Loaded extractor configuration: gpt-4-turbo
[2024-01-15 10:30:17] INFO - Processing document: financial_report_2024.pdf
[2024-01-15 10:30:18] INFO - Extracted 1,247 tokens from page 1
[2024-01-15 10:30:19] INFO - Extracted 1,156 tokens from page 2
[2024-01-15 10:30:20] INFO - Extracted 1,334 tokens from page 3
[2024-01-15 10:30:21] INFO - Processing document: quarterly_summary.pdf
[2024-01-15 10:30:22] INFO - Extracted 892 tokens from page 1
[2024-01-15 10:30:23] INFO - Extracted 1,078 tokens from page 2
[2024-01-15 10:30:24] INFO - Completed extraction for 2 documents
[2024-01-15 10:30:25] INFO - Total tokens extracted: 5,707
[2024-01-15 10:30:26] INFO - Extraction process completed successfully`

  const chunking_logs = `[2024-01-15 10:30:30] INFO - Starting text chunking process
[2024-01-15 10:30:31] INFO - Using chunking strategy: fixed_window
[2024-01-15 10:30:32] INFO - Chunk size: 512 tokens, Overlap: 50 tokens
[2024-01-15 10:30:33] INFO - Processing document: financial_report_2024.pdf
[2024-01-15 10:30:34] INFO - Created 12 chunks from document
[2024-01-15 10:30:35] INFO - Processing document: quarterly_summary.pdf
[2024-01-15 10:30:36] INFO - Created 8 chunks from document
[2024-01-15 10:30:37] INFO - Total chunks created: 20
[2024-01-15 10:30:38] INFO - Average chunk size: 285.35 tokens
[2024-01-15 10:30:39] INFO - Chunking process completed successfully`

  const embedding_logs = `[2024-01-15 10:30:45] INFO - Starting vector embedding process
[2024-01-15 10:30:46] INFO - Using embedding model: text-embedding-3-small
[2024-01-15 10:30:47] INFO - Embedding dimension: 1536
[2024-01-15 10:30:48] INFO - Processing chunk 1/20
[2024-01-15 10:30:49] INFO - Processing chunk 2/20
[2024-01-15 10:30:50] INFO - Processing chunk 3/20
[2024-01-15 10:30:51] INFO - Processing chunk 4/20
[2024-01-15 10:30:52] INFO - Processing chunk 5/20
[2024-01-15 10:30:53] INFO - Processing chunk 6/20
[2024-01-15 10:30:54] INFO - Processing chunk 7/20
[2024-01-15 10:30:55] INFO - Processing chunk 8/20
[2024-01-15 10:30:56] INFO - Processing chunk 9/20
[2024-01-15 10:30:57] INFO - Processing chunk 10/20
[2024-01-15 10:30:58] INFO - Processing chunk 11/20
[2024-01-15 10:30:59] INFO - Processing chunk 12/20
[2024-01-15 10:31:00] INFO - Processing chunk 13/20
[2024-01-15 10:31:01] INFO - Processing chunk 14/20
[2024-01-15 10:31:02] INFO - Processing chunk 15/20
[2024-01-15 10:31:03] INFO - Processing chunk 16/20
[2024-01-15 10:31:04] INFO - Processing chunk 17/20
[2024-01-15 10:31:05] INFO - Processing chunk 18/20
[2024-01-15 10:31:06] INFO - Processing chunk 19/20
[2024-01-15 10:31:07] INFO - Processing chunk 20/20
[2024-01-15 10:31:08] INFO - All chunks embedded successfully
[2024-01-15 10:31:09] INFO - Embedding process completed successfully`

  function copy_logs_to_clipboard(logs: string) {
    navigator.clipboard.writeText(logs)
  }

  function download_logs(logs: string, step_name: string) {
    const blob = new Blob([logs], { type: "text/plain" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `${step_name}_logs_${new Date().toISOString().split("T")[0]}.txt`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  // Reactive progress values that update when config_progress changes
  $: extraction_progress_value = get_step_progress_value(
    "extraction",
    config_progress,
  )
  $: chunking_progress_value = get_step_progress_value(
    "chunking",
    config_progress,
  )
  $: embedding_progress_value = get_step_progress_value(
    "embedding",
    config_progress,
  )

  // Reactive max values for progress bars
  $: progress_max = config_progress?.total_document_count || 100

  // Overall pipeline status calculation (same logic as table component)
  $: total_docs = config_progress?.total_document_count || 0
  $: completed_pct =
    total_docs > 0
      ? Math.round(
          ((config_progress?.total_document_completed_count || 0) /
            total_docs) *
            100,
        )
      : 0
  $: overall_status = (() => {
    if (completed_pct === 100)
      return {
        text: "Complete",
        color: "badge-primary",
        bg: "bg-primary/10",
        border: "border-primary/20",
        icon: "✓",
        iconColor: "text-primary",
      }
    if (completed_pct > 0)
      return {
        text: "In Progress",
        color: "badge-warning",
        bg: "bg-warning/10",
        border: "border-warning/20",
        icon: "●",
        iconColor: "text-warning",
      }
    return {
      text: "Not Started",
      color: "badge-neutral",
      bg: "bg-neutral/10",
      border: "border-neutral/20",
      icon: "○",
      iconColor: "text-neutral",
    }
  })()

  function toggle_extraction_logs() {
    extraction_logs_expanded = !extraction_logs_expanded
  }

  function toggle_chunking_logs() {
    chunking_logs_expanded = !chunking_logs_expanded
  }

  function toggle_embedding_logs() {
    embedding_logs_expanded = !embedding_logs_expanded
  }

  async function view_logs() {
    try {
      const { error } = await client.POST("/api/open_logs", {})
      if (error) {
        const errorMessage = (error as Record<string, unknown>)?.message
        if (typeof errorMessage === "string") {
          throw new Error(errorMessage)
        } else {
          throw new Error("Unknown error")
        }
      }
    } catch (e) {
      logs_error = "Failed to open logs: " + e
    }
  }

  function get_progress_icon(
    step: string,
    config_progress: RagProgress | null,
  ) {
    const status = get_status_for_step(step, config_progress)

    switch (status) {
      case "completed":
        return "✓"
      case "pending":
        return "●"
      default:
        return "?"
    }
  }

  function get_progress_icon_color(
    step: string,
    config_progress: RagProgress | null,
  ) {
    const status = get_status_for_step(step, config_progress)
    switch (status) {
      case "completed":
        return "bg-primary"
      case "pending":
        return "bg-warning"
      default:
        return "bg-neutral"
    }
  }

  function is_step_completed(
    step: string,
    config_progress: RagProgress | null,
  ): boolean {
    return get_status_for_step(step, config_progress) === "completed"
  }

  function get_step_container_classes(
    step: string,
    config_progress: RagProgress | null,
  ): string {
    const baseClasses =
      "flex flex-col gap-2 max-w-2xl rounded-md border transition-all duration-300"
    const isCompleted = is_step_completed(step, config_progress)

    if (isCompleted) {
      return `${baseClasses} border-primary/40 shadow-sm`
    }

    return `${baseClasses} border-base-300`
  }

  function get_timeline_indicator_classes(
    step: string,
    config_progress: RagProgress | null,
  ): string {
    const baseClasses =
      "absolute left-0 top-2 flex items-center justify-center w-6 h-6 rounded-full border-4 border-white text-white text-xs font-bold transition-all duration-300"
    const isCompleted = is_step_completed(step, config_progress)

    if (isCompleted) {
      return `${baseClasses} ${get_progress_icon_color(step, config_progress)} shadow-lg ring-2 ring-primary/20`
    }

    return `${baseClasses} ${get_progress_icon_color(step, config_progress)}`
  }

  function get_timeline_bar_classes(
    config_progress: RagProgress | null,
  ): string {
    const baseClasses =
      "absolute left-3 top-0 bottom-0 w-0.5 transition-all duration-500"

    // Check if any step is completed to determine timeline color
    const extractionCompleted = is_step_completed("extraction", config_progress)
    const chunkingCompleted = is_step_completed("chunking", config_progress)
    const embeddingCompleted = is_step_completed("embedding", config_progress)

    if (extractionCompleted || chunkingCompleted || embeddingCompleted) {
      return `${baseClasses} bg-gradient-to-b from-primary to-primary/60`
    }

    return `${baseClasses} bg-neutral`
  }

  onMount(async () => {
    await get_rag_config()
    await get_rag_sub_configs()
    await get_rag_config_progress()
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

  async function get_rag_config_progress() {
    const { data: progress_data, error: get_error } = await client.POST(
      "/api/projects/{project_id}/rag_configs/progress",
      {
        params: { path: { project_id } },
        body: {
          rag_config_ids: [rag_config_id],
        },
      },
    )
    if (get_error) {
      throw get_error
    }

    config_progress = progress_data[rag_config_id]
    console.log("RAG Config Progress:", config_progress)
  }

  function get_status_for_step(
    step: string,
    config_progress: RagProgress | null,
  ) {
    if (!config_progress) return "pending"

    switch (step) {
      case "extraction": {
        if (config_progress.total_document_count === 0) {
          return "pending"
        }
        return config_progress.total_document_extracted_count >=
          config_progress.total_document_count
          ? "completed"
          : "pending"
      }
      case "chunking": {
        if (config_progress.total_document_count === 0) {
          return "pending"
        }
        return config_progress.total_document_chunked_count >=
          config_progress.total_document_count
          ? "completed"
          : "pending"
      }
      case "embedding": {
        if (config_progress.total_document_count === 0) {
          return "pending"
        }
        return config_progress.total_document_embedded_count >=
          config_progress.total_document_count
          ? "completed"
          : "pending"
      }
      default:
        return "pending"
    }
  }

  function get_step_status_info(
    step: string,
    config_progress: RagProgress | null,
  ) {
    const percentage = get_step_progress_percentage(step, config_progress)

    if (percentage === 100) {
      return {
        text: "Complete",
        color: "badge-primary",
        bg: "bg-primary/10",
        border: "border-primary/20",
      }
    }
    if (percentage > 0) {
      return {
        text: "In Progress",
        color: "badge-warning",
        bg: "bg-warning/10",
        border: "border-warning/20",
      }
    }
    return {
      text: "Not Started",
      color: "badge-neutral",
      bg: "bg-neutral/10",
      border: "border-neutral/20",
    }
  }

  function get_step_progress_percentage(
    step: string,
    config_progress: RagProgress | null,
  ) {
    if (!config_progress || config_progress.total_document_count === 0) {
      return 0
    }

    let result = 0
    switch (step) {
      case "extraction":
        result = Math.round(
          (config_progress.total_document_extracted_count /
            config_progress.total_document_count) *
            100,
        )
        return result
      case "chunking":
        result = Math.round(
          (config_progress.total_document_chunked_count /
            config_progress.total_document_count) *
            100,
        )
        return result
      case "embedding":
        result = Math.round(
          (config_progress.total_document_embedded_count /
            config_progress.total_document_count) *
            100,
        )
        return result
      default:
        return 0
    }
  }

  function get_step_progress_value(
    step: string,
    config_progress: RagProgress | null,
  ) {
    if (!config_progress) return 0

    switch (step) {
      case "extraction":
        return config_progress.total_document_extracted_count
      case "chunking":
        return config_progress.total_document_chunked_count
      case "embedding":
        return config_progress.total_document_embedded_count
      default:
        return 0
    }
  }
</script>

<AppPage
  title="RAG Pipeline"
  subtitle={loading ? "" : rag_config?.name || "Unknown"}
  action_buttons={[
    {
      label: "Run",
      handler: run_rag_config,
      primary: true,
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
          <div class={get_timeline_bar_classes(config_progress)}></div>

          <!-- Stage 1: Extractor -->
          <div class="relative pl-16 mb-6 flex flex-col gap-2">
            <!-- Timeline indicator with progress -->
            <div
              class={get_timeline_indicator_classes(
                "extraction",
                config_progress,
              )}
            >
              {get_progress_icon("extraction", config_progress)}
            </div>

            <div class="flex flex-col gap-2">
              <div
                class={get_step_container_classes(
                  "extraction",
                  config_progress,
                )}
              >
                <div class="p-4">
                  <div class="flex items-center gap-3">
                    <h3 class="text-lg font-medium">Extraction</h3>
                    {#if extractor_config}
                      <a
                        href={`/docs/extractors/${project_id}/${extractor_config.id}/extractor`}
                        class="text-sm text-gray-600 hover:text-gray-800 underline"
                      >
                        View Extractor Details
                      </a>
                    {/if}
                  </div>
                  <div class="text-sm text-gray-500 mb-2">
                    Extract content from your documents.
                  </div>

                  <!-- Status Badge and Progress Bar -->
                  <div class="flex items-center justify-between mb-3">
                    <div
                      class="badge {get_step_status_info(
                        'extraction',
                        config_progress,
                      ).color} badge-outline text-xs font-medium"
                    >
                      {get_step_status_info("extraction", config_progress).text}
                    </div>
                    <span class="text-sm text-base-content/60"
                      >{get_step_progress_percentage(
                        "extraction",
                        config_progress,
                      )}%</span
                    >
                  </div>
                  <progress
                    class="progress progress-primary bg-primary/20 w-full h-2 mb-2"
                    value={extraction_progress_value}
                    max={progress_max}
                  ></progress>
                  {#if config_progress && config_progress.total_document_count > 0}
                    <div class="text-xs text-base-content/50 text-start mb-3">
                      {extraction_progress_value} of {config_progress.total_document_count}
                      documents processed
                    </div>
                  {/if}

                  <!-- Config Details -->
                  <div class="p-4 rounded-md bg-gray-50 mb-4">
                    {#if extractor_config}
                      <PropertyList
                        properties={[
                          {
                            name: "Model Provider",
                            value: extractor_config.model_provider_name,
                          },
                          {
                            name: "Model",
                            value:
                              "" + extractor_config.properties?.model_name ||
                              "N/A",
                          },
                          {
                            name: "Output Format",
                            value: extractor_config.output_format,
                            tooltip:
                              "The format of the extracted content (e.g., text, markdown, json)",
                          },
                        ]}
                      />
                    {:else}
                      <div class="text-gray-500 text-sm">
                        No extractor configured
                      </div>
                    {/if}
                  </div>

                  <!-- Expandable Logs -->
                  <div class="flex items-center justify-end mb-3 gap-2">
                    <button
                      on:click={toggle_extraction_logs}
                      class="inline-flex items-center px-2 py-1 text-xs leading-4 font-medium rounded-md text-base-content/60 bg-base-200 hover:bg-base-300 focus:outline-none focus:ring-offset-0 focus:ring-0 transition-colors duration-150"
                      title={extraction_logs_expanded
                        ? "Hide extraction logs"
                        : "Show extraction logs"}
                    >
                      <svg
                        class="h-3 w-3 mr-1"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          stroke-linecap="round"
                          stroke-linejoin="round"
                          stroke-width="2"
                          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                        />
                      </svg>
                      {extraction_logs_expanded ? "Hide" : "Show"} Logs
                    </button>
                  </div>
                </div>
                <!-- Collapsible Logs -->
                {#if extraction_logs_expanded}
                  <div class="border-t p-4 rounded-b-md bg-gray-50">
                    <div class="flex items-center justify-between mb-3">
                      <h4 class="text-sm font-medium text-base-content">
                        Extraction Logs
                      </h4>
                      <div class="flex items-center gap-2">
                        <button
                          on:click={() =>
                            copy_logs_to_clipboard(extraction_logs)}
                          class="btn btn-sm btn-square btn-outline"
                          title="Copy logs to clipboard"
                        >
                          <svg
                            class="w-4 h-4"
                            viewBox="0 0 64 64"
                            xmlns="http://www.w3.org/2000/svg"
                            stroke-width="3"
                            stroke="currentColor"
                            fill="none"
                          >
                            <rect
                              x="11.13"
                              y="17.72"
                              width="33.92"
                              height="36.85"
                              rx="2.5"
                            />
                            <path
                              d="M19.35,14.23V13.09a3.51,3.51,0,0,1,3.33-3.66H49.54a3.51,3.51,0,0,1,3.33,3.66V42.62a3.51,3.51,0,0,1-3.33,3.66H48.39"
                            />
                          </svg>
                        </button>
                        <button
                          on:click={() =>
                            download_logs(extraction_logs, "extraction")}
                          class="btn btn-sm btn-outline btn-primary"
                        >
                          Download
                        </button>
                        <button
                          on:click={view_logs}
                          class="btn btn-sm btn-outline"
                        >
                          Open Folder
                        </button>
                      </div>
                    </div>
                    {#if logs_error}
                      <div class="text-error text-sm mb-3">{logs_error}</div>
                    {/if}
                    <div class="bg-base-200 rounded border overflow-hidden">
                      <pre
                        class="text-xs font-mono text-base-content/80 p-3 max-h-48 overflow-y-auto whitespace-pre-wrap">{extraction_logs}</pre>
                    </div>
                  </div>
                {/if}
              </div>
            </div>
          </div>

          <!-- Stage 2: Chunker -->
          <div class="relative pl-16 mb-6">
            <!-- Timeline indicator with progress -->
            <div
              class={get_timeline_indicator_classes(
                "chunking",
                config_progress,
              )}
            >
              {get_progress_icon("chunking", config_progress)}
            </div>

            <div class="flex flex-col gap-2">
              <div
                class={get_step_container_classes("chunking", config_progress)}
              >
                <div class="p-4">
                  <div class="flex items-center gap-3">
                    <h3 class="text-lg font-medium">Text Chunking</h3>
                  </div>
                  <div class="text-sm text-gray-500 mb-2">
                    Split the content from your documents into smaller chunks.
                  </div>

                  <!-- Status Badge and Progress Bar -->
                  <div class="flex items-center justify-between mb-3">
                    <div
                      class="badge {get_step_status_info(
                        'chunking',
                        config_progress,
                      ).color} badge-outline text-xs font-medium"
                    >
                      {get_step_status_info("chunking", config_progress).text}
                    </div>
                    <span class="text-sm text-base-content/60"
                      >{get_step_progress_percentage(
                        "chunking",
                        config_progress,
                      )}%</span
                    >
                  </div>
                  <progress
                    class="progress progress-primary bg-primary/20 w-full h-2 mb-2"
                    value={chunking_progress_value}
                    max={progress_max}
                  ></progress>
                  {#if config_progress && config_progress.total_document_count > 0}
                    <div class="text-xs text-base-content/50 text-start mb-3">
                      {chunking_progress_value} of {config_progress.total_document_count}
                      documents processed
                    </div>
                  {/if}

                  <!-- Config Details -->
                  <div class="p-4 rounded-md bg-gray-50 mb-4">
                    {#if chunker_config}
                      <PropertyList
                        properties={[
                          {
                            name: "Strategy",
                            value: chunker_config.chunker_type,
                            tooltip:
                              "The method used to split text into chunks",
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
                        ]}
                      />
                    {:else}
                      <div class="text-gray-500 text-sm">
                        No chunker configured
                      </div>
                    {/if}
                  </div>

                  <!-- Expandable Logs -->
                  <div class="flex items-center justify-end mb-3 gap-2">
                    <button
                      on:click={toggle_chunking_logs}
                      class="inline-flex items-center px-2 py-1 text-xs leading-4 font-medium rounded-md text-base-content/60 bg-base-200 hover:bg-base-300 focus:outline-none focus:ring-offset-0 focus:ring-0 transition-colors duration-150"
                      title={chunking_logs_expanded
                        ? "Hide chunking logs"
                        : "Show chunking logs"}
                    >
                      <svg
                        class="h-3 w-3 mr-1"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          stroke-linecap="round"
                          stroke-linejoin="round"
                          stroke-width="2"
                          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                        />
                      </svg>
                      {chunking_logs_expanded ? "Hide" : "Show"} Logs
                    </button>
                  </div>
                </div>

                <!-- Collapsible Logs -->
                {#if chunking_logs_expanded}
                  <div class="border-t p-4 rounded-b-md bg-gray-50">
                    <div class="flex items-center justify-between mb-3">
                      <h4 class="text-sm font-medium text-base-content">
                        Chunking Logs
                      </h4>
                      <div class="flex items-center gap-2">
                        <button
                          on:click={() => copy_logs_to_clipboard(chunking_logs)}
                          class="btn btn-sm btn-square btn-outline"
                          title="Copy logs to clipboard"
                        >
                          <svg
                            class="w-4 h-4"
                            viewBox="0 0 64 64"
                            xmlns="http://www.w3.org/2000/svg"
                            stroke-width="3"
                            stroke="currentColor"
                            fill="none"
                          >
                            <rect
                              x="11.13"
                              y="17.72"
                              width="33.92"
                              height="36.85"
                              rx="2.5"
                            />
                            <path
                              d="M19.35,14.23V13.09a3.51,3.51,0,0,1,3.33-3.66H49.54a3.51,3.51,0,0,1,3.33,3.66V42.62a3.51,3.51,0,0,1-3.33,3.66H48.39"
                            />
                          </svg>
                        </button>
                        <button
                          on:click={() =>
                            download_logs(chunking_logs, "chunking")}
                          class="btn btn-sm btn-outline btn-primary"
                        >
                          Download
                        </button>
                        <button
                          on:click={view_logs}
                          class="btn btn-sm btn-outline"
                        >
                          Open Folder
                        </button>
                      </div>
                    </div>
                    {#if logs_error}
                      <div class="text-error text-sm mb-3">{logs_error}</div>
                    {/if}
                    <div class="bg-base-200 rounded border overflow-hidden">
                      <pre
                        class="text-xs font-mono text-base-content/80 p-3 max-h-48 overflow-y-auto whitespace-pre-wrap">{chunking_logs}</pre>
                    </div>
                  </div>
                {/if}
              </div>
            </div>
          </div>

          <!-- Stage 3: Embedding -->
          <div class="relative pl-16 mb-6">
            <!-- Timeline indicator with progress -->
            <div
              class={get_timeline_indicator_classes(
                "embedding",
                config_progress,
              )}
            >
              {get_progress_icon("embedding", config_progress)}
            </div>

            <div class="flex flex-col gap-2">
              <div
                class={get_step_container_classes("embedding", config_progress)}
              >
                <div class="p-4">
                  <div class="flex items-center gap-3">
                    <h3 class="text-lg font-medium">Vector Embedding</h3>
                  </div>
                  <div class="text-sm text-gray-500 mb-2">
                    Turn your document chunks into searchable vectors.
                  </div>

                  <!-- Status Badge and Progress Bar -->
                  <div class="flex items-center justify-between mb-3">
                    <div
                      class="badge {get_step_status_info(
                        'embedding',
                        config_progress,
                      ).color} badge-outline text-xs font-medium"
                    >
                      {get_step_status_info("embedding", config_progress).text}
                    </div>
                    <span class="text-sm text-base-content/60"
                      >{get_step_progress_percentage(
                        "embedding",
                        config_progress,
                      )}%</span
                    >
                  </div>
                  <progress
                    class="progress progress-primary bg-primary/20 w-full h-2 mb-2"
                    value={embedding_progress_value}
                    max={progress_max}
                  ></progress>
                  {#if config_progress && config_progress.total_document_count > 0}
                    <div class="text-xs text-base-content/50 text-start mb-3">
                      {embedding_progress_value} of {config_progress.total_document_count}
                      documents processed
                    </div>
                  {/if}

                  <!-- Config Details -->
                  <div class="p-4 rounded-md bg-gray-50 mb-4">
                    {#if embedding_config}
                      <PropertyList
                        properties={[
                          {
                            name: "Provider",
                            value:
                              embedding_config.model_provider_name || "Unknown",
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
                        ]}
                      />
                    {:else}
                      <div class="text-gray-500 text-sm">
                        No embedding model configured
                      </div>
                    {/if}
                  </div>

                  <!-- Expandable Logs -->
                  <div class="flex items-center justify-end mb-3 gap-2">
                    <button
                      on:click={toggle_embedding_logs}
                      class="inline-flex items-center px-2 py-1 text-xs leading-4 font-medium rounded-md text-base-content/60 bg-base-200 hover:bg-base-300 focus:outline-none focus:ring-offset-0 focus:ring-0 transition-colors duration-150"
                      title={embedding_logs_expanded
                        ? "Hide embedding logs"
                        : "Show embedding logs"}
                    >
                      <svg
                        class="h-3 w-3 mr-1"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          stroke-linecap="round"
                          stroke-linejoin="round"
                          stroke-width="2"
                          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                        />
                      </svg>
                      {embedding_logs_expanded ? "Hide" : "Show"} Logs
                    </button>
                  </div>
                </div>

                <!-- Collapsible Logs -->
                {#if embedding_logs_expanded}
                  <div class="border-t p-4 rounded-b-md bg-gray-50">
                    <div class="flex items-center justify-between mb-3">
                      <h4 class="text-sm font-medium text-base-content">
                        Embedding Logs
                      </h4>
                      <div class="flex items-center gap-2">
                        <button
                          on:click={() =>
                            copy_logs_to_clipboard(embedding_logs)}
                          class="btn btn-sm btn-square btn-outline"
                          title="Copy logs to clipboard"
                        >
                          <svg
                            class="w-4 h-4"
                            viewBox="0 0 64 64"
                            xmlns="http://www.w3.org/2000/svg"
                            stroke-width="3"
                            stroke="currentColor"
                            fill="none"
                          >
                            <rect
                              x="11.13"
                              y="17.72"
                              width="33.92"
                              height="36.85"
                              rx="2.5"
                            />
                            <path
                              d="M19.35,14.23V13.09a3.51,3.51,0,0,1,3.33-3.66H49.54a3.51,3.51,0,0,1,3.33,3.66V42.62a3.51,3.51,0,0,1-3.33,3.66H48.39"
                            />
                          </svg>
                        </button>
                        <button
                          on:click={() =>
                            download_logs(embedding_logs, "embedding")}
                          class="btn btn-sm btn-outline btn-primary"
                        >
                          Download
                        </button>
                        <button
                          on:click={view_logs}
                          class="btn btn-sm btn-outline"
                        >
                          Open Folder
                        </button>
                      </div>
                    </div>
                    {#if logs_error}
                      <div class="text-error text-sm mb-3">{logs_error}</div>
                    {/if}
                    <div class="bg-base-200 rounded border overflow-hidden">
                      <pre
                        class="text-xs font-mono text-base-content/80 p-3 max-h-48 overflow-y-auto whitespace-pre-wrap">{embedding_logs}</pre>
                    </div>
                  </div>
                {/if}
              </div>
            </div>
          </div>
        </div>

        <!-- Final Pipeline Status Node -->
        <div class="relative pl-16 mb-6">
          <!-- Timeline indicator with overall status - larger and more prominent -->
          <div
            class="absolute left-0 top-2 flex items-center justify-center w-8 h-8 rounded-full border-4 border-white text-white text-sm font-bold transition-all duration-300 {get_progress_icon_color(
              'embedding',
              config_progress,
            )} shadow-xl ring-4 {overall_status.border}"
          >
            {overall_status.icon}
          </div>

          <div class="flex flex-col gap-2">
            <div
              class="flex flex-col gap-2 max-w-2xl rounded-xl transition-all duration-300 border-base-300 bg-base-100"
            >
              <div class="p-6">
                <div class="flex items-center justify-between mb-6">
                  <div class="flex items-center gap-3">
                    <div
                      class="flex items-center justify-center w-12 h-12 rounded-xl {overall_status.bg} border-2 {overall_status.border}"
                    >
                      <span
                        class="text-2xl font-bold {overall_status.iconColor}"
                        >{overall_status.icon}</span
                      >
                    </div>
                    <div>
                      <h3 class="text-xl font-semibold text-base-content">
                        {overall_status.text}
                      </h3>
                      <p class="text-sm text-base-content/60">
                        {completed_pct}% finished
                      </p>
                    </div>
                  </div>
                </div>

                <div class="text-sm text-base-content/70">
                  {#if completed_pct === 100}
                    <div
                      class="flex items-center gap-2 text-success font-medium"
                    >
                      <svg
                        class="w-4 h-4"
                        fill="currentColor"
                        viewBox="0 0 20 20"
                      >
                        <path
                          fill-rule="evenodd"
                          d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                          clip-rule="evenodd"
                        ></path>
                      </svg>
                      Ready for use
                    </div>
                  {:else if completed_pct > 0}
                    <div
                      class="flex items-center gap-2 text-warning font-medium"
                    >
                      <svg
                        class="w-4 h-4 animate-spin"
                        fill="currentColor"
                        viewBox="0 0 20 20"
                      >
                        <path
                          fill-rule="evenodd"
                          d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z"
                          clip-rule="evenodd"
                        ></path>
                      </svg>
                      Processing documents
                    </div>
                  {:else}
                    <div
                      class="flex items-center gap-2 text-neutral font-medium"
                    >
                      <svg
                        class="w-4 h-4"
                        fill="currentColor"
                        viewBox="0 0 20 20"
                      >
                        <path
                          fill-rule="evenodd"
                          d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z"
                          clip-rule="evenodd"
                        ></path>
                      </svg>
                      Click "Run" to start
                    </div>
                  {/if}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="w-72 2xl:w-96 flex-none flex flex-col gap-4">
        {#if rag_config}
          <PropertyList
            title="Properties"
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
