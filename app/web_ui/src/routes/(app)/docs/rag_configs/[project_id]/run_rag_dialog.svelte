<script lang="ts">
  import type {
    LogMessage,
    RagConfigWithSubConfigs,
    RagWorkflowStepNames,
  } from "$lib/types"
  import Dialog from "$lib/ui/dialog.svelte"
  import {
    ragProgressStore,
    type StepProgress,
  } from "$lib/stores/rag_progress_store"
  import Checkmark from "$lib/ui/checkmark.svelte"

  export let dialog: Dialog | null = null
  export let project_id: string
  export let rag_config_id: string
  export let rag_config: RagConfigWithSubConfigs

  $: orchestration_progress =
    $ragProgressStore.orchestration_progress[rag_config_id] || null

  $: is_running =
    $ragProgressStore.orchestration_progress[rag_config_id]?.status ===
    "running"

  $: extraction_progress =
    $ragProgressStore.substep_progress[rag_config_id]?.extracting || null
  $: chunking_progress =
    $ragProgressStore.substep_progress[rag_config_id]?.chunking || null
  $: embedding_progress =
    $ragProgressStore.substep_progress[rag_config_id]?.embedding || null
  $: indexing_progress =
    $ragProgressStore.substep_progress[rag_config_id]?.indexing || null

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

  // autoscroll to the bottom of the logs when the logs change
  $: if (log_messages && log_container && end_of_logs) {
    end_of_logs?.scrollIntoView({
      behavior: "smooth",
      block: "end",
    })
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

  function get_step_percentage(step: StepProgress | null): number {
    if (!step) {
      return 0
    }
    if (step.expected_count === 0) {
      return 0
    }
    if (step.expected_count === null) {
      return 0
    }
    if (step.success_count === null) {
      return 0
    }

    return (step.success_count / step.expected_count) * 100
  }

  $: is_step_completed = (step: string): boolean => {
    if (!(step in ["extracting", "chunking", "embedding", "indexing"])) {
      return false
    }
    const step_progress =
      $ragProgressStore.substep_progress[rag_config_id]?.[
        step as RagWorkflowStepNames
      ]
    if (!step_progress) {
      return false
    }
    return step_progress.status === "complete"
  }

  $: is_step_pending = (step: string): boolean => {
    if (!(step in ["extracting", "chunking", "embedding", "indexing"])) {
      return false
    }
    const step_progress =
      $ragProgressStore.substep_progress[rag_config_id]?.[
        step as RagWorkflowStepNames
      ]
    if (!step_progress) {
      return false
    }
    return step_progress.status === "pending"
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
      hide: orchestration_progress.status === "complete",
    },
  ]}
>
  <div class="flex flex-col gap-6">
    <!-- Processing Steps -->
    <div class="flex flex-col gap-4 max-w-md mx-auto">
      {#each [{ name: "extracting", label: "Extraction", progress: extraction_progress, pct: get_step_percentage(extraction_progress) }, { name: "chunking", label: "Chunking", progress: chunking_progress, pct: get_step_percentage(chunking_progress) }, { name: "embedding", label: "Embedding", progress: embedding_progress, pct: get_step_percentage(embedding_progress) }, { name: "indexing", label: "Indexing", progress: indexing_progress, pct: get_step_percentage(indexing_progress) }] as step}
        <div
          class="flex items-center gap-4 p-3 rounded-lg border border-base-200 bg-base-50/30 hover:bg-base-50/50 transition-all duration-200"
        >
          <div
            class="flex items-center justify-center w-8 h-8 rounded-full {is_step_completed(
              step.name,
            )
              ? 'bg-primary/10 text-primary'
              : is_running
                ? 'bg-warning/10 text-warning'
                : 'bg-base-200 text-gray-500'}"
          >
            {#if is_step_completed(step.name)}
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
            {#if step.progress && !is_step_pending(step.name)}
              {#if step.name === "indexing"}
                <div class="text-xs text-gray-500">
                  {step.progress.success_count || 0} / {step.progress
                    .expected_count || 0} chunks
                </div>
              {:else}
                <div class="text-xs text-gray-500">
                  {step.progress.success_count || 0} / {step.progress
                    .expected_count || 0} documents
                </div>
              {/if}
            {:else if is_step_pending(step.name)}
              <div class="text-xs text-gray-500">Pending</div>
            {:else}
              <div class="text-xs text-gray-500">Not started</div>
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
