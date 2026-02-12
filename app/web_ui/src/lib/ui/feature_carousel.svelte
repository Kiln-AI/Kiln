<script lang="ts">
  import InfoTooltip from "./info_tooltip.svelte"
  import type { CarouselFeature } from "./feature_carousel_types"

  export let features: CarouselFeature[]

  $: has_metrics = features.some((f) => f.metrics)
</script>

<div
  class="grid gap-4 bg-base-200 p-4 rounded-box"
  style="grid-template-columns: repeat(auto-fill, minmax({has_metrics
    ? '280px'
    : '180px'}, {has_metrics ? '350px' : '200px'}));"
>
  {#each features as feature}
    <div
      class="card bg-base-100 shadow-md hover:shadow-lg hover:border-primary/50 border border-base-300 cursor-pointer transition-all duration-200 transform hover:-translate-y-1 hover:z-10 h-full flex flex-col p-4"
      on:click={feature.on_click}
      on:keydown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault()
          feature.on_click()
        }
      }}
      tabindex="0"
      role="button"
      aria-label={feature.name}
    >
      <div class="flex flex-col flex-1">
        <div class="text-lg font-semibold leading-tight">
          {feature.name}
        </div>
        {#if feature.subtitle}
          <div class="text-xs text-gray-500 font-medium mt-1">
            {feature.subtitle}
          </div>
        {/if}
        <p class="text-base-content/70 text-xs leading-relaxed mt-2">
          {feature.description}
        </p>

        {#if feature.metrics}
          <div class="flex-1 flex items-center mt-4">
            <div class="space-y-4 w-full">
              {#each Object.entries(feature.metrics) as [label, value]}
                <div class="flex items-center gap-4">
                  <span class="text-gray-500 w-24 text-xs">{label}</span>
                  <div class="flex gap-2 flex-1">
                    {#each Array(5) as _, i}
                      <div
                        class="h-3 rounded-full flex-1 {i < value
                          ? 'bg-secondary'
                          : 'bg-gray-200'}"
                      />
                    {/each}
                  </div>
                </div>
              {/each}
            </div>
          </div>
        {/if}
      </div>

      {#if feature.tooltip}
        <div class="absolute top-1 right-1">
          <InfoTooltip
            tooltip_text={feature.tooltip}
            no_pad={true}
            position="bottom"
          />
        </div>
      {/if}
    </div>
  {/each}
</div>
