<script lang="ts">
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import Dialog from "$lib/ui/dialog.svelte"

  export let btn_size: "normal" | "mid" = "mid"
  export let on_run_complete: () => void = () => {}
  export let run_url: string
  export let extractor_state:
    | "not_started"
    | "running"
    | "complete"
    | "complete_with_errors" = "not_started"

  let run_dialog: Dialog | null = null
  let running_progress_dialog: Dialog | null = null
  let extractor_run_error: KilnError | null = null

  let extracted_count = 0
  let total_count = 0
  let error_count = 0

  function run_extractor(): boolean {
    if (!run_url) {
      extractor_run_error = new KilnError("Extractor run URL missing", null)
      extractor_state = "complete_with_errors"
      running_progress_dialog?.show()
      return true
    }

    extractor_state = "running"
    extracted_count = 0
    total_count = 0
    error_count = 0

    const eventSource = new EventSource(run_url)

    eventSource.onmessage = (event) => {
      try {
        if (event.data === "complete") {
          eventSource.close()
          extractor_state =
            error_count > 0 ? "complete_with_errors" : "complete"
          on_run_complete()
        } else {
          const data = JSON.parse(event.data)
          extracted_count = data.progress
          total_count = data.total
          error_count = data.errors
          extractor_state = "running"
        }
      } catch (error) {
        eventSource.close()
        extractor_run_error = createKilnError(error)
        extractor_state = "complete_with_errors"
        on_run_complete()
      }
    }

    eventSource.onerror = (error) => {
      eventSource.close()
      extractor_state = "complete_with_errors"
      extractor_run_error = createKilnError(error)
      on_run_complete()
    }

    running_progress_dialog?.show()
    return true
  }

  function re_run_extractor(): boolean {
    run_extractor()
    return false
  }

  function run_dialog_buttons(state: string) {
    let buttons = []

    if (state === "complete" || state === "complete_with_errors") {
      buttons.push({
        label: "Close",
        isCancel: true,
        isPrimary: false,
      })
    }

    if (state === "complete_with_errors") {
      buttons.push({
        label: "Re-run",
        isPrimary: true,
        action: re_run_extractor,
      })
    }

    return buttons
  }
</script>

{#if extractor_state === "not_started"}
  <button
    class="btn {btn_size === 'mid'
      ? 'btn-mid'
      : ''} btn-primary whitespace-nowrap"
    on:click={() => {
      run_dialog?.show()
    }}
  >
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
    Run
  </button>
{:else}
  <button
    class="btn {btn_size === 'mid' ? 'btn-mid' : ''} whitespace-nowrap"
    on:click={() => {
      running_progress_dialog?.show()
    }}
  >
    {#if extractor_state === "running"}
      <div class="loading loading-spinner loading-xs"></div>
      Running...
    {:else if extractor_state === "complete"}
      Complete
    {:else if extractor_state === "complete_with_errors"}
      Complete with Errors
    {:else}
      Status
    {/if}
  </button>
{/if}

<Dialog
  bind:this={running_progress_dialog}
  title=""
  action_buttons={run_dialog_buttons(extractor_state)}
>
  <div
    class="mt-12 mb-6 flex flex-col items-center justify-center min-h-[100px] text-center"
  >
    {#if extractor_state === "complete"}
      <div class="font-medium">Extraction Complete 🎉</div>
    {:else if extractor_state === "complete_with_errors"}
      <div class="font-medium">Extraction Complete with Errors</div>
    {:else if extractor_state === "running"}
      <div class="loading loading-spinner loading-lg text-success"></div>
      <div class="font-medium mt-4">Running...</div>
    {/if}
    <div class="text-sm font-light min-w-[120px]">
      {#if total_count > 0}
        <div>{extracted_count + error_count} of {total_count}</div>
      {/if}
      {#if error_count > 0}
        <div class="text-error font-light text-xs">
          {error_count} error{error_count === 1 ? "" : "s"}
        </div>
      {/if}
      {#if extractor_run_error}
        <div class="text-error font-light text-xs mt-2">
          {extractor_run_error.getMessage() || "An unknown error occurred"}
        </div>
      {/if}
    </div>
  </div>
</Dialog>

<Dialog
  bind:this={run_dialog}
  title="Extract all documents?"
  action_buttons={[
    { label: "Cancel", isCancel: true },
    { label: "Extract all documents", action: run_extractor, isPrimary: true },
  ]}
>
  <div class="flex flex-col gap-2 font-light mt-4">
    <div>
      This may take a while, depending on the number of documents. We won't
      extract documents that have already been extracted.
    </div>
    <div>Don't close this page if you want to monitor progress.</div>
  </div>
</Dialog>
