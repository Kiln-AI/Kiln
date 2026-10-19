<script lang="ts">
  import CalloutCard from "../callout_card.svelte"

  export let testid: string | null = null
</script>

<CalloutCard {testid}>
  <svelte:fragment slot="icon">
    <svg data-testid="icon-svg" viewBox="0 0 24 24"><circle r="10" /></svg>
  </svelte:fragment>
  <p data-testid="slot-content">Content with icon</p>
</CalloutCard>
