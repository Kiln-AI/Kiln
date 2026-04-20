<script lang="ts">
  import { onDestroy } from "svelte"

  export let url: string
  export let message: string =
    "Your browser blocked the popup. Copy the link below and open it manually in a new tab."
  export let compact: boolean = false

  let copied = false
  let copy_timer: ReturnType<typeof setTimeout> | null = null

  async function copy() {
    try {
      await navigator.clipboard.writeText(url)
      copied = true
      if (copy_timer) clearTimeout(copy_timer)
      copy_timer = setTimeout(() => {
        copied = false
      }, 1500)
    } catch {
      // Clipboard API may be unavailable; users can still select the text.
    }
  }

  onDestroy(() => {
    if (copy_timer) clearTimeout(copy_timer)
  })
</script>

<div
  class="w-full border border-warning/40 bg-warning/5 rounded-lg {compact
    ? 'p-3'
    : 'p-4'} flex flex-col gap-2"
>
  <p class="{compact ? 'text-xs' : 'text-sm'} text-gray-700">
    {message}
  </p>
  <div class="flex items-stretch gap-2">
    <input
      type="text"
      readonly
      value={url}
      class="input input-bordered {compact
        ? 'input-xs'
        : 'input-sm'} flex-1 font-mono text-xs"
      on:focus={(e) => e.currentTarget.select()}
    />
    <button
      type="button"
      class="btn {compact ? 'btn-xs' : 'btn-sm'} btn-primary"
      on:click={copy}
    >
      {copied ? "Copied" : "Copy"}
    </button>
  </div>
</div>
