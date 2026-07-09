<script lang="ts" context="module">
  export const showCalls: string[] = []
  export const closeCalls: string[] = []
  export const actionButtonsByTitle: Record<
    string,
    Array<Record<string, unknown>>
  > = {}
  export function resetCalls() {
    showCalls.length = 0
    closeCalls.length = 0
    for (const key of Object.keys(actionButtonsByTitle)) {
      delete actionButtonsByTitle[key]
    }
  }
</script>

<script lang="ts">
  export let title: string = ""
  export let subtitle: string = ""
  export let width: string = ""
  export let action_buttons: Array<Record<string, unknown>> = []

  $: actionButtonsByTitle[title] = action_buttons

  export function show() {
    showCalls.push(title)
  }
  export function close() {
    closeCalls.push(title)
  }
</script>

<div
  data-testid="dialog-stub"
  data-title={title}
  data-subtitle={subtitle}
  data-width={width}
  data-action-buttons={JSON.stringify(action_buttons)}
>
  <slot />
</div>
