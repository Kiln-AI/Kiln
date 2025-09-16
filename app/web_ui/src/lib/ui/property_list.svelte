<script lang="ts">
  import InfoTooltip from "./info_tooltip.svelte"
  import type { UiProperty } from "./property_list"

  export let properties: UiProperty[]
  export let title: string | null = null
</script>

<div>
  {#if title}
    <div class="text-xl font-bold mb-4">{title}</div>
  {/if}
  <div class="grid grid-cols-[auto,1fr] gap-y-2 gap-x-4 text-sm 2xl:text-base">
    {#each properties || [] as property}
      <div class="flex items-center">
        {property.name}
        {#if property.tooltip}
          <InfoTooltip tooltip_text={property.tooltip} />
        {/if}
      </div>
      <div
        class="flex items-center overflow-x-hidden {property.error
          ? 'text-error'
          : 'text-gray-500'}"
      >
        {#if property.link}
          <a href={property.link} class="link">{property.value}</a>
        {:else}
          {property.value}
        {/if}
      </div>
    {/each}
  </div>
</div>
