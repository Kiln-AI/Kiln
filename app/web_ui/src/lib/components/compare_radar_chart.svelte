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

  const SCALE_TOOLTIP = `**Relative**: each axis is scaled to the highest value across the selected run configs. Best for spotting differences between configs.

**Full Scale**: each axis uses the score's own range (0-1 for pass/fail, 1-5 for 5-star). Best when looking at one run config on its own, where there is nothing to compare against.

Cost and latency axes score each run config against the others, so they stay relative in both modes. With a single run config there's nothing to compare against and they both sit at the midpoint.`

  // Chart instance
  let chartInstance: echarts.ECharts | null = null

  // Keys that should be included in radar chart where lower is better
  const COST_KEY = "cost::mean_cost"
  const LATENCY_KEY = "cost::mean_total_llm_latency_ms"

  // Check if a key is a lower-is-better metric
  function isLowerIsBetterMetric(key: string): boolean {
    return key === COST_KEY || key === LATENCY_KEY
  }

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

  // Get all data keys: include eval metrics + cost (but exclude token counts)
  $: dataKeys = [
    ...comparisonFeatures
      .filter((f) => f.eval_id !== "kiln_cost_section")
      .flatMap((f) => f.items.map((item) => item.key)),
    COST_KEY,
    LATENCY_KEY,
  ]

  // Run configs that will actually be drawn: selected, and with at least one eval
  // result. A config with nothing to show shouldn't make the chart behave as though
  // there's something to compare against.
  $: plottedConfigCount = selectedRunConfigIds.filter(
    (configId) =>
      run_configs.some((c) => c.id === configId) &&
      dataKeys.some((key) => getModelValueRaw(configId, key) !== null),
  ).length

  // Get labels for radar indicators
  function getKeyLabel(dataKey: string): string {
    // Special handling for lower-is-better metrics
    if (dataKey === COST_KEY) {
      return "Cost Efficiency"
    }
    if (dataKey === LATENCY_KEY) {
      return "Speed"
    }
    for (const feature of comparisonFeatures) {
      const item = feature.items.find((i) => i.key === dataKey)
      if (item) return item.label
    }
    return dataKey
  }

  // Get simple display name for the series (used as the internal name/key)
  function getSeriesDisplayName(config: TaskRunConfig): string {
    if (config.name) return config.name
    if (isMcpRunConfig(config.run_config_properties)) {
      return config.run_config_properties.tool_reference.tool_name ?? "MCP Tool"
    }
    return getRunConfigModelDisplayName(config, model_info) ?? "Unknown"
  }

  function buildLegendSubtext(config: TaskRunConfig): string {
    if (isMcpRunConfig(config.run_config_properties)) {
      const toolName =
        config.run_config_properties.tool_reference.tool_name ?? "MCP Tool"
      return `{sub|Tool: ${toolName}}`
    }
    const modelName =
      getRunConfigModelDisplayName(config, model_info) || "Unknown"
    const promptName = getRunConfigPromptDisplayName(config, prompts)
    const parts = [`{sub|Model: ${modelName}}`]
    if (promptName) parts.push(`{sub|Prompt: ${promptName}}`)
    const transformLabel = getRunConfigInputTransformSummaryLabel(config)
    if (transformLabel) parts.push(`{sub|Input Transform: ${transformLabel}}`)
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

  // Build full tooltip HTML for a run config (reused by chart tooltip and legend tooltip)
  function buildRunConfigTooltip(
    name: string,
    lowerIsBetterValues: Record<string, number[]>,
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
    html += `<div style="font-weight: bold; margin-bottom: 4px; padding-top: 8px;">Values</div>`

    dataKeys.forEach((key) => {
      const label = getKeyLabel(key)
      const rawValue = config?.id ? getModelValueRaw(config.id, key) : null
      if (rawValue === null) {
        html += `<div>${label}: N/A</div>`
      } else if (key === COST_KEY) {
        const displayValue = metricToScore(
          rawValue,
          lowerIsBetterValues[key] || [],
        )
        html += `<div>${label}: ${displayValue.toFixed(1)} <span style="color: #888;">(Mean Cost: $${rawValue.toFixed(6)})</span></div>`
      } else if (key === LATENCY_KEY) {
        const displayValue = metricToScore(
          rawValue,
          lowerIsBetterValues[key] || [],
        )
        const formatted =
          rawValue < 1000
            ? `${Math.round(rawValue)}ms`
            : `${(rawValue / 1000).toFixed(1)}s`
        html += `<div>${label}: ${displayValue.toFixed(1)} <span style="color: #888;">(Mean Latency: ${formatted})</span></div>`
      } else {
        html += `<div>${label}: ${rawValue.toFixed(3)}</div>`
      }
    })

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
    series: { value: number[]; name: string }[]
    legend: string[]
    lowerIsBetterValues: Record<string, number[]>
  } {
    const indicators: { name: string; max: number }[] = []
    const series: { value: number[]; name: string }[] = []
    const legend: string[] = []
    const lowerIsBetterValues: Record<string, number[]> = {}

    if (dataKeys.length === 0 || selectedRunConfigIds.length === 0) {
      return { indicators, series, legend, lowerIsBetterValues }
    }

    // Calculate the max of each axis, in the current scale mode
    const axisMaxes: Record<string, number> = {}

    for (const key of dataKeys) {
      let max = 0
      for (const configId of selectedRunConfigIds) {
        const value = getModelValueRaw(configId, key)
        if (value !== null && value > max) {
          max = value
        }
        if (value !== null && isLowerIsBetterMetric(key)) {
          if (!lowerIsBetterValues[key]) lowerIsBetterValues[key] = []
          lowerIsBetterValues[key].push(value)
        }
      }
      if (isLowerIsBetterMetric(key)) {
        // Already a 0-100 score, in both scale modes
        axisMaxes[key] = 100
        continue
      }
      // Add 10% padding to max for better visualization
      const paddedMax = max > 0 ? max * 1.1 : 1
      axisMaxes[key] = absoluteScale
        ? absoluteAxisMax(key, max, paddedMax)
        : paddedMax
    }

    for (const key of dataKeys) {
      indicators.push({
        name: getKeyLabel(key),
        max: axisMaxes[key],
      })
    }

    // Build series data for each selected run config
    for (const configId of selectedRunConfigIds) {
      const config = run_configs.find((c) => c.id === configId)
      if (!config) continue

      const values: number[] = []
      let hasAnyValue = false

      for (const key of dataKeys) {
        const rawValue = getModelValueRaw(configId, key)
        let displayValue: number
        if (rawValue === null) {
          displayValue = 0
        } else if (isLowerIsBetterMetric(key)) {
          displayValue = metricToScore(rawValue, lowerIsBetterValues[key] || [])
        } else {
          displayValue = rawValue
        }
        values.push(displayValue)
        if (rawValue !== null) hasAnyValue = true
      }

      // Only include if at least one value is available
      if (hasAnyValue) {
        const name = getSeriesDisplayName(config)
        legend.push(name)
        series.push({ value: values, name })
      }
    }

    return { indicators, series, legend, lowerIsBetterValues }
  }

  // Check if there's data to display (reactive, depends on dataKeys and selectedRunConfigIds)
  $: hasData = (() => {
    if (!dataKeys || dataKeys.length === 0 || !selectedRunConfigIds) {
      return false
    }
    const { indicators, series } = generateChartData()
    return indicators.length > 0 && series.length > 0
  })()

  function updateChart() {
    if (!chartInstance) return

    if (!hasData) {
      chartInstance.clear()
      return
    }

    const { indicators, series, legend, lowerIsBetterValues } =
      generateChartData()

    const legendFormatter = buildLegendFormatter()

    // A couple of configs don't need a legend column - centering the radar and
    // dropping the legend underneath buys a much larger plot.
    const compactLayout = series.length <= 2

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
          formatter: (params: { name: string }) =>
            buildRunConfigTooltip(params.name, lowerIsBetterValues),
        },
        legend: {
          data: legend,
          formatter: (name: string) => legendFormatter[name] || name,
          tooltip: {
            show: true,
            formatter: (params: { name: string }) =>
              buildRunConfigTooltip(params.name, lowerIsBetterValues),
          },
          textStyle: legendTextStyle,
          ...(compactLayout
            ? {
                orient: "horizontal" as const,
                bottom: 0,
                left: "center" as const,
                itemGap: 40,
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
          center: compactLayout ? ["50%", "46%"] : ["32%", "50%"],
          radius: compactLayout ? "62%" : "85%",
          axisName: {
            color: "#666",
            fontSize: 12,
            // Wrap long score names instead of letting neighbours collide
            width: 110,
            overflow: "break",
            lineHeight: 14,
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
    scoreAxisMaxes &&
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

    updateChart()

    return {
      destroy() {
        resizeObserver.disconnect()
        chartInstance?.dispose()
        chartInstance = null
      },
    }
  }
</script>

<!-- Radar charts don't really work with <3 items -->
{#if dataKeys.length >= 3}
  <div
    class="bg-white border border-gray-200 rounded-lg p-6 mb-6 h-full flex flex-col"
  >
    <div class="flex flex-row gap-4 items-start">
      <div class="flex-grow">
        <div class="text-xl font-bold">Radar Chart</div>
        <div class="text-sm text-gray-500 mb-4">
          Compare the evaluation scores of the run configurations selected
          above.
        </div>
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
      <div
        use:initChart
        class="w-full flex-1 min-h-[500px] xl:min-h-[620px]"
      ></div>
    {:else}
      <ChartNoData />
    {/if}
  </div>
{/if}
