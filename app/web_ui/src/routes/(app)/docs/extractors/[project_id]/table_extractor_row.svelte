<script lang="ts">
  import type { ExtractorConfig } from "$lib/types"
  import { formatDate } from "$lib/utils/formatters"
  import {
    extractorProgressStore,
    formatProgressPercentage,
  } from "$lib/stores/extractor_progress_store"
  import RunExtractorControl from "./run_extractor_control.svelte"
  import { mime_type_to_string } from "$lib/utils/formatters"
  import { goto } from "$app/navigation"

  export let extractor_config: ExtractorConfig
  export let project_id: string

  function row_clicked() {
    goto(`/docs/extractors/${project_id}/${extractor_config.id}/extractor`)
  }
</script>

<tr
  class="hover cursor-pointer"
  on:click={() => {
    row_clicked()
  }}
>
  <td>
    {extractor_config.name}
  </td>
  <td>
    {#if extractor_config.properties && extractor_config.properties["model_name"]}
      {extractor_config.properties["model_name"]}
    {:else}
      {extractor_config.extractor_type}
    {/if}
  </td>
  <td>{mime_type_to_string(extractor_config.output_format)}</td>
  <td>{formatDate(extractor_config.created_at)}</td>
  <td class="md:w-[550px]">
    <div class="flex flex-row gap-8 place-items-center">
      <RunExtractorControl {extractor_config} {project_id} />
      <div class="flex flex-col gap-1">
        {#if extractor_config.is_archived}
          <div class="badge badge-neutral badge-outline py-3 font-medium">
            Archived
          </div>
        {:else if $extractorProgressStore.status[extractor_config.id || ""] === "completed_with_errors"}
          <div class="badge badge-error badge-outline py-3 font-medium">
            Errors
          </div>
        {:else if $extractorProgressStore.status[extractor_config.id || ""] === "running"}
          <div class="badge badge-success badge-outline py-3 font-medium">
            Running
          </div>
        {:else if $extractorProgressStore.status[extractor_config.id || ""] === "complete"}
          <div class="badge badge-primary badge-outline py-3 font-medium">
            Complete
          </div>
        {:else if $extractorProgressStore.status[extractor_config.id || ""] === "incomplete"}
          <div class="badge badge-error badge-outline py-3 font-medium">
            Incomplete (
            {formatProgressPercentage(
              $extractorProgressStore.progress[extractor_config.id || ""],
            )})
          </div>
        {:else if $extractorProgressStore.status[extractor_config.id || ""] === "not_started"}
          <div class="badge badge-warning badge-outline py-3 font-medium">
            Not Started
          </div>
        {/if}
      </div>
    </div>
  </td>
</tr>
