<script lang="ts">
  import type { RagConfigWithSubConfigs } from "$lib/types"
  import { formatDate } from "$lib/utils/formatters"
  import RunRagControl from "./run_rag_control.svelte"
  import {
    embedding_model_name,
    model_name,
    provider_name_from_id,
    vector_store_name,
  } from "$lib/stores"
  import {
    compute_overall_completion_percentage,
    ragProgressStore,
    type RagConfigurationStatus,
  } from "$lib/stores/rag_progress_store"
  import { goto } from "$app/navigation"

  export let rag_config: RagConfigWithSubConfigs
  export let project_id: string
  $: rag_progress = $ragProgressStore.progress[rag_config.id || ""]

  let row_hovered = false

  // Calculate percentages for progress bar
  $: total_docs = rag_progress?.total_document_count || 0
  $: completed_pct = compute_overall_completion_percentage(rag_progress)

  $: status = $ragProgressStore.status[rag_config.id || ""]

  function status_to_badge_props(
    status: RagConfigurationStatus,
    is_archived: boolean,
  ) {
    if (is_archived) {
      return {
        text: "Archived",
        archived: true,
      }
    }

    switch (status) {
      case "complete": {
        return {
          text: "Complete",
          primary: true,
        }
      }
      case "incomplete": {
        return {
          text: "Incomplete",
          warning: true,
          show_percentage: true,
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
          show_percentage: true,
        }
      }
      default: {
        return {
          text: "Not Started",
        }
      }
    }
  }

  $: status_badge_props = status_to_badge_props(status, rag_config.is_archived)

  function open() {
    goto(`/docs/rag_configs/${project_id}/${rag_config.id}/rag_config`)
  }
</script>

{#if rag_progress && rag_config}
  <tr
    class="{row_hovered ? 'hover' : ''} cursor-pointer hover:bg-base-200"
    on:click|stopPropagation={open}
  >
    <!-- Step Info Card -->
    <td class="align-top p-4">
      <div class="flex flex-col gap-2">
        <!-- Header -->
        <div class="font-medium">
          {rag_config.name}
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
          <div>
            Search Index: {vector_store_name(
              rag_config.vector_store_config.store_type,
            ) || "N/A"}
          </div>
          <div class="text-xs text-gray-500">
            Created {formatDate(rag_config.created_at)}
          </div>
          <div class="text-xs text-gray-500 flex flex-row flex-wrap gap-2 w-80">
            {#each rag_config.tags || [] as tag}
              <div class="badge bg-gray-200 text-gray-500 text-xs">
                {tag}
              </div>
            {/each}
          </div>
        </div>
      </div>
    </td>

    <!-- Progress Section -->
    {#if total_docs > 0}
      <td class="p-4 align-top">
        <div class="flex flex-col gap-2 w-full max-w-[360px]">
          <!-- Status and Action Row -->
          <div class="flex items-center justify-between gap-4">
            <div
              class="badge px-3 py-1 {status_badge_props?.warning
                ? 'badge-outline badge-warning'
                : ''} {status_badge_props?.running
                ? 'badge-outline badge-success'
                : ''} {status_badge_props?.error
                ? 'badge-outline badge-error'
                : ''} {status_badge_props?.primary
                ? 'badge-outline badge-primary'
                : ''} {status_badge_props?.archived ? 'badge-secondary' : ''}"
            >
              {status_badge_props?.text}
              {#if status_badge_props?.show_percentage}
                ({completed_pct}%)
              {/if}
            </div>
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
                value={completed_pct || 0}
                max={100}
              ></progress>
            </div>
          {:else if total_docs > 0 && !rag_config.is_archived}
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

          {#if !rag_config.is_archived}
            <div role="presentation" on:click|stopPropagation>
              <RunRagControl {rag_config} {project_id} />
            </div>
          {/if}
        </div>
      </td>
    {:else}
      <td class="p-4 align-top">
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
