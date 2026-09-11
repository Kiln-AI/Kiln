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
  import { escapeHtml } from "$lib/utils/escape_html"
  import { formatLatency } from "$lib/utils/formatters"
  import {
    COST_KEY,
    LATENCY_KEY,
    TOTAL_TOKENS_KEY,
  } from "$lib/utils/compare_metric_keys"
  import {
    buildRadarChartData,
    plottedRunConfigs,
    rankTooltipScores,
    MIN_RADAR_AXES,
  } from "$lib/utils/radar_chart_data"
  import type {
    ComparisonFeature,
    RadarChartData,
  } from "$lib/utils/radar_chart_data"
  import ChartNoData from "$lib/components/chart_no_data.svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"

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
  // Display names the user has given rows in the table, by key. They win over the
  // usage axis names too, so a renamed cost row is renamed on its axis.
  export let metricLabels: Record<string, string> = {}

  // Axis scaling mode. Relative scales each axis to the best value across the selected
  // run configs, which is the better lens for spotting differences between configs.
  // Full scale uses the score's own range, which is the only readable option when
  // there's nothing to compare against. Default follows the selection until the user
  // picks a mode, after which their choice sticks.
  let absoluteScale = false
  let userChoseScale = false

  const SCALE_TOOLTIP = `**Relative**: each axis is scaled to the highest value across the selected run configs. Best for spotting differences between configs.

**Full Scale**: each axis uses the score's own range (0-1 for pass/fail, 1-5 for 5-star). Best when looking at one run config on its own, where there is nothing to compare against.

Cost, latency and token axes score each run config against the others, so they stay relative in both modes. With a single run config there's nothing to compare against and they all sit at the midpoint. Hide one with the x on its row in the table above.`

  // Chart instance
  let chartInstance: echarts.ECharts | null = null

  // Held apart from chartData rather than read back out of it: the scale default
  // below depends on how many configs are plotted, and chartData depends on the
  // scale. One source, two readers, no cycle.
  $: plottedConfigs = plottedRunConfigs({
    comparisonFeatures,
    runConfigs: run_configs,
    selectedRunConfigIds,
    getValue: getModelValueRaw,
  })

  $: if (!userChoseScale) {
    absoluteScale = plottedConfigs.length <= 1
  }

  $: chartData = buildRadarChartData({
    comparisonFeatures,
    plottedConfigs,
    selectedRunConfigIds,
    getValue: getModelValueRaw,
    modelInfo: model_info,
    scoreAxisMaxes,
    metricLabels,
    absoluteScale,
  })

  $: omittedAxisCount = chartData.omittedKeyCount

  $: notShownNote =
    omittedAxisCount > 0
      ? `Not shown: ${omittedAxisCount} ${
          omittedAxisCount === 1 ? "score" : "scores"
        } without results for every selected run config. See the table above.`
      : null

  // When there's nothing to draw, say which of the two reasons it is
  $: noDataMessage =
    omittedAxisCount > 0
      ? `The selected run configurations share fewer than ${MIN_RADAR_AXES} scores with results. Run the missing evals, or compare fewer run configurations.`
      : "Create and run evals to see a comparison chart."

  function setScale(useAbsolute: boolean) {
    absoluteScale = useAbsolute
    userChoseScale = true
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
    const meanTotalTokens = raw(TOTAL_TOKENS_KEY)
    return {
      cost: meanCost === null ? null : formatUsageValue(COST_KEY, meanCost),
      latency:
        meanLatency === null
          ? null
          : formatUsageValue(LATENCY_KEY, meanLatency),
      totalTokens:
        meanTotalTokens === null
          ? null
          : formatUsageValue(TOTAL_TOKENS_KEY, meanTotalTokens),
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

  function buildLegendFormatter(data: RadarChartData): Record<string, string> {
    const formatter: Record<string, string> = {}
    for (const [name, config] of Object.entries(data.configsBySeriesName)) {
      formatter[name] = `${name}\n${buildLegendSubtext(config)}`
    }
    return formatter
  }

  // Build full tooltip HTML for a run config (reused by chart tooltip and legend tooltip)
  function buildRunConfigTooltip(name: string, data: RadarChartData): string {
    const config = data.configsBySeriesName[name]

    let html = `<div style="font-weight: bold; margin-bottom: 4px;">${escapeHtml(
      name,
    )}</div>`
    if (config && isMcpRunConfig(config.run_config_properties)) {
      const toolName =
        config.run_config_properties.tool_reference.tool_name ?? "MCP Tool"
      html += `<div>MCP Tool: ${escapeHtml(toolName)}</div>`
    } else {
      const modelName = config
        ? getRunConfigModelDisplayName(config, model_info) || "Unknown"
        : "Unknown"
      const promptName = config
        ? getRunConfigPromptDisplayName(config, prompts)
        : null
      html += `<div>Model: ${escapeHtml(modelName)}</div>`
      if (promptName) {
        html += `<div>Prompt: ${escapeHtml(promptName)}</div>`
      }
      if (config) {
        const transformLabel = getRunConfigInputTransformSummaryLabel(config)
        if (transformLabel) {
          html += `<div>Input Transform: ${escapeHtml(transformLabel)}</div>`
        }
      }
    }

    const usage = getUsageSummary(config)
    if (usage.cost) html += `<div>Mean Cost: ${usage.cost}</div>`
    if (usage.latency) html += `<div>Mean Latency: ${usage.latency}</div>`
    if (usage.totalTokens) {
      html += `<div>Mean Total Tokens: ${usage.totalTokens}</div>`
    }

    const { scores, trimmedCount } = rankTooltipScores({
      keys: data.keys,
      axisMaxes: data.axisMaxes,
      axisLabels: data.axisLabels,
      getValue: (key) => (config?.id ? getModelValueRaw(config.id, key) : null),
    })

    html += `<div style="font-weight: bold; margin-bottom: 4px; padding-top: 8px;">${
      trimmedCount > 0 ? "Lowest Scores" : "Values"
    }</div>`
    for (const score of scores) {
      const formatted = score.value === null ? "N/A" : score.value.toFixed(3)
      html += `<div>${escapeHtml(score.label)}: ${formatted}</div>`
    }
    if (trimmedCount > 0) {
      html += `<div style="color: #888; padding-top: 4px;">+${trimmedCount} more in the table above</div>`
    }

    return html
  }

  function updateChart() {
    if (!chartInstance) return

    if (!chartData.hasData) {
      chartInstance.clear()
      return
    }

    const data = chartData
    const legendFormatter = buildLegendFormatter(data)

    // A couple of configs don't need a legend column - centering the radar and
    // dropping the legend underneath buys a much larger plot.
    const compactLayout = data.series.length <= 2

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
            buildRunConfigTooltip(params.name, data),
        },
        legend: {
          data: data.legend,
          formatter: (name: string) => legendFormatter[name] || name,
          tooltip: {
            show: true,
            formatter: (params: { name: string }) =>
              buildRunConfigTooltip(params.name, data),
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
          indicator: data.indicators,
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
            data: data.series,
            lineStyle: {
              width: 2,
            },
            symbolSize: 6,
            // Filling one shape makes it readable. Filling several makes mud.
            ...(data.series.length === 1
              ? { areaStyle: { opacity: 0.2 } }
              : {}),
          },
        ],
      },
      true,
    )
  }

  // Redraw whenever the data changes. prompts reaches the chart only through the
  // legend and tooltip text, so it is named here to make it a dependency too.
  $: if (chartInstance && chartData && (prompts || prompts === null)) {
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

<!-- Radar charts don't really work with <3 items. Counts the usage axes too: they
     are axes like any other, and a task with one or two eval scores still has a
     chart worth drawing once cost, latency and tokens are on it. -->
{#if chartData.candidateAxisCount >= MIN_RADAR_AXES}
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
    {#if chartData.hasData}
      <div
        use:initChart
        class="w-full flex-1 min-h-[500px] xl:min-h-[620px]"
      ></div>
    {:else}
      <ChartNoData
        title={omittedAxisCount > 0
          ? "Not Enough Shared Scores"
          : "No Data Available"}
        message={noDataMessage}
      />
    {/if}
  </div>
{/if}
