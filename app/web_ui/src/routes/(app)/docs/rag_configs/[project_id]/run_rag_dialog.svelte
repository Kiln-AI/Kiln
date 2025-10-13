<script lang="ts">
  import type {
    LogMessage,
    RagConfigWithSubConfigs,
    RagProgress,
  } from "$lib/types"
  import Dialog from "$lib/ui/dialog.svelte"
  import {
    ragProgressStore,
    getProjectRagStateStore,
  } from "$lib/stores/rag_progress_store"
  import Checkmark from "$lib/ui/icons/checkmark.svelte"

  $: projectStateStore = getProjectRagStateStore(project_id)
  $: ragProgressState = $projectStateStore

  export let dialog: Dialog | null = null
  export let project_id: string
  export let rag_config_id: string
  export let rag_config: RagConfigWithSubConfigs

  $: config_progress = ragProgressState.progress[rag_config_id] || null
  $: is_running = ragProgressState.running_rag_configs[rag_config_id] || false

  let log_container: HTMLPreElement
  $: log_messages = ragProgressState.logs[rag_config_id] || []
  let end_of_logs: HTMLDivElement | null = null

  // user can override the default behavior of showing logs when there are error logs
  let show_logs_explicit_open: boolean = false
  let show_logs_explicit_close: boolean = false
  $: has_error_logs = log_messages.some((log) => log.level === "error")
  $: show_logs =
    !show_logs_explicit_close && (has_error_logs || show_logs_explicit_open)

  function copy_logs_to_clipboard(logs: LogMessage[]) {
    const logs_string = logs
      .map((log) => `${log.level.toUpperCase()}: ${log.message}`)
      .join("\n")
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(logs_string).catch(console.error)
    } else {
      // Fallback for older browsers or non-HTTPS contexts
      console.warn("Clipboard API not available")
    }
  }

  function download_logs(logs: LogMessage[], step_name: string) {
    const logs_string = logs
      .map((log) => `${log.level.toUpperCase()}: ${log.message}`)
      .join("\n")
    const blob = new Blob([logs_string], { type: "text/plain" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `${step_name}_logs_${new Date().toISOString().split("T")[0]}.txt`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

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
  $: indexing_progress_value = get_step_progress_value(
    "indexing",
    config_progress,
  )

  $: document_progress_max = config_progress?.total_document_count || 100
  $: extraction_progress_pct = Math.floor(
    (extraction_progress_value / document_progress_max) * 100,
  )
  $: chunking_progress_pct = Math.floor(
    (chunking_progress_value / document_progress_max) * 100,
  )
  $: embedding_progress_pct = Math.floor(
    (embedding_progress_value / document_progress_max) * 100,
  )

  $: chunk_progress_max = config_progress?.total_chunk_count || 100
  $: indexing_progress_pct = Math.floor(
    (indexing_progress_value / chunk_progress_max) * 100,
  )

  $: total_docs = config_progress?.total_document_count || 0
  $: docs_completed_pct =
    total_docs > 0
      ? Math.floor(
          ((config_progress?.total_document_completed_count || 0) /
            total_docs) *
            100,
        )
      : 0

  $: total_chunks = config_progress?.total_chunk_count || 0
  $: chunks_completed_pct =
    total_chunks > 0
      ? Math.floor(
          ((config_progress?.total_chunk_completed_count || 0) / total_chunks) *
            100,
        )
      : 0

  // autoscroll to the bottom of the logs when the logs change
  $: if (log_messages && log_container && end_of_logs) {
    end_of_logs?.scrollIntoView({
      behavior: "smooth",
      block: "end",
    })
  }

  function is_step_completed(
    step: string,
    config_progress: RagProgress | null,
  ): boolean {
    return get_status_for_step(step, config_progress) === "completed"
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
      case "indexing": {
        // for indexing, we only know the total chunk count after chunking is complete
        // so if any upstream step is not complete, we can't know if indexing is complete
        if (
          !is_step_completed("extraction", config_progress) ||
          !is_step_completed("chunking", config_progress) ||
          !is_step_completed("embedding", config_progress)
        ) {
          return "pending"
        }
        if (
          config_progress.total_document_count === 0 ||
          config_progress.total_chunk_count === 0
        ) {
          return "pending"
        }
        return config_progress.total_chunks_indexed_count >=
          config_progress.total_chunk_count
          ? "completed"
          : "pending"
      }
      default:
        return "pending"
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
      case "indexing":
        return config_progress.total_chunks_indexed_count
      default:
        return 0
    }
  }

  function get_log_color(level: "info" | "error" | "warning"): string {
    switch (level) {
      case "info":
        return "text-base-content"
      case "error":
        return "text-error"
      case "warning":
        return "text-warning"
      default:
        return "text-base-content"
    }
  }
</script>

<Dialog
  title="Processing Status"
  subtitle={`Search Tool: ${rag_config.name}`}
  width="wide"
  bind:this={dialog}
  action_buttons={[
    {
      isPrimary: true,
      label: is_running ? "Running..." : has_error_logs ? "Retry" : "Run RAG",
      asyncAction: async () => {
        // we don't want to await because we show the progress in the UI
        // and don't need the built-in loading spinner
        ragProgressStore
          .run_rag_config(project_id, rag_config_id)
          .catch((error) => {
            console.error("Error running rag config", error)
            return true
          })

        // keep open so the user can see the progress
        return false
      },
      loading: is_running,
      hide: docs_completed_pct === 100 && chunks_completed_pct === 100,
    },
  ]}
>
  <div class="flex flex-col gap-6">
    <!-- Processing Steps -->
    <div class="flex flex-col gap-4 max-w-md mx-auto">
      {#each [{ name: "extraction", label: "Extraction", progress: extraction_progress_value, pct: extraction_progress_pct }, { name: "chunking", label: "Chunking", progress: chunking_progress_value, pct: chunking_progress_pct }, { name: "embedding", label: "Embedding", progress: embedding_progress_value, pct: embedding_progress_pct }, { name: "indexing", label: "Indexing", progress: indexing_progress_value, pct: indexing_progress_pct }] as step}
        <div
          class="flex items-center gap-4 p-3 rounded-lg border border-base-200 bg-base-50/30 hover:bg-base-50/50 transition-all duration-200"
        >
          <div
            class="flex items-center justify-center w-8 h-8 rounded-full {is_step_completed(
              step.name,
              config_progress,
            )
              ? 'bg-primary/10 text-primary'
              : is_running
                ? 'bg-warning/10 text-warning'
                : 'bg-base-200 text-gray-500'}"
          >
            {#if is_step_completed(step.name, config_progress)}
              <div class="w-4 h-4">
                <Checkmark />
              </div>
            {:else if is_running}
              <div class="bg-current rounded-full loading loading-sm"></div>
            {:else}
              <div class="w-2 h-2 bg-current rounded-full"></div>
            {/if}
          </div>
          <div class="flex-1 min-w-0">
            <div class="font-medium text-xs">
              {step.label}
            </div>
            {#if step.name === "indexing"}
              <div class="text-xs text-gray-500">
                {step.progress} / {chunk_progress_max} chunks
              </div>
            {:else}
              <div class="text-xs text-gray-500">
                {step.progress} / {document_progress_max} documents
              </div>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  </div>

  <!-- Logs Section -->
  {#if log_messages && log_messages.length > 0}
    <div class="mt-6">
      <!-- Toggle Button -->
      <div class="flex justify-center mb-4">
        <button
          on:click={() => {
            if (show_logs) {
              show_logs_explicit_close = true
              show_logs_explicit_open = false
            } else {
              show_logs_explicit_open = true
              show_logs_explicit_close = false
            }
          }}
          class={`btn btn-sm btn-outline ${
            has_error_logs ? "btn-error" : "btn"
          }`}
        >
          {#if show_logs}
            <div>Hide Logs</div>
          {:else}
            <div>Show Logs ({log_messages.length})</div>
          {/if}
        </button>
      </div>

      <!-- Logs Content -->
      {#if show_logs}
        <div class="rounded-md border">
          <div class="flex items-center justify-end p-4 gap-4">
            <button
              on:click={() => copy_logs_to_clipboard(log_messages)}
              class="btn btn-sm btn-square"
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
              on:click={() => download_logs(log_messages, "rag_run_logs")}
              class="btn btn-sm"
            >
              Download
            </button>
          </div>
          <div class="bg-base-200 rounded">
            <pre
              bind:this={log_container}
              class="px-2 text-xs font-mono text-gray-500 min-h-48 max-h-48 overflow-y-auto text-left">
              {#each log_messages as log}
                <div
                  class="text-xs font-mono {get_log_color(
                    log.level,
                  )} block m-0 p-0 break-words whitespace-pre-wrap mb-2">{log.level.toUpperCase()}: {log.message}</div>
              {/each}
              <div bind:this={end_of_logs}></div>
            </pre>
          </div>
        </div>
      {/if}
    </div>
  {/if}
</Dialog>
