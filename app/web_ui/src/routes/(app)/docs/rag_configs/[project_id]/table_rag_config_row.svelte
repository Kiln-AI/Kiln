<script lang="ts">
  import type { RagConfigWithSubConfigs } from "$lib/types"
  import { formatDate } from "$lib/utils/formatters"
  import RunRagControl from "./run_rag_control.svelte"
  import {
    embedding_model_name,
    model_name,
    provider_name_from_id,
  } from "$lib/stores"
  import { ragProgressStore } from "$lib/stores/rag_progress_store"

  export let rag_config: RagConfigWithSubConfigs
  export let project_id: string
  $: rag_progress = $ragProgressStore.progress[rag_config.id || ""]

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

  $: status = $ragProgressStore.status[rag_config.id || ""]
</script>

{#if rag_progress && rag_config}
  <tr class={row_hovered ? "hover" : ""}>
    <!-- Step Info Card -->
    <td class="align-top p-4 h-full">
      <div class="flex flex-col gap-2">
        <!-- Header -->
        <div class="flex items-center justify-between">
          <a
            class="font-medium text-base-content cursor-pointer link"
            href={`/docs/rag_configs/${project_id}/${rag_config.id}/rag_config`}
          >
            {rag_config.name}
          </a>
        </div>

        <!-- Description -->
        <div class="space-y-1 text-xs text-gray-500">
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
          <div class="text-xs text-gray-500">
            Created {formatDate(rag_config.created_at)}
          </div>
        </div>
      </div>
    </td>

    <!-- Progress Section -->
    {#if total_docs > 0}
      <td class="p-4 cursor-default align-top flex flex-row gap-4">
        <div class="flex flex-col gap-3">
          <!-- Overall Progress -->
          <div class="flex items-center justify-between">
            {#if status === "running"}
              <span class="text-sm text-gray-500">{completed_pct}%</span>
            {/if}
          </div>
          {#if status === "running"}
            <progress
              class="progress progress-secondary bg-secondary/20 w-full h-2"
              value={rag_progress.total_document_completed_count || 0}
              max={total_docs || 100}
            ></progress>
          {/if}
          {#if total_docs > 0}
            <div class="text-xs text-gray-500 text-start">
              {rag_progress.total_document_completed_count || 0} of {total_docs}
              documents processed
            </div>
          {/if}
          <div class="flex flex-row justify-start">
            <RunRagControl {rag_config} {project_id} />
          </div>
        </div>
      </td>
    {:else}
      <td class="p-4 cursor-default align-top">
        <div class="flex flex-col gap-3">
          <div class="text-xs text-gray-500 text-start">
            <p>Looks like you don't have any documents yet.</p>
            <p>
              <a href={`/docs/library/${project_id}`} class="link">
                Create documents
              </a>
              to get started.
            </p>
          </div>
        </div>
      </td>
    {/if}
  </tr>
{/if}
