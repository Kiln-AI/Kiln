<script lang="ts">
  import InfoTooltip from "./info_tooltip.svelte"
  import type { CarouselFeature } from "./feature_carousel_types"

  export let features: CarouselFeature[]

  $: has_metrics = features.some((f) => f.metrics)

  let container_width = 0
  const GAP = 16
  const PADDING = 32

  $: min_col_width = has_metrics ? 280 : 180
  $: max_col_width = has_metrics ? 350 : 200

  $: max_fitting =
    container_width > 0
      ? Math.max(
          1,
          Math.floor((container_width - PADDING + GAP) / (min_col_width + GAP)),
        )
      : features.length

  function balanced_cols(n: number, max_cols: number): number {
    if (n <= 1) return 1
    if (n <= max_cols) return n
    let best_cols = 2
    let best_score = -Infinity
    for (let c = 2; c <= max_cols; c++) {
      const remainder = n % c
      const fullness = remainder === 0 ? 1.0 : remainder / c
      const score = fullness * 10 + c * 2
      if (score > best_score) {
        best_score = score
        best_cols = c
      }
    }
    return best_cols
  }

  $: col_count = balanced_cols(features.length, max_fitting)
</script>

<div bind:clientWidth={container_width}>
  <div
    class="grid w-fit gap-4 bg-base-200 p-4 rounded-box"
    style="grid-template-columns: repeat({col_count}, minmax({min_col_width}px, {max_col_width}px));"
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
</div>
