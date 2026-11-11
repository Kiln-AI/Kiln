<script lang="ts">
  import Dialog from "$lib/ui/dialog.svelte"
  import TraceView from "$lib/ui/trace/trace.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import type { Trace } from "$lib/types"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"

  /** The judge's conversation, when the caller already has it. */
  export let trace: Trace | null = null
  /**
   * Fetches the conversation on first open, for callers that only know one exists.
   * Pass null when there is none, so the link stays hidden.
   */
  export let load_trace: (() => Promise<Trace | null>) | null = null

  let dialog: Dialog | null = null
  let opened = false
  let loading = false
  let error: KilnError | null = null

  $: has_trace = (trace !== null && trace.length > 0) || load_trace !== null

  async function open() {
    opened = true
    dialog?.show()
    if (trace !== null || load_trace === null || loading) {
      return
    }
    loading = true
    error = null
    try {
      trace = await load_trace()
    } catch (e) {
      error = createKilnError(e)
    } finally {
      loading = false
    }
  }
</script>

{#if has_trace}
  <button class="text-xs link link-hover text-gray-400" on:click={open}>
    Judge trace
  </button>

  <Dialog bind:this={dialog} title="Judge Trace" width="extra_wide">
    {#if loading}
      <div
        class="flex justify-center items-center min-h-[100px]"
        data-testid="judge-trace-loading"
      >
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if error}
      <Warning
        warning_color="error"
        warning_message={error.getMessage() ||
          "The judge trace could not be loaded."}
      />
    {:else if opened && trace && trace.length > 0}
      {#key trace}
        <TraceView {trace} />
      {/key}
    {:else if opened}
      <p class="font-light text-sm">No judge trace was saved for this run.</p>
    {/if}
  </Dialog>
{/if}
