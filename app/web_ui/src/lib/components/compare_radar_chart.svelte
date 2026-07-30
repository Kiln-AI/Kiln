<script lang="ts">
  import * as echarts from "echarts"
  import type {
    TaskRunConfig,
    ProviderModels,
    PromptResponse,
  } from "$lib/types"
  import { isMcpRunConfig } from "$lib/types"
  import {
    getRunConfigModelDisplayName,
    getRunConfigPromptDisplayName,
    getRunConfigInputTransformSummaryLabel,
  } from "$lib/utils/run_config_formatters"
  import { formatLatency } from "$lib/utils/formatters"
  import ChartNoData from "$lib/components/chart_no_data.svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"

  // Type for comparison features (same as parent page)
  type ComparisonFeature = {
    category: string
    items: { label: string; key: string }[]
    has_default_eval_config: boolean | undefined
    eval_id: string
  }

  // Props
  export let comparisonFeatures: ComparisonFeature[]
  export let getModelValueRaw: (
    modelKey: string | null,
    dataKey: string,
  ) => number | null
  export let run_configs: TaskRunConfig[]
  export let model_info: ProviderModels | null
  export let prompts: PromptResponse | null = null
  export let selectedRunConfigIds: string[]
  // Full-range maximum for a data key (eg 1 for pass/fail, 5 for 5-star), used by
  // the "Full Scale" axis mode. Keys without an entry (unbounded custom scores)
  // fall back to the data-relative max.
  export let scoreAxisMaxes: Record<string, number> = {}
  // Improvement direction per data key: "higher_is_better" | "lower_is_better" |
  // "informational". Unknown keys are treated as higher-is-better, which is what
  // every rating scale is by definition.
  export let scoreDirections: Record<string, string> = {}
  // Optional: when set, clicking a legend entry invokes this with the config's
  // id instead of toggling the series' visibility (the default echarts
  // behavior). Used by pages that treat the legend as a selection surface.
  export let onConfigClick: ((configId: string) => void) | null = null
  // Where the legend sits. "side" (default) keeps the historical behavior: a
  // vertical legend to the right of the radar, which collapses to a horizontal
  // one underneath when there are at most two series. "bottom" always puts a
  // scrollable horizontal legend underneath, so it can never paint over the
  // right-hand axis labels — for narrow columns with many configs.
  export let legend_position: "side" | "bottom" = "side"

  // Axis scaling mode. Relative scales each axis to the best value across the selected
  // run configs, which is the better lens for spotting differences between configs.
  // Full scale uses the score's own range, which is the only readable option when
  // there's nothing to compare against. Default follows the selection until the user
  // picks a mode, after which their choice sticks.
  let absoluteScale = false
  let userChoseScale = false
  $: if (!userChoseScale) {
    absoluteScale = plottedConfigCount <= 1
  }

  function setScale(useAbsolute: boolean) {
    absoluteScale = useAbsolute
    userChoseScale = true
  }

  // Fallback full-scale max when we don't know the score's type. Most eval scores are
  // normalized to 0-1, and we only use it when the data actually fits under it.
  const DEFAULT_ABSOLUTE_MAX = 1

  // Above this many scores the tooltip lists only the weakest ones - the full set is
  // in the comparison table above.
  const MAX_TOOLTIP_SCORES = 10

  // Below this many axes there's no shape to read, so there's no chart to draw
  const MIN_RADAR_AXES = 3

  const SCALE_TOOLTIP = `**Relative**: each axis is scaled to the highest value across the selected run configs. Best for spotting differences between configs.

**Full Scale**: each axis uses the score's own range (0-1 for pass/fail, 1-5 for 5-star). Best when looking at one run config on its own, where there is nothing to compare against.

Cost, latency and token axes score each run config against the others, so they stay relative in both modes. With a single run config there's nothing to compare against and they all sit at the midpoint. Hide one with the x on its row in the table above.`

  // Chart instance
  let chartInstance: echarts.ECharts | null = null

  // Which axis the pointer is nearest. echarts' radar tooltip is per-series - its
  // formatTooltip() is handed a dataIndex and maps over every indicator - so the
  // hovered axis has to be worked out from the pointer instead.
  let hoveredAxisIndex: number | null = null

  type RadarCoordSys = {
    cx: number
    cy: number
    getIndicatorAxes: () => { angle: number }[]
  }

  // getModel() is private in echarts' typings, and the radar's coordinate system is
  // the only place its centre and axis angles are exposed. Kept behind one cast and
  // fully guarded, so a change in echarts degrades to the whole-config tooltip
  // rather than throwing.
  function radarCoordSys(): RadarCoordSys | null {
    if (!chartInstance) return null
    const chart = chartInstance as unknown as {
      getModel?: () => {
        getComponent?: (
          mainType: string,
        ) => { coordinateSystem?: RadarCoordSys } | undefined
      }
    }
    const coordSys = chart
      .getModel?.()
      ?.getComponent?.("radar")?.coordinateSystem
    if (!coordSys || typeof coordSys.cx !== "number") return null
    if (typeof coordSys.getIndicatorAxes !== "function") return null
    return coordSys
  }

  // Prefer the symbol under the pointer, which echarts tags with the axis it belongs
  // to. Falls back to the nearest axis by angle, so hovering the line or the filled
  // area still resolves to one metric.
  function axisIndexFromPointer(event: {
    target?: { __dimIdx?: number }
    offsetX?: number
    offsetY?: number
  }): number | null {
    const dimIdx = event.target?.__dimIdx
    if (typeof dimIdx === "number") return dimIdx

    const coordSys = radarCoordSys()
    if (
      !coordSys ||
      event.offsetX === undefined ||
      event.offsetY === undefined
    ) {
      return null
    }
    const axes = coordSys.getIndicatorAxes()
    if (!axes?.length) return null

    // Same convention as the radar's dataToPoint: y grows downward, angles don't
    const pointerAngle = Math.atan2(
      coordSys.cy - event.offsetY,
      event.offsetX - coordSys.cx,
    )
    let best = 0
    let bestDelta = Infinity
    axes.forEach((axis, index) => {
      let delta = Math.abs(pointerAngle - axis.angle) % (Math.PI * 2)
      if (delta > Math.PI) delta = Math.PI * 2 - delta
      if (delta < bestDelta) {
        bestDelta = delta
        best = index
      }
    })
    return best
  }

  const COST_KEY = "cost::mean_cost"
  const LATENCY_KEY = "cost::mean_total_llm_latency_ms"

  // Cost, latency and token counts are lower-is-better raw quantities with no
  // absolute range, so they're scored by position within the selected run configs
  // (metricToScore) on a shared 0-100 axis. That's a comparison, which means these
  // axes only carry information when there are at least two configs to compare - and
  // it's why they stay relative even in Full Scale mode.
  //
  // On the chart they're named for the direction that's better, since a bigger value
  // means less cost / less time / fewer tokens.
  const USAGE_LABELS: Record<string, string> = {
    [COST_KEY]: "Cost Efficiency",
    [LATENCY_KEY]: "Speed",
    "cost::mean_total_tokens": "Token Efficiency",
    "cost::mean_input_tokens": "Input Token Efficiency",
    "cost::mean_output_tokens": "Output Token Efficiency",
  }

  function isLowerIsBetterMetric(key: string): boolean {
    return key.startsWith("cost::")
  }

  // Position of a lower-is-better value within the selected configs, as a 0-100
  // score. Ties (or a single config) land at 50: no better, no worse.
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

  // Eval score keys (the cost section is excluded - its metrics come back as usage
  // axes below, on their own terms)
  $: dataKeys = comparisonFeatures
    .filter((f) => f.eval_id !== "kiln_cost_section")
    .flatMap((f) => f.items.map((item) => item.key))

  // Usage axes come from the cost section of the table, so hiding a row there with
  // its x removes the axis here too - one control, where the numbers are.
  $: visibleUsageKeys = comparisonFeatures
    .filter((f) => f.eval_id === "kiln_cost_section")
    .flatMap((f) => f.items.map((item) => item.key))

  // Run configs that will actually be drawn: selected, and with at least one eval
  // result. A config with nothing to show shouldn't make the chart behave as though
  // there's something to compare against. Computed here rather than read back out of
  // generateChartData() so that the scale default below doesn't depend on a value
  // that itself depends on the scale.
  $: plottedConfigCount = selectedRunConfigIds.filter(
    (configId) =>
      run_configs.some((c) => c.id === configId) &&
      chartKeys.some((key) => getModelValueRaw(configId, key) !== null),
  ).length

  // A radar reads "further from center is better". Scores that don't share that
  // grammar are left off rather than drawn backwards: a lower-is-better score would
  // put its best result closest to the center, and an informational score has no
  // better end at all. Both stay in the table and the metric correlation chart.
  $: excludedKeys = dataKeys.filter(
    (key) =>
      scoreDirections[key] === "lower_is_better" ||
      scoreDirections[key] === "informational",
  )
  $: chartKeys = dataKeys.filter((key) => !excludedKeys.includes(key))

  $: notShownNote = (() => {
    const parts: string[] = []
    if (excludedKeys.length > 0) {
      parts.push(
        `${excludedKeys.length} lower-is-better or informational ${
          excludedKeys.length === 1 ? "score" : "scores"
        }`,
      )
    }
    if (noResultAxisCount > 0) {
      parts.push(
        `${noResultAxisCount} ${
          noResultAxisCount === 1 ? "score" : "scores"
        } without results for every selected run config`,
      )
    }
    if (parts.length === 0) return null
    return `Not shown: ${parts.join(", ")}. See the table above.`
  })()

  // Get labels for radar indicators
  function getKeyLabel(dataKey: string): string {
    if (USAGE_LABELS[dataKey]) return USAGE_LABELS[dataKey]
    for (const feature of comparisonFeatures) {
      const item = feature.items.find((i) => i.key === dataKey)
      if (item) return item.label
    }
    return dataKey
  }

  // Axis names are drawn just outside the outermost ring, where the left and
  // right ones run straight into the chart's edge. Hard-wrapping them keeps
  // every line inside the box instead of letting echarts clip it.
  const AXIS_NAME_LINE_CHARS = 14
  const AXIS_NAME_MAX_LINES = 3

  export function wrapAxisName(
    name: string,
    lineChars: number = AXIS_NAME_LINE_CHARS,
  ): string {
    const lines: string[] = []
    let line = ""
    const push = () => {
      if (line.length > 0) {
        lines.push(line)
        line = ""
      }
    }
    for (const word of name.split(/\s+/).filter((w) => w.length > 0)) {
      // A word longer than the line budget is hard-split rather than overflowing
      if (word.length > lineChars) {
        push()
        for (let i = 0; i < word.length; i += lineChars) {
          lines.push(word.slice(i, i + lineChars))
        }
        line = lines.pop() ?? ""
        continue
      }
      if (line.length === 0) {
        line = word
      } else if (line.length + 1 + word.length <= lineChars) {
        line = `${line} ${word}`
      } else {
        push()
        line = word
      }
    }
    push()
    if (lines.length > AXIS_NAME_MAX_LINES) {
      const kept = lines.slice(0, AXIS_NAME_MAX_LINES)
      kept[AXIS_NAME_MAX_LINES - 1] = `${kept[AXIS_NAME_MAX_LINES - 1]}…`
      return kept.join("\n")
    }
    return lines.join("\n")
  }

  // Get simple display name for the series (used as the internal name/key)
  function getSeriesDisplayName(config: TaskRunConfig): string {
    if (config.name) return config.name
    if (isMcpRunConfig(config.run_config_properties)) {
      return config.run_config_properties.tool_reference.tool_name ?? "MCP Tool"
    }
    return getRunConfigModelDisplayName(config, model_info) ?? "Unknown"
  }

  // The raw quantity behind a usage axis, in its own units
  function formatUsageValue(key: string, value: number | null): string {
    if (value === null) return "N/A"
    if (key === COST_KEY) return `$${value.toFixed(6)}`
    if (key === LATENCY_KEY) return formatLatency(value)
    return `${Math.round(value).toLocaleString()} tokens`
  }

  // Mean usage for a config, formatted for display. Null when unavailable.
  function getUsageSummary(config: TaskRunConfig | undefined): {
    cost: string | null
    latency: string | null
    totalTokens: string | null
  } {
    const raw = (key: string) =>
      config?.id ? getModelValueRaw(config.id, key) : null
    const meanCost = raw(COST_KEY)
    const meanLatency = raw(LATENCY_KEY)
    const meanTotalTokens = raw("cost::mean_total_tokens")
    return {
      cost: meanCost === null ? null : formatUsageValue(COST_KEY, meanCost),
      latency:
        meanLatency === null
          ? null
          : formatUsageValue(LATENCY_KEY, meanLatency),
      totalTokens:
        meanTotalTokens === null
          ? null
          : formatUsageValue("cost::mean_total_tokens", meanTotalTokens),
    }
  }

  function buildLegendSubtext(config: TaskRunConfig): string {
    const parts: string[] = []
    if (isMcpRunConfig(config.run_config_properties)) {
      const toolName =
        config.run_config_properties.tool_reference.tool_name ?? "MCP Tool"
      parts.push(`{sub|Tool: ${toolName}}`)
    } else {
      const modelName =
        getRunConfigModelDisplayName(config, model_info) || "Unknown"
      const promptName = getRunConfigPromptDisplayName(config, prompts)
      parts.push(`{sub|Model: ${modelName}}`)
      if (promptName) parts.push(`{sub|Prompt: ${promptName}}`)
      const transformLabel = getRunConfigInputTransformSummaryLabel(config)
      if (transformLabel) parts.push(`{sub|Input Transform: ${transformLabel}}`)
    }
    return parts.join("\n")
  }

  function buildLegendFormatter(): Record<string, string> {
    const formatter: Record<string, string> = {}
    for (const configId of selectedRunConfigIds) {
      const config = run_configs.find((c) => c.id === configId)
      if (!config) continue
      const displayName = getSeriesDisplayName(config)
      formatter[displayName] = `${displayName}\n${buildLegendSubtext(config)}`
    }
    return formatter
  }

  // Colours are assigned per data item from the palette, in series order
  function seriesColorAt(index: number): string {
    const palette = chartInstance?.getOption()?.color as string[] | undefined
    if (!palette?.length) return "#888"
    return palette[index % palette.length]
  }

  function tooltipMarker(color: string): string {
    return `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${color};margin-right:6px;"></span>`
  }

  // One metric across every plotted run config, so hovering a point answers "how do
  // they compare here" rather than reciting everything this config scored.
  function buildAxisTooltip(
    axisIndex: number,
    keys: string[],
    series: { value: (number | null)[]; name: string }[],
    hoveredName: string,
  ): string {
    const key = keys[axisIndex]
    const isUsage = isLowerIsBetterMetric(key)

    let html = `<div style="font-weight: bold; margin-bottom: 6px;">${getKeyLabel(key)}</div>`
    series.forEach((entry, index) => {
      const plotted = entry.value[axisIndex]
      const config = run_configs.find(
        (c) => getSeriesDisplayName(c) === entry.name,
      )
      const rawValue = config?.id ? getModelValueRaw(config.id, key) : null

      let shown: string
      if (plotted === null || rawValue === null) {
        shown = "N/A"
      } else if (isUsage) {
        // The axis plots a relative score, so give the quantity behind it too
        shown = `${plotted.toFixed(1)} <span style="color: #888;">(${formatUsageValue(key, rawValue)})</span>`
      } else {
        shown = rawValue.toFixed(3)
      }

      const weight = entry.name === hoveredName ? "600" : "400"
      html += `<div style="font-weight: ${weight};">${tooltipMarker(
        seriesColorAt(index),
      )}${entry.name}: ${shown}</div>`
    })
    return html
  }

  // Build full tooltip HTML for a run config (reused by chart tooltip and legend tooltip)
  function buildRunConfigTooltip(
    name: string,
    axisMaxes: Record<string, number>,
    keys: string[],
  ): string {
    const config = run_configs.find((c) => getSeriesDisplayName(c) === name)

    let html = `<div style="font-weight: bold; margin-bottom: 4px;">${name}</div>`
    if (config && isMcpRunConfig(config.run_config_properties)) {
      const toolName =
        config.run_config_properties.tool_reference.tool_name ?? "MCP Tool"
      html += `<div>MCP Tool: ${toolName}</div>`
    } else {
      const modelName = config
        ? getRunConfigModelDisplayName(config, model_info) || "Unknown"
        : "Unknown"
      const promptName = config
        ? getRunConfigPromptDisplayName(config, prompts)
        : null
      html += `<div>Model: ${modelName}</div>`
      if (promptName) {
        html += `<div>Prompt: ${promptName}</div>`
      }
      if (config) {
        const transformLabel = getRunConfigInputTransformSummaryLabel(config)
        if (transformLabel) {
          html += `<div>Input Transform: ${transformLabel}</div>`
        }
      }
    }

    const usage = getUsageSummary(config)
    if (usage.cost) html += `<div>Mean Cost: ${usage.cost}</div>`
    if (usage.latency) html += `<div>Mean Latency: ${usage.latency}</div>`
    if (usage.totalTokens) {
      html += `<div>Mean Total Tokens: ${usage.totalTokens}</div>`
    }

    // Eval scores only. The usage axes plot a relative score rather than their raw
    // quantity, so ranking them against pass rates would compare unlike things -
    // their real values are listed above instead.
    const scores = keys
      .filter((key) => !isLowerIsBetterMetric(key))
      .map((key) => {
        const value = config?.id ? getModelValueRaw(config.id, key) : null
        const max = axisMaxes[key] || 1
        return {
          label: getKeyLabel(key),
          value,
          // Rank by position on the axis, so scores with different ranges (0-1 vs
          // 1-5) are comparable. Missing values sort first: "didn't run" is worth
          // surfacing.
          position: value === null ? -1 : value / max,
        }
      })

    const trimmed = scores.length > MAX_TOOLTIP_SCORES
    const shown = trimmed
      ? [...scores]
          .sort((a, b) => a.position - b.position)
          .slice(0, MAX_TOOLTIP_SCORES)
      : scores

    html += `<div style="font-weight: bold; margin-bottom: 4px; padding-top: 8px;">${
      trimmed ? "Lowest Scores" : "Values"
    }</div>`
    for (const score of shown) {
      const formatted = score.value === null ? "N/A" : score.value.toFixed(3)
      html += `<div>${score.label}: ${formatted}</div>`
    }
    if (trimmed) {
      html += `<div style="color: #888; padding-top: 4px;">+${
        scores.length - shown.length
      } more in the table above</div>`
    }

    return html
  }

  // Axis max in "Full Scale" mode: the score's own range when we know it, otherwise
  // the normalized 0-1 default. Never returns a max below the data, so nothing is
  // clipped for unbounded (custom) scores or unrecognized score types.
  function absoluteAxisMax(
    key: string,
    rawMax: number,
    paddedMax: number,
  ): number {
    const knownMax = scoreAxisMaxes[key]
    if (knownMax !== undefined && knownMax >= rawMax) {
      return knownMax
    }
    return rawMax <= DEFAULT_ABSOLUTE_MAX ? DEFAULT_ABSOLUTE_MAX : paddedMax
  }

  function generateChartData(): {
    indicators: { name: string; max: number }[]
    series: { value: (number | null)[]; name: string }[]
    legend: string[]
    axisMaxes: Record<string, number>
    keys: string[]
    noResultKeyCount: number
  } {
    const indicators: { name: string; max: number }[] = []
    const series: { value: (number | null)[]; name: string }[] = []
    const legend: string[] = []
    const axisMaxes: Record<string, number> = {}
    const empty = {
      indicators,
      series,
      legend,
      axisMaxes,
      keys: [] as string[],
    }

    if (chartKeys.length === 0 || selectedRunConfigIds.length === 0) {
      return { ...empty, noResultKeyCount: 0 }
    }

    // Run configs with at least one result. One with nothing to plot is left out
    // entirely rather than emptying every axis. Same rule as the module-level
    // plottedConfigCount, which the scale default reads.
    const plottedConfigs = selectedRunConfigIds
      .map((configId) => run_configs.find((c) => c.id === configId))
      .filter((config): config is TaskRunConfig => !!config)
      .filter((config) =>
        chartKeys.some(
          (key) => getModelValueRaw(config.id ?? null, key) !== null,
        ),
      )

    const candidateKeys = [...chartKeys, ...visibleUsageKeys]

    // Only scores every plotted config has a result for. ECharts draws a missing
    // radar value at the center of the chart (radarLayout's getValueMissingPoint),
    // which is indistinguishable from scoring zero - so an axis one config hasn't
    // been evaluated on can't be drawn honestly at all. It's left out, and counted
    // under the chart title instead.
    const keys = candidateKeys.filter((key) =>
      plottedConfigs.every(
        (config) => getModelValueRaw(config.id ?? null, key) !== null,
      ),
    )
    const noResultKeyCount = candidateKeys.length - keys.length

    if (keys.length < MIN_RADAR_AXES) {
      return { ...empty, noResultKeyCount }
    }

    // Every value on a usage axis, so each can be scored by its position among them
    const usageValues: Record<string, number[]> = {}
    for (const key of keys) {
      if (!isLowerIsBetterMetric(key)) continue
      usageValues[key] = plottedConfigs
        .map((config) => getModelValueRaw(config.id ?? null, key))
        .filter((value): value is number => value !== null)
    }

    // Calculate max values for each data key across the plotted run configs
    for (const key of keys) {
      if (isLowerIsBetterMetric(key)) {
        // Already a 0-100 score, in both scale modes
        axisMaxes[key] = 100
        continue
      }
      let max = 0
      for (const config of plottedConfigs) {
        const value = getModelValueRaw(config.id ?? null, key)
        if (value !== null && value > max) {
          max = value
        }
      }
      // Add 10% padding to max for better visualization
      const paddedMax = max > 0 ? max * 1.1 : 1
      axisMaxes[key] = absoluteScale
        ? absoluteAxisMax(key, max, paddedMax)
        : paddedMax
    }

    for (const key of keys) {
      indicators.push({
        name: getKeyLabel(key),
        max: axisMaxes[key],
      })
    }

    // Build series data for each plotted run config. Every one of them has a value
    // for every key by construction above.
    for (const config of plottedConfigs) {
      const values = keys.map((key) => {
        const rawValue = getModelValueRaw(config.id ?? null, key)
        if (rawValue === null) return null
        return isLowerIsBetterMetric(key)
          ? metricToScore(rawValue, usageValues[key] || [])
          : rawValue
      })
      const name = getSeriesDisplayName(config)
      legend.push(name)
      series.push({ value: values, name })
    }

    return { indicators, series, legend, axisMaxes, keys, noResultKeyCount }
  }

  // Check if there's data to display (reactive - references every input that can
  // change what generateChartData() returns)
  $: chartSummary = (() => {
    // visibleUsageKeys is referenced so this re-runs when a usage row is hidden
    if (
      !chartKeys ||
      chartKeys.length === 0 ||
      !selectedRunConfigIds ||
      !visibleUsageKeys
    ) {
      return { hasData: false, noResultKeyCount: 0 }
    }
    const { indicators, series, noResultKeyCount } = generateChartData()
    return {
      hasData: indicators.length > 0 && series.length > 0,
      noResultKeyCount,
    }
  })()
  $: hasData = chartSummary.hasData
  $: noResultAxisCount = chartSummary.noResultKeyCount

  // When there's nothing to draw, say which of the two reasons it is
  $: noDataMessage =
    noResultAxisCount > 0
      ? `The selected run configurations share fewer than ${MIN_RADAR_AXES} scores with results. Run the missing evals, or compare fewer run configurations.`
      : "Create and run evals to see a comparison chart."

  function updateChart() {
    if (!chartInstance) return

    if (!hasData) {
      chartInstance.clear()
      return
    }

    const { indicators, series, legend, axisMaxes, keys } = generateChartData()

    const legendFormatter = buildLegendFormatter()

    // A couple of configs don't need a legend column - centering the radar and
    // dropping the legend underneath buys a much larger plot. legend_position
    // "bottom" asks for that arrangement whatever the series count.
    const forceBottomLegend = legend_position === "bottom"
    const compactLayout = forceBottomLegend || series.length <= 2

    const legendTextStyle = {
      lineHeight: 16,
      rich: {
        sub: {
          fontSize: 11,
          color: "#666",
          lineHeight: 14,
        },
      },
    }

    chartInstance.setOption(
      {
        tooltip: {
          trigger: "item",
          confine: true,
          formatter: (params: { name: string }) => {
            // The legend keeps the whole-config summary; on the chart itself a
            // hovered point is a question about one metric.
            if (
              hoveredAxisIndex !== null &&
              hoveredAxisIndex >= 0 &&
              hoveredAxisIndex < keys.length
            ) {
              return buildAxisTooltip(
                hoveredAxisIndex,
                keys,
                series,
                params.name,
              )
            }
            return buildRunConfigTooltip(params.name, axisMaxes, keys)
          },
        },
        legend: {
          data: legend,
          formatter: (name: string) => legendFormatter[name] || name,
          tooltip: {
            show: true,
            formatter: (params: { name: string }) =>
              buildRunConfigTooltip(params.name, axisMaxes, keys),
          },
          textStyle: legendTextStyle,
          ...(compactLayout
            ? {
                orient: "horizontal" as const,
                bottom: 0,
                left: "center" as const,
                itemGap: forceBottomLegend ? 24 : 40,
                // Many configs in a narrow column would otherwise wrap into the
                // plot; scroll mode keeps the legend to one paged row.
                ...(forceBottomLegend ? { type: "scroll" as const } : {}),
              }
            : {
                orient: "vertical" as const,
                left: "60%",
                top: "middle" as const,
                itemGap: 16,
              }),
        },
        radar: {
          indicator: indicators,
          center: forceBottomLegend
            ? ["50%", "44%"]
            : compactLayout
              ? ["50%", "46%"]
              : ["32%", "50%"],
          radius: compactLayout ? "62%" : "85%",
          axisName: {
            color: "#666",
            ...(forceBottomLegend
              ? {
                  // Hard-wrapped by the formatter below, so no echarts-side
                  // width/overflow is needed (and nothing gets clipped).
                  fontSize: 10,
                  lineHeight: 12,
                  formatter: (name: string) => wrapAxisName(name),
                }
              : {
                  fontSize: 12,
                  // Wrap long score names instead of letting neighbours collide
                  width: 110,
                  overflow: "break",
                  lineHeight: 14,
                }),
          },
          splitArea: {
            areaStyle: {
              color: ["#f8f9fa", "#ffffff"],
            },
          },
          splitLine: {
            lineStyle: {
              color: "#e5e7eb",
            },
          },
          axisLine: {
            lineStyle: {
              color: "#e5e7eb",
            },
          },
        },
        series: [
          {
            name: "Eval Scores",
            type: "radar",
            data: series,
            lineStyle: {
              width: 2,
            },
            symbolSize: 6,
            // Filling one shape makes it readable. Filling several makes mud.
            ...(series.length === 1 ? { areaStyle: { opacity: 0.2 } } : {}),
          },
        ],
      },
      true,
    )
  }

  // Named so the reactive block below re-runs when the scaling mode is toggled
  $: axisScaleMode = absoluteScale ? "absolute" : "relative"

  // Update chart when data changes (model_info and prompts may load async). Every
  // input that changes what's drawn has to be referenced here, or the chart keeps
  // showing the previous render.
  $: if (
    chartInstance &&
    comparisonFeatures &&
    selectedRunConfigIds &&
    axisScaleMode &&
    legend_position &&
    scoreAxisMaxes &&
    scoreDirections &&
    visibleUsageKeys &&
    (model_info || model_info === null) &&
    (prompts || prompts === null)
  ) {
    updateChart()
  }

  // Svelte action to initialize chart when element is added to DOM
  function initChart(node: HTMLElement) {
    chartInstance = echarts.init(node)

    const resizeObserver = new ResizeObserver(() => {
      chartInstance?.resize()
    })
    resizeObserver.observe(node)

    // Legend-as-selection: undo the visibility toggle and report the click
    chartInstance.on("legendselectchanged", (params) => {
      if (!onConfigClick) return
      const name = (params as { name?: string }).name
      if (!name) return
      chartInstance?.dispatchAction({ type: "legendSelect", name })
      const config = run_configs.find((c) => getSeriesDisplayName(c) === name)
      if (config?.id) {
        onConfigClick(config.id)
      }
    })

    // Track the pointer at the zrender level: it updates before the tooltip is
    // built, so the formatter knows which axis is under the cursor.
    const zr = chartInstance.getZr()
    const onPointerMove = (event: {
      target?: { __dimIdx?: number }
      offsetX?: number
      offsetY?: number
    }) => {
      hoveredAxisIndex = axisIndexFromPointer(event)
    }
    const onPointerOut = () => {
      hoveredAxisIndex = null
    }
    zr.on("mousemove", onPointerMove)
    zr.on("globalout", onPointerOut)

    updateChart()

    return {
      destroy() {
        resizeObserver.disconnect()
        zr.off("mousemove", onPointerMove)
        zr.off("globalout", onPointerOut)
        chartInstance?.dispose()
        chartInstance = null
      },
    }
  }
</script>

<!-- Radar charts don't really work with <3 items. Counts the usage axes too: they
     are axes like any other, and a task with one or two eval scores still has a
     chart worth drawing once cost, latency and tokens are on it. -->
{#if chartKeys.length + visibleUsageKeys.length >= MIN_RADAR_AXES}
  <div
    class="bg-white border border-gray-200 rounded-lg p-6 mb-6 h-full flex flex-col"
  >
    <div class="flex flex-row gap-4 items-start">
      <div class="flex-grow">
        <div class="text-xl font-bold">Radar Chart</div>
        <div class="text-sm text-gray-500 {notShownNote ? '' : 'mb-4'}">
          Compare the evaluation scores of the run configurations selected
          above.
        </div>
        {#if notShownNote}
          <div class="text-xs text-gray-400 mt-1 mb-4">{notShownNote}</div>
        {/if}
      </div>
      <div class="flex flex-row gap-1 items-center flex-shrink-0">
        <div class="join">
          <button
            type="button"
            class="join-item btn btn-sm {absoluteScale ? '' : 'btn-active'}"
            aria-pressed={!absoluteScale}
            on:click={() => setScale(false)}
          >
            Relative
          </button>
          <button
            type="button"
            class="join-item btn btn-sm {absoluteScale ? 'btn-active' : ''}"
            aria-pressed={absoluteScale}
            on:click={() => setScale(true)}
          >
            Full Scale
          </button>
        </div>
        <InfoTooltip tooltip_text={SCALE_TOOLTIP} position="bottom" />
      </div>
    </div>
    {#if hasData}
      <!-- With the legend underneath the plot the card is sized by its column,
           so it only needs a floor tall enough for the radar plus the legend. -->
      <div
        use:initChart
        class="w-full flex-1 {legend_position === 'bottom'
          ? 'min-h-[380px]'
          : 'min-h-[500px] xl:min-h-[620px]'}"
      ></div>
    {:else}
      <ChartNoData
        title={noResultAxisCount > 0
          ? "Not Enough Shared Scores"
          : "No Data Available"}
        message={noDataMessage}
      />
    {/if}
  </div>
{/if}
