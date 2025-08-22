<script lang="ts">
  import Dialog from "$lib/ui/dialog.svelte"
  import type { RagConfigWithSubConfigs } from "$lib/types"
  import RunRagDialog from "./run_rag_dialog.svelte"
  import { ragProgressStore } from "$lib/stores/rag_progress_store"
  import type { RagConfigurationStatus } from "$lib/stores/rag_progress_store"

  export let project_id: string
  export let rag_config: RagConfigWithSubConfigs

  $: rag_config_id = rag_config.id || ""

  let run_rag_dialog: Dialog | null = null

  function status_to_btn_props(status: RagConfigurationStatus) {
    switch (status) {
      case "complete": {
        return {
          text: "Complete",
          color: "btn-success",
          action: () => {
            run_rag_dialog?.show()
          },
        }
      }
      case "incomplete": {
        return {
          text: "Incomplete",
          color: "btn-warning",
          action: () => {
            run_rag_dialog?.show()
          },
        }
      }
      case "running": {
        return {
          text: "Running",
          color: "btn-neutral",
          action: () => {
            run_rag_dialog?.show()
          },
        }
      }
      case "completed_with_errors": {
        return {
          text: "Completed with errors",
          color: "btn-error",
          action: () => {
            run_rag_dialog?.show()
          },
        }
      }
      default: {
        return {
          text: "Run",
          color: "btn-primary btn-outline px-4",
          action: () => {
            run_rag_dialog?.show()
          },
        }
      }
    }
  }

  $: status = $ragProgressStore.status[rag_config_id]

  $: btn_props = status_to_btn_props(status)
</script>

{#if status !== "complete"}
  <button
    class="btn btn-sm {btn_props.color} font-medium"
    on:click={(event) => {
      event.stopPropagation()
      btn_props.action()
    }}
  >
    {#if status === "running"}
      <div class="loading loading-spinner loading-xs mr-2"></div>
    {/if}
    <span>{btn_props.text}</span>
  </button>
{:else}
  <button
    class="link text-sm text-gray-500"
    on:click={() => {
      run_rag_dialog?.show()
    }}
  >
    Details
  </button>
{/if}

<RunRagDialog
  bind:dialog={run_rag_dialog}
  {rag_config_id}
  {project_id}
  {rag_config}
/>
