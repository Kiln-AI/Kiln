<script lang="ts">
  export let value: number
  export let min: number = 1
  export let max: number = 50
</script>

<div class="flex flex-row gap-2 items-center">
  <button
    class="btn btn-sm"
    on:click={() => (value = Math.max(min, value - 1))}
  >
    -
  </button>
  <span class="text-lg font-medium w-8 text-center">{value}</span>
  <button
    class="btn btn-sm"
    on:click={() => (value = Math.min(max, value + 1))}
  >
    +
  </button>
</div>
