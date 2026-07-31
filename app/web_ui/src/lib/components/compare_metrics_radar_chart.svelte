<script lang="ts">
  // The performance-metrics radar: cost, latency, token usage and call counts,
  // as a sibling to the eval-score radar rather than more axes on it.
  //
  // Splitting them is not just tidiness. The two charts answer different
  // questions ("is it right" vs "what did it cost") and, more importantly, they
  // are scaled differently and cannot honestly share a ring:
  //
  //   - an eval score has its own range (0-1 for pass/fail, 1-5 for five star)
  //     and higher is better, so it can be plotted against an absolute scale.
  //   - a metric has no range at all - there is no maximum cost - so the only
  //     meaningful scale is position among the configs on the chart. See
  //     relative_metric_score.
  //
  // One grammar, and it is carried by the labels rather than by a caption:
  // every axis is named for the virtue it measures ("Cost Efficiency", not
  // "Cost"; "Skill Read Efficiency", not "Skill Reads Repeat"), so further from
  // the centre reads as better on a glance instead of needing the reader to
  // remember that this chart is inverted. Which end of a raw scale is the good
  // one lives on the axis itself, since it is not always the low end - cache
  // reuse is better the more of it there is. See $lib/utils/evolution/
  // metric_axes for the naming, the families and the direction of each metric.
  //
  // Because the scale is a comparison, one run config has nothing to be scored
  // against - it would sit at the midpoint on every axis and draw a regular
  // polygon that looks like a result but is an artefact. That case is refused
  // explicitly below rather than rendered.

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
  import { relative_metric_score } from "$lib/utils/relative_metric_score"
  import {
    format_metric_value,
    wrap_axis_label,
    MIN_METRIC_AXES,
    type MetricAxis,
  } from "$lib/utils/evolution/metric_axes"
  import ChartNoData from "$lib/components/chart_no_data.svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"

  // The axes to plot, already narrowed to the user's selection by the page
  export let axes: MetricAxis[] = []
  // Raw value of a metric for a run config, in its own units. Null when the
  // config has no number for it.
  export let getMetricValue: (runConfigId: string, key: string) => number | null
  export let run_configs: TaskRunConfig[] = []
  export let model_info: ProviderModels | null = null
  export let prompts: PromptResponse | null = null
  export let selectedRunConfigIds: string[] = []
  // Rendered under the subtitle - what the page left off and why
  export let notShownNote: string | null = null

  // A comparison needs two sides
  const MIN_METRIC_CONFIGS = 2

  const SCALE_TOOLTIP = `Each axis is named for the quality it measures, so further from the centre is better on every one of them - cheaper, faster, leaner, more cache reuse.

Scores are **relative to the other run configs on the chart**, on a shared 0-100 scale: unlike a pass rate, cost and latency have no maximum to plot against, so there is no "full scale" mode here.

Because it is a comparison, at least two run configs are needed. Raw values are in the tooltip and in the table below.`

  const AXIS_MAX = 100
  const LABEL_COLOR = "#666"

  let chartInstance: echarts.ECharts | null = null

  // Which axis the pointer is nearest. echarts' radar tooltip is per-series -
  // its formatter is handed a series, not an indicator - so the hovered axis
  // has to be worked out from the pointer. Same approach, and same guards, as
  // compare_radar_chart.
  let hoveredAxisIndex: number | null = null

  type RadarCoordSys = {
    cx: number
    cy: number
    getIndicatorAxes: () => { angle: number }[]
  }

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
    const axisList = coordSys.getIndicatorAxes()
    if (!axisList?.length) return null

    // Same convention as the radar's dataToPoint: y grows downward, angles don't
    const pointerAngle = Math.atan2(
      coordSys.cy - event.offsetY,
      event.offsetX - coordSys.cx,
    )
    let best = 0
    let bestDelta = Infinity
    axisList.forEach((axis, index) => {
      let delta = Math.abs(pointerAngle - axis.angle) % (Math.PI * 2)
      if (delta > Math.PI) delta = Math.PI * 2 - delta
      if (delta < bestDelta) {
        bestDelta = delta
        best = index
      }
    })
    return best
  }

  function getSeriesDisplayName(config: TaskRunConfig): string {
    if (config.name) return config.name
    if (isMcpRunConfig(config.run_config_properties)) {
      return config.run_config_properties.tool_reference.tool_name ?? "MCP Tool"
    }
    return getRunConfigModelDisplayName(config, model_info) ?? "Unknown"
  }

  // Run configs that will actually be drawn: selected, resolvable, and with at
  // least one metric to their name. A config with nothing to plot must not count
  // towards the two needed to make a comparison.
  $: plottedConfigs = selectedRunConfigIds
    .map((configId) => run_configs.find((config) => config.id === configId))
    .filter((config): config is TaskRunConfig => !!config?.id)
    .filter((config) =>
      axes.some(
        (axis) => getMetricValue(config.id as string, axis.key) !== null,
      ),
    )

  // Only axes every plotted config has a value for. echarts draws a missing
  // radar value at the centre of the chart, which is indistinguishable from
  // scoring worst on that axis - so an axis one config has no number for cannot
  // be drawn honestly at all. It is left out and counted under the title.
  $: plottedAxes = axes.filter((axis) =>
    plottedConfigs.every(
      (config) => getMetricValue(config.id as string, axis.key) !== null,
    ),
  )
  $: incompleteAxisCount = axes.length - plottedAxes.length

  $: enoughConfigs = plottedConfigs.length >= MIN_METRIC_CONFIGS
  $: hasData = enoughConfigs && plottedAxes.length >= MIN_METRIC_AXES

  $: noDataTitle = !enoughConfigs
    ? "Nothing to Compare Against"
    : "Not Enough Shared Metrics"
  $: noDataMessage = !enoughConfigs
    ? plottedConfigs.length === 0
      ? "Select run configs with results to compare their cost, speed and usage."
      : "These metrics are scored against the other run configs on the chart, so at least two are needed. Add another run config to compare."
    : incompleteAxisCount > 0
      ? `The selected run configs share fewer than ${MIN_METRIC_AXES} metrics with results. Add more metric axes, or compare run configs that have all been run.`
      : `A metrics radar needs at least ${MIN_METRIC_AXES} axes. Turn more on with the Axes menu.`

  $: shownNote = (() => {
    const parts: string[] = []
    if (incompleteAxisCount > 0) {
      parts.push(
        `${incompleteAxisCount} ${
          incompleteAxisCount === 1 ? "metric" : "metrics"
        } without results for every selected run config`,
      )
    }
    if (notShownNote) parts.push(notShownNote)
    if (parts.length === 0) return null
    return `Not shown: ${parts.join(", ")}. See the table below.`
  })()

  function seriesColorAt(index: number): string {
    const palette = chartInstance?.getOption()?.color as string[] | undefined
    if (!palette?.length) return "#888"
    return palette[index % palette.length]
  }

  function tooltipMarker(color: string): string {
    return `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${color};margin-right:6px;"></span>`
  }

  // The axis is labelled with the virtue, so the tooltip is where the raw
  // quantity behind it is spelled out - "Cost Efficiency" over "Cost · usage
  // rollup" - along with where the number came from.
  function axisSubtitle(axis: MetricAxis): string {
    return `${axis.valueLabel} · ${axis.evalName ?? "usage rollup"}`
  }

  // One metric across every plotted config, so hovering a point answers "how do
  // they compare here" rather than reciting everything this config used. The
  // relative score is what the ring shows, so the raw quantity comes with it -
  // the score alone is unreadable as a cost.
  function buildAxisTooltip(
    axisIndex: number,
    chartAxes: MetricAxis[],
    series: { value: number[]; name: string }[],
    hoveredName: string,
  ): string {
    const axis = chartAxes[axisIndex]
    if (!axis) return ""

    let html = `<div style="font-weight: bold;">${axis.label}</div>
      <div style="color: #888; margin-bottom: 6px;">${axisSubtitle(axis)}</div>`
    series.forEach((entry, index) => {
      const config = run_configs.find(
        (candidate) => getSeriesDisplayName(candidate) === entry.name,
      )
      const rawValue = config?.id ? getMetricValue(config.id, axis.key) : null
      const score = entry.value[axisIndex]
      const shown =
        rawValue === null || score === undefined
          ? "N/A"
          : `${score.toFixed(1)} <span style="color: #888;">(${format_metric_value(
              axis.unit,
              rawValue,
            )})</span>`
      const weight = entry.name === hoveredName ? "600" : "400"
      html += `<div style="font-weight: ${weight};">${tooltipMarker(
        seriesColorAt(index),
      )}${entry.name}: ${shown}</div>`
    })
    return html
  }

  // The legend keeps the whole-config summary: what it is, and its raw numbers.
  function buildRunConfigTooltip(
    name: string,
    chartAxes: MetricAxis[],
  ): string {
    const config = run_configs.find(
      (candidate) => getSeriesDisplayName(candidate) === name,
    )

    let html = `<div style="font-weight: bold; margin-bottom: 4px;">${name}</div>`
    if (config && isMcpRunConfig(config.run_config_properties)) {
      const toolName =
        config.run_config_properties.tool_reference.tool_name ?? "MCP Tool"
      html += `<div>MCP Tool: ${toolName}</div>`
    } else {
      const modelName = config
        ? getRunConfigModelDisplayName(config, model_info) || "Unknown"
        : "Unknown"
      html += `<div>Model: ${modelName}</div>`
      const promptName = config
        ? getRunConfigPromptDisplayName(config, prompts)
        : null
      if (promptName) html += `<div>Prompt: ${promptName}</div>`
      if (config) {
        const transformLabel = getRunConfigInputTransformSummaryLabel(config)
        if (transformLabel) {
          html += `<div>Input Transform: ${transformLabel}</div>`
        }
      }
    }

    html += `<div style="font-weight: bold; margin-bottom: 4px; padding-top: 8px;">Values</div>`
    for (const axis of chartAxes) {
      const rawValue = config?.id ? getMetricValue(config.id, axis.key) : null
      // The raw quantity's own name, not the axis label: "Cost: $0.0123", not
      // "Cost Efficiency: $0.0123", which would read as a score.
      html += `<div>${axis.valueLabel}: ${format_metric_value(
        axis.unit,
        rawValue,
      )}</div>`
    }
    return html
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

  function generateChartData(): {
    indicators: { name: string; max: number }[]
    series: { value: number[]; name: string }[]
    legend: string[]
    chartAxes: MetricAxis[]
  } {
    const chartAxes = plottedAxes
    const indicators = chartAxes.map((axis) => ({
      name: wrap_axis_label(axis.label),
      max: AXIS_MAX,
    }))

    // Every value on an axis, so each config can be scored by its position
    // among them. Direction correction lives in relative_metric_score, pointed
    // by the axis: the best raw value gets the highest score, which is what
    // puts the cheapest and fastest config furthest from the centre.
    const valuesByAxis = new Map<string, number[]>()
    for (const axis of chartAxes) {
      valuesByAxis.set(
        axis.key,
        plottedConfigs
          .map((config) => getMetricValue(config.id as string, axis.key))
          .filter((value): value is number => value !== null),
      )
    }

    const series: { value: number[]; name: string }[] = []
    const legend: string[] = []
    for (const config of plottedConfigs) {
      // Every plotted config has a value for every plotted axis by construction
      const value = chartAxes.map((axis) =>
        relative_metric_score(
          getMetricValue(config.id as string, axis.key) as number,
          valuesByAxis.get(axis.key) ?? [],
          { higherIsBetter: axis.better === "higher" },
        ),
      )
      const name = getSeriesDisplayName(config)
      legend.push(name)
      series.push({ value, name })
    }

    return { indicators, series, legend, chartAxes }
  }

  function updateChart() {
    if (!chartInstance) return
    if (!hasData) {
      chartInstance.clear()
      return
    }

    const { indicators, series, legend, chartAxes } = generateChartData()

    const legendFormatter: Record<string, string> = {}
    for (const config of plottedConfigs) {
      const displayName = getSeriesDisplayName(config)
      legendFormatter[displayName] =
        `${displayName}\n${buildLegendSubtext(config)}`
    }

    chartInstance.setOption(
      {
        tooltip: {
          trigger: "item",
          confine: true,
          formatter: (params: { name: string }) => {
            if (
              hoveredAxisIndex !== null &&
              hoveredAxisIndex >= 0 &&
              hoveredAxisIndex < chartAxes.length
            ) {
              return buildAxisTooltip(
                hoveredAxisIndex,
                chartAxes,
                series,
                params.name,
              )
            }
            return buildRunConfigTooltip(params.name, chartAxes)
          },
        },
        legend: {
          data: legend,
          // Clicking a legend entry hides/shows that run config's polygon -
          // with several overlapping shapes, isolating one is the only way to
          // read the chart. Same behaviour as the eval-score radar.
          selectedMode: true,
          formatter: (name: string) => legendFormatter[name] || name,
          tooltip: {
            show: true,
            formatter: (params: { name: string }) =>
              buildRunConfigTooltip(params.name, chartAxes),
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
          orient: "horizontal" as const,
          bottom: 0,
          left: "center" as const,
          itemGap: 24,
          // This chart sits in a column beside the eval-score radar, so a
          // wrapping legend would eat the plot. Scroll keeps it to one row.
          type: "scroll" as const,
        },
        radar: {
          indicator: indicators,
          center: ["50%", "44%"],
          radius: "58%",
          axisName: {
            color: LABEL_COLOR,
            fontSize: 11,
            // Names arrive pre-wrapped from wrap_axis_label: echarts' own
            // width/overflow wrapping does not reach radar axis names, and an
            // unwrapped one runs off the side of a half-width card. The axis
            // count is capped by the page's default set, so unlike the
            // eval-score radar this never needs hand-placed labels.
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
            name: "Performance Metrics",
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

  // Redraw when anything that changes the picture changes. Every input has to
  // be referenced here, or the chart keeps showing the previous render.
  // getMetricValue is passed through rather than tested: it is always defined,
  // so a truthiness check would be meaningless, but referencing it is what
  // makes a rebuilt getter (the page rebuilds one when lazily fetched usage
  // arrives) count as a dependency.
  $: redraw(
    chartInstance,
    axes,
    plottedAxes,
    plottedConfigs,
    selectedRunConfigIds,
    getMetricValue,
    model_info,
    prompts,
  )
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  function redraw(..._dependencies: unknown[]) {
    updateChart()
  }

  function initChart(node: HTMLElement) {
    chartInstance = echarts.init(node)

    const resizeObserver = new ResizeObserver(() => {
      chartInstance?.resize()
    })
    resizeObserver.observe(node)

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

<div
  class="bg-white border border-gray-200 rounded-lg p-6 h-full flex flex-col"
>
  <div class="flex flex-row gap-4 items-start">
    <div class="flex-grow">
      <div class="text-xl font-bold">Performance Metrics</div>
      <div class="text-sm text-gray-500 {shownNote ? '' : 'mb-4'}">
        Cost, speed and usage for the selected run configurations. Higher is
        better on every axis.
      </div>
      {#if shownNote}
        <div class="text-xs text-gray-400 mt-1 mb-4">{shownNote}</div>
      {/if}
    </div>
    <div class="flex flex-row gap-1 items-center flex-shrink-0">
      <!-- The page owns which axes are on, so it supplies the control -->
      <slot name="controls" />
      <InfoTooltip tooltip_text={SCALE_TOOLTIP} position="bottom" />
    </div>
  </div>
  {#if hasData}
    <!-- Matches the eval-score radar's bottom-legend box, so the two charts
         line up when they sit side by side. -->
    <div use:initChart class="w-full flex-1 min-h-[640px]"></div>
  {:else}
    <ChartNoData title={noDataTitle} message={noDataMessage} />
  {/if}
</div>
