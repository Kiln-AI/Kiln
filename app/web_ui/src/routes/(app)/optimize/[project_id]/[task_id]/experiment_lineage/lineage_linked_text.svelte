<script lang="ts">
  import type { LinkedValue } from "$lib/utils/lineage/lineage_display"

  export let value: LinkedValue
</script>

{#if value.link}<a href={value.link} class="link">{value.text}</a
  >{:else}{value.text}{/if}
