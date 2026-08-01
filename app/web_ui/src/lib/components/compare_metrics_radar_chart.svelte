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
    metric_family_bands,
    fit_radar,
    MIN_METRIC_AXES,
    type MetricAxis,
    type RadarAxisLabel,
    type RadarFit,
  } from "$lib/utils/evolution/metric_axes"
  import {
    family_band_arc,
    type FamilyBand,
  } from "$lib/utils/evolution/family_bands"
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

Related axes sit together: reading **clockwise from the top** the ring goes cost, tokens, calls, speed, responsiveness, and the arcs just outside it mark where each family ends. Switching axes off in the Axes menu keeps the grouping.

Because it is a comparison, at least two run configs are needed. Raw values are in the tooltip and in the table below.`

  const AXIS_MAX = 100
  const LABEL_COLOR = "#666"

  // The chain reads clockwise from the top. echarts lays indicators out
  // counterclockwise by default, which drew the families cost -> responsiveness
  // backwards; `clockwise` on the radar fixes the picture without reversing the
  // list everything else - the axis picker, the tooltips, the key below the
  // title - reads in order. See METRIC_FAMILIES.
  const RADAR_START_ANGLE = 90

  // The family band: a thin arc outside the ring, broken at each boundary.
  //
  // Sixteen labels in one weight of grey read as an undifferentiated ring even
  // though the families behind them are contiguous, so the grouping needs to be
  // a property of the image rather than of the data. The band is drawn OUTSIDE
  // the plot on purpose: the run configs are the subject of this chart, and an
  // arc swept under them would sit beneath every polygon and change what the
  // series look like from one sector to the next.
  //
  // It is neutral for the same reason. A family hue per arc is the obvious
  // move and it does not survive contact with the constraint: to be told apart
  // from each other five hues have to be about as saturated as the series
  // themselves, and then the chart has two colour systems competing for the
  // eye. Muting them far enough to recede takes them below the point where they
  // are distinguishable at all - five pastels measure a worst pair of ~5 in
  // OKLab dE where ~15 is the floor for telling two colours apart, so the
  // colour would be decoration that looks like meaning. What a reader actually
  // needed was the boundary; the axis names already say which family they are
  // ("Tool Call Economy", "LLM Call Economy") and the key under the title names
  // the runs in order with their counts. So: no new colour at all, one neutral,
  // and the GAPS carry the boundary.
  //
  // Alternating two neutrals was tried and dropped. Five families is odd, so the
  // first and last arc came out the same tone on either side of twelve o'clock
  // and read as one arc oddly broken; and two tones over five groups says
  // "two kinds of family", which is not a thing. A single tone with a gap wide
  // enough to see says exactly what is true and nothing more.
  const BAND_RING_GAP = 6
  const BAND_THICKNESS = 5
  const BAND_LABEL_GAP = 6
  // Read as the boundary, so it is generous; clamped per band by family_band_arc
  const BAND_ARC_GAP = 16
  const BAND_TONE = "#aeb4bf"

  // Axis names, for solving the radius. Measured rather than estimated: a name
  // is anchored at its axis tip and laid AWAY from the centre, so its whole
  // width counts against the side of the card it points at, and a character
  // count generous enough to be safe would cost real radius on every axis. The
  // per-character fallback is for a context that cannot measure text (jsdom);
  // it only has to be conservative, since nothing is drawn there anyway.
  const AXIS_LABEL_FONT_SIZE = 11
  const AXIS_LABEL_LINE_HEIGHT = 14
  const AXIS_LABEL_FONT = `${AXIS_LABEL_FONT_SIZE}px InterVariable, Inter, system-ui, sans-serif`
  const AXIS_LABEL_CHAR_WIDTH = 6.6
  const CHART_PAD = 4

  // The bottom legend, which the ring has to sit above: one line for the run
  // config's name plus one per line of subtext, at the line heights set below.
  const LEGEND_NAME_LINE_HEIGHT = 16
  const LEGEND_SUB_LINE_HEIGHT = 14
  const LEGEND_PADDING = 10

  let chartInstance: echarts.ECharts | null = null
  // The drawing box, tracked because the radius is solved from it rather than
  // left to echarts' percentage of min(width, height)
  let boxWidth = 0
  let boxHeight = 0

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

  // The family runs as they will actually be drawn. Derived from the plotted
  // axes rather than the selected ones, so an axis switched off in the Axes
  // menu - or dropped for having no number on every config - takes its share of
  // the arc with it, and a family emptied that way leaves neither an orphaned
  // arc nor a name in the key. See metric_family_bands for the single-family
  // case, where there is no boundary to draw and the band is silent.
  $: familyBands = metric_family_bands(plottedAxes)

  $: enoughConfigs = plottedConfigs.length >= MIN_METRIC_CONFIGS
  $: hasData = enoughConfigs && plottedAxes.length >= MIN_METRIC_AXES
  // No chart, or only one family, means no arcs - and a key to arcs that are
  // not there would be worse than no key at all.
  $: showFamilyKey = hasData && familyBands.length > 0

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

  // One canvas for the life of the component: measuring text needs a 2d context
  // and creating one per redraw is pure waste.
  let textMeasurer: CanvasRenderingContext2D | null | undefined

  function measureTextWidth(text: string): number {
    if (textMeasurer === undefined) {
      textMeasurer = document.createElement("canvas").getContext("2d")
      if (textMeasurer) textMeasurer.font = AXIS_LABEL_FONT
    }
    if (!textMeasurer) return text.length * AXIS_LABEL_CHAR_WIDTH
    return textMeasurer.measureText(text).width
  }

  // Every axis name as a box at the angle echarts will draw it. The angles have
  // to be derived the same way the radar does it - from the start angle,
  // clockwise, one slot per axis - because that is what decides which side of
  // the chart each name is laid out towards.
  function axisLabels(names: string[]): RadarAxisLabel[] {
    const step = (Math.PI * 2) / Math.max(names.length, 1)
    const start = (RADAR_START_ANGLE * Math.PI) / 180
    return names.map((name, index) => {
      const lines = name.split("\n")
      return {
        angle: start - index * step,
        width: Math.max(...lines.map(measureTextWidth)),
        height: lines.length * AXIS_LABEL_LINE_HEIGHT,
      }
    })
  }

  // What the bottom legend will occupy, from the subtext it is actually going
  // to carry - an MCP config prints one line under its name, a model-and-prompt
  // config three - so the ring is never held off by room nothing will use.
  function legendHeight(): number {
    let subLines = 0
    for (const config of plottedConfigs) {
      subLines = Math.max(
        subLines,
        buildLegendSubtext(config).split("\n").length,
      )
    }
    return (
      LEGEND_PADDING +
      LEGEND_NAME_LINE_HEIGHT +
      subLines * LEGEND_SUB_LINE_HEIGHT
    )
  }

  // The band lives between the ring and the axis names, so from the radius
  // solver's point of view it is part of the gap the names are held off by.
  const AXIS_NAME_GAP = BAND_RING_GAP + BAND_THICKNESS + BAND_LABEL_GAP

  function radarLayout(names: string[]): RadarFit {
    return fit_radar(
      { width: boxWidth, height: boxHeight },
      axisLabels(names),
      {
        legendHeight: legendHeight(),
        labelGap: AXIS_NAME_GAP,
        pad: CHART_PAD,
      },
    )
  }

  // One arc per family run, drawn as a graphic rather than by the radar: echarts
  // splits a radar's background into rings, never into sectors, and a ring is
  // the one division this chart does not need.
  function bandGraphics(
    bands: FamilyBand[],
    axisCount: number,
    layout: RadarFit,
  ) {
    const inner = layout.radius + BAND_RING_GAP
    const outer = inner + BAND_THICKNESS
    return bands.map((band) => {
      const arc = family_band_arc(band, axisCount, {
        startAngleDegrees: RADAR_START_ANGLE,
        // A gap in px, as an angle at the radius it is drawn at, so the boundary
        // looks the same width whatever the card size
        gapRadians: BAND_ARC_GAP / outer,
      })
      return {
        type: "sector",
        // Inert. The tooltip works out which axis is under the cursor from the
        // pointer, and anything that could become the event target first would
        // break that - see axisIndexFromPointer.
        silent: true,
        z: 0,
        shape: {
          cx: layout.cx,
          cy: layout.cy,
          r0: inner,
          r: outer,
          startAngle: arc.startAngle,
          endAngle: arc.endAngle,
          clockwise: true,
          cornerRadius: BAND_THICKNESS / 2,
        },
        style: {
          fill: BAND_TONE,
        },
      }
    })
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
    // The radius is solved from the box, so there is nothing to draw until the
    // box has been measured. The ResizeObserver fires on observe, so this only
    // skips the render before the first frame.
    if (boxWidth <= 0 || boxHeight <= 0) return

    const { indicators, series, legend, chartAxes } = generateChartData()
    const layout = radarLayout(indicators.map((indicator) => indicator.name))

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
        graphic: bandGraphics(familyBands, chartAxes.length, layout),
        radar: {
          indicator: indicators,
          // Solved rather than a percentage of min(width, height): this card is
          // much taller than it is wide, so a percentage resolved against the
          // width and left a small ring adrift in a tall card. See fit_radar.
          center: [layout.cx, layout.cy],
          radius: layout.radius,
          startAngle: RADAR_START_ANGLE,
          // Families read cost -> tokens -> calls -> speed -> responsiveness
          // going clockwise, the direction a ring is read. Without this echarts
          // walks the indicators the other way and draws the chain backwards.
          clockwise: true,
          axisNameGap: AXIS_NAME_GAP,
          axisName: {
            color: LABEL_COLOR,
            fontSize: 11,
            // Names arrive pre-wrapped from wrap_axis_label: echarts' own
            // width/overflow wrapping does not reach radar axis names, and an
            // unwrapped one runs off the side of a half-width card. The axis
            // count is capped by the page's default set, so unlike the
            // eval-score radar this never needs hand-placed labels.
            lineHeight: AXIS_LABEL_LINE_HEIGHT,
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
    familyBands,
    plottedConfigs,
    selectedRunConfigIds,
    getMetricValue,
    model_info,
    prompts,
    // The radius and the band are solved from the box, so a resize is a redraw
    // and not just an echarts resize()
    boxWidth,
    boxHeight,
  )
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  function redraw(..._dependencies: unknown[]) {
    updateChart()
  }

  function initChart(node: HTMLElement) {
    chartInstance = echarts.init(node)
    // Measured up front as well as from the observer, whose first callback is a
    // frame away - otherwise the first paint is an empty chart.
    boxWidth = node.clientWidth
    boxHeight = node.clientHeight

    // Resizing the canvas is not enough on its own: centre, radius and the
    // family arcs are all in px, solved from the box, so the new size has to
    // reach the reactive statement that redraws them.
    const resizeObserver = new ResizeObserver(() => {
      chartInstance?.resize()
      boxWidth = node.clientWidth
      boxHeight = node.clientHeight
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
      <div
        class="text-sm text-gray-500 {shownNote || showFamilyKey ? '' : 'mb-4'}"
      >
        Cost, speed and usage for the selected run configurations. Higher is
        better on every axis.
      </div>
      {#if shownNote}
        <div class="text-xs text-gray-400 mt-1 {showFamilyKey ? '' : 'mb-4'}">
          {shownNote}
        </div>
      {/if}
      {#if showFamilyKey}
        <!-- The arcs show WHERE the families divide; this says WHICH they are.
             Order and count are the whole mapping - the first arc clockwise
             from twelve o'clock covers the first name here, over as many axes
             as it claims - so no swatch is needed and, more to the point, no
             colour: a per-family hue would be a second colour system arguing
             with the series. Both this and the arcs are built from the same
             runs, so an axis switched off cannot leave a name without an arc. -->
        <div class="flex flex-wrap items-center gap-x-3 gap-y-1 mt-2 mb-4">
          <span class="text-xs text-gray-400">
            Axis families, clockwise from the top:
          </span>
          {#each familyBands as band}
            <span class="text-xs text-gray-500">
              {band.label}
              <span class="text-gray-400">{band.count}</span>
            </span>
          {/each}
        </div>
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
