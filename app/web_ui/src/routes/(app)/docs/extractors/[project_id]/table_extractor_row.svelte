<script lang="ts">
  import type { ExtractorConfig } from "$lib/types"
  import { extractor_output_format, formatDate } from "$lib/utils/formatters"
  import {
    extractorProgressStore,
    formatProgressPercentage,
  } from "$lib/stores/extractor_progress_store"
  import RunExtractorControl from "./run_extractor_control.svelte"
  import { goto } from "$app/navigation"

  export let extractor_config: ExtractorConfig
  export let project_id: string

  function row_clicked() {
    goto(`/docs/extractors/${project_id}/${extractor_config.id}/extractor`)
  }

  let row_hovered = false

  function rows(): string[] {
    let model: string = `${extractor_config.model_name} (${extractor_config.model_provider_name})`
    return [
      extractor_config.name,
      model,
      extractor_output_format(extractor_config.output_format),
      formatDate(extractor_config.created_at),
    ]
  }
</script>

<tr class={row_hovered ? "hover" : ""}>
  {#each rows() as row}
    <td
      class="cursor-pointer"
      on:mouseenter={() => {
        row_hovered = true
      }}
      on:mouseleave={() => {
        row_hovered = false
      }}
      on:click={() => {
        row_clicked()
      }}
    >
      {row}
    </td>
  {/each}
  <td class="no-hover cursor-default">
    <div class="flex flex-row gap-8 place-items-center min-w-[350px]">
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
