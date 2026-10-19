<script lang="ts">
  // The row a synthetic data surface uses to set how many items it asks for.
  import IncrementUi from "$lib/ui/increment_ui.svelte"

  export let label: string
  export let value: number
  // Left undefined so the stepper applies its own bounds.
  export let min: number | undefined = undefined
  export let max: number | undefined = undefined
</script>

<div class="flex flex-row items-center gap-4">
  <div class="flex-grow font-medium text-sm">{label}</div>
  <IncrementUi bind:value {min} {max} />
</div>
