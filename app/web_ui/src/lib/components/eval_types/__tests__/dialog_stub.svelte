<script lang="ts" context="module">
  export const actionButtonsByTitle: Record<
    string,
    Array<Record<string, unknown>>
  > = {}
  export function resetActionButtons() {
    for (const key of Object.keys(actionButtonsByTitle)) {
      delete actionButtonsByTitle[key]
    }
  }
  // Titles of the dialogs whose show() was called, in call order.
  export const shownTitles: string[] = []
  export function resetShownTitles() {
    shownTitles.length = 0
  }
</script>

<script lang="ts">
  export let title: string = ""
  export let subtitle: string = ""
  export let sub_subtitle: string = ""
  export let width: string = ""
  export let action_buttons: Array<Record<string, unknown>> = []

  $: actionButtonsByTitle[title] = action_buttons

  export function show() {
    shownTitles.push(title)
  }
  export function close() {}
</script>

<div
  data-testid="dialog-stub"
  data-title={title}
  data-width={width}
  data-subtitle={subtitle}
  data-sub-subtitle={sub_subtitle}
>
  <slot />
</div>
