import type { TaskRunConfig, ProviderModels, PromptResponse } from "$lib/types"
import { isMcpRunConfig } from "$lib/types"
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
 * The lines under the name in a legend entry: what this config actually IS,
 * since a memorable name says nothing about the model or prompt behind it.
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
  if (isMcpRunConfig(config.run_config_properties)) {
    const tool_name =
      config.run_config_properties.tool_reference.tool_name ?? "MCP Tool"
    return [`Tool: ${tool_name}`]
  }
  const lines = [
    `Model: ${getRunConfigModelDisplayName(config, model_info) || "Unknown"}`,
  ]
  const prompt_name = getRunConfigPromptDisplayName(config, prompts)
  if (prompt_name) lines.push(`Prompt: ${prompt_name}`)
  const transform_label = getRunConfigInputTransformSummaryLabel(config)
  if (transform_label) lines.push(`Input Transform: ${transform_label}`)
  return lines
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
