<script lang="ts">
  import type { RagConfig } from "$lib/types"
  import { formatDate } from "$lib/utils/formatters"
  import { goto } from "$app/navigation"
  import RunRagControl from "./run_rag_control.svelte"

  export let rag_config: RagConfig
  export let project_id: string

  function row_clicked() {
    goto(`/docs/rag_configs/${project_id}/${rag_config.id}/rag_config`)
  }

  let row_hovered = false

  function columns(): string[] {
    let name: string = rag_config.name || ""
    let extractor_config_id: string = rag_config.extractor_config_id || ""
    let chunker_config_id: string = rag_config.chunker_config_id || ""
    let embedding_config_id: string = rag_config.embedding_config_id || ""
    return [
      name,
      extractor_config_id,
      chunker_config_id,
      embedding_config_id,
      formatDate(rag_config.created_at),
    ]
  }

  const fakeRagProgressStore = {
    status: {
      [rag_config.id || ""]: "complete",
    },
    progress: {
      [rag_config.id || ""]: {
        total: 100,
        success: 100,
        error: 0,
      },
    },
  }
</script>

<tr class={row_hovered ? "hover" : ""}>
  {#each columns() as column}
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
      {column}
    </td>
  {/each}
  <td class="no-hover cursor-default">
    <div class="flex flex-row gap-8 place-items-center min-w-[350px]">
      <RunRagControl {rag_config} {project_id} />
      <div class="flex flex-col gap-1">
        {#if fakeRagProgressStore.status[rag_config.id || ""] === "completed_with_errors"}
          <div class="badge badge-error badge-outline py-3 font-medium">
            Errors
          </div>
        {:else if fakeRagProgressStore.status[rag_config.id || ""] === "running"}
          <div class="badge badge-success badge-outline py-3 font-medium">
            Running
          </div>
        {:else if fakeRagProgressStore.status[rag_config.id || ""] === "complete"}
          <div class="badge badge-primary badge-outline py-3 font-medium">
            Complete
          </div>
        {:else if fakeRagProgressStore.status[rag_config.id || ""] === "incomplete"}
          <div class="badge badge-error badge-outline py-3 font-medium">
            Incomplete (50%)
          </div>
        {:else if fakeRagProgressStore.status[rag_config.id || ""] === "not_started"}
          <div class="badge badge-warning badge-outline py-3 font-medium">
            Not Started
          </div>
        {/if}
      </div>
    </div>
  </td>
</tr>
