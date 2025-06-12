<script lang="ts">
  import Dialog from "$lib/ui/dialog.svelte"
  import { extractorProgress } from "$lib/stores/extractor_progress"

  export let extractor_config_id: string
  export let project_id: string
  export let btn_size: "normal" | "mid" = "mid"

  let progress_dialog: Dialog | null = null
  export function show() {
    progress_dialog?.show()
  }

  export function close() {
    progress_dialog?.close()
    return true
  }

  function run_dialog_buttons(state: string) {
    let buttons = []

    if (state === "complete") {
      buttons.push({
        label: "Close",
        isCancel: true,
        isPrimary: false,
      })
    }

    if (state === "incomplete" || state === "completed_with_errors") {
      buttons.push({
        label: "Re-run",
        isPrimary: true,
        action: () => {
          extractorProgress.run_extractor(project_id, extractor_config_id)
          return false
        },
      })
    }

    return buttons
  }

  $: error_count = $extractorProgress.progress[extractor_config_id]?.error || 0
  $: total_count = $extractorProgress.progress[extractor_config_id]?.total || 0
  $: success_count =
    $extractorProgress.progress[extractor_config_id]?.success || 0
</script>

{#if $extractorProgress.status[extractor_config_id] === "running"}
  <button
    class="btn {btn_size === 'mid' ? 'btn-mid' : ''} whitespace-nowrap"
    on:click={() => {
      progress_dialog?.show()
    }}
  >
    <div class="loading loading-spinner loading-xs"></div>
    Running... ({$extractorProgress.progress[extractor_config_id]?.success} of
    {$extractorProgress.progress[extractor_config_id]?.total})
  </button>
{:else if $extractorProgress.status[extractor_config_id] === "completed_with_errors"}
  <button
    class="btn btn-mid"
    on:click={() => {
      progress_dialog?.show()
    }}
  >
    Retry
  </button>
{/if}

<Dialog
  bind:this={progress_dialog}
  title=""
  action_buttons={run_dialog_buttons(
    $extractorProgress.status[extractor_config_id],
  )}
>
  <div
    class="mt-12 mb-6 flex flex-col items-center justify-center min-h-[100px] text-center"
  >
    {#if $extractorProgress.status[extractor_config_id] === "complete"}
      <div class="font-medium">Extraction Complete 🎉</div>
    {:else if $extractorProgress.status[extractor_config_id] === "incomplete"}
      <div class="font-medium">Extraction Incomplete</div>
    {:else if $extractorProgress.status[extractor_config_id] === "running"}
      <div class="loading loading-spinner loading-lg text-success"></div>
      <div class="font-medium mt-4">Running...</div>
    {/if}
    <div class="text-sm font-light min-w-[120px]">
      {#if total_count > 0}
        <div>
          Completed {success_count} of {total_count}
        </div>
      {/if}
      {#if error_count > 0}
        <div class="text-error font-light text-xs">
          {error_count} error{error_count === 1 ? "" : "s"}
        </div>
      {/if}
    </div>
  </div>
</Dialog>
