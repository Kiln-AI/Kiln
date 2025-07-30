<script lang="ts">
  import type { RagConfig, RagProgress } from "$lib/types"
  import { formatDate } from "$lib/utils/formatters"
  import { goto } from "$app/navigation"
  import RunRagControl from "./run_rag_control.svelte"

  export let rag_config: RagConfig
  export let project_id: string
  export let rag_progress: RagProgress | null = null

  let row_hovered = false
  let details_expanded = false

  function row_clicked() {
    goto(`/docs/rag_configs/${project_id}/${rag_config.id}/rag_config`)
  }

  function toggle_details(event: Event) {
    event.stopPropagation()
    details_expanded = !details_expanded
  }

  // Calculate percentages for progress bars
  $: total_docs = rag_progress?.total_document_count || 0
  $: extracted_pct =
    total_docs > 0
      ? Math.round(
          ((rag_progress?.total_document_extracted_count || 0) / total_docs) *
            100,
        )
      : 0
  $: chunked_pct =
    total_docs > 0
      ? Math.round(
          ((rag_progress?.total_document_chunked_count || 0) / total_docs) *
            100,
        )
      : 0
  $: embedded_pct =
    total_docs > 0
      ? Math.round(
          ((rag_progress?.total_document_embedded_count || 0) / total_docs) *
            100,
        )
      : 0
  $: completed_pct =
    total_docs > 0
      ? Math.round(
          ((rag_progress?.total_document_completed_count || 0) / total_docs) *
            100,
        )
      : 0

  // Get status and color
  $: status = (() => {
    if (completed_pct === 100)
      return {
        text: "Complete",
        color: "badge-primary",
        bg: "bg-primary/10",
        border: "border-primary/20",
      }
    if (completed_pct > 0)
      return {
        text: "In Progress",
        color: "badge-warning",
        bg: "bg-warning/10",
        border: "border-warning/20",
      }
    return {
      text: "Not Started",
      color: "badge-neutral",
      bg: "bg-neutral/10",
      border: "border-neutral/20",
    }
  })()
</script>

<tr class={row_hovered ? "hover" : ""}>
  <!-- Pipeline Info Card -->
  <td class="align-top p-4 cursor-pointer h-full" on:click={row_clicked}>
    <div class="flex flex-col gap-3">
      <!-- Header -->
      <div class="flex items-center justify-between">
        <h3 class="font-semibold text-lg text-base-content">
          {rag_config.name}
        </h3>
      </div>

      <!-- Description -->
      {#if rag_config.description}
        <p class="text-sm text-base-content/70 leading-relaxed">
          {rag_config.description}
        </p>
      {/if}

      <!-- Pipeline Components -->
      <div class="flex flex-col gap-2">
        <div class="flex items-center gap-2 text-xs">
          <div class="w-2 h-2 rounded-full bg-primary"></div>
          <span class="font-medium">Extractor:</span>
          <span class="text-base-content/60"
            >ID: {rag_config.extractor_config_id
              ? rag_config.extractor_config_id.slice(0, 8) + "..."
              : "Not set"}</span
          >
        </div>
        <div class="flex items-center gap-2 text-xs">
          <div class="w-2 h-2 rounded-full bg-secondary"></div>
          <span class="font-medium">Chunker:</span>
          <span class="text-base-content/60"
            >ID: {rag_config.chunker_config_id
              ? rag_config.chunker_config_id.slice(0, 8) + "..."
              : "Not set"}</span
          >
        </div>
        <div class="flex items-center gap-2 text-xs">
          <div class="w-2 h-2 rounded-full bg-accent"></div>
          <span class="font-medium">Embedding:</span>
          <span class="text-base-content/60"
            >ID: {rag_config.embedding_config_id
              ? rag_config.embedding_config_id.slice(0, 8) + "..."
              : "Not set"}</span
          >
        </div>
      </div>

      <!-- Created Date -->
      <div class="text-xs text-base-content/50">
        Created {formatDate(rag_config.created_at)}
      </div>
    </div>
  </td>

  <!-- Progress Section -->
  <td class="p-4 cursor-default align-top">
    <div class="flex flex-col gap-3">
      <!-- Overall Progress -->
      <div class="flex items-center justify-between">
        <div class="badge {status.color} badge-outline text-xs font-medium">
          {status.text}
        </div>
        <span class="text-sm text-base-content/60">{completed_pct}%</span>
      </div>
      <progress
        class="progress progress-primary bg-primary/20 w-full h-2"
        value={rag_progress?.total_document_completed_count || 0}
        max={total_docs || 100}
      ></progress>
      {#if total_docs > 0}
        <div class="text-xs text-base-content/50 text-start">
          {rag_progress?.total_document_completed_count || 0} of {total_docs} documents
          processed
        </div>
      {/if}

      <!-- Expandable Details -->
      <div class="flex items-center justify-end">
        <button
          on:click={toggle_details}
          class="inline-flex items-center px-2 py-1 text-xs leading-4 font-medium rounded-md text-base-content/60 bg-base-200 hover:bg-base-300 focus:outline-none focus:ring-offset-0 focus:ring-0 transition-colors duration-150"
          title={details_expanded
            ? "Hide detailed progress"
            : "Show detailed progress"}
        >
          <svg
            class="h-3 w-3 mr-1 transition-transform duration-200 {details_expanded
              ? 'rotate-180'
              : ''}"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M19 9l-7 7-7-7"
            />
          </svg>
          {details_expanded ? "Hide" : "Show"} Details
        </button>
      </div>

      <!-- Collapsible Pipeline Steps -->
      {#if details_expanded}
        <div
          class="space-y-3 pt-2 border-t border-base-300 bg-gray-50 p-4 rounded-b-md"
        >
          <!-- Extraction Step -->
          <div class="flex flex-col gap-1">
            <div class="flex items-center gap-2">
              <div class="w-2 h-2 rounded-full bg-primary"></div>
              <span class="text-xs font-medium">Extraction</span>
              <span class="text-xs text-base-content/50">
                ({extracted_pct}%)
              </span>
            </div>
            <progress
              class="progress progress-primary bg-primary/20 w-11/12 h-1.5 ml-2"
              value={(rag_progress?.total_document_extracted_count || 0) - 1}
              max={total_docs || 100}
            ></progress>
          </div>

          <!-- Chunking Step -->
          <div class="flex flex-col gap-1">
            <div class="flex items-center gap-2">
              <div class="w-2 h-2 rounded-full bg-secondary"></div>
              <span class="text-xs font-medium">Chunking</span>
              <span class="text-xs text-base-content/50">
                ({chunked_pct}%)
              </span>
            </div>
            <progress
              class="progress progress-primary bg-primary/20 w-11/12 h-1.5 ml-2"
              value={rag_progress?.total_document_chunked_count || 0}
              max={total_docs || 100}
            ></progress>
          </div>

          <!-- Embedding Step -->
          <div class="flex flex-col gap-1">
            <div class="flex items-center gap-2">
              <div class="w-2 h-2 rounded-full bg-accent"></div>
              <span class="text-xs font-medium">Embedding</span>
              <span class="text-xs text-base-content/50">
                ({embedded_pct}%)
              </span>
            </div>
            <progress
              class="progress progress-primary bg-primary/20 w-11/12 h-1.5 ml-2"
              value={rag_progress?.total_document_embedded_count || 0}
              max={total_docs || 100}
            ></progress>
          </div>
        </div>
      {/if}
    </div>
  </td>

  <!-- Actions -->
  <td class="p-4 cursor-default">
    <div class="flex flex-col gap-3 items-start">
      <RunRagControl {rag_config} {project_id} />
    </div>
  </td>
</tr>
