<svelte:options accessors />

<script lang="ts">
  import type { FilterKey } from "$lib/utils/lineage/lineage_graph"
  import LineageFilterChips from "../lineage_filter_chips.svelte"

  export let counts: Record<FilterKey, number>
  export let active: Set<FilterKey>
</script>

<LineageFilterChips {counts} bind:active />
