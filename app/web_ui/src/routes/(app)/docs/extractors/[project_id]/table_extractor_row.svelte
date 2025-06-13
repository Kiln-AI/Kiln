<script lang="ts">
  import type { ExtractorConfig } from "$lib/types"
  import { formatDate } from "$lib/utils/formatters"
  import {
    extractorProgress,
    formatProgressPercentage,
  } from "$lib/stores/extractor_progress"
  import RunExtractorControl from "./run_extractor_control.svelte"

  export let extractor_config: ExtractorConfig
  export let project_id: string
</script>

<tr>
  <td class="flex flex-col gap-1">
    <div class="font-medium">
      <a
        href={`/docs/extractors/${project_id}/${extractor_config.id}/extractor`}
        class="link"
      >
        {extractor_config.name}
      </a>
    </div>

    <div class="text-sm text-gray-500">
      Description: {extractor_config.description || "N/A"}
    </div>

    <div class="text-sm text-gray-500">
      Output: {extractor_config.output_format}
    </div>

    <div class="text-sm text-gray-500">
      Created: {formatDate(extractor_config.created_at)}
    </div>
  </td>
  <td>{extractor_config.extractor_type}</td>
  <td>
    <div class="flex flex-col gap-1">
      {#if extractor_config.is_archived}
        <div class="badge badge-neutral badge-outline py-3 font-medium">
          Archived
        </div>
      {:else if $extractorProgress.status[extractor_config.id || ""] === "completed_with_errors"}
        <div class="badge badge-error badge-outline py-3 font-medium">
          Errors
        </div>
      {:else if $extractorProgress.status[extractor_config.id || ""] === "running"}
        <div class="badge badge-success badge-outline py-3 font-medium">
          Running
        </div>
      {:else if $extractorProgress.status[extractor_config.id || ""] === "complete"}
        <div class="badge badge-primary badge-outline py-3 font-medium">
          Complete
        </div>
      {:else if $extractorProgress.status[extractor_config.id || ""] === "incomplete"}
        <div class="badge badge-error badge-outline py-3 font-medium">
          Incomplete (
          {formatProgressPercentage(
            $extractorProgress.progress[extractor_config.id || ""],
          )})
        </div>
      {:else if $extractorProgress.status[extractor_config.id || ""] === "not_started"}
        <div class="badge badge-warning badge-outline py-3 font-medium">
          Not Started
        </div>
      {/if}
    </div>
  </td>
  <td>
    <RunExtractorControl {extractor_config} {project_id} />
  </td>
</tr>
