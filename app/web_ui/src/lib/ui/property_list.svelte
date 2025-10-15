<script lang="ts">
  import { goto } from "$app/navigation"
  import InfoTooltip from "./info_tooltip.svelte"
  import type { UiProperty } from "./property_list"
  import Warning from "./warning.svelte"

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
        {#if property.warn_icon}
          <Warning
            warning_message=" "
            warning_icon="exclaim"
            warning_color="warning"
            tight={true}
          />
        {/if}
        {#if Array.isArray(property.value)}
          {#if property.badge}
            <div class="flex flex-wrap gap-1">
              {#each property.value as value, i}
                {@const link = property.links
                  ? property.links.length == property.value.length
                    ? property.links[i]
                    : null
                  : null}
                <button
                  class="badge badge-outline"
                  on:click={() => {
                    if (link) {
                      goto(link)
                    }
                  }}
                >
                  {value}
                </button>
              {/each}
            </div>
          {:else}
            <div class="flex flex-wrap gap-1">
              {#each property.value as value, i}
                {@const link =
                  property.links &&
                  property.links.length === property.value.length
                    ? property.links[i]
                    : null}

                {#if link}
                  <a href={link} class="link">{value}</a>
                {:else}
                  <span>{value}</span>
                {/if}
              {/each}
            </div>
          {/if}
        {:else if property.badge}
          <button
            class="badge badge-outline"
            on:click={() => {
              if (property.link) {
                goto(property.link)
              }
            }}
          >
            {property.value}
          </button>
        {:else if property.link}
          <a href={property.link} class="link">{property.value}</a>
        {:else}
          {property.value}
        {/if}
      </div>
    {/each}
  </div>
</div>
