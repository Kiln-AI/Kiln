import type { ProviderModels, TaskRunConfig } from "$lib/types"
import { isMcpRunConfig } from "$lib/types"
import {
  COST_SECTION_ID,
  USAGE_METRICS,
  isUsageMetricKey,
} from "./compare_metric_keys"
import { getRunConfigModelDisplayName } from "./run_config_formatters"

// A section of the comparison table: one eval's scores, or the usage section.
export type ComparisonFeature = {
  category: string
  items: { label: string; key: string }[]
  has_default_eval_config: boolean | undefined
  eval_id: string
}

// Reads one run config's value for one row of the comparison table.
export type RadarValueLookup = (
  modelKey: string | null,
  dataKey: string,
) => number | null

export type RadarIndicator = { name: string; max: number }

export type RadarSeriesDatum = { value: (number | null)[]; name: string }

export type TooltipScore = { label: string; value: number | null }

export type RadarChartData = {
  // Axes in plot order, already labelled.
  indicators: RadarIndicator[]
  // One entry per plotted run config, values in `keys` order.
  series: RadarSeriesDatum[]
  legend: string[]
  // The run config behind each series name. Echarts hands a formatter the series
  // name and nothing else, so this is how a tooltip gets back to the config that
  // drew the shape - by identity, not by display name.
  configsBySeriesName: Record<string, TaskRunConfig>
  axisMaxes: Record<string, number>
  keys: string[]
  // Candidate axes dropped because some plotted config had no result for them.
  omittedKeyCount: number
  axisLabels: Record<string, string>
  // Rows the table is offering as axes, hidden ones already dropped upstream. Zero
  // of them means there is nothing to put on a card at all.
  candidateAxisCount: number
  // Whether the table has an eval section at all. A section keeps its place once
  // every one of its rows is hidden, so this tells a task with no evals apart from
  // one whose score rows are hidden - they need different advice.
  hasEvalSections: boolean
  hasData: boolean
}

export type RadarChartInput = {
  comparisonFeatures: ComparisonFeature[]
  plottedConfigs: TaskRunConfig[]
  selectedRunConfigIds: string[]
  getValue: RadarValueLookup
  modelInfo: ProviderModels | null
  scoreAxisMaxes: Record<string, number>
  metricLabels: Record<string, string>
  absoluteScale: boolean
}

// Fallback full-scale max when we don't know the score's type. Most eval scores are
// normalized to 0-1, and we only use it when the data actually fits under it.
export const DEFAULT_ABSOLUTE_MAX = 1

// Usage axes carry a 0-100 position score rather than a raw quantity, in both
// scale modes.
export const USAGE_AXIS_MAX = 100

// Above this many scores the tooltip lists only the weakest ones - the full set is
// in the comparison table above.
export const MAX_TOOLTIP_SCORES = 10

// Below this many axes there's no shape to read, so there's no chart to draw
export const MIN_RADAR_AXES = 3

// Cost, latency and token counts are lower-is-better raw quantities with no
// absolute range, so they're scored by position within the selected run configs
// (metricToScore) on a shared 0-100 axis. That's a comparison, which means these
// axes only carry information when there are at least two configs to compare - and
// it's why they stay relative even in Full Scale mode.
//
// On the chart they're named for the direction that's better, since a bigger value
// means less cost / less time / fewer tokens.
export const USAGE_LABELS: Record<string, string> = Object.fromEntries(
  USAGE_METRICS.map((metric) => [metric.key, metric.axisLabel]),
)

/**
 * Position of a lower-is-better value within the selected configs, as a 0-100
 * score. Ties (or a single config) land at 50: no better, no worse.
 */
export function metricToScore(
  cost: number,
  costs: number[],
  {
    padding = 10, // keep endpoints away from 0/100
    relFull = 0.7, // when (hi-lo)/|hi| reaches this, use full spread (k=1)
  }: {
    padding?: number
    relFull?: number
  } = {},
): number {
  const lo = Math.min(...costs)
  const hi = Math.max(...costs)

  const range = hi - lo
  if (range <= 0) return 50

  // 1) range-based normalized position
  const t = (cost - lo) / range

  // 2) raw padded linear score (lower cost = higher score)
  const raw = padding + (1 - t) * (100 - 2 * padding)

  // 3) compress based on range relative to magnitude ("scale from zero")
  const scale = Math.max(Math.abs(hi), 1e-12)
  const relRange = range / scale // e.g. 0.02..0.03 => 0.01/0.03 ≈ 0.33
  const k = Math.max(0, Math.min(1, relRange / relFull)) // small relRange -> k<1 -> compress

  // 4) mix toward midpoint
  const score = 50 + k * (raw - 50)

  return Math.max(0, Math.min(100, score))
}

/**
 * The table's row keys, split into eval score axes and usage axes. Hiding a usage
 * row in the table removes it here too - one control, where the numbers are.
 */
export function splitAxisKeys(comparisonFeatures: ComparisonFeature[]): {
  scoreKeys: string[]
  usageKeys: string[]
} {
  const scoreKeys: string[] = []
  const usageKeys: string[] = []
  for (const feature of comparisonFeatures) {
    const target = feature.eval_id === COST_SECTION_ID ? usageKeys : scoreKeys
    for (const item of feature.items) {
      target.push(item.key)
    }
  }
  return { scoreKeys, usageKeys }
}

/**
 * Run configs that will actually be drawn: selected, and with at least one eval
 * result. One with nothing to plot is left out entirely rather than emptying every
 * axis.
 */
export function plottedRunConfigs({
  comparisonFeatures,
  runConfigs,
  selectedRunConfigIds,
  getValue,
}: {
  comparisonFeatures: ComparisonFeature[]
  runConfigs: TaskRunConfig[]
  selectedRunConfigIds: string[]
  getValue: RadarValueLookup
}): TaskRunConfig[] {
  const { scoreKeys } = splitAxisKeys(comparisonFeatures)
  return selectedRunConfigIds
    .map((configId) => runConfigs.find((config) => config.id === configId))
    .filter((config): config is TaskRunConfig => !!config)
    .filter((config) =>
      scoreKeys.some((key) => getValue(config.id ?? null, key) !== null),
    )
}

/**
 * The candidate axes every plotted config has a result for, and how many were
 * dropped. ECharts draws a missing radar value at the center of the chart
 * (radarLayout's getValueMissingPoint), which is indistinguishable from scoring
 * zero - so an axis one config hasn't been evaluated on can't be drawn honestly at
 * all.
 */
export function sharedAxisKeys(
  candidateKeys: string[],
  plottedConfigs: TaskRunConfig[],
  getValue: RadarValueLookup,
): { keys: string[]; omittedCount: number } {
  const keys = candidateKeys.filter((key) =>
    plottedConfigs.every((config) => getValue(config.id ?? null, key) !== null),
  )
  return { keys, omittedCount: candidateKeys.length - keys.length }
}

/**
 * The top of one eval score axis. Relative mode pads the observed maximum; full
 * scale uses the score's own range when we know it, and never returns a max below
 * the data, so nothing is clipped for unbounded (custom) or unrecognized scores.
 */
export function axisMaxFor(
  key: string,
  rawMax: number,
  {
    absoluteScale,
    scoreAxisMaxes,
  }: { absoluteScale: boolean; scoreAxisMaxes: Record<string, number> },
): number {
  const paddedMax = rawMax > 0 ? rawMax * 1.1 : 1
  if (!absoluteScale) {
    return paddedMax
  }
  const knownMax = scoreAxisMaxes[key]
  if (knownMax !== undefined && knownMax >= rawMax) {
    return knownMax
  }
  return rawMax <= DEFAULT_ABSOLUTE_MAX ? DEFAULT_ABSOLUTE_MAX : paddedMax
}

/**
 * Axis name per row key: the name the user gave the row wins, then the usage axis
 * name, then the table's own label, then the raw key.
 */
export function buildAxisLabels(
  comparisonFeatures: ComparisonFeature[],
  metricLabels: Record<string, string>,
): Record<string, string> {
  const tableLabels: Record<string, string> = {}
  for (const feature of comparisonFeatures) {
    for (const item of feature.items) {
      if (item.key in tableLabels) continue
      tableLabels[item.key] = item.label
    }
  }
  const labels: Record<string, string> = {}
  for (const [key, tableLabel] of Object.entries(tableLabels)) {
    labels[key] = metricLabels[key] || USAGE_LABELS[key] || tableLabel
  }
  return labels
}

/** The series name of a run config, which is also its legend entry. */
export function runConfigSeriesName(
  config: TaskRunConfig,
  modelInfo: ProviderModels | null,
): string {
  if (config.name) return config.name
  if (isMcpRunConfig(config.run_config_properties)) {
    return config.run_config_properties.tool_reference.tool_name ?? "MCP Tool"
  }
  return getRunConfigModelDisplayName(config, modelInfo) ?? "Unknown"
}

/**
 * Series name per run config, in plot order. Echarts keys a series by its name and
 * two run configs can carry the same one, so every occurrence of a repeated name is
 * numbered. A name that occurs once is left exactly as it is.
 */
export function runConfigSeriesNames(
  configs: TaskRunConfig[],
  modelInfo: ProviderModels | null,
): string[] {
  const names = configs.map((config) => runConfigSeriesName(config, modelInfo))
  const totals: Record<string, number> = {}
  for (const name of names) {
    totals[name] = (totals[name] ?? 0) + 1
  }
  const seen: Record<string, number> = {}
  return names.map((name) => {
    if (totals[name] === 1) return name
    seen[name] = (seen[name] ?? 0) + 1
    return `${name} (${seen[name]})`
  })
}

/**
 * The eval scores a tooltip should list, trimmed to the weakest `limit` of them.
 * The usage axes plot a relative score rather than their raw quantity, so ranking
 * them against pass rates would compare unlike things - they are left out.
 */
export function rankTooltipScores({
  keys,
  axisMaxes,
  axisLabels,
  getValue,
  limit = MAX_TOOLTIP_SCORES,
}: {
  keys: string[]
  axisMaxes: Record<string, number>
  axisLabels: Record<string, string>
  getValue: (key: string) => number | null
  limit?: number
}): { scores: TooltipScore[]; trimmedCount: number } {
  const ranked = keys
    .filter((key) => !isUsageMetricKey(key))
    .map((key) => {
      const value = getValue(key)
      const max = axisMaxes[key] || 1
      return {
        label: axisLabels[key] ?? key,
        value,
        // Rank by position on the axis, so scores with different ranges (0-1 vs
        // 1-5) are comparable. Missing values sort first: "didn't run" is worth
        // surfacing.
        position: value === null ? -1 : value / max,
      }
    })

  const strip = (entry: (typeof ranked)[number]): TooltipScore => ({
    label: entry.label,
    value: entry.value,
  })

  if (ranked.length <= limit) {
    return { scores: ranked.map(strip), trimmedCount: 0 }
  }
  const shown = [...ranked]
    .sort((a, b) => a.position - b.position)
    .slice(0, limit)
  return {
    scores: shown.map(strip),
    trimmedCount: ranked.length - shown.length,
  }
}

/** Everything the radar chart draws, derived from the table and the selection. */
export function buildRadarChartData(input: RadarChartInput): RadarChartData {
  const {
    comparisonFeatures,
    plottedConfigs,
    selectedRunConfigIds,
    getValue,
    modelInfo,
    scoreAxisMaxes,
    metricLabels,
    absoluteScale,
  } = input

  const { scoreKeys, usageKeys } = splitAxisKeys(comparisonFeatures)
  const axisLabels = buildAxisLabels(comparisonFeatures, metricLabels)
  const empty: RadarChartData = {
    indicators: [],
    series: [],
    legend: [],
    configsBySeriesName: {},
    axisMaxes: {},
    keys: [],
    omittedKeyCount: 0,
    axisLabels,
    candidateAxisCount: scoreKeys.length + usageKeys.length,
    hasEvalSections: comparisonFeatures.some(
      (feature) => feature.eval_id !== COST_SECTION_ID,
    ),
    hasData: false,
  }

  if (scoreKeys.length === 0 || selectedRunConfigIds.length === 0) {
    return empty
  }

  const { keys, omittedCount } = sharedAxisKeys(
    [...scoreKeys, ...usageKeys],
    plottedConfigs,
    getValue,
  )

  if (keys.length < MIN_RADAR_AXES) {
    return { ...empty, omittedKeyCount: omittedCount }
  }

  // Every value on a usage axis, so each can be scored by its position among them
  const usageValues: Record<string, number[]> = {}
  for (const key of keys) {
    if (!isUsageMetricKey(key)) continue
    usageValues[key] = plottedConfigs
      .map((config) => getValue(config.id ?? null, key))
      .filter((value): value is number => value !== null)
  }

  const axisMaxes: Record<string, number> = {}
  for (const key of keys) {
    if (isUsageMetricKey(key)) {
      axisMaxes[key] = USAGE_AXIS_MAX
      continue
    }
    let rawMax = 0
    for (const config of plottedConfigs) {
      const value = getValue(config.id ?? null, key)
      if (value !== null && value > rawMax) {
        rawMax = value
      }
    }
    axisMaxes[key] = axisMaxFor(key, rawMax, { absoluteScale, scoreAxisMaxes })
  }

  const indicators = keys.map((key) => ({
    name: axisLabels[key] ?? key,
    max: axisMaxes[key],
  }))

  const seriesNames = runConfigSeriesNames(plottedConfigs, modelInfo)

  // Every plotted config has a value for every key by construction above.
  const series = plottedConfigs.map((config, index) => ({
    value: keys.map((key) => {
      const rawValue = getValue(config.id ?? null, key)
      if (rawValue === null) return null
      return isUsageMetricKey(key)
        ? metricToScore(rawValue, usageValues[key] || [])
        : rawValue
    }),
    name: seriesNames[index],
  }))

  const configsBySeriesName: Record<string, TaskRunConfig> = {}
  plottedConfigs.forEach((config, index) => {
    configsBySeriesName[seriesNames[index]] = config
  })

  return {
    indicators,
    series,
    legend: series.map((datum) => datum.name),
    configsBySeriesName,
    axisMaxes,
    keys,
    omittedKeyCount: omittedCount,
    axisLabels,
    candidateAxisCount: empty.candidateAxisCount,
    hasEvalSections: empty.hasEvalSections,
    hasData: indicators.length > 0 && series.length > 0,
  }
}
