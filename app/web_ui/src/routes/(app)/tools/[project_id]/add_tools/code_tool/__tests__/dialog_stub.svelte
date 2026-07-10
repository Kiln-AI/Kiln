<script lang="ts">
  export let title: string = ""
  export let subtitle: string = ""
  export let width: string = ""
  export let action_buttons: unknown = []

  export function show(): void {}
  export function close(): void {}
</script>

<div
  data-testid="dialog-stub"
  data-title={title}
  data-subtitle={subtitle}
  data-width={width}
  data-actions={action_buttons ? "set" : ""}
>
  <slot />
</div>
