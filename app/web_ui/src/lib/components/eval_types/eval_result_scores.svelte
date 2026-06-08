<script lang="ts">
  export let scores: Record<string, number> = {}
  export let skipped_reason: string | null = null
  export let skipped_detail: string | null = null

  function format_skipped_reason(reason: string): string {
    return reason.replace(/_/g, " ")
  }
</script>

{#if skipped_reason}
  <div class="flex flex-col gap-1 text-sm">
    <div class="badge badge-warning badge-sm gap-1">
      <i class="bi bi-skip-forward-fill text-xs"></i>
      Skipped
    </div>
    <div class="text-gray-500 capitalize">
      {format_skipped_reason(skipped_reason)}
    </div>
    {#if skipped_detail}
      <div class="text-gray-400 text-xs">{skipped_detail}</div>
    {/if}
  </div>
{:else if Object.keys(scores).length > 0}
  <div class="flex flex-col gap-1">
    {#each Object.entries(scores) as [key, value]}
      <div class="flex justify-between gap-4 text-sm">
        <span class="font-medium text-gray-600">{key}:</span>
        <span class="font-mono">{value.toFixed(2)}</span>
      </div>
    {/each}
  </div>
{:else}
  <span class="text-sm text-gray-500">No scores available.</span>
{/if}
