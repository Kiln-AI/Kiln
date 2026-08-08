<script lang="ts">
  // The quality scores again, as parallel coordinates with their confidence
  // intervals drawn - the uncertainty view of the radar directly above it.
  //
  // Why this exists beside the radar rather than instead of it. A radar spends
  // its only encoding, position, on the point estimate, so there is nowhere for
  // the interval to go; and an eval mean is an estimate with a wide one. A pass
  // rate of 0.5 over 25 runs carries a 95% interval about 36 points wide -
  // better than a third of the axis - which is enough to make two configs that
  // differ by nothing draw visibly different shapes. The radar is the better
  // glance; this is the chart that says whether the glance means anything.
  //
  // Bands, not error bars, and not line width. Width-as-uncertainty was the
  // first instinct and it is the wrong encoding twice over: thickness is hard
  // to compare across a chart, and a "z-score" belongs to a PAIR of configs,
  // not to one line - a single polygon has no z until you name what it is being
  // compared against. A band is that config's own interval, needs no reference,
  // and answers the question the reader actually has by overlapping: where two
  // bands overlap, those two configs are not distinguishable on that axis.
  //
  // Parallel coordinates rather than a second ring, for the same reason the
  // metrics chart is bars: a radar reads as a shape, and the shape's area is an
  // artefact of axis ORDER as much as of the scores. Columns have no area to
  // over-read and leave vertical room for the bands.
  //
  // Axes can be different score types, so every axis is plotted as a fraction
  // of its own full range - the radar's Full Scale convention, so a config sits
  // at the same height on both charts. Real values are in the tooltip.

  import * as echarts from "echarts"
  import type { TaskRunConfig, ProviderModels } from "$lib/types"
  import { isMcpRunConfig } from "$lib/types"
  import { getRunConfigModelDisplayName } from "$lib/utils/run_config_formatters"
  import {
    build_parallel_rows,
    widest_band_pp,
    type ParallelAxisSpec,
    type ParallelRow,
  } from "$lib/utils/evolution/parallel_bands"
  import { wrap_axis_label } from "$lib/utils/evolution/metric_axes"
  import ChartNoData from "$lib/components/chart_no_data.svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"

  export let axes: ParallelAxisSpec[] = []
  export let getValue: (runConfigId: string, key: string) => number | null
  export let getSampleSize: (runConfigId: string, key: string) => number | null
  export let run_configs: TaskRunConfig[] = []
  // Only for the model-name fallback when a config has no name of its own; the
  // tooltip here is per-axis rather than per-config, so it has no room for the
  // model/prompt block the sibling charts carry.
  export let model_info: ProviderModels | null = null
  export let selectedRunConfigIds: string[] = []

  // Below this there is no comparison to draw - a single config's bands are
  // still true, but the chart's whole job is telling configs apart.
  const MIN_AXES = 2

  let chartInstance: echarts.ECharts | null = null

  // Which configs the reader has left switched on, by series name. Kept here
  // rather than read off the chart because the tooltip needs it, and because
  // the option is rebuilt with notMerge on every redraw - echarts would forget
  // the reader's selection each time the props change.
  let legendSelected: Record<string, boolean> = {}

  function seriesName(config: TaskRunConfig): string {
    if (config.name) return config.name
    if (isMcpRunConfig(config.run_config_properties)) {
      return config.run_config_properties.tool_reference.tool_name ?? "MCP Tool"
    }
    return getRunConfigModelDisplayName(config, model_info) ?? "Unknown"
  }

  $: plottedConfigs = selectedRunConfigIds
    .map((id) => run_configs.find((config) => config.id === id))
    .filter((config): config is TaskRunConfig => !!config?.id)

  $: rows = build_parallel_rows(
    axes,
    plottedConfigs.map((config) => config.id as string),
    getValue,
    getSampleSize,
  )
  $: drawnRows = rows.filter((row) => row.hasData)
  $: hasData = axes.length >= MIN_AXES && drawnRows.length > 0
  $: widestBand = widest_band_pp(rows)

  // Any axis whose score type has no honest interval (see score_intervals):
  // named rather than left as a silently bandless line.
  $: unbandedAxes = axes
    .filter((_axis, axisIndex) =>
      rows.some(
        (row) =>
          row.cells[axisIndex]?.fraction !== null &&
          !row.cells[axisIndex]?.banded,
      ),
    )
    .map((axis) => axis.label)

  $: SCALE_TOOLTIP = `Each line is one run config's scores; the band around it is the **95% confidence interval** for that score, given how many runs it was measured over.

**Where two bands overlap, those configs are not distinguishable on that axis** - the difference you can see is inside what re-running would move on its own.

Every axis is drawn as a share of its own full scale (0-1 for pass/fail, 1-5 for five star), so a config sits at the same height here as on the radar above. Hover a point for the score in its own units, its interval and its sample size.

Intervals need a proportion to be exact, so only pass/fail scores carry a band. Other score types plot their point alone rather than a band that would be wrong.`

  function tooltipMarker(color: string): string {
    return `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${color};margin-right:6px;"></span>`
  }

  function seriesColor(index: number): string {
    const palette = chartInstance?.getOption()?.color as string[] | undefined
    if (!palette?.length) return "#888"
    return palette[index % palette.length]
  }

  function formatScore(value: number | null): string {
    if (value === null) return "—"
    return Number.isInteger(value) ? `${value}` : value.toFixed(2)
  }

  function axisTooltip(axisIndex: number): string {
    const axis = axes[axisIndex]
    if (!axis) return ""
    let html = `<div style="font-weight:bold;margin-bottom:2px;">${axis.label}</div>`
    html += `<div style="color:#888;margin-bottom:6px;">${axis.evalName}</div>`
    drawnRows.forEach((row, rowIndex) => {
      const cell = row.cells[axisIndex]
      if (!cell || cell.fraction === null) return
      const config = plottedConfigs.find((c) => c.id === row.runConfigId)
      const name = config ? seriesName(config) : "Unknown"
      // This formatter builds the tooltip from our own rows rather than from
      // what echarts hands it, so legend state has to be applied by hand -
      // otherwise a config the reader switched off still reports its numbers.
      if (legendSelected[name] === false) return
      const color = seriesColor(rowIndex)
      html += `<div style="margin-top:3px;">${tooltipMarker(color)}${name}: <b>${formatScore(cell.value)}</b>`
      if (cell.banded && cell.lower !== null && cell.upper !== null) {
        // Bounds are fractions of the axis; for pass/fail that is the score's
        // own unit, which is the only banded type today.
        html += ` <span style="color:#888;">[${cell.lower.toFixed(2)}–${cell.upper.toFixed(2)}], n=${cell.n}</span>`
      } else if (cell.n !== null) {
        html += ` <span style="color:#888;">n=${cell.n}, no interval for this score type</span>`
      }
      html += `</div>`
    })
    return html
  }

  function buildSeries(): echarts.SeriesOption[] {
    const series: echarts.SeriesOption[] = []
    drawnRows.forEach((row: ParallelRow, index: number) => {
      const config = plottedConfigs.find((c) => c.id === row.runConfigId)
      const name = config ? seriesName(config) : "Unknown"
      const color = seriesColor(index)

      // All three series share the config's name, which is what ties them to
      // one legend entry: echarts toggles by NAME, so a band named separately
      // from its line stays on screen after the reader switches the config off
      // - four bands under two lines. They are one thing to the reader and have
      // to be one thing to the legend.
      //
      // The estimate goes in FIRST because the legend takes its swatch colour
      // from the first series of that name, and the band series are deliberately
      // colourless outlines. Draw order is set by `z`, not by array order, so
      // the bands still render behind the lines.
      series.push({
        name,
        type: "line",
        symbol: "circle",
        symbolSize: 7,
        lineStyle: { width: 2, color },
        itemStyle: { color, borderColor: "#fff", borderWidth: 1.5 },
        // No focus-blur on hover. It dims every other series, and what it dims
        // here is mostly translucent band - the chart washes out to nearly
        // nothing the moment the pointer crosses the legend. Comparing bands IS
        // the chart, so nothing may fade them. Neither sibling chart blurs
        // either, and the tooltip is axis-wide rather than per series.
        data: row.cells.map((cell) => cell.fraction),
        z: 3,
      })
      // The band is drawn the way echarts draws any band: an invisible series
      // at the lower bound, and the band's own height stacked on top of it.
      // Both are silent so only the estimate line answers the tooltip. Each
      // config gets its own stack group so one config's band cannot pile onto
      // another's.
      series.push({
        name,
        type: "line",
        stack: `band-${index}`,
        silent: true,
        symbol: "none",
        lineStyle: { opacity: 0 },
        itemStyle: { color },
        tooltip: { show: false },
        data: row.cells.map((cell) => cell.lower),
        z: 1,
      })
      series.push({
        name,
        type: "line",
        stack: `band-${index}`,
        silent: true,
        symbol: "none",
        lineStyle: { opacity: 0 },
        areaStyle: { color, opacity: 0.16 },
        itemStyle: { color },
        tooltip: { show: false },
        data: row.cells.map((cell) =>
          cell.upper === null || cell.lower === null
            ? null
            : cell.upper - cell.lower,
        ),
        z: 1,
      })
    })
    return series
  }

  function updateChart() {
    if (!chartInstance || !hasData) return
    const legendNames = drawnRows.map((row) => {
      const config = plottedConfigs.find((c) => c.id === row.runConfigId)
      return config ? seriesName(config) : "Unknown"
    })
    // Drop remembered selections for configs that are no longer plotted, so an
    // unpinned-then-repinned config comes back switched on rather than
    // invisible for a reason nothing on screen explains.
    legendSelected = Object.fromEntries(
      legendNames
        .filter((name) => legendSelected[name] === false)
        .map((name) => [name, false]),
    )

    chartInstance.setOption(
      {
        tooltip: {
          trigger: "axis",
          axisPointer: { type: "line" },
          formatter: (params: unknown) => {
            const list = Array.isArray(params) ? params : [params]
            const first = list[0] as { dataIndex?: number } | undefined
            return axisTooltip(first?.dataIndex ?? 0)
          },
          borderWidth: 0,
          textStyle: { fontSize: 12 },
        },
        legend: {
          data: legendNames,
          selected: legendSelected,
          bottom: 0,
          type: "scroll",
          icon: "roundRect",
          itemWidth: 18,
          itemHeight: 8,
          textStyle: { fontSize: 12, color: "#374151" },
        },
        // The first and last axes sit ON the edges of the plot (boundaryGap
        // false is what makes these parallel axes rather than bar categories),
        // so their labels are centred on the edge and half of each hangs
        // outside. containLabel does not rescue them - it measures the axis as
        // a whole, not a label straddling the end - so the gutters are wide
        // enough for half a wrapped label on either side.
        grid: { left: 96, right: 96, top: 24, bottom: 96, containLabel: true },
        xAxis: {
          type: "category",
          boundaryGap: false,
          data: axes.map((axis) => wrap_axis_label(axis.label)),
          axisLabel: {
            color: "#374151",
            fontSize: 12,
            interval: 0,
            lineHeight: 15,
          },
          axisTick: { show: false },
          axisLine: { lineStyle: { color: "#e5e7eb" } },
          splitLine: { show: true, lineStyle: { color: "#f3f4f6" } },
        },
        yAxis: {
          type: "value",
          min: 0,
          max: 1,
          name: "share of each score's full scale",
          nameLocation: "middle",
          nameGap: 42,
          nameTextStyle: { color: "#9ca3af", fontSize: 11 },
          axisLabel: {
            color: "#9ca3af",
            fontSize: 11,
            formatter: (value: number) => `${Math.round(value * 100)}%`,
          },
          splitLine: { lineStyle: { color: "#f3f4f6" } },
        },
        series: buildSeries(),
      },
      { notMerge: true },
    )
  }

  // Redraw whenever the inputs the option is built from change. Series colours
  // come off the live instance, so this has to run after init as well.
  $: redraw(axes, drawnRows, plottedConfigs, hasData)
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  function redraw(..._dependencies: unknown[]) {
    updateChart()
  }

  function initChart(node: HTMLElement) {
    chartInstance = echarts.init(node)
    // Remember what the reader switched off. echarts hides the series itself;
    // this is for the tooltip, which is built from our rows, and to survive the
    // next redraw.
    chartInstance.on("legendselectchanged", (event: unknown) => {
      const selected = (event as { selected?: Record<string, boolean> })
        ?.selected
      if (selected) legendSelected = { ...selected }
    })
    const resizeObserver = new ResizeObserver(() => chartInstance?.resize())
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

<div class="bg-white border border-gray-200 rounded-lg p-6 flex flex-col">
  <div class="flex flex-row gap-4 items-start">
    <div class="flex-grow">
      <div class="text-xl font-bold">Quality Scores with Confidence</div>
      <div class="text-sm text-gray-500">
        The same scores as the radar, with the range each one could plausibly
        take given how many runs it was measured over. Overlapping bands mean
        the configs are not distinguishable on that axis.
      </div>
      {#if widestBand !== null}
        <div class="text-xs text-gray-400 mt-1">
          Widest interval on this chart: {Math.round(widestBand)} points of its axis.{#if unbandedAxes.length > 0}
            &nbsp;No interval for {unbandedAxes.join(", ")} — only pass/fail scores
            can be given one exactly.{/if}
        </div>
      {/if}
    </div>
    <div class="flex flex-row gap-1 items-center flex-shrink-0">
      <InfoTooltip tooltip_text={SCALE_TOOLTIP} position="bottom" />
    </div>
  </div>
  {#if hasData}
    <div use:initChart class="w-full flex-1 min-h-[420px]"></div>
  {:else}
    <ChartNoData
      title={axes.length < MIN_AXES
        ? "Not enough scores to compare"
        : "Pin configs to compare"}
      message={axes.length < MIN_AXES
        ? `This view needs at least ${MIN_AXES} quality scores to place side by side.`
        : "Select a run config, or hover a card and hit Pin, to build a compare set."}
    />
  {/if}
</div>
