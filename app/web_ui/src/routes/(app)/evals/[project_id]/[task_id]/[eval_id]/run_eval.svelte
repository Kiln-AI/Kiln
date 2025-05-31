<script lang="ts">
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import Dialog from "$lib/ui/dialog.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import { _ } from "svelte-i18n"

  export let btn_size: "normal" | "mid" = "mid"
  export let on_run_complete: () => void = () => {}
  export let run_url: string
  export let eval_state:
    | "not_started"
    | "running"
    | "complete"
    | "complete_with_errors" = "not_started"

  let run_dialog: Dialog | null = null
  let running_progress_dialog: Dialog | null = null
  let eval_run_error: KilnError | null = null

  let eval_complete_count = 0
  let eval_total_count = 0
  let eval_error_count = 0

  async function run_eval(): Promise<boolean> {
    if (!run_url) {
      eval_run_error = new KilnError(
        $_("evaluation.select_all_options_error"),
        null,
      )
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

    // Switch over to the progress dialog, closing the run dialog
    running_progress_dialog?.show()
    return true
  }

  // Returns false so the dialog isn't closed
  async function re_run_eval(): Promise<boolean> {
    await run_eval()
    return false
  }

  function run_dialog_buttons(eval_state: string) {
    let buttons = []

    if (eval_state === "complete" || eval_state === "complete_with_errors") {
      buttons.push({
        label: $_("common.close"),
        isCancel: true,
        isPrimary: false,
      })
    }

    if (eval_state === "complete_with_errors") {
      buttons.push({
        label: $_("evaluation.re_run_eval"),
        isPrimary: true,
        asyncAction: re_run_eval,
      })
    }

    return buttons
  }
</script>

{#if eval_state === "not_started"}
  <button
    class="btn {btn_size === 'mid'
      ? 'btn-mid'
      : ''} btn-primary whitespace-nowrap"
    on:click={() => {
      run_dialog?.show()
    }}>{$_("evaluation.run_eval")}</button
  >
{:else}
  <button
    class="btn {btn_size === 'mid' ? 'btn-mid' : ''} whitespace-nowrap"
    on:click={() => {
      running_progress_dialog?.show()
    }}
  >
    {#if eval_state === "running"}
      <div class="loading loading-spinner loading-xs"></div>
      {$_("evaluation.running")}
    {:else if eval_state === "complete"}
      {$_("evaluation.eval_complete")}
    {:else if eval_state === "complete_with_errors"}
      {$_("evaluation.eval_complete_with_errors")}
    {:else}
      {$_("evaluation.eval_status")}
    {/if}
  </button>
{/if}

<Dialog
  bind:this={running_progress_dialog}
  title=""
  action_buttons={run_dialog_buttons(eval_state)}
>
  <div
    class="mt-12 mb-6 flex flex-col items-center justify-center min-h-[100px] text-center"
  >
    {#if eval_state === "complete" && eval_complete_count == 0}
      <div class="font-medium">{$_("evaluation.no_data_needed")}</div>
      <div class="text-gray-500 text-sm mt-2 flex flex-col gap-2">
        <div>
          {$_("evaluation.add_more_data_instruction")}
          <a
            href="https://docs.getkiln.ai/docs/evaluations#create-your-eval-datasets"
            target="_blank"
            class="link">{$_("evaluation.read_docs")}</a
          >
          {$_("evaluation.for_instructions")}.
        </div>
      </div>
    {:else if eval_state === "complete"}
      <div class="font-medium">{$_("evaluation.eval_complete")} 🎉</div>
    {:else if eval_state === "complete_with_errors"}
      <div class="font-medium">
        {$_("evaluation.eval_complete_with_errors")}
      </div>
    {:else if eval_state === "running"}
      <div class="loading loading-spinner loading-lg text-success"></div>
      <div class="font-medium mt-4">{$_("evaluation.running")}</div>
    {/if}
    <div class="text-sm font-light min-w-[120px]">
      {#if eval_total_count > 0}
        <div>
          {eval_complete_count + eval_error_count}
          {$_("evaluation.of")}
          {eval_total_count}
        </div>
      {/if}
      {#if eval_error_count > 0}
        <div class="text-error font-light text-xs">
          {eval_error_count}
          {$_("evaluation.error")}{eval_error_count === 1
            ? ""
            : $_("evaluation.errors_plural")}
        </div>
      {/if}
      {#if eval_run_error}
        <div class="text-error font-light text-xs mt-2">
          {eval_run_error.getMessage() ||
            $_("evaluation.unknown_error_occurred")}
        </div>
      {/if}
    </div>
  </div>
</Dialog>

<Dialog
  bind:this={run_dialog}
  title={$_("evaluation.run_eval")}
  action_buttons={[
    { label: $_("common.cancel"), isCancel: true },
    {
      label: $_("evaluation.run_eval"),
      asyncAction: run_eval,
      isPrimary: true,
    },
  ]}
>
  <div class="flex flex-col gap-2 font-light mt-4">
    <div>{$_("evaluation.run_with_config")}</div>
    <div>{$_("evaluation.dont_close_page")}</div>
    <Warning
      warning_color="warning"
      warning_message={$_("evaluation.considerable_compute")}
      tight={true}
    />
  </div>
</Dialog>
