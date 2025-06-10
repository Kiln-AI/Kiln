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
    <!-- Attribution: https://www.svgrepo.com/svg/532511/play -->
    <svg
      viewBox="0 0 24 24"
      fill="currentColor"
      class="w-4 h-4"
      xmlns="http://www.w3.org/2000/svg"
      ><g id="SVGRepo_bgCarrier" stroke-width="0"></g><g
        id="SVGRepo_tracerCarrier"
        stroke-linecap="round"
        stroke-linejoin="round"
      ></g><g id="SVGRepo_iconCarrier">
        <path
          d="M16.6582 9.28638C18.098 10.1862 18.8178 10.6361 19.0647 11.2122C19.2803 11.7152 19.2803 12.2847 19.0647 12.7878C18.8178 13.3638 18.098 13.8137 16.6582 14.7136L9.896 18.94C8.29805 19.9387 7.49907 20.4381 6.83973 20.385C6.26501 20.3388 5.73818 20.0469 5.3944 19.584C5 19.053 5 18.1108 5 16.2264V7.77357C5 5.88919 5 4.94701 5.3944 4.41598C5.73818 3.9531 6.26501 3.66111 6.83973 3.6149C7.49907 3.5619 8.29805 4.06126 9.896 5.05998L16.6582 9.28638Z"
          stroke="#000000"
          stroke-width="2"
          stroke-linejoin="round"
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
