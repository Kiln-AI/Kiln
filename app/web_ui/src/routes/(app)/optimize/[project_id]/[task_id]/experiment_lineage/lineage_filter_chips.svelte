<script lang="ts">
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
  import {
    FILTER_KEYS,
    type FilterKey,
    type LineageStatus,
  } from "$lib/utils/lineage/lineage_graph"
  import { FILTER_LABELS, GLYPH } from "$lib/utils/lineage/lineage_glyph"
  import LineageSwatch from "./lineage_swatch.svelte"

  export let counts: Record<FilterKey, number>
  export let active: Set<FilterKey>

  const FILTER_HELP =
    "Each square shows what changed from its parent run configuration. One change fills the square. More changes split it, always in the order prompt, tools, skills, model, settings. Settings covers temperature, top P, thinking level, structured output mode and input transform. Click a chip to filter."

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
  <div class="flex items-center text-sm font-medium">
    Changed from parent
    <InfoTooltip tooltip_text={FILTER_HELP} position="bottom" />
  </div>
  {#each FILTER_KEYS as key}
    {@const on = active.has(key)}
    <button
      type="button"
      class="btn btn-sm gap-2 {on ? 'btn-secondary' : 'btn-outline'}"
      aria-pressed={on}
      on:click={() => toggle(key)}
    >
      <LineageSwatch status={swatch_status(key)} glyph={GLYPH.swatch} />
      {FILTER_LABELS[key]}
      <span class="tabular-nums {on ? 'opacity-70' : 'text-gray-500'}"
        >{counts[key]}</span
      >
    </button>
  {/each}
  {#if active.size > 0}
    <button type="button" class="link text-sm text-gray-500" on:click={clear}>
      Clear
    </button>
  {/if}
</div>
