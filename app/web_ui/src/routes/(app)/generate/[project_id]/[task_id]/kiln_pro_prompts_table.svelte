<script lang="ts">
  import KilnProPlansTable from "./kiln_pro_plans_table.svelte"

  export let prompts: string[]
  // When provided, each row gets a delete action.
  export let on_delete: ((index: number) => void) | null = null

  let show_prompts = false
  $: count = prompts.length
</script>

<div class="rounded-lg border">
  <button
    class="w-full flex items-center justify-between px-4 py-3 text-left"
    aria-label={show_prompts ? "Hide dataset items" : "Show dataset items"}
    aria-expanded={show_prompts}
    on:click={() => (show_prompts = !show_prompts)}
  >
    <span class="text-sm font-medium">All Dataset Items ({count})</span>
    <div class="flex items-center text-sm text-gray-500">
      <svg
        class="w-4 h-4 transition-transform {show_prompts ? 'rotate-180' : ''}"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <polyline points="6 9 12 15 18 9" />
      </svg>
    </div>
  </button>

  {#if show_prompts}
    <div class="border-t">
      <div class="px-4 pt-3 text-sm font-light text-gray-500">
        Each prompt here will be used to guide one dataset sample.
      </div>
      <KilnProPlansTable {prompts} {on_delete} />
    </div>
  {/if}
</div>
