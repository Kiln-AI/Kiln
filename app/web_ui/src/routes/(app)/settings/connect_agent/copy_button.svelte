<script lang="ts">
  import { onDestroy } from "svelte"

  export let text: string
  // Names the copied thing for assistive tech, e.g. "prompt".
  export let what: string
  export let primary: boolean = false
  export let testid: string | null = null

  const COPIED_LABEL_MS = 1500

  let copied = false
  let copied_timer: ReturnType<typeof setTimeout> | null = null

  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
      copied = true
      if (copied_timer) clearTimeout(copied_timer)
      copied_timer = setTimeout(() => {
        copied = false
      }, COPIED_LABEL_MS)
    } catch {
      // The Clipboard API is missing outside a secure context; the text stays selectable.
    }
  }

  onDestroy(() => {
    if (copied_timer) clearTimeout(copied_timer)
  })
</script>

<button
  type="button"
  class="btn btn-sm w-20 flex-shrink-0 {primary ? 'btn-primary' : ''}"
  data-testid={testid}
  aria-label={copied ? `Copied ${what}` : `Copy ${what}`}
  on:click={copy}
>
  {copied ? "Copied" : "Copy"}
</button>
<span class="sr-only" aria-live="polite">{copied ? `Copied ${what}` : ""}</span>
