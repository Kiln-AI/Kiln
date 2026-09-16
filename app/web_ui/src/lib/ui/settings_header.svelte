<script lang="ts">
  export let title: string
  export let subtitle: string | null = null
</script>

<div class="pb-3 border-b border-gray-200">
  <h2 class="text-lg font-medium text-gray-900">{title}</h2>
  {#if subtitle}
    <p class="text-sm text-gray-500">{subtitle}</p>
  {/if}
</div>
