import type { TaskRunConfig, ProviderModels, PromptResponse } from "$lib/types"
import { isMcpRunConfig, isKilnAgentRunConfig } from "$lib/types"
import { get_model_info, provider_name_from_id } from "$lib/stores"
import {
  getRunConfigModelDisplayName,
  getRunConfigPromptDisplayName,
  getRunConfigInputTransformSummaryLabel,
} from "$lib/utils/run_config_formatters"

/**
 * What a run config is called, and what colour it is, on every chart that
 * plots it.
 *
 * Both used to be decided per chart. The name was three near-identical private
 * copies of the same fallback chain, and the colour was worse than duplicated:
 * each chart took the palette by its OWN series index, so a config a chart
 * could not plot - no result for its axes, or switched off in that chart's
 * legend - shifted the colour of every config after it. The same run config
 * came out blue on the radar and orange on the bars, which makes three charts
 * of one comparison unreadable as one comparison.
 */

/**
 * echarts 6's default series palette, by value.
 *
 * Copied rather than read off a live chart instance, because that is the whole
 * point: the colour has to be knowable for a config that no chart is drawing,
 * and by the page's legend, which is DOM and has no echarts instance at all.
 * These are the values the charts were already painting with, so the page
 * looks the same - see echarts/lib/visual/tokens.js, `color.theme`.
 */
export const SERIES_PALETTE = [
  "#5070dd",
  "#b6d634",
  "#505372",
  "#ff994d",
  "#0ca8df",
  "#ffd10a",
  "#fb628b",
  "#785db0",
  "#3fbe95",
] as const

/** What a chart draws when it has no colour for a series at all. */
export const FALLBACK_SERIES_COLOR = "#888"

/**
 * The name a run config goes by on a chart: its own if it has one, the MCP
 * tool it wraps, or the model behind it.
 *
 * The config's OWN name leads, because the config is what this page compares.
 * A pinned set is routinely several arms of one model - same model, different
 * prompt or transform - so leading with the model prints the same headline on
 * chip after chip and the reader cannot tell which arm they are looking at.
 * The name is the one thing chosen per config, and it is the only fact here
 * that is always distinct. The model is not lost: it sits directly under the
 * name in the legend chip (series_subtext), and it joins single-line chart
 * labels wherever a name is shared (series_display_map).
 */
export function series_label(
  config: TaskRunConfig,
  model_info: ProviderModels | null,
): string {
  if (config.name) return config.name
  if (isMcpRunConfig(config.run_config_properties)) {
    return config.run_config_properties.tool_reference.tool_name ?? "MCP Tool"
  }
  return getRunConfigModelDisplayName(config, model_info) ?? "Unknown"
}

/**
 * The MODEL behind a run config, by its display name alone - "GPT-5.6 Luna",
 * not "GPT-5.6 Luna (OpenRouter)" and not the raw id.
 *
 * Null rather than a placeholder when there is no model to name: an MCP config
 * has none at all, and a model id the catalog cannot resolve (model_info still
 * loading, a provider that has since dropped the model) has no display name
 * either. Callers print nothing rather than a placeholder, and lean on the
 * config's own name, which is the one thing that is always known.
 *
 * The provider is deliberately NOT in here. It is a property of where the
 * model was run rather than of what was run, it doubles the length of every
 * chart label, and on the pinned sets this page is built for it almost never
 * changes between configs. It rides in the legend chip's detail line instead.
 */
export function series_model_label(
  config: TaskRunConfig,
  model_info: ProviderModels | null,
): string | null {
  const properties = config.run_config_properties
  if (!isKilnAgentRunConfig(properties)) return null
  return get_model_info(properties.model_name, model_info)?.name ?? null
}

/** Who served the model, for the chip's detail line. Null for an MCP config. */
function series_provider_label(config: TaskRunConfig): string | null {
  const properties = config.run_config_properties
  if (!isKilnAgentRunConfig(properties)) return null
  return provider_name_from_id(properties.model_provider_name) || null
}

/**
 * The lines under the config's name in a legend chip: what it ran on, and what
 * else it is made of.
 *
 * The MODEL leads them. It is the second-most identifying fact about a config
 * after what it is called, and it is the one the reader reaches for once they
 * know which config they are looking at - so it gets its own line rather than
 * a slot in the dot-joined detail line under it.
 *
 * Whatever the top line already said is left out rather than repeated, so the
 * chip never prints one fact twice - an unnamed MCP config named by its tool
 * gets no "Tool:" line, and an unnamed config whose top line has fallen back
 * to its model gets no model line.
 *
 * Plain strings, not echarts rich text. The legend is DOM now, and the two
 * charts that still draw a native legend of their own keep their `{sub|...}`
 * markup where it belongs - in the chart.
 */
export function series_subtext(
  config: TaskRunConfig,
  model_info: ProviderModels | null,
  prompts: PromptResponse | null,
): string[] {
  const primary = series_label(config, model_info)
  const lines: string[] = []
  // Only under a headline that is the config's OWN name. An unnamed config has
  // already fallen back to its model up there - provider and all - and a line
  // repeating it would be the chip saying one fact twice.
  const own_name = config.name?.trim()
  const model = series_model_label(config, model_info)
  if (own_name && model && model !== own_name) lines.push(model)

  if (isMcpRunConfig(config.run_config_properties)) {
    const tool_name =
      config.run_config_properties.tool_reference.tool_name ?? "MCP Tool"
    if (tool_name !== primary) lines.push(`Tool: ${tool_name}`)
    return lines
  }

  // One line, dot-joined, rather than one line each: the chips sit in a wrap
  // row above three charts, and every line they grow is height taken off the
  // charts. The provider leads it, directly under the model it served.
  const details: string[] = []
  const provider = series_provider_label(config)
  if (provider) details.push(provider)
  const prompt_name = getRunConfigPromptDisplayName(config, prompts)
  if (prompt_name) details.push(`Prompt: ${prompt_name}`)
  const transform_label = getRunConfigInputTransformSummaryLabel(config)
  if (transform_label) details.push(`Input Transform: ${transform_label}`)
  if (details.length > 0) lines.push(details.join(" · "))
  return lines
}

/**
 * What every chart CALLS each pinned run config, keyed by id: the config's own
 * name, and the model after it only where that name does not tell two configs
 * apart.
 *
 * A chart label is one line beside a dot or a polygon - there is no subtext to
 * disambiguate with, the way a legend chip has - so name-first naming has to
 * carry the collision itself. Two configs called the same thing would
 * otherwise draw two series with one label, and a tooltip naming one of them
 * would be answering about either.
 *
 * The rule, and it is deliberately conditional: a name that appears on exactly
 * ONE pinned config is the whole label, because a suffix nobody needs is noise
 * on every one of them. A name shared by several takes "<name> — <model>",
 * which is the fact most likely to differ between two configs a person gave
 * the same name.
 *
 * Built over the WHOLE pinned set rather than the visible one, so hiding a
 * chip in the legend cannot rename the configs still on screen. Order-free:
 * a label depends only on that config and on which names are in the set.
 */
export function series_display_map(
  configs: TaskRunConfig[],
  model_info: ProviderModels | null,
): Record<string, string> {
  // First entry wins for a repeated id, and a repeat must not count twice
  // towards its own name's collision either.
  const unique: TaskRunConfig[] = []
  const seen = new Set<string>()
  for (const config of configs) {
    const id = config.id
    if (!id || seen.has(id)) continue
    seen.add(id)
    unique.push(config)
  }

  // Counted over the label each config would get on its own, not over
  // config.name: an unnamed config goes by its tool or its model, and two of
  // those landing on the same string collide exactly the same way.
  const label_counts = new Map<string, number>()
  for (const config of unique) {
    const label = series_label(config, model_info)
    label_counts.set(label, (label_counts.get(label) ?? 0) + 1)
  }

  const labels: Record<string, string> = {}
  for (const config of unique) {
    const id = config.id as string
    const label = series_label(config, model_info)
    const own_name = config.name?.trim()
    const model = series_model_label(config, model_info)
    const shared = (label_counts.get(label) ?? 0) > 1
    // A shared label with no model to add has nothing to be disambiguated BY:
    // an MCP config, a catalog that cannot resolve the id, or an unnamed
    // config whose label IS its model already. Inventing something ("#2")
    // would name it after its position in a list the reader is free to
    // reorder, so it keeps the bare label and its colour tells it from its
    // twin.
    const suffix = own_name && model && model !== own_name ? model : null
    labels[id] = shared && suffix ? `${label} — ${suffix}` : label
  }
  return labels
}

/**
 * The colour at a position in the pinned list.
 *
 * Cycles past the end of the palette, exactly as echarts does, so a page that
 * pins more configs than there are colours behaves as it always did rather
 * than running out of series.
 */
export function series_color(index: number): string {
  if (!Number.isFinite(index)) return FALLBACK_SERIES_COLOR
  const length = SERIES_PALETTE.length
  // Modulo that survives a negative index, which JS's % does not
  const position = ((Math.trunc(index) % length) + length) % length
  return SERIES_PALETTE[position]
}

/**
 * One colour per pinned run config, fixed by its POSITION IN THE PINNED LIST.
 *
 * Position in the pinned list, and not in any chart's series array, is the
 * whole fix: it is the one ordering all three charts share, and it exists for
 * a config none of them can draw. Pinning another config below never restains
 * the ones above it.
 */
export function series_color_map(pinned_ids: string[]): Record<string, string> {
  const colors: Record<string, string> = {}
  pinned_ids.forEach((id, index) => {
    // First position wins, so a list that somehow repeats an id still gives
    // that id one colour rather than the last one it happens to appear at.
    if (colors[id] === undefined) {
      colors[id] = series_color(index)
    }
  })
  return colors
}
