<script lang="ts">
  // Stub for $lib/ui/dialog.svelte: jsdom does not implement <dialog>.showModal(),
  // and these tests only need the page body, not the dialogs.
  export let title: string = ""
  export let blur_background: boolean = false
  export let action_buttons: Array<Record<string, unknown>> = []
  // Referenced so svelte-check does not flag them unused; the page passes both.
  void blur_background
  void action_buttons
  export function show() {}
  export function close() {}
</script>

<div data-testid="dialog-stub" data-title={title}>
  <slot />
</div>
