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
</script>

{#if entries.length > 0}
  <div class="bg-white border border-gray-200 rounded-lg px-6 py-4">
    <div class="flex flex-row flex-wrap items-baseline gap-x-3 gap-y-1 mb-3">
      <div class="text-sm font-medium text-gray-900">Run configs</div>
      <div class="text-xs text-gray-400">
        Click one to hide it on every chart below.
      </div>
    </div>
    <div class="flex flex-row flex-wrap gap-2">
      {#each entries as entry (entry.id)}
        <button
          type="button"
          class="flex flex-row items-start gap-2 rounded-lg border px-3 py-2 text-left
                 max-w-full transition-colors
                 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500
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
                 an identity, not a property. -->
            <span class="block text-sm font-medium text-gray-900 truncate">
              {entry.label}
            </span>
            {#each entry.subtext as line, index}
              <span
                class="block text-xs truncate {index === 0
                  ? 'text-gray-600'
                  : 'text-gray-500'}">{line}</span
              >
            {/each}
          </span>
        </button>
      {/each}
    </div>
    {#if all_hidden}
      <div class="text-xs text-gray-500 mt-3">
        Every run config is hidden, so the charts below have nothing to draw.
        Click a chip to bring one back.
      </div>
    {/if}
  </div>
{/if}
