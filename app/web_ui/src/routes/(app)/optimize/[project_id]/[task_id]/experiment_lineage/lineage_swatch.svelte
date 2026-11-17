<script lang="ts">
  import type { LineageStatus } from "$lib/utils/lineage/lineage_graph"
  import type { GlyphSize } from "$lib/utils/lineage/lineage_glyph"
  import LineageGlyph from "./lineage_glyph.svelte"

  export let status: LineageStatus
  export let glyph: GlyphSize
</script>

<svg
  width={glyph.size}
  height={glyph.size}
  viewBox="0 0 {glyph.size} {glyph.size}"
  aria-hidden="true"
  class="shrink-0 overflow-hidden"
  style="border-radius: {glyph.radius}px;"
>
  <LineageGlyph {status} {glyph} />
</svg>
