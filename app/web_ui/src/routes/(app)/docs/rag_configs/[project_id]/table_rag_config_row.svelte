<script lang="ts">
  import type { RagConfigWithSubConfigs, RagProgress } from "$lib/types"
  import { formatDate } from "$lib/utils/formatters"
  import RunRagControl from "./run_rag_control.svelte"
  import {
    embedding_model_name,
    model_name,
    provider_name_from_id,
  } from "$lib/stores"
  import {
    ragProgressStore,
    type RagConfigurationStatus,
  } from "$lib/stores/rag_progress_store"

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

  function status_to_badge_props(
    status: RagConfigurationStatus,
    rag_progress: RagProgress,
  ) {
    switch (status) {
      case "complete": {
        return {
          text: "Complete",
        }
      }
      case "incomplete": {
        if (rag_progress.total_document_completed_count === 0) {
          return {
            text: "Not Started",
          }
        }
        return {
          text: "Incomplete",
          warning: true,
        }
      }
      case "running": {
        return {
          text: "Running",
          running: true,
        }
      }
      case "completed_with_errors": {
        return {
          text: "Complete with Errors",
          error: true,
        }
      }
      default: {
        return {
          text: "Not Started",
        }
      }
    }
  }

  $: status_badge_props = status_to_badge_props(status, rag_progress)
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
      <td class="p-4 cursor-default align-top">
        <div class="flex flex-col gap-2 w-full max-w-[360px]">
          <!-- Status and Action Row -->
          <div class="flex items-center justify-between gap-4">
            <div
              class={`badge badge-outline px-3 py-1 ${status_badge_props?.warning ? "badge-warning" : ""} ${status_badge_props?.running ? "badge-success" : ""} ${status_badge_props?.error ? "badge-error" : ""}`}
            >
              {status_badge_props?.text}
            </div>
            <RunRagControl {rag_config} {project_id} />
          </div>

          <!-- Progress Bar (only when running) -->
          {#if status === "running"}
            <div class="flex flex-col gap-2 pt-2">
              <div class="flex items-center justify-between">
                <span class="text-gray-500">{completed_pct}% Complete</span>
                <span class="text-gray-500">
                  {rag_progress.total_document_completed_count || 0} of {total_docs}
                  documents
                </span>
              </div>
              <progress
                class="progress progress-primary bg-base-200 w-full h-2"
                value={rag_progress.total_document_completed_count || 0}
                max={total_docs || 100}
              ></progress>
            </div>
          {:else if total_docs > 0}
            <!-- Document count for non-running states -->
            <div class="text-gray-500">
              {#if rag_progress.total_document_completed_count < total_docs}
                {rag_progress.total_document_completed_count || 0} of {total_docs}
                documents
              {:else}
                {rag_progress.total_document_completed_count || 0}
                documents
              {/if}
            </div>
          {/if}
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
