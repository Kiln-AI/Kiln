<script lang="ts">
  import Dialog from "$lib/ui/dialog.svelte"
  import { extractorProgressStore } from "$lib/stores/extractor_progress_store"
  import type { RagConfigWithSubConfigs, RagProgress } from "$lib/types"
  import RunRagDialog from "./run_rag_dialog.svelte"

  export let btn_size: "normal" | "mid" = "mid"
  export let project_id: string
  export let rag_config: RagConfigWithSubConfigs
  export let rag_progress: RagProgress

  $: rag_config_id = rag_config.id || ""

  let run_rag_dialog: Dialog | null = null

  let progress_dialog: Dialog | null = null
  export function show() {
    progress_dialog?.show()
  }

  export function close() {
    progress_dialog?.close()
    return true
  }

  $: get_status = () => {
    if (rag_progress.total_document_completed_count === 0) {
      return "not_started"
    }

    if (
      rag_progress.total_document_completed_count ===
      rag_progress.total_document_count
    ) {
      return "complete"
    }

    return "incomplete"
  }

  function get_state_to_label(status: string) {
    const state_to_label: Record<
      string,
      {
        label: string
        icon: "play" | "loading" | null
        action: () => void
        isPrimary: boolean
      } | null
    > = {
      not_started: {
        label: "Run",
        icon: "play",
        isPrimary: true,
        action: () => {
          run_rag_dialog?.show()
        },
      },
      running: {
        label: "Running",
        icon: "loading",
        isPrimary: false,
        action: () => {
          progress_dialog?.show()
        },
      },
      completed_with_errors: {
        label: "View details",
        icon: null,
        isPrimary: false,
        action: () => {
          progress_dialog?.show()
        },
      },
      complete: {
        label: "View details",
        icon: null,
        isPrimary: false,
        action: () => {
          console.log("view details")
        },
      },
      incomplete: {
        label: "Retry",
        icon: "play",
        isPrimary: true,
        action: () => {
          extractorProgressStore.run_extractor(project_id, rag_config_id)
          return false
        },
      },
    }

    return state_to_label[status]
  }

  $: status = get_status()
  $: disabled = status === "complete"
  $: button_state = get_state_to_label(status)

  $: console.log(status)
  $: console.log(button_state)
</script>

{#if button_state}
  <button
    class="btn {btn_size === 'mid'
      ? 'btn-mid'
      : ''} whitespace-nowrap {button_state?.isPrimary ? 'btn-primary' : ''}"
    on:click={(event) => {
      event.stopPropagation()
      button_state?.action()
    }}
    {disabled}
  >
    {#if button_state?.icon === "loading"}
      <div class="loading loading-spinner loading-xs"></div>
    {:else if button_state?.icon === "play"}
      <!-- Attribution: https://www.svgrepo.com/svg/526106/play -->
      <svg
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        class="w-4 h-4"
        ><g id="SVGRepo_bgCarrier" stroke-width="0"></g><g
          id="SVGRepo_tracerCarrier"
          stroke-linecap="round"
          stroke-linejoin="round"
        ></g><g id="SVGRepo_iconCarrier">
          <path
            d="M21.4086 9.35258C23.5305 10.5065 23.5305 13.4935 21.4086 14.6474L8.59662 21.6145C6.53435 22.736 4 21.2763 4 18.9671L4 5.0329C4 2.72368 6.53435 1.26402 8.59661 2.38548L21.4086 9.35258Z"
            fill="currentColor"
          ></path>
        </g></svg
      >
    {/if}
    {button_state?.label}
  </button>
{/if}

<RunRagDialog bind:dialog={run_rag_dialog} {rag_config_id} {project_id} />
