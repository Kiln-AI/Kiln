<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import type { KilnError } from "$lib/utils/error_handlers"

  export let submit_visible: boolean = true
  export let submit_label: string = "Submit"
  export let error: KilnError | null = null
  export let submitting: boolean = false
  export let warn_before_unload: boolean = false
  export let keyboard_submit: boolean = true

  const dispatch = createEventDispatcher()

  export function triggerSubmit() {
    dispatch("submit")
  }

  export function validate_and_submit() {
    submitting = true
    dispatch("submit")
  }
</script>

<div
  data-testid="form-container-stub"
  data-submit-visible={submit_visible}
  data-submit-label={submit_label}
>
  <slot />
  {#if submit_visible}
    <button
      data-testid="form-submit-button"
      type="button"
      disabled={submitting}
      on:click={() => {
        submitting = true
        dispatch("submit")
      }}
    >
      {submit_label}
    </button>
  {/if}
</div>
