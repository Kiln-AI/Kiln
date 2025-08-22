<script lang="ts">
  import type {
    LogMessage,
    RagConfigWithSubConfigs,
    RagProgress,
  } from "$lib/types"
  import Dialog from "$lib/ui/dialog.svelte"
  import { ragProgressStore } from "$lib/stores/rag_progress_store"
  import Checkmark from "$lib/ui/checkmark.svelte"

  export let dialog: Dialog | null = null
  export let project_id: string
  export let rag_config_id: string
  export let rag_config: RagConfigWithSubConfigs

  $: config_progress = $ragProgressStore.progress[rag_config_id] || null
  $: is_running = $ragProgressStore.running_rag_configs[rag_config_id] || false

  let log_container: HTMLPreElement
  $: log_messages = $ragProgressStore.logs[rag_config_id] || []
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

  $: progress_max = config_progress?.total_document_count || 100
  $: extraction_progress_pct = Math.round(
    (extraction_progress_value / progress_max) * 100,
  )
  $: chunking_progress_pct = Math.round(
    (chunking_progress_value / progress_max) * 100,
  )
  $: embedding_progress_pct = Math.round(
    (embedding_progress_value / progress_max) * 100,
  )
  $: total_docs = config_progress?.total_document_count || 0
  $: completed_pct =
    total_docs > 0
      ? Math.round(
          ((config_progress?.total_document_completed_count || 0) /
            total_docs) *
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
  title="Processing Status"
  subtitle={`Search Tool: ${rag_config.name}`}
  width="wide"
  bind:this={dialog}
  action_buttons={[
    {
      isPrimary: true,
      label: is_running ? "Running..." : has_error_logs ? "Retry" : "Run RAG",
      asyncAction: async () => {
        ragProgressStore.run_rag_config(project_id, rag_config_id)

        // keep open so the user can see the progress
        return false
      },
      loading: is_running,
      hide: completed_pct === 100,
    },
  ]}
>
  <div class="flex flex-col gap-6">
    <!-- Overall RAG Progress Header -->
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
          <div
            class="inline-flex items-center gap-2 px-3 py-1 rounded-full {completed_pct ===
            100
              ? 'bg-success/10 text-success'
              : completed_pct > 0
                ? 'bg-warning/10 text-warning'
                : 'bg-base-200 text-gray-500'}"
          >
            {#if completed_pct === 100}
              <Checkmark classOverride="w-4 h-4" />
              <span class="text-xs font-medium">Complete</span>
            {:else if is_running}
              <div class="bg-current rounded-full loading loading-sm"></div>
              <span class="text-xs font-medium">Processing...</span>
            {:else if has_error_logs}
              <div class="bg-error rounded-full"></div>
              <span class="text-xs font-medium text-error"
                >Completed with errors</span
              >
            {:else}
              <div class="bg-current rounded-full"></div>
              <span class="text-xs font-medium">Ready to start</span>
            {/if}
          </div>
          <div class="mt-2 text-xs text-gray-500">
            {config_progress?.total_document_completed_count || 0} of
            {config_progress?.total_document_count || 0} documents
          </div>
        </div>
      </div>
    </div>

    <!-- RAG Steps -->
    <div class="flex flex-col gap-4 max-w-md mx-auto">
      {#each [{ name: "extraction", label: "Extraction", progress: extraction_progress_value, pct: extraction_progress_pct }, { name: "chunking", label: "Chunking", progress: chunking_progress_value, pct: chunking_progress_pct }, { name: "embedding", label: "Embedding", progress: embedding_progress_value, pct: embedding_progress_pct }] as step}
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
              <Checkmark classOverride="w-4 h-4" />
            {:else if is_running}
              <div class="bg-current rounded-full loading loading-sm"></div>
            {:else}
              <div class="w-2 h-2 bg-current rounded-full"></div>
            {/if}
          </div>
          <div class="flex-1 min-w-0">
            <div class="font-medium text-sm text-base-content">
              {step.label}
            </div>
            <div class="text-xs text-gray-500">
              {step.progress} / {progress_max} documents
            </div>
          </div>
          <div
            class="radial-progress {is_step_completed(
              step.name,
              config_progress,
            )
              ? 'text-primary'
              : is_running
                ? 'text-warning'
                : 'text-base-300'}"
            style="--value:{step.pct}; --size:2.5rem; --thickness:3px;"
            aria-valuenow={step.pct}
            role="progressbar"
          >
            <span class="text-xs font-medium">{step.pct}%</span>
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
