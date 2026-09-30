<script lang="ts">
  import CalloutCard from "../callout_card.svelte"

  export let testid: string | null = null
</script>

<CalloutCard {testid}>
  <p data-testid="slot-content">Hello from slot</p>
</CalloutCard>
