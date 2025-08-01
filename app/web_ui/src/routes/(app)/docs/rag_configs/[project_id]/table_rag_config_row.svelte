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
  let config_expanded = false

  function toggle_config_expanded(event: Event) {
    event.stopPropagation()
    config_expanded = !config_expanded
  }

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
          <button
            on:click={toggle_config_expanded}
            class="text-base-content/40 hover:text-base-content/70 transition-colors"
            title={config_expanded
              ? "Hide configuration details"
              : "Show configuration details"}
          >
            <div class="flex items-center justify-center">
              <svg
                fill="currentColor"
                class="h-4 w-4 transition-transform duration-200 {config_expanded
                  ? 'rotate-180'
                  : ''}"
                version="1.1"
                id="Layer_1"
                xmlns="http://www.w3.org/2000/svg"
                xmlns:xlink="http://www.w3.org/1999/xlink"
                viewBox="0 0 407.437
              407.437"
                xml:space="preserve"
              >
                <polygon
                  points="386.258,91.567 203.718,273.512 21.179,91.567 0,112.815 203.718,315.87 407.437,112.815 "
                />
              </svg>
            </div>
          </button>
        </div>

        <!-- Description -->
        <p class="text-sm text-gray-500 leading-relaxed">
          Description: {rag_config.description || "N/A"}
        </p>

        <!-- Detailed Configuration -->
        {#if config_expanded}
          <div class="space-y-3 pt-2">
            <!-- Extractor Details -->
            <div class="space-y-1">
              <div class="flex items-center gap-2">
                <div class="w-2 h-2 rounded-full bg-primary"></div>
                <span class="text-xs font-medium">Extractor</span>
              </div>
              <div class="ml-4 space-y-1 text-xs text-base-content/70">
                <div>
                  Provider: {provider_name_from_id(
                    rag_config.extractor_config.model_provider_name,
                  ) || "N/A"}
                </div>
                <div>
                  Model: {model_name(
                    rag_config.extractor_config?.model_name,
                    null,
                  ) || "N/A"}
                </div>
                <div>
                  Format: {rag_config.extractor_config.output_format || "N/A"}
                </div>
              </div>
            </div>

            <!-- Chunker Details -->
            <div class="space-y-1">
              <div class="flex items-center gap-2">
                <div class="w-2 h-2 rounded-full bg-secondary"></div>
                <span class="text-xs font-medium">Chunker</span>
              </div>
              <div class="ml-4 space-y-1 text-xs text-base-content/70">
                <div>
                  Strategy: {rag_config.chunker_config.chunker_type || "N/A"}
                </div>
                {#if rag_config.chunker_config.properties?.chunk_size}
                  <div>
                    Size: {rag_config.chunker_config.properties.chunk_size} tokens
                  </div>
                {/if}
                {#if rag_config.chunker_config.properties?.chunk_overlap}
                  <div>
                    Overlap: {rag_config.chunker_config.properties
                      .chunk_overlap} tokens
                  </div>
                {/if}
              </div>
            </div>

            <!-- Embedding Details -->
            <div class="space-y-1">
              <div class="flex items-center gap-2">
                <div class="w-2 h-2 rounded-full bg-accent"></div>
                <span class="text-xs font-medium">Embedding</span>
              </div>
              <div class="ml-4 space-y-1 text-xs text-base-content/70">
                <div>
                  Provider: {provider_name_from_id(
                    rag_config.embedding_config.model_provider_name,
                  ) || "N/A"}
                </div>
                <div>
                  Model: {embedding_model_name(
                    rag_config.embedding_config.model_name,
                    rag_config.embedding_config.model_provider_name,
                  ) || "N/A"}
                </div>
              </div>
            </div>
          </div>
        {/if}

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
