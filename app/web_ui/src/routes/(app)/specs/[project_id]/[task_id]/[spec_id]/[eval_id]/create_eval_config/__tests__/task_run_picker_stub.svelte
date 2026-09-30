<script lang="ts">
  import { createEventDispatcher } from "svelte"
  export let available_runs: Array<Record<string, unknown>> = []

  const dispatch = createEventDispatcher()
</script>

{#if available_runs.length > 0}
  <div data-testid="task-run-picker">
    {#each available_runs as run, i}
      <button
        type="button"
        class="btn btn-xs"
        data-testid="select-run-{i}"
        on:click={() => dispatch("select", run)}
      >
        Select
      </button>
    {/each}
  </div>
{:else}
  <div data-testid="no-runs">No runs</div>
{/if}
