<script context="module" lang="ts">
  // Counts opens across every stub instance, so a test can tell which of two
  // dialogs opened last and so sits on top.
  let open_count = 0
</script>

<script lang="ts">
  // Stub for $lib/ui/dialog.svelte: jsdom does not implement <dialog>.showModal(),
  // so the stub tracks open state itself. The real dialog's slot is inside a
  // <dialog> the user cannot see until show(), so the stub only renders its
  // content once opened — a test that forgets to open it sees nothing.
  import { createEventDispatcher } from "svelte"

  export let title: string = ""
  export let blur_background: boolean = false
  export let action_buttons: Array<Record<string, unknown>> = []
  export let width: string = "normal"
  // Referenced so svelte-check does not flag them unused; the page passes them.
  void blur_background
  void action_buttons
  void width

  const dispatch = createEventDispatcher()
  let is_open = false
  let opened_at = 0
  export function show() {
    is_open = true
    opened_at = ++open_count
  }
  export function close() {
    if (!is_open) return
    is_open = false
    dispatch("close")
  }
</script>

<div
  data-testid="dialog-stub"
  data-title={title}
  data-open={is_open}
  data-opened-at={opened_at}
>
  {#if is_open}
    <button type="button" data-testid="dialog-stub-close" on:click={close}
      >Close</button
    >
    <slot />
  {/if}
</div>
