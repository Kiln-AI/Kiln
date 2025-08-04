<script lang="ts">
  import type { RagConfigWithSubConfigs, RagProgress } from "$lib/types"
  import { formatDate } from "$lib/utils/formatters"
  import RunRagControl from "./run_rag_control.svelte"
  import {
    embedding_model_name,
    model_name,
    provider_name_from_id,
  } from "$lib/stores"

  export let rag_config: RagConfigWithSubConfigs
  export let project_id: string
  export let rag_progress: RagProgress

  let row_hovered = false

  // Calculate percentages for progress bar
  $: total_docs = rag_progress?.total_document_count || 0
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

    const hasPartialProgress = [
      rag_progress?.total_document_extracted_count,
      rag_progress?.total_document_chunked_count,
      rag_progress?.total_document_embedded_count,
    ].some((count) => count < total_docs)

    if (hasPartialProgress)
      return {
        text: "Incomplete",
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

{#if rag_progress && rag_config}
  <tr class={row_hovered ? "hover" : ""}>
    <!-- Pipeline Info Card -->
    <td class="align-top p-4 h-full">
      <div class="flex flex-col gap-3">
        <!-- Header -->
        <div class="flex items-center justify-between">
          <a
            class="font-semibold text-lg text-base-content cursor-pointer link"
            href={`/docs/rag_configs/${project_id}/${rag_config.id}/rag_config`}
          >
            {rag_config.name}
          </a>
        </div>

        <!-- Description -->
        <div class="space-y-1 text-xs text-base-content/70">
          <div>
            Extractor: {model_name(
              rag_config.extractor_config?.model_name,
              null,
            ) || "N/A"} ({provider_name_from_id(
              rag_config.extractor_config.model_provider_name,
            ) || ""})
          </div>
          <div>
            Chunk size: {rag_config.chunker_config.properties?.chunk_size ||
              "N/A"}
          </div>
          <div>
            Chunk overlap: {rag_config.chunker_config.properties
              ?.chunk_overlap || "N/A"}
          </div>
          <div>
            Embedding: {embedding_model_name(
              rag_config.embedding_config.model_name,
              rag_config.embedding_config.model_provider_name,
            ) || "N/A"}
          </div>
          <div class="text-xs text-base-content/50">
            Created {formatDate(rag_config.created_at)}
          </div>
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
          value={rag_progress.total_document_completed_count || 0}
          max={total_docs || 100}
        ></progress>
        {#if total_docs > 0}
          <div class="text-xs text-base-content/50 text-start">
            {rag_progress.total_document_completed_count || 0} of {total_docs} documents
            processed
          </div>
        {/if}
      </div>
    </td>

    <!-- Actions -->
    <td class="p-4 cursor-default align-top">
      <RunRagControl {rag_config} {project_id} {rag_progress} />
    </td>
  </tr>
{/if}
