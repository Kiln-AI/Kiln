<script lang="ts">
  import Dialog from "$lib/ui/dialog.svelte"
  import { base_url } from "$lib/api_client"
  import CheckmarkIcon from "$lib/ui/icons/checkmark_icon.svelte"
  import { goto } from "$app/navigation"
  import { onDestroy } from "svelte"

  export let dialog: Dialog | null = null
  export let project_id: string
  export let doc_skill_id: string

  type LogMessage = {
    level: "info" | "error" | "warning"
    message: string
  }

  type DocSkillProgress = {
    total_document_count: number
    total_document_extracted_count: number
    total_document_extracted_error_count: number
    total_document_chunked_count: number
    total_document_chunked_error_count: number
    skill_created: boolean
    logs: LogMessage[]
  }

  let progress: DocSkillProgress | null = null
  let is_running = false
  let is_complete = false
  let has_error = false
  let has_warnings = false
  let log_messages: LogMessage[] = []
  let event_source: EventSource | null = null
  let started = false

  let log_container: HTMLPreElement
  let end_of_logs: HTMLDivElement | null = null

  let show_logs_explicit_open: boolean = false
  let show_logs_explicit_close: boolean = false
  $: has_error_logs = log_messages.some((log) => log.level === "error")
  $: show_logs =
    !show_logs_explicit_close && (has_error_logs || show_logs_explicit_open)

  $: if (log_messages && log_container && end_of_logs) {
    end_of_logs?.scrollIntoView({
      behavior: "smooth",
      block: "end",
    })
  }

  $: extraction_complete =
    progress !== null &&
    progress.total_document_count > 0 &&
    progress.total_document_extracted_count +
      progress.total_document_extracted_error_count >=
      progress.total_document_count

  $: chunking_complete =
    progress !== null &&
    progress.total_document_count > 0 &&
    progress.total_document_chunked_count +
      progress.total_document_chunked_error_count >=
      progress.total_document_count

  $: skill_complete = progress?.skill_created === true

  $: document_max = progress?.total_document_count || 0

  $: active_step = !extraction_complete
    ? "extraction"
    : !chunking_complete
      ? "chunking"
      : "skill"

  function run_pipeline() {
    if (is_running) return
    is_running = true
    is_complete = false
    has_error = false
    has_warnings = false
    log_messages = []
    progress = null

    const run_url = `${base_url}/api/projects/${project_id}/doc_skills/${doc_skill_id}/run`
    event_source = new EventSource(run_url)

    event_source.onmessage = (event) => {
      try {
        if (event.data === "complete") {
          event_source?.close()
          event_source = null
          is_running = false
          is_complete = true
          if (has_error_logs) {
            has_warnings = true
          }
          return
        }

        const payload = JSON.parse(event.data) as DocSkillProgress
        progress = payload

        if (payload.logs && payload.logs.length > 0) {
          log_messages = [...log_messages, ...payload.logs]
        }
      } catch (err) {
        log_messages = [
          ...log_messages,
          {
            level: "error",
            message: `Error processing event: ${String(err)}`,
          },
        ]
        event_source?.close()
        event_source = null
        is_running = false
        has_error = true
      }
    }

    event_source.onerror = () => {
      log_messages = [
        ...log_messages,
        {
          level: "error",
          message: "Connection to server lost. Please try again.",
        },
      ]
      event_source?.close()
      event_source = null
      is_running = false
      has_error = true
    }
  }

  // Auto-start once on mount
  $: if (dialog && doc_skill_id && !started) {
    started = true
    run_pipeline()
  }

  onDestroy(() => {
    event_source?.close()
    event_source = null
  })

  function copy_logs_to_clipboard(logs: LogMessage[]) {
    const logs_string = logs
      .map((log) => `${log.level.toUpperCase()}: ${log.message}`)
      .join("\n")
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(logs_string).catch(console.error)
    }
  }

  function download_logs(logs: LogMessage[]) {
    const logs_string = logs
      .map((log) => `${log.level.toUpperCase()}: ${log.message}`)
      .join("\n")
    const blob = new Blob([logs_string], { type: "text/plain" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `doc_skill_logs_${new Date().toISOString().split("T")[0]}.txt`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
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

  type StepInfo = {
    name: string
    label: string
    complete: boolean
    progress_value: number
    progress_max: number
    progress_label: string
  }

  $: steps = [
    {
      name: "extraction",
      label: "Extracting documents",
      complete: extraction_complete,
      progress_value: progress?.total_document_extracted_count || 0,
      progress_max: document_max,
      progress_label: "documents",
    },
    {
      name: "chunking",
      label: "Chunking documents",
      complete: chunking_complete,
      progress_value: progress?.total_document_chunked_count || 0,
      progress_max: document_max,
      progress_label: "documents",
    },
    {
      name: "skill",
      label: "Creating skill",
      complete: skill_complete,
      progress_value: skill_complete ? 1 : 0,
      progress_max: 1,
      progress_label: "",
    },
  ] as StepInfo[]
</script>

<Dialog
  title="Creating Doc Skill"
  width="wide"
  bind:this={dialog}
  action_buttons={[
    ...(is_complete
      ? [
          {
            isPrimary: true,
            label: "View Doc Skill",
            action: () => {
              goto(`/docs/doc_skills/${project_id}/${doc_skill_id}/doc_skill`)
              return true
            },
          },
        ]
      : []),
    ...(has_error
      ? [
          {
            isPrimary: true,
            label: "Try Again",
            action: () => {
              run_pipeline()
              return false
            },
          },
        ]
      : []),
    ...(is_running
      ? [
          {
            label: "Running...",
            loading: true,
            isPrimary: true,
            disabled: true,
            action: () => false,
          },
        ]
      : []),
  ]}
>
  <div class="flex flex-col gap-6">
    <div class="flex flex-col gap-4 max-w-md mx-auto">
      {#each steps as step}
        <div
          class="flex items-center gap-4 p-3 rounded-lg border border-base-200 bg-base-50/30 hover:bg-base-50/50 transition-all duration-200"
        >
          <div
            class="flex items-center justify-center w-8 h-8 rounded-full {step.complete
              ? 'bg-primary/10 text-primary'
              : is_running && active_step === step.name
                ? 'bg-warning/10 text-warning'
                : 'bg-base-200 text-gray-500'}"
          >
            {#if step.complete}
              <div class="w-4 h-4">
                <CheckmarkIcon />
              </div>
            {:else if is_running && active_step === step.name}
              <div class="bg-current rounded-full loading loading-sm"></div>
            {:else}
              <div class="w-2 h-2 bg-current rounded-full"></div>
            {/if}
          </div>
          <div class="flex-1 min-w-0">
            <div class="font-medium text-xs">
              {step.label}
            </div>
            {#if step.progress_label}
              <div class="text-xs text-gray-500">
                {step.progress_value} / {step.progress_max}
                {step.progress_label}
              </div>
            {/if}
          </div>
        </div>
      {/each}
    </div>

    {#if is_complete}
      <div class="text-center text-sm text-success font-medium">
        Doc skill created successfully.
      </div>
      {#if has_warnings}
        <div class="text-center text-xs text-warning font-medium">
          Completed with warnings. Check the logs for details.
        </div>
      {/if}
    {/if}

    {#if has_error && !is_running}
      <div class="text-center text-sm text-error font-medium">
        An error occurred. Check the logs for details.
      </div>
    {/if}
  </div>

  {#if log_messages && log_messages.length > 0}
    <div class="mt-6">
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
              on:click={() => download_logs(log_messages)}
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
