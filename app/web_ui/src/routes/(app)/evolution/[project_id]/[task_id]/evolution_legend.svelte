<script lang="ts">
  // ONE legend for the whole compare section.
  //
  // The three plots below - the quality radar, the performance bars and the
  // parallel-coordinates view of the same quality scores - are one comparison
  // drawn three ways, and each of them used to carry its own echarts legend.
  // Those legends were keyed by display name, coloured by each chart's own
  // series index, and toggled independently, so switching a config off to read
  // the radar left it drawn on the two charts underneath, in a different
  // colour. This is that legend, once, above all three: a chip switched off
  // here is gone from every plot in the same click.
  //
  // DOM rather than canvas, and that is not a stylistic preference. A legend
  // that belongs to the page cannot live inside one chart's canvas; and it has
  // to be reachable by a keyboard and readable to a screen reader, which an
  // echarts legend entry is not.
  //
  // Hiding is subtraction at the source: the page filters the pinned list by
  // this store and hands each chart only what it should draw. No chart knows
  // this component exists.
  //
  // It STICKS to the top of the viewport, because the colour it assigns is the
  // only thing tying a dot on the price/latency chart - two screens further
  // down - to the config it stands for. A legend that scrolls away turns every
  // chart under it into anonymous coloured marks. The page mounts this at the
  // top of the comparison section and nothing else, so this component owns both
  // its own top margin and its stuck behaviour; its containing block is the
  // page body, which is what gives it something to travel over.

  import type {
    TaskRunConfig,
    ProviderModels,
    PromptResponse,
  } from "$lib/types"
  import {
    FALLBACK_SERIES_COLOR,
    series_primary_label,
    series_subtext,
  } from "$lib/utils/evolution/series_identity"
  import {
    hidden_run_config_ids,
    toggle_run_config,
  } from "$lib/utils/evolution/visibility_store"

  export let run_configs: TaskRunConfig[] = []
  // In pinned order, which is also the order the colours were assigned in
  export let pinned_ids: string[] = []
  export let model_info: ProviderModels | null = null
  export let prompts: PromptResponse | null = null
  // Colour per run config id, from series_color_map. Passed in rather than
  // computed here so the legend and the charts cannot disagree about it.
  export let colors: Record<string, string> = {}

  $: entries = pinned_ids
    .map((id) => run_configs.find((config) => config.id === id))
    .filter((config): config is TaskRunConfig => !!config?.id)
    .map((config) => {
      const id = config.id as string
      // The MODEL is the chip's headline - what the reader is comparing -
      // and the config's own name drops into the subtext under it. Several
      // chips may therefore share a top line; they stay unique through that
      // subtext, so no suffix is added here. The single-line contexts that
      // have no subtext to lean on dedup instead - see series_display_map.
      const label = series_primary_label(config, model_info)
      const name = config.name?.trim()
      return {
        id,
        label,
        subtext: series_subtext(config, model_info, prompts),
        // A tooltip is one line with nothing under it, so it carries the name
        // beside the model rather than repeating a headline three chips share.
        title_label: name && name !== label ? `${label} — ${name}` : label,
        color: colors[id] ?? FALLBACK_SERIES_COLOR,
        hidden: $hidden_run_config_ids.has(id),
      }
    })

  // Every chart is empty in this state, and each one says so in its own words
  // ("No data available", "at least two run configs are needed") - none of
  // which is the truth, which is that the reader switched them all off. The
  // control that undoes it is right here, so the explanation belongs here too.
  $: all_hidden = entries.length > 0 && entries.every((entry) => entry.hidden)

  // Whether the bar is currently pinned to the top of the viewport. CSS has no
  // "is stuck" selector, so a one-pixel sentinel is left behind in the normal
  // flow directly above the bar: once IT has scrolled off the top of the
  // window, the bar above it is being held there. An IntersectionObserver
  // rather than a scroll handler - the browser reports the crossing itself,
  // instead of this component measuring on every frame of every scroll.
  let stuck = false
  function watch_stuck(node: HTMLElement) {
    // jsdom and SSR have no observer; the bar simply never reports itself
    // stuck, which costs a shadow and nothing else.
    if (typeof IntersectionObserver === "undefined") return
    const observer = new IntersectionObserver(
      ([entry]) => {
        // Off the BOTTOM of the window is not stuck - that is the bar still
        // below the fold on a freshly loaded page.
        stuck = !entry.isIntersecting && entry.boundingClientRect.top < 0
      },
      { threshold: 0 },
    )
    observer.observe(node)
    return {
      destroy() {
        observer.disconnect()
      },
    }
  }
</script>

{#if entries.length > 0}
  <!-- The sentinel: where the bar sits when the page is at rest. Zero-width
       borders and one pixel of height, so it is nothing but a position to
       watch. -->
  <div use:watch_stuck class="h-px" aria-hidden="true"></div>
  <!-- The sticky band. `top-0` against the app shell, which has no fixed
       header of its own - the shell's header strip scrolls with the page - so
       the viewport top is where this belongs. The padding is INSIDE the sticky
       box rather than a margin above it: sticky offsets are measured to the
       margin box, so a margin would hold the bar 24px down the screen and let
       the charts scroll through the gap. Opaque, in the page's own background
       colour, and above the charts: an echarts canvas that is merely later in
       the DOM would otherwise draw straight over it. -->
  <div class="sticky top-0 z-20 pt-6 bg-base-100">
    <div
      class="bg-white border rounded-lg px-6 transition-shadow {stuck
        ? 'py-3 border-gray-300 shadow-md'
        : 'py-4 border-gray-200'}"
    >
      <div
        class="flex flex-row flex-wrap items-baseline gap-x-3 gap-y-1 {stuck
          ? 'mb-2'
          : 'mb-3'}"
      >
        <div class="text-sm font-medium text-gray-900">Run configs</div>
        <div class="text-xs text-gray-400">
          Click one to hide it on every chart below.
        </div>
      </div>
      <div class="flex flex-row flex-wrap gap-2">
        {#each entries as entry (entry.id)}
          <button
            type="button"
            class="flex flex-row items-start gap-2 rounded-lg border text-left
                   max-w-full transition-colors
                   focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500
                   {stuck ? 'px-3 py-1.5' : 'px-3 py-2'}
                   {entry.hidden
              ? 'border-gray-200 bg-gray-50 opacity-45 hover:opacity-70'
              : 'border-gray-300 bg-white hover:bg-gray-50'}"
            aria-pressed={!entry.hidden}
            title="{entry.hidden
              ? 'Show'
              : 'Hide'} {entry.title_label} on every chart"
            on:click={() => toggle_run_config(entry.id)}
          >
            <!-- Colour is the only thing tying this chip to a line on a chart,
                 so it is the same swatch shape the charts' own legends used. -->
            <span
              class="mt-[3px] h-2.5 w-4 flex-shrink-0 rounded-sm"
              style="background-color: {entry.color}"
              aria-hidden="true"
            ></span>
            <span class="min-w-0">
              <!-- Three tiers, heaviest first: the model, then which config on
                   it, then what else it is made of. The first subtext line is
                   the config's own name (series_subtext puts it there), so it
                   is set a shade darker than the detail line under it - it is
                   an identity, not a property.

                   Stuck, the bar is spending viewport the charts under it need,
                   so it drops to two tiers: the model and the config's NAME,
                   which is the pair that answers "what is the blue one". The
                   detail line (provider, prompt, input transform) is a property
                   of a config already identified, and it is a scroll away. -->
              <span class="block text-sm font-medium text-gray-900 truncate">
                {entry.label}
              </span>
              {#each entry.subtext as line, index}
                {#if index === 0 || !stuck}
                  <span
                    class="block text-xs truncate {index === 0
                      ? 'text-gray-600'
                      : 'text-gray-500'}">{line}</span
                  >
                {/if}
              {/each}
            </span>
          </button>
        {/each}
      </div>
      {#if all_hidden}
        <div class="text-xs text-gray-500 {stuck ? 'mt-2' : 'mt-3'}">
          Every run config is hidden, so the charts below have nothing to draw.
          Click a chip to bring one back.
        </div>
      {/if}
    </div>
  </div>
{/if}
