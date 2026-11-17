<svelte:options namespace="svg" />

<script lang="ts">
  import type { LineageStatus } from "$lib/utils/lineage/lineage_graph"
  import {
    CHANGE_KIND_COLORS,
    glyph_rects,
    type GlyphSize,
  } from "$lib/utils/lineage/lineage_glyph"

  export let status: LineageStatus
  export let glyph: GlyphSize

  $: rects =
    status.type === "changed"
      ? glyph_rects(status.kinds, glyph.size, glyph.gap)
      : []
  // The outline sits half a pixel in so its 1px stroke stays inside the
  // square; its radius is reduced to match so the corners follow the clip.
  $: outline_size = glyph.size - 1
  $: outline_radius = Math.max(glyph.radius - 0.5, 0)
</script>

{#if status.type === "changed"}
  {#each rects as rect}
    {#if rect.overlay}
      <rect
        x={rect.x - glyph.gap}
        y={rect.y - glyph.gap}
        width={rect.w + 2 * glyph.gap}
        height={rect.h + 2 * glyph.gap}
        class="fill-base-100"
      />
    {/if}
    <rect
      x={rect.x}
      y={rect.y}
      width={rect.w}
      height={rect.h}
      fill={CHANGE_KIND_COLORS[rect.kind]}
    />
  {/each}
{:else if status.type === "copy"}
  <rect width={glyph.size} height={glyph.size} class="fill-base-300" />
{:else if status.type === "starting_point"}
  <rect width={glyph.size} height={glyph.size} class="fill-secondary" />
{:else}
  <rect
    x="0.5"
    y="0.5"
    width={outline_size}
    height={outline_size}
    rx={outline_radius}
    class="fill-base-100 stroke-base-300"
    stroke-width="1"
    stroke-dasharray={status.type === "deleted" ? "2 1.5" : undefined}
  />
{/if}
