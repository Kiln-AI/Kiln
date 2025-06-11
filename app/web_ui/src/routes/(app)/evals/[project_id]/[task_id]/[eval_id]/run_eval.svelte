<script lang="ts">
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import Dialog from "$lib/ui/dialog.svelte"
  import Warning from "$lib/ui/warning.svelte"

  export let btn_size: "normal" | "mid" | "sm" = "mid"
  export let on_run_complete: () => void = () => {}
  export let run_url: string
  export let eval_state:
    | "not_started"
    | "running"
    | "complete"
    | "complete_with_errors" = "not_started"
  export let button_text: string = "Run All"

  let eval_complete_count = 0
  let eval_total_count = 0
  let eval_error_count = 0

  let run_dialog: Dialog | null = null
  let running_progress_dialog: Dialog | null = null
  let eval_run_error: KilnError | null = null

  async function run_eval(): Promise<boolean> {
    if (!run_url) {
      eval_run_error = new KilnError("No run URL provided", null)
      eval_state = "complete_with_errors"
      // True to close the run dialog, and then show the error in the progress dialog
      running_progress_dialog?.show()
      return true
    }

    eval_state = "running"
    eval_complete_count = 0
    eval_total_count = 0
    eval_error_count = 0

    const eventSource = new EventSource(run_url)

    eventSource.onmessage = (event) => {
      try {
        if (event.data === "complete") {
          // Special end message
          eventSource.close()
          eval_state =
            eval_error_count > 0 ? "complete_with_errors" : "complete"

          on_run_complete()
        } else {
          const data = JSON.parse(event.data)
          eval_complete_count = data.progress
          eval_total_count = data.total
          eval_error_count = data.errors
          eval_state = "running"
        }
      } catch (error) {
        eventSource.close()
        eval_run_error = createKilnError(error)
        eval_state = "complete_with_errors"
        on_run_complete()
      }
    }

    // Don't restart on an error (default SSE behavior)
    eventSource.onerror = (error) => {
      eventSource.close()
      eval_state = "complete_with_errors"
      eval_run_error = createKilnError(error)
      on_run_complete()
    }

    // Wait a moment to ensure dialog is properly closed before showing progress
    await new Promise((resolve) => setTimeout(resolve, 50))

    // Switch over to the progress dialog
    running_progress_dialog?.show()
    return true
  }

  // Returns false so the dialog isn't closed
  function re_run_eval(): boolean {
    run_eval()
    return false
  }

  function run_dialog_buttons(eval_state: string) {
    let buttons = []

    if (eval_state === "complete" || eval_state === "complete_with_errors") {
      buttons.push({
        label: "Close",
        isCancel: true,
        isPrimary: false,
      })
    }

    if (eval_state === "complete_with_errors") {
      buttons.push({
        label: "Re-run Eval",
        isPrimary: true,
        action: re_run_eval,
      })
    }

    return buttons
  }
</script>

{#if eval_state === "not_started"}
  <button
    class="btn {btn_size === 'mid'
      ? 'btn-mid'
      : btn_size === 'sm'
        ? 'btn-sm'
        : ''} btn-primary whitespace-nowrap"
    on:click|stopPropagation={() => {
      run_dialog?.show()
    }}
    disabled={!run_url}>{button_text}</button
  >
{:else}
  <button
    class="btn {btn_size === 'mid'
      ? 'btn-mid'
      : btn_size === 'sm'
        ? 'btn-sm'
        : ''} whitespace-nowrap"
    on:click|stopPropagation={() => {
      running_progress_dialog?.show()
    }}
  >
    {#if eval_state === "running"}
      <div class="loading loading-spinner loading-xs"></div>
      Running...
    {:else if eval_state === "complete"}
      Eval Complete
    {:else if eval_state === "complete_with_errors"}
      Eval Complete with Errors
    {:else}
      Eval Status
    {/if}
  </button>
{/if}

<Dialog
  bind:this={running_progress_dialog}
  title="Running Evaluation"
  action_buttons={run_dialog_buttons(eval_state)}
>
  <div
    class="mt-12 mb-6 flex flex-col items-center justify-center min-h-[100px] text-center"
  >
    {#if eval_state === "complete" && eval_complete_count == 0}
      <div class="font-medium">No Data Needed to be Evaluated</div>
      <div class="text-gray-500 text-sm mt-2 flex flex-col gap-2">
        <div>
          If you want to add more data to your eval,
          <a
            href="https://docs.getkiln.ai/docs/evaluations#create-your-eval-datasets"
            target="_blank"
            class="link">read the docs</a
          > for instructions.
        </div>
      </div>
    {:else if eval_state === "complete"}
      <div class="font-medium">Eval Complete 🎉</div>
    {:else if eval_state === "complete_with_errors"}
      <div class="font-medium">Eval Complete with Errors</div>
    {:else if eval_state === "running"}
      <div class="loading loading-spinner loading-lg text-success"></div>
      <div class="font-medium mt-4">Running...</div>
    {/if}
    <div class="text-sm font-light min-w-[120px]">
      {#if eval_total_count > 0}
        <div>
          {eval_complete_count + eval_error_count} of {eval_total_count}
        </div>
      {/if}
      {#if eval_error_count > 0}
        <div class="text-error font-light text-xs">
          {eval_error_count} error{eval_error_count === 1 ? "" : "s"}
        </div>
      {/if}
      {#if eval_run_error}
        <div class="text-error font-light text-xs mt-2">
          {eval_run_error.getMessage() || "An unknown error occurred"}
        </div>
      {/if}
    </div>
  </div>
</Dialog>

<Dialog
  bind:this={run_dialog}
  title="Run Eval"
  action_buttons={[
    {
      label: "Cancel",
      isCancel: true,
    },
    {
      label: "Run Eval",
      asyncAction: run_eval,
      isPrimary: true,
    },
  ]}
>
  <div class="flex flex-col gap-2 font-light mt-4">
    <div>Run this eval with the selected configuration?</div>
    <div>Don't close this page if you want to monitor progress.</div>
    <Warning
      warning_color="warning"
      warning_message="This may use considerable compute/credits."
      tight={true}
    />
  </div>
</Dialog>
