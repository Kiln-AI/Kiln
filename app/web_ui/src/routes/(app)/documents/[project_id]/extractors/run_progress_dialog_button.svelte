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
    <!-- Attribution: https://www.svgrepo.com/svg/532134/hourglass-start -->
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
          d="M15 6H9M20 21H19M19 21H5M19 21C19 18.4898 17.7877 16.1341 15.7451 14.675L12 12M5 21H4M5 21C5 18.4898 6.21228 16.1341 8.25493 14.675L12 12M20 3H19M19 3H5M19 3C19 5.51022 17.7877 7.86592 15.7451 9.32495L12 12M5 3H4M5 3C5 5.51022 6.21228 7.86592 8.25493 9.32495L12 12"
          stroke="#000000"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        ></path>
      </g></svg
    >
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
