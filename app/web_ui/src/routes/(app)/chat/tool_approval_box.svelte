<script lang="ts">
  export let description: string = ""
  export let onRun: () => void
  export let onSkip: () => void
</script>

<div
  class="max-w-md rounded-md bg-base-content/[0.04] px-3 py-2.5 flex flex-col gap-2"
>
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
