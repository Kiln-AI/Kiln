<script lang="ts">
  import Dialog from "$lib/ui/dialog.svelte"
  import TraceView from "$lib/ui/trace/trace.svelte"
  import type { Trace } from "$lib/types"

  export let judge_trace: Trace

  let dialog: Dialog | null = null
  // Dialog renders its slot even while closed, and expanding every message turns
  // off TraceView's lazy rendering, so a judge trace (which can be hundreds of KB) is
  // built only while the dialog is open.
  let is_open = false

  export function show() {
    dialog?.show()
  }
</script>

<Dialog
  bind:this={dialog}
  title="Judge Trace"
  width="wide"
  on:show={() => (is_open = true)}
  on:close={() => (is_open = false)}
>
  {#if is_open}
    <TraceView
      trace={judge_trace}
      auto_expand_indices={judge_trace.map((_, index) => index)}
    />
  {/if}
</Dialog>
