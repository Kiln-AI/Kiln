<script lang="ts">
  export let title: string = ""
  export let width: string = ""
  export let action_buttons: Array<Record<string, unknown>> = []

  export function show() {}
  export function close() {}
</script>

<div data-testid="dialog-stub" data-title={title} data-width={width}>
  <slot />
</div>
