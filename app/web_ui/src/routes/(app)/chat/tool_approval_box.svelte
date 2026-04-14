<script lang="ts">
  export let description: string = ""
  export let method: string = ""
  export let url: string = ""
  export let onRun: () => void
  export let onSkip: () => void
</script>

<div
  class="max-w-md rounded-md bg-base-content/[0.04] px-3 py-2.5 flex flex-col gap-2"
>
  {#if method || url}
    <div
      class="flex items-center gap-1.5 text-xs font-mono text-base-content/70"
    >
      {#if method}
        <span class="font-semibold text-base-content/90 uppercase"
          >{method}</span
        >
      {/if}
      {#if url}
        <span class="truncate">{url}</span>
      {/if}
    </div>
  {/if}
  <p class="text-xs text-base-content/80 leading-relaxed">
    {#if description.trim()}
      {description}
    {:else}
      This tool call requires approval.
    {/if}
  </p>
  <div class="flex flex-row flex-wrap items-center justify-end gap-2">
    <button type="button" class="btn btn-ghost btn-sm" on:click={onSkip}>
      Skip
    </button>
    <button type="button" class="btn btn-primary btn-sm" on:click={onRun}>
      Run
    </button>
  </div>
</div>
