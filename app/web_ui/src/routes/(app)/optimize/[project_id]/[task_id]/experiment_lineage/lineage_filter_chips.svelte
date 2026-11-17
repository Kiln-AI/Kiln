<script lang="ts">
  import {
    FILTER_KEYS,
    type FilterKey,
    type LineageStatus,
  } from "$lib/utils/lineage/lineage_graph"
  import { FILTER_LABELS, GLYPH } from "$lib/utils/lineage/lineage_glyph"
  import LineageSwatch from "./lineage_swatch.svelte"

  export let counts: Record<FilterKey, number>
  export let active: Set<FilterKey>

  function swatch_status(key: FilterKey): LineageStatus {
    return key === "copy" ? { type: "copy" } : { type: "changed", kinds: [key] }
  }

  function toggle(key: FilterKey) {
    const next = new Set(active)
    if (next.has(key)) {
      next.delete(key)
    } else {
      next.add(key)
    }
    active = next
  }

  function clear() {
    active = new Set()
  }
</script>

<div class="flex flex-wrap items-center gap-2">
  <div class="text-sm font-medium">Changed from parent</div>
  {#each FILTER_KEYS as key}
    {@const on = active.has(key)}
    <!-- The chips double as the graph's color legend, so at rest they have no
         outline and read as plain legend items. -->
    <button
      type="button"
      class="btn btn-sm gap-2 font-normal shadow-none hover:bg-base-200 {on
        ? 'bg-base-200 border-base-300 hover:border-base-300'
        : 'bg-transparent border-transparent hover:border-transparent'}"
      aria-pressed={on}
      on:click={() => toggle(key)}
    >
      <LineageSwatch status={swatch_status(key)} glyph={GLYPH.swatch} />
      {FILTER_LABELS[key]}
      <span class="tabular-nums text-gray-500">{counts[key]}</span>
    </button>
  {/each}
  {#if active.size > 0}
    <button type="button" class="link text-sm text-gray-500" on:click={clear}>
      Clear
    </button>
  {/if}
</div>
