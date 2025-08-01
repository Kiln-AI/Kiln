<script lang="ts">
  import { base_url, client } from "$lib/api_client"
  import type { RagConfigWithSubConfigs, RagProgress } from "$lib/types"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"

  type LogMessage = { level: "info" | "error" | "warning"; message: string }

  type RagProgressEventPayload = RagProgress & {
    log?: LogMessage
    total_error_count: number
  }

  export let project_id: string
  export let rag_config_id: string
  export let dialog: Dialog | null = null

  let loading: boolean = false
  let error: KilnError | null = null
  let rag_config: RagConfigWithSubConfigs | null = null

  let config_progress: RagProgressEventPayload | null = null

  // Logs state
  let logs_error: string | null = null
  let logContainer: HTMLPreElement
  let log_messages: LogMessage[] = []
  let end_of_logs: HTMLDivElement | null = null
  let show_logs: boolean = false

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

  $: extraction_progress_pct = Math.round(
    (extraction_progress_value / progress_max) * 100,
  )
  $: chunking_progress_pct = Math.round(
    (chunking_progress_value / progress_max) * 100,
  )
  $: embedding_progress_pct = Math.round(
    (embedding_progress_value / progress_max) * 100,
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

  // Auto-scroll logs to bottom when content changes
  $: if (log_messages && logContainer && end_of_logs) {
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

  onMount(async () => {
    await get_rag_config()
    await get_rag_config_progress()
    // dialog?.show()
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

  let _: KilnError | null = null
  let rag_run_logs: string = ""

  let is_running: boolean = false

  async function run_rag_config() {
    is_running = true
    // subscribe to SSE
    const eventSource = new EventSource(
      `${base_url}/api/projects/${project_id}/rag_configs/${rag_config_id}/run`,
    )

    eventSource.onmessage = (event) => {
      try {
        if (event.data === "complete") {
          // Special end message
          eventSource.close()
          is_running = false
        } else {
          const payload = JSON.parse(event.data) as RagProgressEventPayload
          if (payload.log) {
            log_messages = [...log_messages, payload.log]
          }
          config_progress = payload
        }
      } catch (error) {
        eventSource.close()
        _ = createKilnError(error)
        // mark as failed
        log_messages = [
          ...log_messages,
          {
            level: "error",
            message: event.data,
          },
        ]
        is_running = false
      }
    }

    // Don't restart on an error (default SSE behavior)
    eventSource.onerror = (error) => {
      eventSource.close()
      _ = createKilnError(error)
      // mark as failed
      log_messages = [
        ...log_messages,
        {
          level: "error",
          message: error.toString(),
        },
      ]
      is_running = false
      console.error("Error running RAG config", error)
    }
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

    config_progress = {
      ...progress_data[rag_config_id],

      // error count is transient / not persisted on the backend so we initialize it here
      total_error_count: 0,
    }
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
  title="Processing RAG Pipeline"
  width="wide"
  bind:this={dialog}
  action_buttons={[
    {
      isPrimary: true,
      label: "Run Pipeline",
      asyncAction: async () => {
        await run_rag_config()

        // keep open so the user can see the progress
        return false
      },
      disabled: is_running,
    },
  ]}
>
  <div class="flex flex-col gap-6">
    <!-- Overall Pipeline Progress Header -->
    <div class="text-center">
      <div class="flex flex-col items-center gap-4">
        <div
          class="radial-progress text-primary bg-primary/10 border-4 border-primary/20"
          style="--value:{completed_pct}; --size:5rem; --thickness:6px;"
          aria-valuenow={completed_pct}
          role="progressbar"
        >
          <div class="text-center">
            <div class="text-lg font-bold text-primary">{completed_pct}%</div>
          </div>
        </div>
        <div class="text-center">
          <div class="text-sm font-medium text-base-content">
            Processing RAG Pipeline
          </div>
          <div class="text-xs text-base-content/60">
            {config_progress?.total_document_completed_count || 0} of {config_progress?.total_document_count ||
              0} documents processed
          </div>
        </div>
      </div>
    </div>

    <!-- Pipeline Steps -->
    <div class="flex flex-col gap-4 max-w-md mx-auto">
      <!-- Extraction Step -->
      <div
        class="flex items-center gap-4 p-3 rounded-lg border border-base-200 bg-base-50/30 hover:bg-base-50/50 transition-all duration-200"
      >
        <div
          class="flex items-center justify-center w-8 h-8 rounded-full {is_step_completed(
            'extraction',
            config_progress,
          )
            ? 'bg-primary/10 text-primary'
            : extraction_progress_value > 0
              ? 'bg-warning/10 text-warning'
              : 'bg-base-200 text-base-content/50'}"
        >
          {#if is_step_completed("extraction", config_progress)}
            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path
                fill-rule="evenodd"
                d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                clip-rule="evenodd"
              ></path>
            </svg>
          {:else if extraction_progress_value > 0}
            <div class="w-2 h-2 bg-current rounded-full animate-ping"></div>
          {:else}
            <div class="w-2 h-2 bg-current rounded-full"></div>
          {/if}
        </div>
        <div class="flex-1 min-w-0">
          <div class="font-medium text-sm text-base-content">Extraction</div>
          <div class="text-xs text-base-content/60">
            {extraction_progress_value} / {progress_max} documents
          </div>
        </div>
        <div
          class="radial-progress {is_step_completed(
            'extraction',
            config_progress,
          )
            ? 'text-primary'
            : extraction_progress_value > 0
              ? 'text-warning'
              : 'text-base-300'}"
          style="--value:{extraction_progress_pct}; --size:2.5rem; --thickness:3px;"
          aria-valuenow={extraction_progress_pct}
          role="progressbar"
        >
          <span class="text-xs font-medium">{extraction_progress_pct}%</span>
        </div>
      </div>

      <!-- Chunking Step -->
      <div
        class="flex items-center gap-4 p-3 rounded-lg border border-base-200 bg-base-50/30 hover:bg-base-50/50 transition-all duration-200"
      >
        <div
          class="flex items-center justify-center w-8 h-8 rounded-full {is_step_completed(
            'chunking',
            config_progress,
          )
            ? 'bg-primary/10 text-primary'
            : chunking_progress_value > 0
              ? 'bg-warning/10 text-warning'
              : 'bg-base-200 text-base-content/50'}"
        >
          {#if is_step_completed("chunking", config_progress)}
            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path
                fill-rule="evenodd"
                d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                clip-rule="evenodd"
              ></path>
            </svg>
          {:else if chunking_progress_value > 0}
            <div class="w-2 h-2 bg-current rounded-full animate-pulse"></div>
          {:else}
            <div class="w-2 h-2 bg-current rounded-full"></div>
          {/if}
        </div>
        <div class="flex-1 min-w-0">
          <div class="font-medium text-sm text-base-content">Chunking</div>
          <div class="text-xs text-base-content/60">
            {chunking_progress_value} / {progress_max} documents
          </div>
        </div>
        <div
          class="radial-progress {is_step_completed('chunking', config_progress)
            ? 'text-primary'
            : chunking_progress_value > 0
              ? 'text-warning'
              : 'text-base-300'}"
          style="--value:{chunking_progress_pct}; --size:2.5rem; --thickness:3px;"
          aria-valuenow={chunking_progress_pct}
          role="progressbar"
        >
          <span class="text-xs font-medium">{chunking_progress_pct}%</span>
        </div>
      </div>

      <!-- Embedding Step -->
      <div
        class="flex items-center gap-4 p-3 rounded-lg border border-base-200 bg-base-50/30 hover:bg-base-50/50 transition-all duration-200"
      >
        <div
          class="flex items-center justify-center w-8 h-8 rounded-full {is_step_completed(
            'embedding',
            config_progress,
          )
            ? 'bg-primary/10 text-primary'
            : embedding_progress_value > 0
              ? 'bg-warning/10 text-warning'
              : 'bg-base-200 text-base-content/50'}"
        >
          {#if is_step_completed("embedding", config_progress)}
            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path
                fill-rule="evenodd"
                d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                clip-rule="evenodd"
              ></path>
            </svg>
          {:else if embedding_progress_value > 0}
            <div class="w-2 h-2 bg-current rounded-full animate-pulse"></div>
          {:else}
            <div class="w-2 h-2 bg-current rounded-full"></div>
          {/if}
        </div>
        <div class="flex-1 min-w-0">
          <div class="font-medium text-sm text-base-content">Embedding</div>
          <div class="text-xs text-base-content/60">
            {embedding_progress_value} / {progress_max} documents
          </div>
        </div>
        <div
          class="radial-progress {is_step_completed(
            'embedding',
            config_progress,
          )
            ? 'text-primary'
            : embedding_progress_value > 0
              ? 'text-warning'
              : 'text-base-300'}"
          style="--value:{embedding_progress_pct}; --size:2.5rem; --thickness:3px;"
          aria-valuenow={embedding_progress_pct}
          role="progressbar"
        >
          <span class="text-xs font-medium">{embedding_progress_pct}%</span>
        </div>
      </div>
    </div>

    <!-- Overall Status Footer -->
    <div class="text-center pt-2 border-t border-base-200">
      <div
        class="inline-flex items-center gap-2 px-3 py-1 rounded-full {completed_pct ===
        100
          ? 'bg-success/10 text-success'
          : completed_pct > 0
            ? 'bg-warning/10 text-warning'
            : 'bg-base-200 text-base-content/60'}"
      >
        {#if completed_pct === 100}
          <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
            <path
              fill-rule="evenodd"
              d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
              clip-rule="evenodd"
            ></path>
          </svg>
          <span class="text-xs font-medium">Complete</span>
        {:else if completed_pct > 0}
          <div class="w-1.5 h-1.5 bg-current rounded-full animate-pulse"></div>
          <span class="text-xs font-medium">Processing...</span>
        {:else}
          <div class="w-1.5 h-1.5 bg-current rounded-full"></div>
          <span class="text-xs font-medium">Ready to start</span>
        {/if}
      </div>
    </div>
  </div>

  <!-- Logs Section -->
  {#if log_messages && log_messages.length > 0}
    <div class="mt-6">
      <!-- Toggle Button -->
      <div class="flex justify-end mb-4">
        <button
          on:click={() => (show_logs = !show_logs)}
          class="btn btn-sm btn-outline btn-primary"
        >
          {#if show_logs}
            <svg
              class="w-4 h-4 mr-2"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M5 15l7-7 7 7"
              ></path>
            </svg>
            Hide Logs
          {:else}
            <svg
              class="w-4 h-4 mr-2"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M19 9l-7 7-7-7"
              ></path>
            </svg>
            Show Logs ({log_messages.length})
          {/if}
        </button>
      </div>

      <!-- Logs Content -->
      {#if show_logs}
        <div class="rounded-md border">
          <div class="flex items-center justify-end p-4 gap-4">
            <button
              on:click={() => copy_logs_to_clipboard(rag_run_logs)}
              class="btn btn-sm btn-square btn-outline btn-primary"
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
              on:click={() => download_logs(rag_run_logs, "rag_run_logs")}
              class="btn btn-sm btn-outline btn-primary"
            >
              Download
            </button>
          </div>
          {#if logs_error}
            <div class="text-error text-sm mb-3">{logs_error}</div>
          {/if}
          <div class="bg-base-200 rounded">
            <pre
              bind:this={logContainer}
              class="px-2 text-xs font-mono text-base-content/80 min-h-48 max-h-48 overflow-y-auto text-left">
              {#each log_messages as log}
                <div
                  class="text-xs font-mono {get_log_color(
                    log.level,
                  )} block m-0 p-0">{log.level.toUpperCase()}: {log.message}</div>
              {/each}
              <div bind:this={end_of_logs}></div>
            </pre>
          </div>
        </div>
      {/if}
    </div>
  {/if}
</Dialog>
