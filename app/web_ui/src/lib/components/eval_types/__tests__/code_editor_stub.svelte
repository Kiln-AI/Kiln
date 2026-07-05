<script lang="ts">
  import { createEventDispatcher } from "svelte"

  export let value: string = ""
  export let readonly: boolean = false
  export let placeholder: string = ""
  export let min_height: string = "200px"

  const dispatch = createEventDispatcher<{ change: string }>()

  export function setValue(newValue: string) {
    value = newValue
    dispatch("change", value)
  }

  export function getValue(): string {
    return value
  }
</script>

<div data-testid="code-editor-stub">
  <textarea
    data-testid="code-editor-textarea"
    {readonly}
    {placeholder}
    style="min-height: {min_height}"
    bind:value
    on:input={() => dispatch("change", value)}
  ></textarea>
</div>
