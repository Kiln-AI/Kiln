<script lang="ts">
  import InfoTooltip from "./info_tooltip.svelte"
  import type { CarouselFeature } from "./feature_carousel_types"

  export let features: CarouselFeature[]
</script>

<div
  class="carousel carousel-center max-w-full p-4 space-x-4 bg-base-200 rounded-box"
>
  {#each features as feature}
    <div class="carousel-item">
      <div
        class="card bg-base-100 shadow-md hover:shadow-xl hover:border-primary border border-base-200 cursor-pointer transition-all duration-200 transform hover:-translate-y-1 w-48 hover:z-10"
        on:click={feature.on_click}
        on:keydown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault()
            feature.on_click()
          }
        }}
        tabindex="0"
        role="button"
        aria-label="Connect {feature.name}"
      >
        <div class="p-4">
          <div class="text-lg font-semibold leading-tight">
            {feature.name}
          </div>
          {#if feature.subtitle}
            <div class="text-xs text-gray-500 font-medium mt-1">
              {feature.subtitle}
            </div>
          {/if}
          <p class="text-base-content/70 text-xs leading-relaxed mt-3">
            {feature.description}
          </p>
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
    </div>
  {/each}
</div>
