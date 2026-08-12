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
  //
  // Performance metrics are opt-in extra axes, and they are RANKS. A metric has
  // no full range to be a fraction of, so a cost or a latency arrives here
  // already normalized as a capped rank score over the configs currently drawn
  // (rank_score.ts): up is still better, the axis still runs 0..1, and a config
  // still sits at a comparable height. What the height means is different, and
  // is marked as such - the axis name carries "(rank)", the tooltip carries the
  // raw dollars or seconds and the position ("2nd of 5"), and the axis gets no
  // band. Two consequences the reader is told about rather than left to
  // discover: hiding a config in the legend RE-RANKS every metric axis, and a
  // rank axis says which config won without saying by how much.
  //
  // Metric axes do not count toward MIN_AXES. The card exists to compare
  // quality scores against each other; two rank axes and no quality score is
  // not that comparison, and would open the card on a chart of pure ordering.

  import * as echarts from "echarts"
  import type { TaskRunConfig, ProviderModels } from "$lib/types"
  import {
    FALLBACK_SERIES_COLOR,
    series_label,
  } from "$lib/utils/evolution/series_identity"
  import {
    build_parallel_rows,
    reconcile_order,
    reorder,
    widest_band_pp,
    type ParallelAxisSpec,
    type ParallelRow,
  } from "$lib/utils/evolution/parallel_bands"
  import { describe_rank } from "$lib/utils/evolution/rank_score"
  import ChartNoData from "$lib/components/chart_no_data.svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"

  export let axes: ParallelAxisSpec[] = []
  export let getValue: (runConfigId: string, key: string) => number | null
  export let getSampleSize: (runConfigId: string, key: string) => number | null
  // Rank axes only. The page computes these, because a rank is relative to the
  // comparison and the page is what knows the comparison - see the note above.
  export let getRankScore: (
    runConfigId: string,
    key: string,
  ) => number | null = () => null
  // What the metric picker left off, stated under the header rather than
  // silently missing. Null when there is nothing to say.
  export let notShownNote: string | null = null
  export let run_configs: TaskRunConfig[] = []
  // Only for the model-name fallback when a config has no name of its own; the
  // tooltip here is per-axis rather than per-config, so it has no room for the
  // model/prompt block the sibling charts carry.
  export let model_info: ProviderModels | null = null
  // Only what the page's legend has left switched on. This chart has no legend
  // of its own any more: a hidden config never arrives here, so there is
  // nothing to suppress and nothing to remember.
  export let selectedRunConfigIds: string[] = []
  // Colour per run config id, fixed by the page (series_color_map) rather than
  // by this chart's series order - a config the radar cannot plot used to
  // shift every colour after it here. Empty falls back to the theme palette by
  // index, which is what this chart did before.
  export let seriesColors: Record<string, string> = {}
  // What to CALL each run config, by id, decided once by the page for the
  // whole comparison - see series_display_map, which leads with the model and
  // appends the config's name only where a model is shared. It is what the
  // axis tooltip prints beside each point. Empty falls back to series_label.
  export let seriesLabels: Record<string, string> = {}

  // Below this there is no comparison to draw - a single config's bands are
  // still true, but the chart's whole job is telling configs apart. Counted
  // over QUALITY axes only: see the header note.
  const MIN_AXES = 2

  // Room under the plot for the draggable axis-name row. It used to carry the
  // legend underneath that as well; the legend is the page's now.
  const AXIS_HANDLE_ROW_PX = 76

  let chartInstance: echarts.ECharts | null = null

  function seriesName(config: TaskRunConfig): string {
    const assigned = config.id ? seriesLabels[config.id] : undefined
    return assigned ?? series_label(config, model_info)
  }

  // ---- Axis order ---------------------------------------------------------
  // Which axes sit next to each other is the reader's call, not the data's:
  // adjacency is what makes a crossing visible, and the order the evals happen
  // to be stored in is rarely the order that shows what the reader is looking
  // at. So the axes are draggable, and this is where the arrangement lives.
  // It survives the axis set changing (see reconcile_order) - pinning another
  // config must not throw away a layout built to make a point.
  let axisOrder: string[] = []
  $: axisOrder = reconcile_order(
    axisOrder,
    axes.map((axis) => axis.key),
  )
  $: orderedAxes = axisOrder
    .map((key) => axes.find((axis) => axis.key === key))
    .filter((axis): axis is ParallelAxisSpec => !!axis)

  $: plottedConfigs = selectedRunConfigIds
    .map((id) => run_configs.find((config) => config.id === id))
    .filter((config): config is TaskRunConfig => !!config?.id)

  $: rows = build_parallel_rows(
    orderedAxes,
    plottedConfigs.map((config) => config.id as string),
    getValue,
    getSampleSize,
    getRankScore,
  )
  $: drawnRows = rows.filter((row) => row.hasData)
  // Only the quality axes gate the card. A reader who adds two metrics to a
  // task with one quality score has not built a comparison this chart can make.
  $: qualityAxisCount = orderedAxes.filter((axis) => !axis.rank).length
  $: rankAxisCount = orderedAxes.length - qualityAxisCount
  $: hasData = qualityAxisCount >= MIN_AXES && drawnRows.length > 0
  $: widestBand = widest_band_pp(rows)

  // Any axis whose score type has no honest interval (see score_intervals):
  // named rather than left as a silently bandless line. Rank axes are exempt -
  // they are bandless for a different reason, which the header states once for
  // all of them rather than listing them here beside a sentence about score
  // types.
  $: unbandedAxes = orderedAxes
    .filter(
      (axis, axisIndex) =>
        !axis.rank &&
        rows.some(
          (row) =>
            row.cells[axisIndex]?.fraction !== null &&
            !row.cells[axisIndex]?.banded,
        ),
    )
    .map((axis) => axis.label)

  // The line under the header, as whole sentences joined rather than markup
  // strung together with separators. Any of the five can be absent - a task
  // with no pass/fail score has no widest interval, a chart with no metric
  // axes has nothing to say about ranks - and assembling it here is what keeps
  // a missing first clause from leaving the line starting on a space.
  $: footnote = [
    widestBand !== null
      ? `Widest interval on this chart: ${Math.round(widestBand)} points of its axis.`
      : null,
    unbandedAxes.length > 0
      ? `No interval for ${unbandedAxes.join(", ")} — only pass/fail scores can be given one exactly.`
      : null,
    rankAxisCount > 0
      ? `${rankAxisCount} ${
          rankAxisCount === 1 ? "metric is" : "metrics are"
        } plotted as a rank among the ${drawnRows.length} ${
          drawnRows.length === 1 ? "config" : "configs"
        } shown, not as an absolute value — hiding a config re-ranks them.`
      : null,
    notShownNote,
    hasData
      ? "Drag an axis name to reorder — which axes are adjacent decides which crossings you can see."
      : null,
  ]
    .filter((part): part is string => !!part)
    .join(" ")

  $: SCALE_TOOLTIP = `Each line is one run config's scores; the band around it is the **95% confidence interval** for that score, given how many runs it was measured over.

**Where two bands overlap, those configs are not distinguishable on that axis** - the difference you can see is inside what re-running would move on its own.

Every quality axis is drawn as a share of its own full scale (0-1 for pass/fail, 1-5 for five star), so a config sits at the same height here as on the radar above. Hover a point for the score in its own units, its interval and its sample size.

Intervals need a proportion to be exact, so only pass/fail scores carry a band. Other score types plot their point alone rather than a band that would be wrong.

**Performance metrics you add from the Metrics menu are RANK axes**, marked \`(rank)\`. Cost and latency have no full scale to be a share of, so each is plotted as its position among the configs currently shown - highest is best, as on every other axis. That means the axis says which config won and not by how much, and that **adding, removing or hiding a config re-ranks it**. Rank axes carry no band: an interval is a statement about a proportion, not about an ordering. Hover a point for the raw value and the position.`

  function tooltipMarker(color: string): string {
    return `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${color};margin-right:6px;"></span>`
  }

  // The page is the authority on what colour a run config is - see
  // series_color_map. The palette read is the fallback for a caller that does
  // not supply one, and is what this chart used to do for everybody.
  function seriesColor(runConfigId: string, index: number): string {
    const assigned = seriesColors[runConfigId]
    if (assigned) return assigned
    const palette = chartInstance?.getOption()?.color as string[] | undefined
    if (!palette?.length) return FALLBACK_SERIES_COLOR
    return palette[index % palette.length]
  }

  function formatScore(value: number | null): string {
    if (value === null) return "—"
    return Number.isInteger(value) ? `${value}` : value.toFixed(2)
  }

  /**
   * How many configs a rank axis was actually ranked over. Counted off the
   * drawn cells rather than taken from the page, so the "of M" in the tooltip
   * can never disagree with the points the reader is looking at.
   */
  function rankedCount(axisIndex: number): number {
    return drawnRows.filter((row) => row.cells[axisIndex]?.fraction !== null)
      .length
  }

  function axisTooltip(axisIndex: number): string {
    const axis = orderedAxes[axisIndex]
    if (!axis) return ""
    const ranked = axis.rank ? rankedCount(axisIndex) : 0
    let html = `<div style="font-weight:bold;margin-bottom:2px;">${axis.label}${
      axis.rank
        ? ` <span style="color:#9ca3af;font-weight:500;">(rank)</span>`
        : ""
    }</div>`
    html += `<div style="color:#888;margin-bottom:6px;">${axis.evalName}</div>`
    drawnRows.forEach((row, rowIndex) => {
      const cell = row.cells[axisIndex]
      if (!cell || cell.fraction === null) return
      const config = plottedConfigs.find((c) => c.id === row.runConfigId)
      const name = config ? seriesName(config) : "Unknown"
      const color = seriesColor(row.runConfigId, rowIndex)
      if (axis.rank) {
        // The RAW quantity is the bold number, not the rank score. The height
        // already carries the ordering; what the chart cannot say is how many
        // dollars or seconds it took, and that is the whole reason to hover.
        const raw = axis.format
          ? axis.format(cell.value)
          : formatScore(cell.value)
        const place = describe_rank(cell.fraction, ranked)
        html += `<div style="margin-top:3px;">${tooltipMarker(color)}${name}: <b>${raw}</b>`
        if (place) {
          html += ` <span style="color:#888;">ranked ${place} shown</span>`
        }
        html += `</div>`
        return
      }
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

  /**
   * The popup on an axis NAME, which is where a rank axis has to explain
   * itself: the one thing a reader cannot infer from the picture is that the
   * height moved because the comparison changed, not because the config did.
   */
  function axisHandleTitle(axis: ParallelAxisSpec, axisIndex: number): string {
    if (!axis.rank) {
      return `${axis.label} — ${axis.evalName}. Drag, or use the arrow keys, to reorder.`
    }
    const ranked = rankedCount(axisIndex)
    return `${axis.label} — ${axis.evalName}. Ranked among the ${ranked} ${
      ranked === 1 ? "config" : "configs"
    } currently shown — adding, removing or hiding configs re-ranks this axis. Raw values in the tooltip. Drag, or use the arrow keys, to reorder.`
  }

  function buildSeries(): echarts.SeriesOption[] {
    const series: echarts.SeriesOption[] = []
    drawnRows.forEach((row: ParallelRow, index: number) => {
      const config = plottedConfigs.find((c) => c.id === row.runConfigId)
      const name = config ? seriesName(config) : "Unknown"
      const color = seriesColor(row.runConfigId, index)

      // All three series still share the config's name. Nothing toggles by
      // name any more - the page decides what arrives here - but the name is
      // what the tooltip prints, and one config reading as one thing is the
      // point either way. Draw order is set by `z`, not by array order, so the
      // bands render behind the lines whatever order they are pushed in.
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
        // The page carries the legend for all three charts (see
        // evolution_legend.svelte), so this one draws none.
        legend: { show: false },
        // The first and last axes sit ON the edges of the plot (boundaryGap
        // false is what makes these parallel axes rather than bar categories),
        // so anything centred on them hangs half outside. containLabel does not
        // rescue that - it measures the axis as a whole, not a label straddling
        // the end - so the gutters are wide enough for half a handle on either
        // side, and the bottom leaves room for the handle row.
        grid: {
          left: 96,
          right: 96,
          top: 24,
          bottom: AXIS_HANDLE_ROW_PX,
          containLabel: true,
        },
        xAxis: {
          type: "category",
          boundaryGap: false,
          data: orderedAxes.map((axis) => axis.key),
          // The axis names are DOM (see the handle row in the markup): they are
          // draggable, and a canvas label cannot be picked up, focused or
          // reached by a keyboard.
          axisLabel: { show: false },
          axisTick: { show: false },
          axisLine: { lineStyle: { color: "#e5e7eb" } },
          splitLine: { show: true, lineStyle: { color: "#f3f4f6" } },
        },
        yAxis: {
          type: "value",
          min: 0,
          max: 1,
          // Two things share this axis once a metric is added, and the name has
          // to admit it rather than assert the quality convention over both.
          name:
            rankAxisCount > 0
              ? "share of full scale · rank position on (rank) axes"
              : "share of each score's full scale",
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

  // ---- Axis handles -------------------------------------------------------
  // The handle row is DOM sitting over the canvas, so it needs the pixel each
  // axis was drawn at. echarts is the authority on that - the grid's padding,
  // containLabel and the y-axis name all move it - so ask, rather than
  // recomputing the layout here and drifting from it.
  let handleX: number[] = []
  let handleTop = 0
  let plotBox: HTMLElement | null = null

  function measureHandles() {
    if (!chartInstance || !hasData) return
    handleX = orderedAxes.map((_axis, index) => {
      const x = chartInstance?.convertToPixel({ xAxisIndex: 0 }, index)
      return typeof x === "number" ? x : 0
    })
    // Value 0 is the bottom of the plot: where the axis line is, and so where
    // the handles hang from.
    const bottom = chartInstance.convertToPixel(
      { xAxisIndex: 0, yAxisIndex: 0 },
      [0, 0],
    )
    handleTop = Array.isArray(bottom) ? bottom[1] + 10 : 0
  }

  let dragIndex: number | null = null
  let dragOffset = 0
  let dropIndex: number | null = null

  function nearestIndex(clientX: number, container: HTMLElement): number {
    const left = container.getBoundingClientRect().left
    const x = clientX - left
    let best = 0
    let bestDistance = Infinity
    handleX.forEach((position, index) => {
      const distance = Math.abs(position - x)
      if (distance < bestDistance) {
        bestDistance = distance
        best = index
      }
    })
    return best
  }

  function startDrag(event: PointerEvent, index: number) {
    const target = event.currentTarget as HTMLElement
    target.setPointerCapture(event.pointerId)
    dragIndex = index
    dropIndex = index
    dragOffset = 0
  }

  function moveDrag(event: PointerEvent, container: HTMLElement) {
    if (dragIndex === null) return
    dragOffset =
      event.clientX -
      container.getBoundingClientRect().left -
      handleX[dragIndex]
    dropIndex = nearestIndex(event.clientX, container)
  }

  function endDrag() {
    if (dragIndex !== null && dropIndex !== null && dropIndex !== dragIndex) {
      axisOrder = reorder(axisOrder, dragIndex, dropIndex)
    }
    dragIndex = null
    dropIndex = null
    dragOffset = 0
  }

  // Keyboard equivalent: a drag no one can perform without a pointer is not a
  // feature everyone has.
  function moveByKey(event: KeyboardEvent, index: number) {
    const step =
      event.key === "ArrowLeft" ? -1 : event.key === "ArrowRight" ? 1 : 0
    if (step === 0) return
    event.preventDefault()
    const to = index + step
    if (to < 0 || to >= axisOrder.length) return
    axisOrder = reorder(axisOrder, index, to)
    // Keep focus on the axis the reader is moving, not on whatever slid into
    // the slot they left.
    requestAnimationFrame(() => {
      const next = document.querySelector<HTMLElement>(
        `[data-axis-handle="${to}"]`,
      )
      next?.focus()
    })
  }

  // Redraw whenever the inputs the option is built from change. Series colours
  // come off the live instance when the page supplies none, so this has to run
  // after init as well.
  $: redraw(
    orderedAxes,
    drawnRows,
    plottedConfigs,
    hasData,
    seriesColors,
    seriesLabels,
  )
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  function redraw(..._dependencies: unknown[]) {
    updateChart()
    measureHandles()
  }

  function initChart(node: HTMLElement) {
    chartInstance = echarts.init(node)
    const resizeObserver = new ResizeObserver(() => {
      chartInstance?.resize()
      // The handles are positioned in px off the chart's own layout, so a
      // resize moves them too.
      measureHandles()
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

<div class="bg-white border border-gray-200 rounded-lg p-6 flex flex-col">
  <div class="flex flex-row gap-4 items-start">
    <div class="flex-grow">
      <div class="text-xl font-bold">Quality Scores with Confidence</div>
      <div class="text-sm text-gray-500">
        The radar's scores, with the range each one could plausibly take given
        how many runs it was measured over — plus any performance metrics you
        add, as ranked axes. Overlapping bands mean the configs are not
        distinguishable on that axis.
      </div>
      {#if footnote}
        <div class="text-xs text-gray-400 mt-1">{footnote}</div>
      {/if}
    </div>
    <div class="flex flex-row gap-1 items-center flex-shrink-0">
      <!-- The page owns which metrics are on, so it supplies the control -
           the same element the performance track's chart carries. -->
      <slot name="controls" />
      <InfoTooltip tooltip_text={SCALE_TOOLTIP} position="bottom" />
    </div>
  </div>
  {#if hasData}
    <!-- The chart and its axis handles share one positioned box: the handles
         are DOM laid over the canvas at the pixels echarts drew the axes at.
         They have to be DOM - a canvas label cannot be dragged, focused, or
         reached from a keyboard. -->
    <div
      class="relative w-full flex-1 min-h-[460px]"
      bind:this={plotBox}
      on:pointermove={(event) => plotBox && moveDrag(event, plotBox)}
      on:pointerup={endDrag}
      on:pointercancel={endDrag}
    >
      <!-- Absolute rather than h-full: the box above is a flex item whose
           height comes from flex-1, which h-full cannot resolve against - the
           canvas collapses to nothing and takes the chart with it. -->
      <div use:initChart class="absolute inset-0"></div>
      {#if dragIndex !== null && dropIndex !== null && handleX[dropIndex] !== undefined}
        <div
          class="absolute w-0.5 bg-gray-400 pointer-events-none"
          style="left: {handleX[dropIndex]}px; top: 24px; height: {handleTop -
            34}px"
        ></div>
      {/if}
      {#each orderedAxes as axis, index (axis.key)}
        <button
          type="button"
          data-axis-handle={index}
          class="absolute -translate-x-1/2 max-w-[150px] text-center text-xs leading-tight rounded px-2 py-1
                 cursor-grab active:cursor-grabbing select-none
                 hover:bg-gray-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500
                 {dragIndex === index
            ? 'bg-gray-100 shadow-sm z-10 cursor-grabbing'
            : ''}"
          style="left: {handleX[index] ?? 0}px; top: {handleTop}px;
                 {dragIndex === index
            ? `transform: translate(calc(-50% + ${dragOffset}px), 0);`
            : ''}"
          title={axisHandleTitle(axis, index)}
          on:pointerdown={(event) => startDrag(event, index)}
          on:keydown={(event) => moveByKey(event, index)}
        >
          <span class="font-medium text-gray-700">{axis.label}</span>
          {#if axis.rank}
            <!-- Marked on the axis itself, not only in the tooltip: a height on
                 this axis is a POSITION, and a reader who takes it for a score
                 has misread the chart in a way nothing else on it corrects. -->
            <span class="text-gray-400">&nbsp;(rank)</span>
          {/if}
        </button>
      {/each}
    </div>
  {:else}
    <ChartNoData
      title={qualityAxisCount < MIN_AXES
        ? "Not enough scores to compare"
        : "Pin configs to compare"}
      message={qualityAxisCount < MIN_AXES
        ? `This view needs at least ${MIN_AXES} quality scores to place side by side. Performance metrics plot as rank axes beside them and do not count toward that.`
        : "Select a run config, or hover a card and hit Pin, to build a compare set."}
    />
  {/if}
</div>
