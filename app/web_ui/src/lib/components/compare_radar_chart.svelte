<script lang="ts">
  import * as echarts from "echarts"
  import type {
    TaskRunConfig,
    ProviderModels,
    PromptResponse,
  } from "$lib/types"
  import {
    getRunConfigDisplayName,
    getRunConfigPromptDisplayName,
  } from "$lib/utils/run_config_formatters"
  import ChartNoData from "$lib/components/chart_no_data.svelte"

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

  // Chart instance
  let chartInstance: echarts.ECharts | null = null

  // Cost key that should be included in radar chart (inverted, lower is better)
  const COST_KEY = "cost::mean_cost"

  // Check if a key is the cost metric (where lower is better)
  function isCostMetric(key: string): boolean {
    return key === COST_KEY
  }

  export function costToScore(
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
    COST_KEY, // Add cost at the end
  ]

  // Get labels for radar indicators
  function getKeyLabel(dataKey: string): string {
    // Special handling for cost metric
    if (dataKey === COST_KEY) {
      return "Cost Efficiency"
    }
    for (const feature of comparisonFeatures) {
      const item = feature.items.find((i) => i.key === dataKey)
      if (item) return item.label
    }
    return dataKey
  }

  // Get simple display name for the series (used as the internal name/key)
  function getSeriesDisplayName(config: TaskRunConfig): string {
    return (
      config.name || getRunConfigDisplayName(config, model_info) || "Unknown"
    )
  }

  // Build a map from display name to full legend text (name, model, prompt)
  function buildLegendFormatter(): Record<string, string> {
    const formatter: Record<string, string> = {}
    for (const configId of selectedRunConfigIds) {
      const config = run_configs.find((c) => c.id === configId)
      if (!config) continue

      const displayName = getSeriesDisplayName(config)
      const modelName = getRunConfigDisplayName(config, model_info) || "Unknown"
      const promptName = getRunConfigPromptDisplayName(config, prompts)

      // Multi-line legend: display name on first line, model and prompt on 2nd/3rd
      formatter[displayName] =
        `${displayName}\n{sub|Model: ${modelName}}\n{sub|Prompt: ${promptName}}`
    }
    return formatter
  }

  // Build full tooltip HTML for a run config (reused by chart tooltip and legend tooltip)
  function buildRunConfigTooltip(name: string, allCosts: number[]): string {
    const config = run_configs.find((c) => getSeriesDisplayName(c) === name)
    const modelName = config
      ? getRunConfigDisplayName(config, model_info) || "Unknown"
      : "Unknown"
    const promptName = config
      ? getRunConfigPromptDisplayName(config, prompts)
      : "Unknown"

    let html = `<div style="font-weight: bold; margin-bottom: 4px;">${name}</div>`
    html += `<div>Model: ${modelName}</div>`
    html += `<div>Prompt: ${promptName}</div>`
    html += `<div style="font-weight: bold; margin-bottom: 4px; padding-top: 8px;">Values</div>`

    dataKeys.forEach((key) => {
      const label = getKeyLabel(key)
      const rawValue = config?.id ? getModelValueRaw(config.id, key) : null
      if (rawValue === null) {
        html += `<div>${label}: N/A</div>`
      } else if (isCostMetric(key)) {
        const displayValue = costToScore(rawValue, allCosts)
        html += `<div>${label}: ${displayValue.toFixed(1)} <span style="color: #888;">(Mean Cost: $${rawValue.toFixed(6)})</span></div>`
      } else {
        html += `<div>${label}: ${rawValue.toFixed(3)}</div>`
      }
    })

    return html
  }

  function generateChartData(): {
    indicators: { name: string; max: number }[]
    series: { value: number[]; name: string }[]
    legend: string[]
    allCosts: number[]
  } {
    const indicators: { name: string; max: number }[] = []
    const series: { value: number[]; name: string }[] = []
    const legend: string[] = []
    const allCosts: number[] = []

    if (dataKeys.length === 0 || selectedRunConfigIds.length === 0) {
      return { indicators, series, legend, allCosts }
    }

    // Calculate max values for each data key across all selected run configs
    const maxValues: Record<string, number> = {}

    for (const key of dataKeys) {
      let max = 0
      for (const configId of selectedRunConfigIds) {
        const value = getModelValueRaw(configId, key)
        if (value !== null && value > max) {
          max = value
        }
        if (value !== null && isCostMetric(key)) {
          allCosts.push(value)
        }
      }
      // Add 10% padding to max for better visualization
      maxValues[key] = max > 0 ? max * 1.1 : 1
    }

    // Build indicators with actual max values (except cost which uses 0-100 scale)
    for (const key of dataKeys) {
      indicators.push({
        name: getKeyLabel(key),
        max: isCostMetric(key) ? 100 : maxValues[key],
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
        } else if (isCostMetric(key)) {
          displayValue = costToScore(rawValue, allCosts)
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

    return { indicators, series, legend, allCosts }
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

    const { indicators, series, legend, allCosts } = generateChartData()

    const legendFormatter = buildLegendFormatter()

    chartInstance.setOption(
      {
        tooltip: {
          trigger: "item",
          formatter: (params: { name: string }) =>
            buildRunConfigTooltip(params.name, allCosts),
        },
        legend: {
          data: legend,
          orient: "vertical",
          left: "60%",
          top: "middle",
          itemGap: 16,
          formatter: (name: string) => legendFormatter[name] || name,
          tooltip: {
            show: true,
            formatter: (params: { name: string }) =>
              buildRunConfigTooltip(params.name, allCosts),
          },
          textStyle: {
            lineHeight: 16,
            rich: {
              sub: {
                fontSize: 11,
                color: "#666",
                lineHeight: 14,
              },
            },
          },
        },
        radar: {
          indicator: indicators,
          center: ["32%", "50%"],
          radius: "85%",
          axisName: {
            color: "#666",
            fontSize: 12,
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
          },
        ],
      },
      true,
    )
  }

  // Update chart when data changes (model_info and prompts may load async)
  $: if (
    chartInstance &&
    comparisonFeatures &&
    selectedRunConfigIds &&
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
    <div class="text-xl font-bold">Radar Chart</div>
    <div class="text-sm text-gray-500 mb-4">
      Compare the evaluation scores of the run configurations selected above.
    </div>
    {#if hasData}
      <div use:initChart class="w-full flex-1 min-h-[400px]"></div>
    {:else}
      <ChartNoData />
    {/if}
  </div>
{/if}
